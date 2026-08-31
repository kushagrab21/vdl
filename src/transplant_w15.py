"""W15: the belief transplant (PR-011 items 2-3).

A forward hook on decoder layer L27's OUTPUT — the same post-block residual stream F-013
hooked, W4 read and W7 injected into — REPLACES the v_p̂^B component at every generated-token
position of A's teacher-forced prefix:

    h  <-  h + ( m_target(r) - (h . u) ) . u        r = g / (cut - 1)

with u the sha-pinned W5 unit direction and m_target the class-mean projection profile at
matched relative position. The templated prompt's positions are NEVER touched and neither is
any decode position: the edit lives entirely in the prefix, and the continuation is then
generated from the edited state.

Four arms per pair, same seed, same RNG stream:
    SWAP  m_target = class mean of B (the opposite belief)      along u
    SHAM  no modification at all (bitwise identity)             --
    SELF  m_target = class mean of A (A's own class)            along u
    RAND  m_target = class mean of B                            along a fixed random direction

  python3 src/transplant_w15.py --smoke                 # laptop, CPU, tiny model, no GPU
  python3 src/transplant_w15.py --profile               # pod: class-mean projection profiles
  python3 src/transplant_w15.py --transplant            # pod: the four arms
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import numpy as np  # noqa: E402

from gen_neutral import BASE_SEED, TEMPERATURE, TOP_P, split_output  # noqa: E402
from steer_w7 import ngram_ratio, is_degenerate  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
FAMILY_MODE = "no_think"
TAU_B = 4500000000
LAYER = 27
MAX_NEW_TOKENS = 2048                      # PR-011 item 2
GRID = 101                                 # PR-011 item 2: the relative-position grid
RAND_SEEDS = [15070 + j for j in range(4)]  # PR-011 item 2: 4 fixed random directions
SEED_BASE = 15100                          # torch.manual_seed(BASE_SEED + 15100 + pair_index)
VEC = ROOT / "analysis" / "out" / "w5_vectors" / "w5_vphat_B.safetensors"
VEC_SHA = "cbdbbb4a4eccfd085549d3aa1a6b94170c77252bd2dd64718b4f950426b9be64"
ARMS = ("SWAP", "SHAM", "SELF", "RAND")
OUT = ROOT / "analysis" / "out"
RUNS = ROOT / "runs" / "w15_transplant"


# ---------------------------------------------------------------- direction

def load_u(d_model=None):
    from safetensors.numpy import load_file
    got = hashlib.sha256(VEC.read_bytes()).hexdigest()
    if got != VEC_SHA:
        raise RuntimeError("v_phat^B tensor sha256 %s != PR-005/PR-011's %s" % (got, VEC_SHA))
    v = load_file(str(VEC))["vphat"].astype(np.float32)
    assert v.shape == (48, 5120), v.shape
    w = v[LAYER]
    u = w / float(np.linalg.norm(w))
    return (u if d_model is None else u[:d_model] / np.linalg.norm(u[:d_model])), \
        float(np.linalg.norm(w))


def rand_dir(j, d_model):
    g = np.random.default_rng(RAND_SEEDS[j]).standard_normal(5120).astype(np.float32)[:d_model]
    return g / float(np.linalg.norm(g))


# ---------------------------------------------------------------- the hook

class PrefixEditor:
    """Edits layer L's output at prefix generated-token positions only, and records the
    projection onto `u_read` at every position it sees.

    The FIRST forward call of a generate() is the prefill over prompt+prefix; that call is the
    only one edited. Every later call is a decode step and is returned untouched. When
    `targets` is None the hook is a pure recorder and returns `out` unchanged — that is SHAM,
    and it is bitwise identity by construction because the object is not rebuilt.
    """

    def __init__(self, torch, u_edit, u_read, n_prompt, n_prefix, targets):
        self.torch = torch
        self.u_edit_np, self.u_read_np = u_edit, u_read
        self.n_prompt, self.n_prefix = n_prompt, n_prefix
        self.targets_np = targets                 # None => SHAM
        self.reset()

    def reset(self):
        self.prefill_done = False
        self.n_prefill = self.n_decode = self.n_edited = 0
        self.proj_prefix = None
        self.proj_decode = []
        self.edit_norms = None

    def bind(self, device, dtype):
        t = self.torch
        self.u_edit = None if self.u_edit_np is None else \
            t.tensor(self.u_edit_np, device=device, dtype=t.float32)
        self.u_read = t.tensor(self.u_read_np, device=device, dtype=t.float32)
        self.targets = None if self.targets_np is None else \
            t.tensor(self.targets_np, device=device, dtype=t.float32)

    def make_hook(self):
        t = self.torch

        def hook(_m, _a, out):
            hs = out[0] if isinstance(out, tuple) else out
            if not self.prefill_done:
                self.prefill_done = True
                self.n_prefill += 1
                lo, hi = self.n_prompt, self.n_prompt + self.n_prefix
                seg32 = hs[:, lo:hi, :].to(t.float32)
                self.proj_prefix = (seg32 @ self.u_read).detach().cpu().numpy().copy()
                if self.targets is None:
                    return out                       # SHAM: the tensor is not touched at all
                proj = seg32 @ self.u_edit           # (B, n_prefix)
                delta = (self.targets.unsqueeze(0) - proj).unsqueeze(-1) * self.u_edit
                self.edit_norms = delta.norm(dim=-1).detach().cpu().numpy().copy()
                new = hs.clone()
                new[:, lo:hi, :] = (seg32 + delta).to(hs.dtype)
                self.n_edited = self.n_prefix
                return (new,) + tuple(out[1:]) if isinstance(out, tuple) else new
            self.n_decode += 1
            self.proj_decode.append(
                float((hs[0, -1, :].to(t.float32) @ self.u_read).item()))
            return out
        return hook


# ---------------------------------------------------------------- profiles

def resample(v, grid=GRID):
    """Linear interpolation of v onto `grid` points of r in [0,1]."""
    v = np.asarray(v, dtype=np.float64)
    if v.size == 0:
        return np.zeros(grid)
    if v.size == 1:
        return np.full(grid, v[0])
    return np.interp(np.linspace(0.0, 1.0, grid),
                     np.linspace(0.0, 1.0, v.size), v)


def target_profile(mean_grid, cut):
    """The class-mean profile evaluated at A's own prefix positions 0..cut-1."""
    if cut <= 1:
        return np.full(max(cut, 0), mean_grid[0], dtype=np.float32)
    r = np.arange(cut, dtype=np.float64) / (cut - 1)
    return np.interp(r, np.linspace(0.0, 1.0, len(mean_grid)), mean_grid).astype(np.float32)


