"""W12 Step 2 item 2: full-position teacher-forced capture of the frozen W3 form-B
incentive traces.

No text is generated.  The 300 frozen form-B incentive traces (150 above_good,
150 below_good) are reconstructed as `templated_prompt + raw_output` exactly as W4 did --
this file IMPORTS `replay_w4.build_positions`, so the tokenization, the V1-V4 verification
and the `est`/`belief` position conventions are literally W4's, not a re-implementation --
and the residual stream (decoder-layer output) is recorded at EVERY GENERATED token
position for layers {21,23,25,27,29,31,33,35} in fp16.

Output (pod-side only; R-010(3): tensors do not ship):
  runs/w12_acts/w12_acts_<arm>_<shard>.safetensors   [n_rows, 8, 5120] fp16
  runs/w12_acts/w12_index_<arm>.json                 row -> (trace_i, gen_pos) + per-trace meta
  runs/w12_acts/w12_sub_<arm>.safetensors            every SUBSAMPLE_STRIDE-th row (audit)

  python3 src/capture_w12.py --dry-run [--limit N]   # laptop: no model, index + V1-V4 only
  python  src/capture_w12.py                         # the real thing, on the pod
  python  src/capture_w12.py --align-check           # the 10-point position-alignment table
"""
import argparse, json, sys, time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import replay_w4 as w4                                     # noqa: E402
import direction_w5 as w5                                  # noqa: E402

MODEL = w4.MODEL
FORM = "B"
TAU = w4.TAU[FORM]
LAYERS = (21, 23, 25, 27, 29, 31, 33, 35)                  # PR-008 item 2, frozen
ARMS = ("above_good", "below_good")                        # global order for the row index
SRC = {"above_good": "runs/w3_frozen/form_B/above_good.json",
       "below_good": "runs/w3_frozen/form_B/below_good.json"}
OUT = ROOT / "runs" / "w12_acts"
OUT_A = ROOT / "analysis" / "out"
SHARD_TRACES = 50
SUBSAMPLE_STRIDE = 20                                      # 5% audit subsample, frozen
ALIGN_N = 10                                               # position-alignment check points


def traces(arm, limit=None):
    d = json.loads((ROOT / SRC[arm]).read_text())
    rows = d["rows"] if limit is None else d["rows"][:limit]
    return d, rows


def trace_meta(rec, meta, tok, verd):
    """W4's own positions for one trace, reduced to what W12 needs."""
    ids, pts, ver = w4.build_positions(rec, meta, tok, TAU)
    n_p = ver["n_prompt_tokens_replayed"]
    n_gen = len(ids) - n_p
    bel = [p for p in pts if p["kind"] == "belief"]
    est = [p for p in pts if p["kind"] == "est"]
    v = verd.get((FORM, meta["arm"], rec["i"]))
    return ids, n_p, {
        "trace_i": rec["i"], "seed": rec["seed"], "arm": meta["arm"],
        "n_prompt_tokens": n_p, "n_gen": n_gen, "ok": ver["ok"], "ver": ver,
        "verdict": v, "phat": w5.phat_of(meta["arm"], v),
        "belief_gen_pos": (bel[0]["token_index"] - n_p) if bel else None,
        "belief_literal": bel[0]["literal"] if bel else None,
        "est": [{"gen_pos": p["token_index"] - n_p, "value": p["value"],
                 "literal": p["literal"], "abs_index": p["token_index"],
                 "span_token_ids": p["span_token_ids"]} for p in est],
    }


