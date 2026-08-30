"""W4 Step 4: teacher-forced activation replay of the frozen W3 dataset.

Every stored trace of the frozen dataset (700: form A 150+150 incentive + 50 W1 neutral;
form B 150+150 incentive + 50 baseline) is reconstructed as `templated_prompt + raw_output`,
pushed through Qwen2.5-14B-Instruct in ONE forward pass (bf16, the generation dtype), and the
residual stream is read at every decoder layer at a small set of positions.

Nothing here re-generates text. The dataset is frozen (PR-003 item 8); this file only reads it.

POSITION KINDS (per trace)
  end_of_prompt   last token of the templated prompt
  est             last token of a parsed intermediate-estimate literal, tau-echo EXCLUDED
                  and inside the frozen [tau/100, 100*tau] window
  est_offwin      same, but outside that window (intermediate factors: "25 million
                  crocodiles", "800 scales"). Captured because they are the natural
                  within-trace control for `est`; the frozen-rule subset is exactly
                  `kind == "est"`.
  tau_echo        last token of a parsed literal that equals tau exactly (R-008(2) excludes
                  these from estimate points; they are captured as controls)
  final           last token of the final-estimate literal span, frozen PR-001 item 8
                  (LAST numeric literal in the visible answer)
  final_corrected last token of the D-016-corrected final span (PR-003 item 7: last literal
                  that is not exactly tau). Identical to `final` when the trace does not end
                  on a tau echo; on form A that is only ~43% of traces, which is why both
                  are captured.
  belief          last token of the FIRST occurrence of "good cause" or "bad cause"
                  (case-insensitive) in the generated text. Absent -> recorded as absent.

The intermediate parse is asserted, per trace, to reproduce `extract_regex.intermediates()`
value-for-value: the span-keeping parser here is a re-implementation of the frozen rule and
the assertion is what makes it the same rule.

TOKEN-SEQUENCE VERIFICATION (per trace, all four must hold or the trace is quarantined):
  V1 len(tok(templated_prompt)) == the stored n_prompt_tokens vLLM reported at generation
  V2 tok(templated_prompt + raw_output)[:n_prompt] == tok(templated_prompt)   (no BPE merge
     across the prompt/generation boundary, so the replayed prefix IS the generated prefix)
  V3 tok(templated_prompt + raw_output)[n_prompt:] == tok(raw_output)         (same, other side)
  V4 the number of replayed generated tokens equals the stored n_output_tokens, allowing
     exactly one unreplayed trailing token when finish_reason == "stop" (the <|im_end|> that
     vLLM counts but does not put in the text)

  python3 src/replay_w4.py --dry-run     # tokenization + positions + V1-V4, no model, laptop
  python3 src/replay_w4.py               # the real thing, on the pod
  python3 src/replay_w4.py --decode-check # paste the acceptance-check table from stored files
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import extract_regex as ex  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
TAU = {"A": 15300000, "B": 4500000000}
OUT_ACTS = ROOT / "runs" / "w4_acts"
OUT_POS = ROOT / "analysis" / "out" / "w4_positions"
OUT_SUM = ROOT / "analysis" / "out" / "w4_replay_summary.csv"
OUT_DEC = ROOT / "analysis" / "out" / "w4_decode_check.md"
BELIEF_STRINGS = ("good cause", "bad cause")
DECODE_STRIDE = 35                      # acceptance check: every 35th `est` point, global index

# (form, arm, path, is_incentive). Order is FIXED here: it defines the global point index
# the acceptance check samples, so it must not be reordered.
ARMS = [
    ("A", "below_good", "runs/w3_frozen/form_A/below_good.json", True),
    ("A", "above_good", "runs/w3_frozen/form_A/above_good.json", True),
    ("A", "neutral",    "runs/w1_neutral/Qwen2.5-14B-Instruct/neutral.json", False),
    ("B", "below_good", "runs/w3_frozen/form_B/below_good.json", True),
    ("B", "above_good", "runs/w3_frozen/form_B/above_good.json", True),
    ("B", "baseline",   "runs/w3_frozen/form_B/baseline.json", False),
]


# ---------------------------------------------------------------- the frozen parse, with spans

def parsed_spans(text):
    """extract_regex.intermediates() with char spans kept. Asserted equal to it below."""
    nums = ex.all_numbers(text, skip_ranges=True)
    kept = [(v, s, t) for v, s, t in nums
            if v >= ex.INTERMEDIATE_FLOOR and not ex._is_year_shaped(v, t)]
    out = []
    for v, s, t in kept:                       # collapse_repeats: keep the first of a run
        if not out or v != out[-1][0]:
            out.append((v, s, s + len(t), t))
    assert [v for v, _, _, _ in out] == ex.intermediates(text), "span parser diverged from frozen rule"
    return out


def final_span(text):
    """PR-001 item 8: the LAST numeric literal in the visible answer, with its span."""
    nums = ex.all_numbers(text or "", skip_ranges=False)
    if not nums:
        return None
    v, s, t = nums[-1]
    return (v, s, s + len(t), t)


def final_corrected_span(text, tau):
    """PR-003 item 7 / D-016: the last literal that is not exactly tau."""
    nums = [(v, s, t) for v, s, t in ex.all_numbers(text or "", skip_ranges=False) if v != tau]
    if not nums:
        return None
    v, s, t = nums[-1]
    return (v, s, s + len(t), t)


def belief_span(text):
    hits = [(text.lower().find(s), s) for s in BELIEF_STRINGS]
    hits = [(i, s) for i, s in hits if i >= 0]
    if not hits:
        return None
    i, s = min(hits)
    return (i, i + len(s), text[i:i + len(s)])


# ---------------------------------------------------------------- token mapping

def span_tokens(offsets, lo, hi):
    """Indices of every token whose char range intersects [lo, hi). (first, last)."""
    idx = [i for i, (a, b) in enumerate(offsets) if a < hi and b > lo and b > a]
    if not idx:
        return None
    return idx[0], idx[-1]


def build_positions(rec, arm_meta, tok, tau):
    """All positions for one trace, plus the V1-V4 verification record."""
    prompt = arm_meta["templated_prompt"]
    gen = rec["raw_output"]
    full = prompt + gen

    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    g_ids = tok(gen, add_special_tokens=False)["input_ids"]
    enc = tok(full, add_special_tokens=False, return_offsets_mapping=True)
    f_ids, offs = enc["input_ids"], [tuple(o) for o in enc["offset_mapping"]]
    n_p = len(p_ids)

    slack = 1 if rec["finish_reason"] == "stop" else 0
    ver = {
        "v1_prompt_tokens_match": n_p == arm_meta["n_prompt_tokens"],
        "v2_prefix_stable": f_ids[:n_p] == p_ids,
        "v3_suffix_stable": f_ids[n_p:] == g_ids,
        "v4_output_tokens_match": (len(f_ids) - n_p) + slack == rec["n_output_tokens"],
        "n_prompt_tokens_replayed": n_p,
        "n_prompt_tokens_stored": arm_meta["n_prompt_tokens"],
        "n_output_tokens_replayed": len(f_ids) - n_p,
        "n_output_tokens_stored": rec["n_output_tokens"],
        "eos_slack": slack,
        "n_tokens_total": len(f_ids),
    }
    ver["ok"] = all(ver[k] for k in
                    ("v1_prompt_tokens_match", "v2_prefix_stable", "v3_suffix_stable",
                     "v4_output_tokens_match"))

    pts = []

    def add(kind, lo_char, hi_char, value, literal, extra=None):
        sp = span_tokens(offs, lo_char, hi_char)
        if sp is None:
            return
        first, last = sp
        p = {"kind": kind, "token_index": last, "span_token_first": first,
             "span_token_last": last,
             "span_token_ids": f_ids[first:last + 1],
             "char_start": lo_char, "char_end": hi_char,
             "literal": literal, "value": value}
        if extra:
            p.update(extra)
        pts.append(p)

    add("end_of_prompt", offs[n_p - 1][0], offs[n_p - 1][1], None,
        full[offs[n_p - 1][0]:offs[n_p - 1][1]])

    lo_w, hi_w = tau / 100.0, tau * 100.0
    for k, (v, s, e, t) in enumerate(parsed_spans(gen)):
        if v == tau:
            kind = "tau_echo"
        elif lo_w <= v <= hi_w:
            kind = "est"
        else:
            kind = "est_offwin"
        add(kind, len(prompt) + s, len(prompt) + e, v, t, {"parse_ordinal": k})

    fs = final_span(gen)
    if fs:
        add("final", len(prompt) + fs[1], len(prompt) + fs[2], fs[0], fs[3])
    fc = final_corrected_span(gen, tau)
    if fc:
        add("final_corrected", len(prompt) + fc[1], len(prompt) + fc[2], fc[0], fc[3],
            {"same_span_as_final": bool(fs and fc[1] == fs[1])})
    bs = belief_span(gen)
    if bs:
        add("belief", len(prompt) + bs[0], len(prompt) + bs[1], None, bs[2])
    ver["belief_present"] = bool(bs)
    return f_ids, pts, ver


def decoder_layers(model):
    """The decoder-layer ModuleList, whatever transformers is calling it this version.
    Hooking the layer OUTPUT is the same stream smoke-B hooked (F-013)."""
    for path in ("model.layers", "model.model.layers", "model.language_model.layers"):
        obj = model
        try:
            for part in path.split("."):
                obj = getattr(obj, part)
            if hasattr(obj, "__len__") and len(obj) > 1:
                return obj
        except AttributeError:
            continue
    raise RuntimeError("cannot locate decoder layers on %s" % type(model).__name__)


# ---------------------------------------------------------------- driver

def iter_arms(limit=None):
    for form, arm, path, inc in ARMS:
        d = json.loads((ROOT / path).read_text())
        rows = d["rows"] if limit is None else d["rows"][:limit]
        yield form, arm, d, rows, inc


def run(dry, limit, layers_only=None):
    torch = model = None
    if not dry:
        import torch as _torch
        torch = _torch
        from transformers import AutoModelForCausalLM
        t0 = time.time()
        model = AutoModelForCausalLM.from_pretrained(
            MODEL, dtype=torch.bfloat16, device_map="cuda", trust_remote_code=True)
        model.eval()
        print("model loaded in %.1fs | dtype %s | layers %d | d_model %d"
              % (time.time() - t0, next(model.parameters()).dtype,
                 len(decoder_layers(model)), model.config.hidden_size), flush=True)

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)

    OUT_POS.mkdir(parents=True, exist_ok=True)
    OUT_ACTS.mkdir(parents=True, exist_ok=True)
    summary = []

    for form, arm, meta, rows, inc in iter_arms(limit):
        tau = TAU[form]
        t0 = time.time()
        index, bad, acts = [], [], []
        wanted = None
        if not dry:
            n_layers = len(decoder_layers(model))
            d_model = model.config.hidden_size
            grab = {}

            def mk(i):
                def hook(_m, _a, out):
                    hs = out[0] if isinstance(out, tuple) else out
                    grab[i] = hs[0, wanted, :].detach().to(torch.float16).cpu()
                return hook
            handles = [decoder_layers(model)[i].register_forward_hook(mk(i))
                       for i in range(n_layers)]
        else:
            n_layers, d_model = 48, 5120

        for rec in rows:
            ids, pts, ver = build_positions(rec, meta, tok, tau)
            if not ver["ok"]:
                bad.append({"i": rec["i"], **{k: ver[k] for k in ver if k != "ok"}})
                continue
            # `row` is this point's row in the arm's activation tensor.
            for p in pts:
                index.append({"form": form, "arm": arm, "trace_i": rec["i"],
                              "seed": rec["seed"], "row": len(index), **p})
            if not dry:
                wanted = [p["token_index"] for p in pts]
                with torch.no_grad():
                    model(input_ids=torch.tensor([ids], device=model.device))
                stack = torch.stack([grab[i] for i in range(n_layers)], dim=1)  # [npos,L,d]
                acts.append(stack)
                grab.clear()

        if not dry:
            for h in handles:
                h.remove()
            import numpy as np
            from safetensors.numpy import save_file
            arr = torch.cat(acts, dim=0).numpy() if acts else np.zeros((0, n_layers, d_model),
                                                                      dtype="float16")
            path = OUT_ACTS / ("w4_acts_%s_%s.safetensors" % (form, arm))
            save_file({"acts": arr}, str(path), metadata={
                "model": MODEL, "form": form, "arm": arm, "dtype": "float16",
                "shape": json.dumps(list(arr.shape)), "n_layers": str(n_layers),
                "d_model": str(d_model), "stream": "decoder layer output (post-block residual)"})
            assert arr.shape[0] == len(index), "act rows %d != index rows %d" % (
                arr.shape[0], len(index))
            size = path.stat().st_size
        else:
            size = 0

        kinds = {}
        for p in index:
            kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
        n_ok = len({p["trace_i"] for p in index})
        n_belief = kinds.get("belief", 0)
        (OUT_POS / ("w4_positions_%s_%s.json" % (form, arm))).write_text(json.dumps({
            "model": MODEL, "form": form, "arm": arm, "tau": tau, "is_incentive": inc,
            "source": [p for f, a, p, _ in ARMS if f == form and a == arm][0],
            "n_traces_in_arm": len(rows), "n_traces_replayed": n_ok,
            "n_layers": n_layers, "d_model": d_model, "dtype": "float16",
            "stream": "decoder layer output (post-block residual stream)",
            "acts_file": "runs/w4_acts/w4_acts_%s_%s.safetensors" % (form, arm),
            "acts_row_is": "index[k]['row'] is row k of acts[:, :, :]",
            "n_points": len(index), "points_by_kind": kinds,
            "quarantined": bad, "points": index}, indent=1))
        summary.append({"form": form, "arm": arm, "n_traces": len(rows),
                        "n_replayed": n_ok, "n_quarantined": len(bad),
                        "n_points": len(index),
                        **{"n_" + k: kinds.get(k, 0) for k in
                           ("end_of_prompt", "est", "est_offwin", "tau_echo", "final",
                            "final_corrected", "belief")},
                        "belief_absent": n_ok - n_belief,
                        "belief_absent_rate": round(1 - n_belief / n_ok, 4) if n_ok else "",
                        "bytes": size, "wall_secs": round(time.time() - t0, 1)})
        print(json.dumps(summary[-1]), flush=True)

    import csv
    with open(OUT_SUM, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        w.writeheader(); w.writerows(summary)
    print("\nwrote", OUT_SUM)
    tot = sum(s["n_points"] for s in summary)
    print("TOTAL points %d | traces replayed %d | quarantined %d | bytes %.2f GB"
          % (tot, sum(s["n_replayed"] for s in summary),
             sum(s["n_quarantined"] for s in summary),
             sum(s["bytes"] for s in summary) / 1e9))
    return 0


# ---------------------------------------------------------------- acceptance check

def decode_check(paste_all=True):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    glob = []
    for form, arm, _, _ in [(f, a, p, i) for f, a, p, i in ARMS]:
        f = OUT_POS / ("w4_positions_%s_%s.json" % (form, arm))
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        for p in d["points"]:
            if p["kind"] == "est":
                glob.append((form, arm, p))
    picked = glob[::DECODE_STRIDE]
    lines = ["# W4 acceptance check — token spans decode to the parsed literals", "",
             "Fixed rule, stated in `src/replay_w4.py` before the replay ran: **every %dth "
             "`est` point in the global point index**, the index being arm order "
             "`A/below_good, A/above_good, A/neutral, B/below_good, B/above_good, B/baseline` "
             "and, inside an arm, trace order then parse order." % DECODE_STRIDE, "",
             "The rule selects **%d** points out of **%d** `est` points. The order asks for 20; "
             "all %d the rule yields are pasted, and the first 20 — the ones the rule names — "
             "are marked ✱." % (len(picked), len(glob), len(picked)), "",
             "`decoded` is `tokenizer.decode(span_token_ids)` from the STORED index; it passes "
             "only if it reproduces the parsed literal's digits exactly as rendered, commas "
             "included.", "",
             "| # | form | arm | trace | token idx | stored span token ids | decoded | parsed literal | value | exact |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    n_ok = 0
    for k, (form, arm, p) in enumerate(picked):
        dec = tok.decode(p["span_token_ids"])
        ok = dec.strip() == p["literal"].strip()
        n_ok += ok
        lines.append("| %d%s | %s | `%s` | %d | %d | `%s` | `%s` | `%s` | %s | %s |"
                     % (k + 1, " ✱" if k < 20 else "", form, arm, p["trace_i"],
                        p["token_index"], p["span_token_ids"], dec, p["literal"],
                        ("%d" % p["value"]) if float(p["value"]).is_integer() else p["value"],
                        "**PASS**" if ok else "**FAIL**"))
    lines += ["", "**%d / %d exact.**" % (n_ok, len(picked)), ""]

    # position-kind inventory for 3 sampled traces (fixed rule: first trace of the first,
    # fourth and fifth arms in the global order = A/below_good, B/below_good, B/above_good).
    lines += ["## Position-kind inventory, 3 sampled traces", "",
              "Fixed rule: the lowest-index replayed trace of arms 1, 4 and 5 of the global "
              "arm order (`A/below_good`, `B/below_good`, `B/above_good`).", "",
              "| form | arm | trace | end_of_prompt | est | est_offwin | tau_echo | final | "
              "final_corrected | belief | total |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for form, arm in (("A", "below_good"), ("B", "below_good"), ("B", "above_good")):
        f = OUT_POS / ("w4_positions_%s_%s.json" % (form, arm))
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        if not d["points"]:
            continue
        ti = d["points"][0]["trace_i"]
        pts = [p for p in d["points"] if p["trace_i"] == ti]
        c = {}
        for p in pts:
            c[p["kind"]] = c.get(p["kind"], 0) + 1
        lines.append("| %s | `%s` | %d | %s | %d |" % (
            form, arm, ti,
            " | ".join(str(c.get(k, 0)) for k in
                       ("end_of_prompt", "est", "est_offwin", "tau_echo", "final",
                        "final_corrected", "belief")), len(pts)))
    OUT_DEC.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote", OUT_DEC)
    return 0 if n_ok == len(picked) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="tokenization, positions and V1-V4 only; no model, no activations")
    ap.add_argument("--limit", type=int, default=None, help="first N rows per arm")
    ap.add_argument("--decode-check", action="store_true")
    a = ap.parse_args()
    if a.decode_check:
        return decode_check()
    return run(a.dry_run, a.limit)


if __name__ == "__main__":
    sys.exit(main())