# ---------------------------------------------------------------- pod driver

def load_model(torch):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    m = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16,
                                             device_map="cuda", trust_remote_code=True)
    m.eval()
    return m, tok


def encode(tok, templated, gen_text, cut):
    p_ids = tok(templated, add_special_tokens=False)["input_ids"]
    g_ids = tok(gen_text, add_special_tokens=False)["input_ids"]
    return p_ids, g_ids[:cut]


def do_profile(args):
    import torch
    from replay_w4 import decoder_layers
    cand = json.loads((OUT / "w15_candidates.json").read_text())
    harvest = json.loads((ROOT / "runs" / "w15_harvest" / "form_B" / "above_good.json").read_text())
    templated = harvest["templated_prompt"]
    by_i = {r["i"]: r for r in harvest["rows"]}
    m, tok = load_model(torch)
    d_model = m.config.hidden_size
    u, dmu = load_u()
    layers = decoder_layers(m)
    prof = {"1": [], "-1": []}
    per_trace = {}
    t0 = time.time()
    for k, c in enumerate(cand["candidates"]):
        p_ids, g_ids = encode(tok, templated, by_i[c["i"]]["raw_output"], c["cut"])
        ed = PrefixEditor(torch, None, u, len(p_ids), len(g_ids), None)
        ed.bind(next(m.parameters()).device, next(m.parameters()).dtype)
        h = layers[LAYER].register_forward_hook(ed.make_hook())
        try:
            ids = torch.tensor([p_ids + g_ids], device=m.device)
            with torch.no_grad():
                m(input_ids=ids)
        finally:
            h.remove()
        pr = ed.proj_prefix[0]
        prof[str(c["phat"])].append(resample(pr))
        per_trace[str(c["i"])] = {"phat": c["phat"], "cut": c["cut"],
                                  "proj_mean": float(np.mean(pr)),
                                  "proj_first": float(pr[0]), "proj_last": float(pr[-1])}
        if (k + 1) % 20 == 0:
            print("  profiled %d/%d (%.0fs)" % (k + 1, len(cand["candidates"]),
                                                time.time() - t0), flush=True)
    out = {"layer": LAYER, "grid": GRID, "dmu_norm": dmu, "d_model": d_model,
           "vphat_sha256": VEC_SHA, "n": {c: len(v) for c, v in prof.items()},
           "mean": {c: np.mean(np.stack(v), axis=0).tolist() for c, v in prof.items()},
           "sd": {c: np.std(np.stack(v), axis=0).tolist() for c, v in prof.items()},
           "per_trace": per_trace}
    sep = np.array(out["mean"]["1"]) - np.array(out["mean"]["-1"])
    out["class_separation_mean_abs"] = float(np.mean(np.abs(sep)))
    out["class_separation_grid"] = sep.tolist()
    (OUT / "w15_profiles.json").write_text(json.dumps(out))
    print("profiles: n(+1)=%d n(-1)=%d  |mean class separation| = %.4f  wall %.0fs"
          % (out["n"]["1"], out["n"]["-1"], out["class_separation_mean_abs"],
             time.time() - t0))
    return 0


