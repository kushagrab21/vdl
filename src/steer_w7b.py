"""W7b: the low-dose follow-up — inject ±α·v_p̂^B at L27 with α ∈ {0.5, 0.25}.

PR-006. **Stage 2, designed AFTER W7's result was known.** W7's pre-registered grid
(α ∈ {1, 2, 4} in ‖Δμ‖ units; α=2 is 22.8 % of the residual-stream norm) sits in a regime
where a perturbation of that size suppresses landing by 0.158 whatever direction it points
in (P-008 §2). PR-006 asks the one question that grid could not: **does anything
direction-specific survive at doses small enough that the generic distortion vanishes?**

Everything about the injection is W7's, by import and not by re-implementation:

    from steer_w7 import Injector, run_arm, direction_vector, load_vphat

so the arithmetic under test is the code W7's 7/7 laptop smoke certified (F-015). The ONLY
change to that module's state is that the frozen null-seed list is **appended to** — W7's ten
seeds 9001–9010 keep indices 0–9 untouched and bit-identical, and PR-006's four new seeds
9011–9014 take indices 10–13. Clause B1 of this script's smoke asserts exactly that.

  python3 src/steer_w7b.py --smoke     # laptop plumbing test, tiny model, CPU, no GPU
  python3 src/steer_w7b.py             # the real thing, on the pod: all 12 arms
  python3 src/steer_w7b.py --arms B7b_above_L27_ap05
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import numpy as np  # noqa: E402

import steer_w7 as s7  # noqa: E402
from steer_w7 import (MODEL, TAU_B, FORM, N_PER_ARM, BATCH, MAX_NEW_TOKENS,  # noqa: E402
                      VEC_SHA, load_vphat, direction_vector, run_arm,
                      is_degenerate, ngram_ratio)

OUT_ROOT = ROOT / "runs" / "w7b_steer"
SHAM_REUSED = ROOT / "runs" / "w7_steer" / "B_above_sham.json"   # PR-006 item 2, DECLARED

# PR-006 item 2: four NEW random directions, the next four integers after PR-005's 9001–9010.
NULL_SEEDS_7B = [9011, 9012, 9013, 9014]
W7_NULL_SEEDS = list(s7.NULL_SEEDS)                 # snapshot of the ten frozen by PR-005

# Append-only extension of the frozen list. Indices 0–9 are W7's and are never touched, so
# every W7 arm still resolves to the direction PR-005 froze; indices 10–13 are PR-006's.
if len(s7.NULL_SEEDS) == 10:
    s7.NULL_SEEDS.extend(NULL_SEEDS_7B)
assert s7.NULL_SEEDS[:10] == W7_NULL_SEEDS, "W7's frozen null seeds were disturbed"
assert s7.NULL_SEEDS[10:] == NULL_SEEDS_7B

SEED_OFFSET_0 = 9150            # seeds 64+9150 = 9214 …; contiguous with W7's 8064–9213

# --------------------------------------------------------------- the 12 arms (PR-006 item 2)
# key -> (alpha, direction_kind, null_index)
def _arms():
    spec = [
        ("B7b_above_L27_ap05",  +0.50, "vphat", None),
        ("B7b_above_L27_ap025", +0.25, "vphat", None),
        ("B7b_above_L27_am025", -0.25, "vphat", None),
        ("B7b_above_L27_am05",  -0.50, "vphat", None),
    ]
    for j in range(4):
        spec.append(("B7b_above_null%02d_ap05" % (10 + j), +0.50, "random", 10 + j))
        spec.append(("B7b_above_null%02d_am05" % (10 + j), -0.50, "random", 10 + j))
    a = {}
    for k, (key, alpha, kind, jj) in enumerate(spec):
        a[key] = {"key": key, "condition": "above_good", "layer": 27, "alpha": alpha,
                  "direction": kind, "null_index": jj,
                  "seed_offset": SEED_OFFSET_0 + 50 * k}
    return a


ARMS = _arms()
VPHAT_ARMS = [k for k, v in ARMS.items() if v["direction"] == "vphat"]      # the 4 dose arms
NULL_ARM_PAIRS = [("B7b_above_null%02d_ap05" % (10 + j), "B7b_above_null%02d_am05" % (10 + j))
                  for j in range(4)]
PRIMARY_POS, PRIMARY_NEG = "B7b_above_L27_ap05", "B7b_above_L27_am05"


def stamp(path):
    """run_arm writes W7's meta header; re-stamp the packet/pre-registration fields.

    Nothing numeric is touched — only the four provenance strings, so a reader of an arm file
    is never told it belongs to W7 or is governed by PR-005.
    """
    d = json.loads(path.read_text())
    d["packet"] = "W7b"
    d["pre_registration"] = "PR-006"
    d["stage"] = "stage-2 follow-up, designed AFTER W7's result (R-011); W7's verdict stands"
    d["sham_reference"] = "runs/w7_steer/B_above_sham.json (REUSED, not regenerated; PR-006 item 2)"
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    return d


# --------------------------------------------------------------- laptop smoke (PR-006, V-011)

def smoke():
    """W7's seven clauses re-run through the shared code path, plus six W7b-specific ones.

      B0  steer_w7's own smoke still passes 7/7 with the null-seed list extended
      B1  W7's null seeds and directions are BIT-IDENTICAL after the append
      B2  the four new directions are unit-norm, reproducible, mutually distinct, and
          distinct from all ten of W7's
      B3  the arm table matches PR-006 item 2: 12 arms, seeds 9214–9813 contiguous and
          disjoint from W7's 8064–9213
      B4  ‖injected vector‖ = |α|·‖Δμ‖ exactly, at every one of the 12 arms
      B5  the delta added at each decode step equals α·‖Δμ‖·u at α=+0.5 (the smallest
          non-zero dose actually run), and the prefill pass is untouched
      B6  the REUSED W7 sham file is present and is the arm PR-006 item 2 declares
    """
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        ok &= bool(cond)
        print("%s %-4s %s" % ("ok  " if cond else "FAIL", name, extra))

    print("=== B0: steer_w7 smoke (7/7 expected), through the extended module ===")
    rc = s7.smoke()
    print("=== W7b clauses ===")
    chk("B0", rc == 0, "steer_w7.smoke() returned %d (0 = 7/7 PASS)" % rc)

    v = load_vphat()
    dmu = float(np.linalg.norm(v[27]))

    # B1 — W7's ten directions must be unchanged by the append.
    same = True
    for j in range(10):
        got, _ = direction_vector({"layer": 27, "direction": "random", "null_index": j}, v)
        want = np.random.default_rng(W7_NULL_SEEDS[j]).standard_normal(5120).astype(np.float32)
        want = want / float(np.linalg.norm(want))
        same &= np.array_equal(got, want)
    chk("B1", same and s7.NULL_SEEDS[:10] == W7_NULL_SEEDS,
        "W7 null seeds %s unchanged; all 10 directions bit-identical after append"
        % (W7_NULL_SEEDS[0:2] + ["…"] + W7_NULL_SEEDS[-1:]))

    # B2 — the four new directions.
    new = [direction_vector({"layer": 27, "direction": "random", "null_index": 10 + j}, v)[0]
           for j in range(4)]
    rep = direction_vector({"layer": 27, "direction": "random", "null_index": 10}, v)[0]
    old = [direction_vector({"layer": 27, "direction": "random", "null_index": j}, v)[0]
           for j in range(10)]
    u_v = v[27] / dmu
    cos_v = [float(x @ u_v) for x in new]
    distinct = (all(not np.array_equal(a, b) for i, a in enumerate(new) for b in new[i + 1:])
                and all(not np.array_equal(a, b) for a in new for b in old))
    chk("B2", (np.array_equal(new[0], rep) and distinct
               and all(abs(np.linalg.norm(x) - 1) < 1e-5 for x in new)
               and max(abs(c) for c in cos_v) < 0.1),
        "seeds %s unit-norm, reproducible, disjoint from W7's ten; cos(u_null, u_vphat) = %s"
        % (NULL_SEEDS_7B, ["%+.4f" % c for c in cos_v]))

    # B3 — the arm table.
    lo = [64 + a["seed_offset"] for a in ARMS.values()]
    hi = [x + N_PER_ARM - 1 for x in lo]
    allseeds = sorted(s for a in ARMS.values()
                      for s in range(64 + a["seed_offset"], 64 + a["seed_offset"] + N_PER_ARM))
    w7 = set(range(8064, 9214))
    chk("B3", (len(ARMS) == 12 and len(allseeds) == 600 and len(set(allseeds)) == 600
               and allseeds == list(range(9214, 9814)) and not (set(allseeds) & w7)),
        "12 arms, %d seeds %d–%d contiguous, 0 collisions with W7's 8064–9213"
        % (len(allseeds), min(allseeds), max(allseeds)))

    # B4 — injected norms.
    norms, bad = [], 0
    for k, a in ARMS.items():
        u, d_ = direction_vector(a, v)
        n_ = float(np.linalg.norm(a["alpha"] * d_ * u))
        norms.append((k, a["alpha"], n_))
        bad += abs(n_ - abs(a["alpha"]) * dmu) > 1e-3
    chk("B4", bad == 0 and abs(dmu - 12.726012) < 1e-4,
        "‖Δμ‖=%.6f ; ‖δ‖ = %.3f at |α|=0.5 (%.1f%% of ‖h‖=111.65) and %.3f at |α|=0.25 (%.1f%%)"
        % (dmu, 0.5 * dmu, 100 * 0.5 * dmu / 111.65, 0.25 * dmu, 100 * 0.25 * dmu / 111.65))

    # B5 — the injected delta at the dose actually run, captured inside a real generate().
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from replay_w4 import decoder_layers
    name = "Qwen/Qwen2.5-0.5B-Instruct"
    tok = AutoTokenizer.from_pretrained(name)
    m = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float32)
    m.eval()
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    L = decoder_layers(m)
    dmod = m.config.hidden_size
    li = min(2, len(L) - 1)
    u_small = (v[27][:dmod] / np.linalg.norm(v[27][:dmod])).astype(np.float32)
    delta = (0.5 * dmu * u_small).astype(np.float32)
    enc = tok(["The quick brown fox"], return_tensors="pt")
    NEW = 10
    pre, post = {}, {}
    inj = s7.Injector(delta, torch)
    inj.bind(torch.device("cpu"), torch.float32)
    inj.reset()
    hs = [L[li].register_forward_hook(
              lambda _m, _a, o: pre.setdefault(len(pre), (o[0] if isinstance(o, tuple) else o).clone())),
          L[li].register_forward_hook(inj.make_hook()),
          L[li].register_forward_hook(
              lambda _m, _a, o: post.setdefault(len(post), (o[0] if isinstance(o, tuple) else o).clone()))]
    torch.manual_seed(1234)
    with torch.no_grad():
        m.generate(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                   do_sample=True, temperature=1.0, top_p=1.0, max_new_tokens=NEW,
                   min_new_tokens=NEW, pad_token_id=tok.pad_token_id)
    for h in hs:
        h.remove()
    d0 = (post[0] - pre[0]).abs().max().item()
    dd = [(post[k] - pre[k] - torch.tensor(delta)).abs().max().item() for k in range(1, len(pre))]
    chk("B5", d0 == 0.0 and max(dd) < 1e-4 and inj.n_prefill == 1 and inj.n_decode == NEW - 1,
        "alpha=+0.5: prefill delta=%.3g ; decode |added - 0.5*||dmu||*u| max=%.3g over %d steps"
        % (d0, max(dd), len(dd)))

    # B6 — the reused sham.
    if SHAM_REUSED.exists():
        sh = json.loads(SHAM_REUSED.read_text())
        chk("B6", (sh["alpha"] == 0.0 and sh["layer"] == 27 and sh["condition"] == "above_good"
                   and sh["n"] == 50 and sh["seed_lo"] == 8664 and sh["seed_hi"] == 8713
                   and sh["vphat_sha256"] == VEC_SHA),
            "REUSED sham %s: alpha=%+g L%d %s n=%d seeds %d–%d"
            % (SHAM_REUSED.name, sh["alpha"], sh["layer"], sh["condition"], sh["n"],
               sh["seed_lo"], sh["seed_hi"]))
    else:
        chk("B6", False, "REUSED sham file missing: %s" % SHAM_REUSED)

    print("\nW7b SMOKE %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# --------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--arms", nargs="*", default=list(ARMS))
    ap.add_argument("--n", type=int, default=N_PER_ARM)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--max-new", type=int, default=MAX_NEW_TOKENS)
    ap.add_argument("--out-root", default=str(OUT_ROOT))
    ap.add_argument("--tiny", action="store_true",
                    help="end-to-end laptop rehearsal: Qwen2.5-0.5B on CPU, real run_arm path")
    args = ap.parse_args()

    if args.smoke:
        return smoke()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from replay_w4 import decoder_layers
    vphat = load_vphat()
    t0 = time.time()
    if args.tiny:
        name = "Qwen/Qwen2.5-0.5B-Instruct"
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float32)
        vphat = vphat[:, :model.config.hidden_size].copy()
    else:
        name = MODEL
        tok = AutoTokenizer.from_pretrained(MODEL)
        model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16,
                                                     device_map="cuda", trust_remote_code=True)
    model.eval()
    print("model %s loaded in %.1fs | dtype %s | layers %d | d_model %d"
          % (name, time.time() - t0, next(model.parameters()).dtype,
             len(decoder_layers(model)), model.config.hidden_size), flush=True)

    out_root = Path(args.out_root)
    for key in args.arms:
        run_arm(key, ARMS[key], model, tok, torch, vphat, out_root, args.n,
                args.batch, args.max_new)
        stamp(out_root / ("%s.json" % key))
    print("\nall %d W7b arms done in %.1fs" % (len(args.arms), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