def run(dry, limit):
    torch = model = None
    if not dry:
        import torch as _torch
        torch = _torch
        from transformers import AutoModelForCausalLM
        t0 = time.time()
        model = AutoModelForCausalLM.from_pretrained(
            MODEL, dtype=torch.bfloat16, device_map="cuda", trust_remote_code=True)
        model.eval()
        L = w4.decoder_layers(model)
        print("model loaded in %.1fs | layers %d | d_model %d"
              % (time.time() - t0, len(L), model.config.hidden_size), flush=True)
        assert max(LAYERS) < len(L), "layer index out of range"

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    verd = w5.verdicts()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []

    for arm in ARMS:
        meta, rows = traces(arm, limit)
        meta = dict(meta); meta["arm"] = arm
        t0 = time.time()
        index, tmeta, bad = [], [], []
        buf, shard, n_bytes = [], 0, 0
        grab = {}
        if not dry:
            def mk(i):
                def hook(_m, _a, out):
                    hs = out[0] if isinstance(out, tuple) else out
                    grab[i] = hs[0, n_p_cur:, :].detach().to(torch.float16).cpu()
                return hook
            handles = [w4.decoder_layers(model)[i].register_forward_hook(mk(i))
                       for i in LAYERS]

        def flush():
            nonlocal buf, shard, n_bytes
            if not buf:
                return
            from safetensors.numpy import save_file
            arr = np.concatenate(buf, axis=0)
            p = OUT / ("w12_acts_%s_%02d.safetensors" % (arm, shard))
            save_file({"acts": arr}, str(p), metadata={
                "model": MODEL, "form": FORM, "arm": arm, "shard": str(shard),
                "layers": json.dumps(list(LAYERS)), "dtype": "float16",
                "shape": json.dumps(list(arr.shape)),
                "stream": "decoder layer output (post-block residual)"})
            n_bytes += p.stat().st_size
            buf, shard = [], shard + 1

        for k, rec in enumerate(rows):
            ids, n_p, tm = trace_meta(rec, meta, tok, verd)
            if not tm["ok"]:
                bad.append({"trace_i": rec["i"], **tm["ver"]})
                continue
            r0 = len(index)
            tm["row_first"], tm["row_last"] = r0, r0 + tm["n_gen"] - 1
            tm["shard"] = shard
            tmeta.append(tm)
            for g in range(tm["n_gen"]):
                index.append((rec["i"], g))
            if not dry:
                n_p_cur = n_p
                with torch.no_grad():
                    model(input_ids=torch.tensor([ids], device=model.device))
                st = torch.stack([grab[i] for i in LAYERS], dim=1).numpy()  # [n_gen,8,d]
                assert st.shape[0] == tm["n_gen"], (st.shape, tm["n_gen"])
                buf.append(st)
                grab.clear()
            if (k + 1) % SHARD_TRACES == 0:
                flush()
                print("  %s: %d traces, %d rows, %.1f s" % (arm, k + 1, len(index),
                                                            time.time() - t0), flush=True)
        flush()
        if not dry:
            for h in handles:
                h.remove()

        (OUT / ("w12_index_%s.json" % arm)).write_text(json.dumps({
            "model": MODEL, "form": FORM, "arm": arm, "tau": TAU,
            "layers": list(LAYERS), "dtype": "float16",
            "shard_traces": SHARD_TRACES, "subsample_stride": SUBSAMPLE_STRIDE,
            "source": SRC[arm], "n_traces": len(rows), "n_replayed": len(tmeta),
            "n_rows": len(index), "quarantined": bad,
            "row_is": "row r of the concatenated shards is (trace_i, gen_pos) = rows[r]",
            "rows": index, "traces": tmeta}, indent=1))

        # ---- 5% audit subsample: every SUBSAMPLE_STRIDE-th row of this arm's index ----
        if not dry:
            from safetensors.numpy import load_file, save_file
            want = list(range(0, len(index), SUBSAMPLE_STRIDE))
            parts, off = [], 0
            for sh in range(shard):
                a = load_file(str(OUT / ("w12_acts_%s_%02d.safetensors" % (arm, sh))))["acts"]
                sel = [w - off for w in want if off <= w < off + a.shape[0]]
                if sel:
                    parts.append(a[np.array(sel)])
                off += a.shape[0]
            sub = np.concatenate(parts, axis=0)
            sp = OUT / ("w12_sub_%s.safetensors" % arm)
            save_file({"acts": sub}, str(sp), metadata={
                "model": MODEL, "arm": arm, "layers": json.dumps(list(LAYERS)),
                "rule": "every %dth row of w12_index_%s.json['rows'] (5%%)"
                        % (SUBSAMPLE_STRIDE, arm),
                "shape": json.dumps(list(sub.shape))})
            (OUT / ("w12_sub_index_%s.json" % arm)).write_text(json.dumps(
                {"stride": SUBSAMPLE_STRIDE, "rows": [index[w] for w in want]}, indent=1))
            print("  subsample %s: %s -> %.2f GB" % (arm, sub.shape, sp.stat().st_size / 1e9))

        summary.append({"arm": arm, "n_traces": len(rows), "n_replayed": len(tmeta),
                        "n_quarantined": len(bad), "n_rows": len(index),
                        "n_shards": shard, "bytes": n_bytes,
                        "n_labelled": sum(1 for t in tmeta if t["phat"] is not None),
                        "n_phat_pos": sum(1 for t in tmeta if t["phat"] == 1),
                        "n_phat_neg": sum(1 for t in tmeta if t["phat"] == -1),
                        "n_with_belief": sum(1 for t in tmeta
                                             if t["belief_gen_pos"] is not None),
                        "wall_secs": round(time.time() - t0, 1)})
        print(json.dumps(summary[-1]), flush=True)

    import csv
    OUT_A.mkdir(parents=True, exist_ok=True)
    with open(OUT_A / "w12_capture_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        w.writeheader(); w.writerows(summary)
    print("\nTOTAL rows %d | %.2f GB" % (sum(s["n_rows"] for s in summary),
                                         sum(s["bytes"] for s in summary) / 1e9))
    return 0


# --------------------------------------------------------------- alignment check
def align_check():
    """PR-008 item 2: re-run the W4 decode rule on 10 sampled `est` points against THIS
    capture.  The points come from W4's stored index; the check is that (a) the same
    absolute token index exists in this capture as gen_pos = abs - n_prompt, (b) this
    capture's own tokenization decodes that span to the same parsed literal, and (c) the
    row that holds it is the row this capture's index says it is."""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    glob = []
    for arm in ARMS:
        d = json.loads((ROOT / "analysis" / "out" / "w4_positions" /
                        ("w4_positions_B_%s.json" % arm)).read_text())
        for p in d["points"]:
            if p["kind"] == "est":
                glob.append((arm, p))
    stride = max(1, len(glob) // ALIGN_N)
    picked = glob[::stride][:ALIGN_N]
    idx = {arm: json.loads((OUT / ("w12_index_%s.json" % arm)).read_text()) for arm in ARMS}
    lines = ["# W12 position-alignment check — W4's `est` points decode in the W12 capture",
             "",
             "Fixed rule: every %dth `est` point of the W4 form-B global index "
             "(`A`rm order `above_good, below_good`, then trace order, then parse order), "
             "first %d taken. `w12 gen_pos` is `w4 token_index - n_prompt_tokens`; "
             "`w12 row` is the row of the concatenated W12 shards that holds it."
             % (stride, ALIGN_N), "",
             "| # | arm | trace | w4 token idx | n_prompt | w12 gen_pos | w12 row | "
             "decoded span | w4 literal | same row in index | exact |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    n_ok = 0
    for k, (arm, p) in enumerate(picked):
        d = idx[arm]
        tm = [t for t in d["traces"] if t["trace_i"] == p["trace_i"]][0]
        gp = p["token_index"] - tm["n_prompt_tokens"]
        row = tm["row_first"] + gp
        dec = tok.decode(p["span_token_ids"])
        same = d["rows"][row] == [p["trace_i"], gp]
        ok = dec.strip() == p["literal"].strip() and same and 0 <= gp < tm["n_gen"]
        n_ok += ok
        lines.append("| %d | `%s` | %d | %d | %d | %d | %d | `%s` | `%s` | %s | %s |"
                     % (k + 1, arm, p["trace_i"], p["token_index"],
                        tm["n_prompt_tokens"], gp, row, dec, p["literal"],
                        "yes" if same else "**NO**", "**PASS**" if ok else "**FAIL**"))
    lines += ["", "**%d / %d exact.**" % (n_ok, len(picked)), ""]
    out = OUT_A / "w12_align_check.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote", out)
    return 0 if n_ok == len(picked) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--align-check", action="store_true")
    a = ap.parse_args()
    return align_check() if a.align_check else run(a.dry_run, a.limit)


if __name__ == "__main__":
    sys.exit(main())