def do_transplant(args):
    """`--cut-frac F` runs the DECLARED POST-FREEZE DIAGNOSTIC (JC-4), not PR-011's
    experiment: the same pairs, arms, seeds and edit at a cut placed at F of A's generated
    length instead of 25 tokens before its first cause-token. It exists because the frozen
    cut leaves the continuation almost no surface -- only 6 of 40 reconstructions carry
    their final literal inside the continuation -- and a null measured on no surface must be
    bounded before it is read. It is written to a separate directory and never enters the
    frozen statistic."""
    import torch
    from replay_w4 import decoder_layers
    pairs = json.loads((OUT / "w15_pairs.json").read_text())
    prof = json.loads((OUT / "w15_profiles.json").read_text())
    harvest = json.loads((ROOT / "runs" / "w15_harvest" / "form_B" / "above_good.json").read_text())
    templated = harvest["templated_prompt"]
    by_i = {r["i"]: r for r in harvest["rows"]}
    m, tok = load_model(torch)
    d_model = m.config.hidden_size
    u, dmu = load_u()
    layers = decoder_layers(m)
    mean_grid = {c: np.array(v) for c, v in prof["mean"].items()}

    eos_ids = set()
    gc = getattr(m, "generation_config", None)
    e = getattr(gc, "eos_token_id", None) if gc is not None else None
    for x in (e if isinstance(e, (list, tuple)) else [e]) + [tok.eos_token_id]:
        if x is not None:
            eos_ids.add(int(x))

    RUNS.mkdir(parents=True, exist_ok=True)
    n_done = 0
    todo = [d for d in args.directions]
    t0 = time.time()
    for direction in todo:
        rows = []
        plist = pairs[direction]
        for pi, pr in enumerate(plist):
            a_i, b_i = pr["A_i"], pr["B_i"]
            a_phat, b_phat = pr["A_phat"], pr["B_phat"]
            cut = pr["A_cut"]
            if args.cut_frac:
                deep = int(args.cut_frac * by_i[a_i]["n_output_tokens"])
                if deep < 25 or deep >= cut:
                    print("  skip pair %d (deep cut %d not usable against %d)" % (pi, deep, cut))
                    continue
                cut = deep
            p_ids, g_ids = encode(tok, templated, by_i[a_i]["raw_output"], cut)
            n_prefix = len(g_ids)
            tgt_b = target_profile(mean_grid[str(b_phat)], n_prefix)
            tgt_a = target_profile(mean_grid[str(a_phat)], n_prefix)
            urand = rand_dir(pi % 4, d_model)
            ids = torch.tensor([p_ids + g_ids], device=m.device)
            am = torch.ones_like(ids)
            for arm in ARMS:
                spec = {"SWAP": (u, tgt_b), "SELF": (u, tgt_a),
                        "RAND": (urand, tgt_b), "SHAM": (None, None)}[arm]
                ed = PrefixEditor(torch, spec[0], u, len(p_ids), n_prefix, spec[1])
                ed.bind(next(m.parameters()).device, next(m.parameters()).dtype)
                h = layers[LAYER].register_forward_hook(ed.make_hook())
                seed = BASE_SEED + SEED_BASE + pi
                try:
                    torch.manual_seed(seed)
                    with torch.no_grad():
                        outp = m.generate(input_ids=ids, attention_mask=am, do_sample=True,
                                          temperature=TEMPERATURE, top_p=TOP_P,
                                          max_new_tokens=args.max_new,
                                          pad_token_id=tok.pad_token_id or tok.eos_token_id)
                finally:
                    h.remove()
                assert ed.n_prefill == 1, "hook saw %d prefill passes" % ed.n_prefill
                new = outp[0, ids.shape[1]:].tolist()
                hit = [k for k, t in enumerate(new) if t in eos_ids]
                ntok, finish = (hit[0] + 1, "stop") if hit else (len(new), "length")
                cont = tok.decode(new[:ntok], skip_special_tokens=True)
                prefix_text = tok.decode(g_ids, skip_special_tokens=True)
                full = prefix_text + cont
                reasoning, answer, how = split_output(full, FAMILY_MODE)
                rows.append({
                    "direction": direction, "pair_index": pi, "arm": arm,
                    "A_i": a_i, "B_i": b_i, "A_phat": a_phat, "B_phat": b_phat,
                    "A_seed": by_i[a_i]["seed"], "B_seed": by_i[b_i]["seed"],
                    "cut": cut, "n_prefix_tokens": n_prefix, "n_prompt_tokens": len(p_ids),
                    "torch_seed": seed, "rand_dir_index": pi % 4,
                    "rand_dir_seed": RAND_SEEDS[pi % 4],
                    "n_edited_positions": ed.n_edited,
                    "edit_norm_mean": None if ed.edit_norms is None
                    else float(np.mean(ed.edit_norms)),
                    "edit_norm_max": None if ed.edit_norms is None
                    else float(np.max(ed.edit_norms)),
                    "proj_prefix_mean": float(np.mean(ed.proj_prefix[0])),
                    "proj_decode": [round(x, 4) for x in ed.proj_decode],
                    "n_continuation_tokens": ntok,
                    "continuation_token_ids": new[:ntok], "finish_reason": finish,
                    "truncated": finish == "length",
                    "prefix_text": prefix_text, "continuation_text": cont,
                    "reconstructed": full, "visible_answer": answer, "split_method": how,
                    "ngram4_ratio": round(ngram_ratio(full, 4), 4),
                    "degenerate": bool(is_degenerate(full)),
                })
            if (pi + 1) % 5 == 0:
                print("  [%s] pair %d/%d  (%.0fs)"
                      % (direction, pi + 1, len(plist), time.time() - t0), flush=True)
        root = RUNS if not args.cut_frac else (
            RUNS.parent / ("w15_transplant_deep"))
        root.mkdir(parents=True, exist_ok=True)
        path = root / ("%s.json" % direction)
        path.write_text(json.dumps({
            "packet": "W15", "pre_registration": "PR-011", "model": MODEL,
            "direction": direction, "layer": LAYER, "arms": list(ARMS),
            "vphat_sha256": VEC_SHA, "dmu_norm": dmu, "d_model": d_model,
            "templated_prompt": templated, "threshold": TAU_B,
            "sampling": {"temperature": TEMPERATURE, "top_p": TOP_P,
                         "max_new_tokens": args.max_new, "batch": 1,
                         "seed_rule": "torch.manual_seed(%d + %d + pair_index), reseeded "
                                      "before EVERY arm" % (BASE_SEED, SEED_BASE)},
            "rand_dir_seeds": RAND_SEEDS, "n_pairs": len(rows) // len(ARMS),
            "cut_rule": ("PR-011: belief_gen_pos - 25" if not args.cut_frac else
                         "JC-4 DIAGNOSTIC, POST-FREEZE: floor(%.2f * n_gen_A)" % args.cut_frac),
            "rows": rows,
        }, indent=2, ensure_ascii=False))
        print("[%s] %d pairs x %d arms = %d generations -> %s (%.0fs)"
              % (direction, len(rows) // len(ARMS), len(ARMS), len(rows), path,
                 time.time() - t0),
              flush=True)
    return 0


# ---------------------------------------------------------------- laptop smoke

def smoke():
    """PR-011 item 8. Extends W7's S1-S6 with the edit-locality clauses.

      S-E  the sha-pinned W5 tensor loads and ||dmu|| matches w5_layers.csv at L27
      S-F  the 1,000 harvest seeds are distinct and disjoint from every earlier block
      S-A  the edit is 1-D: (h'-h) is parallel to u to float precision, and h'.u == target
      S-B  the edit touches ONLY prefix generated-token positions: prompt positions and every
           decode position are bitwise unchanged
      S-C  SHAM is bitwise identity against the same generation with NO hook at all
      S-D  SWAP / SELF / RAND each change the generated ids, and RAND's edit is orthogonal
           to u to float precision
      S-G  target_profile / resample are exact at the grid endpoints and monotone in r
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from replay_w4 import decoder_layers
    import csv as _csv
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        ok &= bool(cond)
        print("%s %-4s %s" % ("ok  " if cond else "FAIL", name, extra))

    u_full, dmu = load_u()
    want = {int(r["layer"]): float(r["vphat_l2"])
            for r in _csv.DictReader(open(ROOT / "analysis/out/w5_layers.csv"))
            if r["form"] == "B"}
    chk("S-E", abs(dmu - want[LAYER]) < 1e-4 and abs(np.linalg.norm(u_full) - 1) < 1e-5,
        "||v_phat^B(L27)||=%.6f (csv %.6f), u unit-norm, sha256 pinned" % (dmu, want[LAYER]))

    import gen_w15
    seeds = list(range(BASE_SEED + gen_w15.SEED_OFFSET_0,
                       BASE_SEED + gen_w15.SEED_OFFSET_0 + 1000))
    chk("S-F", len(set(seeds)) == 1000 and min(seeds) == 10714 and max(seeds) == 11713,
        "harvest seeds %d-%d, 1000 distinct, disjoint from W14's 10414-10713"
        % (min(seeds), max(seeds)))

    g = resample([0.0, 1.0, 2.0], 101)
    tp = target_profile(np.linspace(0, 1, 101), 50)
    chk("S-G", abs(g[0]) < 1e-12 and abs(g[-1] - 2.0) < 1e-12 and len(g) == 101
        and abs(tp[0]) < 1e-12 and abs(tp[-1] - 1.0) < 1e-12 and np.all(np.diff(tp) > 0),
        "resample endpoints exact; target_profile(cut=50) spans [0,1] monotonically")

    name = os.environ.get("W15_SMOKE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    tok = AutoTokenizer.from_pretrained(name)
    m = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float32)
    m.eval()
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    L = decoder_layers(m)
    li = min(2, len(L) - 1)
    d = m.config.hidden_size
    print("smoke model=%s layers=%d d_model=%d" % (name, len(L), d))

    rng = np.random.default_rng(4242)
    u = rng.standard_normal(d).astype(np.float32); u /= np.linalg.norm(u)
    ur = rand_dir(0, d)
    text = "The quick brown fox jumps over the lazy dog and then keeps running for a while."
    enc = tok([text], return_tensors="pt", add_special_tokens=False)
    ids = enc["input_ids"]
    n_prompt, n_prefix = 6, int(ids.shape[1]) - 6
    tgt = np.linspace(3.0, -3.0, n_prefix).astype(np.float32)
    NEW = 10

    def gen(ed):
        h = None
        if ed is not None:
            ed.bind(torch.device("cpu"), torch.float32)
            ed.reset()
            h = L[li].register_forward_hook(ed.make_hook())
        try:
            torch.manual_seed(1234)
            with torch.no_grad():
                return m.generate(input_ids=ids, attention_mask=enc["attention_mask"],
                                  do_sample=True, temperature=1.0, top_p=1.0,
                                  max_new_tokens=NEW, min_new_tokens=NEW,
                                  pad_token_id=tok.pad_token_id)
        finally:
            if h is not None:
                h.remove()

    # capture the layer's output before and after the editing hook
    pre, post = [], []
    ed = PrefixEditor(torch, u, u, n_prompt, n_prefix, tgt)
    ed.bind(torch.device("cpu"), torch.float32)
    hpre = L[li].register_forward_hook(
        lambda _m, _a, o: pre.append((o[0] if isinstance(o, tuple) else o).clone()))
    hinj = L[li].register_forward_hook(ed.make_hook())
    hpost = L[li].register_forward_hook(
        lambda _m, _a, o: post.append((o[0] if isinstance(o, tuple) else o).clone()))
    torch.manual_seed(1234)
    with torch.no_grad():
        m.generate(input_ids=ids, attention_mask=enc["attention_mask"], do_sample=True,
                   temperature=1.0, top_p=1.0, max_new_tokens=NEW, min_new_tokens=NEW,
                   pad_token_id=tok.pad_token_id)
    for h in (hpre, hinj, hpost):
        h.remove()

    diff = (post[0] - pre[0])[0]                       # (T, d) on the prefill pass
    ut = torch.tensor(u)
    seg = diff[n_prompt:n_prompt + n_prefix]
    par = torch.outer(seg @ ut, ut)
    orth = (seg - par).abs().max().item()
    hit = ((post[0][0, n_prompt:n_prompt + n_prefix] @ ut)
           - torch.tensor(tgt)).abs().max().item()
    chk("S-A", orth < 1e-4 and hit < 1e-3,
        "edit orthogonal residual max=%.3g ; |h'.u - target| max=%.3g" % (orth, hit))

    untouched_prompt = diff[:n_prompt].abs().max().item()
    decode_diffs = [(post[k] - pre[k]).abs().max().item() for k in range(1, len(pre))]
    chk("S-B", untouched_prompt == 0.0 and max(decode_diffs) == 0.0
        and ed.n_edited == n_prefix and ed.n_prefill == 1 and ed.n_decode == NEW - 1,
        "prompt delta=%.3g ; decode delta max=%.3g over %d steps ; edited %d prefix positions"
        % (untouched_prompt, max(decode_diffs), len(decode_diffs), ed.n_edited))

    out_none = gen(None)
    out_sham = gen(PrefixEditor(torch, None, u, n_prompt, n_prefix, None))
    chk("S-C", torch.equal(out_none, out_sham),
        "SHAM (hook installed, targets=None) is bitwise identical to no hook at all")

    out_swap = gen(PrefixEditor(torch, u, u, n_prompt, n_prefix, tgt))
    out_self = gen(PrefixEditor(torch, u, u, n_prompt, n_prefix, tgt * 0.5))
    ed_r = PrefixEditor(torch, ur, u, n_prompt, n_prefix, tgt)
    out_rand = gen(ed_r)
    chk("S-D", (not torch.equal(out_none, out_swap)) and (not torch.equal(out_none, out_rand))
        and (not torch.equal(out_swap, out_self))
        and abs(float(np.dot(u, ur))) < 0.15,
        "SWAP/SELF/RAND all change the ids; cos(u, u_rand)=%.4f" % float(np.dot(u, ur)))
    print("SMOKE %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--transplant", action="store_true")
    ap.add_argument("--directions", nargs="*", default=["primary"])
    ap.add_argument("--max-new", type=int, default=MAX_NEW_TOKENS)
    ap.add_argument("--cut-frac", type=float, default=None,
                    help="JC-4 post-freeze diagnostic: cut at this fraction of A's n_gen")
    a = ap.parse_args()
    if a.smoke:
        return smoke()
    if a.profile:
        return do_profile(a)
    if a.transplant:
        return do_transplant(a)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
