"""W7: the intervention — inject ±α·v_p̂^B into the residual stream during generation.

PR-005. The project's one causal rung. A forward hook on decoder layer ℓ's OUTPUT (the same
post-block residual stream F-013 hooked and W4 read) adds

    α · ‖Δμ‖(ℓ) · u        with   u = v_p̂^B(ℓ) / ‖v_p̂^B(ℓ)‖

at every generated-token position from the first generated token onward. The prefill pass
(the templated prompt) is NEVER modified; every decode step IS. Because v_p̂ is the raw
class-mean difference, ‖Δμ‖(ℓ) = ‖v_p̂^B(ℓ)‖ and the injected vector is numerically α·v_p̂^B(ℓ);
the code keeps the α·‖Δμ‖·u form so the unit definition stays explicit.

Sign, from PR-004 item 1 via direction_w5.phat_of: v_p̂ = mean(p̂=+1) − mean(p̂=−1), and p̂=+1
means the trace believes ABOVE the threshold is favoured. So +α is PREDICTED to raise
P(final > τ_B). That sign is frozen in PR-005 item 1 and is not flipped downstream.

Generation is HF `generate` (vLLM cannot carry the hook), bf16, batch 25, max_new_tokens 2048
(PR-005 item 3's declared amendment to PR-001 item 5). Every generation in an arm shares one
prompt string, so a batch needs no padding.

  python3 src/steer_w7.py --smoke              # laptop plumbing test, tiny model, CPU, no GPU
  python3 src/steer_w7.py                      # the real thing, on the pod: all 23 arms
  python3 src/steer_w7.py --arms B_above_sham  # one arm
  python3 src/steer_w7.py --retry-arm ARM      # the single permitted |α|-halving re-run
"""

import argparse
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
from prompts_w3 import build_prompt_w3  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
FAMILY_MODE = "no_think"
TAU_B = 4500000000
FORM = "B"
N_PER_ARM = 50
BATCH = 25
MAX_NEW_TOKENS = 2048              # PR-005 item 3 (JC-1), amending PR-001 item 5 for W7 only
VEC = ROOT / "analysis" / "out" / "w5_vectors" / "w5_vphat_B.safetensors"
VEC_SHA = "cbdbbb4a4eccfd085549d3aa1a6b94170c77252bd2dd64718b4f950426b9be64"
OUT_ROOT = ROOT / "runs" / "w7_steer"
NULL_SEEDS = [9001 + j for j in range(10)]      # PR-005 item 3, frozen seed list

# ---------------------------------------------------------------- the 23 arms (PR-005 item 3)
# key -> (condition, layer, alpha, direction_kind, null_index_or_None, seed_offset)
def _arms():
    a = {}
    spec = [
        ("B_above_L27_ap1", "above_good", 27, +1.0, "vphat", None),
        ("B_above_L27_ap2", "above_good", 27, +2.0, "vphat", None),
        ("B_above_L27_ap4", "above_good", 27, +4.0, "vphat", None),
        ("B_above_L27_am1", "above_good", 27, -1.0, "vphat", None),
        ("B_above_L27_am2", "above_good", 27, -2.0, "vphat", None),
        ("B_above_L27_am4", "above_good", 27, -4.0, "vphat", None),
        ("B_above_L30_ap2", "above_good", 30, +2.0, "vphat", None),
        ("B_above_L30_am2", "above_good", 30, -2.0, "vphat", None),
        ("B_below_L27_ap2", "below_good", 27, +2.0, "vphat", None),
        ("B_below_L27_am2", "below_good", 27, -2.0, "vphat", None),
        ("B_neutral_L27_ap2", "baseline", 27, +2.0, "vphat", None),
        ("B_neutral_L27_am2", "baseline", 27, -2.0, "vphat", None),
        ("B_above_sham",     "above_good", 27, 0.0, "vphat", None),
    ]
    for j in range(10):
        spec.append(("B_above_null%02d" % j, "above_good", 27, +2.0, "random", j))
    for k, (key, cond, layer, alpha, kind, jj) in enumerate(spec):
        a[key] = {"key": key, "condition": cond, "layer": layer, "alpha": alpha,
                  "direction": kind, "null_index": jj, "seed_offset": 8000 + 50 * k}
    return a


ARMS = _arms()
VPHAT_ARMS = [k for k, v in ARMS.items() if v["direction"] == "vphat"]     # 13, incl. sham


# ---------------------------------------------------------------- direction loading

def load_vphat():
    from safetensors.numpy import load_file
    import hashlib
    got = hashlib.sha256(VEC.read_bytes()).hexdigest()
    if got != VEC_SHA:
        raise RuntimeError("v_phat^B tensor sha256 %s != PR-005 item 1's %s" % (got, VEC_SHA))
    v = load_file(str(VEC))["vphat"]
    assert v.shape == (48, 5120), v.shape
    return v.astype(np.float32)


def direction_vector(arm, vphat, d_model=None):
    """Return (unit direction u, ||dmu|| at that layer). PR-005 items 1 and 3."""
    d_model = vphat.shape[1] if d_model is None else d_model
    layer = arm["layer"]
    dmu = float(np.linalg.norm(vphat[layer]))
    if arm["direction"] == "vphat":
        u = vphat[layer] / dmu
    else:
        g = np.random.default_rng(NULL_SEEDS[arm["null_index"]]).standard_normal(
            5120).astype(np.float32)[:d_model]
        u = g / float(np.linalg.norm(g))
    return u.astype(np.float32), dmu


# ---------------------------------------------------------------- the hook

class Injector:
    """Adds delta = alpha * ||dmu|| * u to layer ell's output at decode positions only.

    `prefill_done` is False until the first forward call of a generate(); that call is the
    prompt pass and is left untouched. Every later call in the same generate() carries the
    one new generated-token position and is steered. Counters are asserted after each batch.
    """

    def __init__(self, delta_np, torch):
        self.delta_np = delta_np
        self.torch = torch
        self.reset()

    def reset(self):
        self.prefill_done = False
        self.n_prefill = 0
        self.n_decode = 0
        self.n_positions_touched = 0

    def make_hook(self):
        def hook(_m, _a, out):
            hs = out[0] if isinstance(out, tuple) else out
            if not self.prefill_done:
                self.prefill_done = True
                self.n_prefill += 1
                return out
            self.n_decode += 1
            self.n_positions_touched += hs.shape[1]
            d = self.delta.to(dtype=hs.dtype, device=hs.device)
            hs = hs + d
            if isinstance(out, tuple):
                return (hs,) + tuple(out[1:])
            return hs
        return hook

    def bind(self, device, dtype):
        self.delta = self.torch.tensor(self.delta_np, device=device, dtype=dtype)


# ---------------------------------------------------------------- degeneration / coherence

def ngram_ratio(text, n=4):
    toks = text.split()
    if len(toks) < n:
        return 1.0
    grams = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    return len(set(grams)) / float(len(grams))


def is_degenerate(text):
    """PR-005 item 4c(iv)."""
    return len(text.split()) >= 100 and ngram_ratio(text, 4) < 0.35


# ---------------------------------------------------------------- driver

def run_arm(key, arm, model, tok, torch, vphat, out_root, n, batch, max_new,
            alpha_override=None, tag=""):
    from replay_w4 import decoder_layers
    alpha = arm["alpha"] if alpha_override is None else alpha_override
    u, dmu = direction_vector(arm, vphat)
    delta = (alpha * dmu * u).astype(np.float32)

    tau = None if arm["condition"] == "baseline" else TAU_B
    prompt_text = build_prompt_w3(FORM, arm["condition"], tau)
    templated = tok.apply_chat_template([{"role": "user", "content": prompt_text}],
                                        tokenize=False, add_generation_prompt=True)
    enc = tok([templated], return_tensors="pt", add_special_tokens=False)
    n_prompt = int(enc["input_ids"].shape[1])

    gc = getattr(model, "generation_config", None)
    e = getattr(gc, "eos_token_id", None) if gc is not None else None
    eos_ids = set()
    for x in (e if isinstance(e, (list, tuple)) else [e]) + [tok.eos_token_id]:
        if x is not None:
            eos_ids.add(int(x))
    assert eos_ids, "no eos token id available"

    inj = Injector(delta, torch)
    layers = decoder_layers(model)
    inj.bind(next(model.parameters()).device, next(model.parameters()).dtype)
    handle = layers[min(arm["layer"], len(layers) - 1)].register_forward_hook(inj.make_hook())

    rows, t0 = [], time.time()
    try:
        for b0 in range(0, n, batch):
            bs = min(batch, n - b0)
            block_seed = BASE_SEED + arm["seed_offset"] + b0
            torch.manual_seed(block_seed)
            ids = enc["input_ids"].repeat(bs, 1).to(model.device)
            am = enc["attention_mask"].repeat(bs, 1).to(model.device)
            inj.reset()
            with torch.no_grad():
                out = model.generate(input_ids=ids, attention_mask=am,
                                     do_sample=True, temperature=TEMPERATURE, top_p=TOP_P,
                                     max_new_tokens=max_new,
                                     pad_token_id=tok.pad_token_id or tok.eos_token_id)
            assert inj.n_prefill == 1, "hook saw %d prefill passes" % inj.n_prefill
            gen = out[:, n_prompt:]
            for r in range(bs):
                g = gen[r]
                # Count real generated tokens INCLUDING the stop token, matching vLLM's
                # n_output_tokens convention (replay_w4 V4). Qwen2.5 stops on <|im_end|>,
                # which is not tok.eos_token_id, so the whole eos set is used.
                toks = g.tolist()
                hit = [k for k, t in enumerate(toks) if t in eos_ids]
                if hit:
                    ntok, finish = hit[0] + 1, "stop"
                else:
                    ntok, finish = len(toks), "length"
                text = tok.decode(toks[:ntok], skip_special_tokens=True)
                reasoning, answer, how = split_output(text, FAMILY_MODE)
                i = b0 + r
                rows.append({
                    "i": i, "seed": BASE_SEED + arm["seed_offset"] + i,
                    "seed_block": block_seed, "row_in_batch": r,
                    "raw_output": text, "reasoning_text": reasoning,
                    "visible_answer": answer, "split_method": how,
                    "finish_reason": finish, "truncated": finish == "length",
                    "n_output_tokens": ntok,
                    "ngram4_ratio": round(ngram_ratio(text, 4), 4),
                    "degenerate": bool(is_degenerate(text)),
                })
            print("  [%s%s] batch %d/%d seed_block=%d decode_steps=%d wall=%.1fs"
                  % (key, tag, b0 // batch + 1, (n + batch - 1) // batch, block_seed,
                     inj.n_decode, time.time() - t0), flush=True)
    finally:
        handle.remove()

    out_root.mkdir(parents=True, exist_ok=True)
    path = out_root / ("%s%s.json" % (key, tag))
    meta = {
        "packet": "W7", "pre_registration": "PR-005", "model": MODEL,
        "family_mode": FAMILY_MODE, "form": FORM, "arm": key + tag,
        "condition": arm["condition"], "threshold": tau,
        "threshold_formatted": None if tau is None else "{:,}".format(int(tau)),
        "layer": arm["layer"], "alpha": alpha,
        "alpha_is_override_of": None if alpha_override is None else arm["alpha"],
        "direction": arm["direction"], "null_index": arm["null_index"],
        "null_seed": None if arm["null_index"] is None else NULL_SEEDS[arm["null_index"]],
        "dmu_norm": dmu, "delta_norm": float(np.linalg.norm(delta)),
        "vphat_sha256": VEC_SHA,
        "injection": "layer-output residual, decode positions only (prefill untouched)",
        "prompt_text": prompt_text, "templated_prompt": templated,
        "n": n, "base_seed": BASE_SEED, "seed_offset": arm["seed_offset"],
        "seed_lo": BASE_SEED + arm["seed_offset"], "seed_hi": BASE_SEED + arm["seed_offset"] + n - 1,
        "sampling": {"temperature": TEMPERATURE, "top_p": TOP_P,
                     "max_new_tokens": max_new, "batch": batch,
                     "seed_rule": "torch.manual_seed(BASE_SEED + %d + batch_start)"
                                  % arm["seed_offset"]},
        "n_prompt_tokens": n_prompt,
        "n_truncated": sum(r["truncated"] for r in rows),
        "n_degenerate": sum(r["degenerate"] for r in rows),
        "wall_secs": round(time.time() - t0, 1),
        "rows": rows,
    }
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    med = sorted(r["n_output_tokens"] for r in rows)[len(rows) // 2]
    print("[%s%s] cond=%s L%d alpha=%+.1f |delta|=%.3f n=%d trunc=%d degen=%d "
          "median_tokens=%d wall=%.1fs -> %s"
          % (key, tag, arm["condition"], arm["layer"], alpha, np.linalg.norm(delta),
             len(rows), meta["n_truncated"], meta["n_degenerate"], med, meta["wall_secs"],
             path), flush=True)
    return meta


# ---------------------------------------------------------------- laptop smoke (PR-005 / V-011)

def smoke():
    """Plumbing only, on CPU with a tiny model. Validates, in order:
      S1  the sha-checked v_p̂^B tensor loads and ‖Δμ‖ matches w5_layers.csv at L27/L30
      S2  the null directions are reproducible from the frozen seed list and unit-norm
      S3  the hook fires on exactly 1 prefill pass and on every decode step, never more
      S4  the delta actually added equals α·‖Δμ‖·u to float precision (captured pre/post)
      S5  α=0 (sham) is a bitwise no-op against the same generation with no hook at all
      S6  a non-zero α changes the generated token ids (the hook is not inert)
      S7  the coherence/degeneration rule fires on a hand-built degenerate string
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from replay_w4 import decoder_layers
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        ok &= bool(cond)
        print("%s %-4s %s %s" % ("ok  " if cond else "FAIL", name, "", extra))

    v = load_vphat()
    import csv as _csv
    want = {}
    with open(ROOT / "analysis" / "out" / "w5_layers.csv") as fh:
        for r in _csv.DictReader(fh):
            if r["form"] == "B":
                want[int(r["layer"])] = float(r["vphat_l2"])
    chk("S1", abs(np.linalg.norm(v[27]) - want[27]) < 1e-4
             and abs(np.linalg.norm(v[30]) - want[30]) < 1e-4,
        "||dmu|| L27=%.6f (csv %.6f)  L30=%.6f (csv %.6f)"
        % (np.linalg.norm(v[27]), want[27], np.linalg.norm(v[30]), want[30]))

    u0, dmu = direction_vector(ARMS["B_above_null00"], v)
    u0b, _ = direction_vector(ARMS["B_above_null00"], v)
    u9, _ = direction_vector(ARMS["B_above_null09"], v)
    chk("S2", np.array_equal(u0, u0b) and abs(np.linalg.norm(u0) - 1) < 1e-5
             and not np.array_equal(u0, u9) and abs(float(u0 @ (v[27] / dmu))) < 0.1,
        "null00 reproducible, unit-norm, cos(null00, u_vphat)=%.4f"
        % float(u0 @ (v[27] / dmu)))

    name = os.environ.get("W7_SMOKE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    tok = AutoTokenizer.from_pretrained(name)
    m = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float32)
    m.eval()
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    L = decoder_layers(m)
    d = m.config.hidden_size
    layer_i = min(2, len(L) - 1)
    print("smoke model=%s layers=%d d_model=%d" % (name, len(L), d))

    rng = np.random.default_rng(4242)
    u = rng.standard_normal(d).astype(np.float32)
    u /= np.linalg.norm(u)
    alpha, dmu_s = 2.0, 7.5
    delta = (alpha * dmu_s * u).astype(np.float32)

    enc = tok(["The quick brown fox"], return_tensors="pt")
    n_prompt = enc["input_ids"].shape[1]
    NEW = 12

    def gen(inj):
        h = None
        if inj is not None:
            inj.bind(torch.device("cpu"), torch.float32)
            inj.reset()
            h = L[layer_i].register_forward_hook(inj.make_hook())
        try:
            torch.manual_seed(1234)
            with torch.no_grad():
                return m.generate(input_ids=enc["input_ids"].repeat(2, 1),
                                  attention_mask=enc["attention_mask"].repeat(2, 1),
                                  do_sample=True, temperature=1.0, top_p=1.0,
                                  max_new_tokens=NEW, min_new_tokens=NEW,
                                  pad_token_id=tok.pad_token_id)
        finally:
            if h is not None:
                h.remove()

    inj = Injector(delta, torch)
    out_steer = gen(inj)
    chk("S3", inj.n_prefill == 1 and inj.n_decode == NEW - 1
             and inj.n_positions_touched == NEW - 1,
        "prefill=%d decode=%d positions=%d (want 1 / %d / %d)"
        % (inj.n_prefill, inj.n_decode, inj.n_positions_touched, NEW - 1, NEW - 1))

    # S4: capture the layer's raw output and the value the next module receives.
    pre, post = {}, {}
    hpre = L[layer_i].register_forward_hook(
        lambda _m, _a, o: pre.setdefault(len(pre), (o[0] if isinstance(o, tuple) else o).clone()))
    inj2 = Injector(delta, torch)
    inj2.bind(torch.device("cpu"), torch.float32)
    inj2.reset()
    hinj = L[layer_i].register_forward_hook(inj2.make_hook())
    hpost = L[layer_i].register_forward_hook(
        lambda _m, _a, o: post.setdefault(len(post), (o[0] if isinstance(o, tuple) else o).clone()))
    torch.manual_seed(1234)
    with torch.no_grad():
        m.generate(input_ids=enc["input_ids"].repeat(2, 1),
                   attention_mask=enc["attention_mask"].repeat(2, 1), do_sample=True,
                   temperature=1.0, top_p=1.0, max_new_tokens=NEW, min_new_tokens=NEW,
                   pad_token_id=tok.pad_token_id)
    for h in (hpre, hinj, hpost):
        h.remove()
    d0 = (post[0] - pre[0]).abs().max().item()                       # prefill: untouched
    diffs = [(post[k] - pre[k] - torch.tensor(delta)).abs().max().item()
             for k in range(1, len(pre))]
    chk("S4", d0 == 0.0 and max(diffs) < 1e-4,
        "prefill delta max=%.3g ; decode |added - alpha*dmu*u| max=%.3g over %d steps"
        % (d0, max(diffs), len(diffs)))

    out_none = gen(None)
    inj0 = Injector(np.zeros(d, dtype=np.float32), torch)
    out_sham = gen(inj0)
    chk("S5", torch.equal(out_none, out_sham),
        "sham (alpha=0, hook installed) is bitwise identical to no-hook")
    chk("S6", not torch.equal(out_none, out_steer),
        "alpha=+2 changes the generated ids (hook is not inert)")

    good = "the model estimated about 4 billion scales across every crocodile species alive"
    bad = ("a b c d " * 40)
    chk("S7", (not is_degenerate(good * 3)) and is_degenerate(bad)
             and ngram_ratio(bad, 4) < 0.35,
        "degenerate rule: clean=%s repeated=%s (ratio %.3f)"
        % (is_degenerate(good * 3), is_degenerate(bad), ngram_ratio(bad, 4)))

    print("\nSMOKE %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--arms", nargs="*", default=list(ARMS))
    ap.add_argument("--n", type=int, default=N_PER_ARM)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--max-new", type=int, default=MAX_NEW_TOKENS)
    ap.add_argument("--retry-arm", default=None,
                    help="PR-005 item 4c: re-run this arm ONCE at half |alpha|")
    ap.add_argument("--out-root", default=str(OUT_ROOT))
    ap.add_argument("--tiny", action="store_true",
                    help="end-to-end laptop rehearsal: Qwen2.5-0.5B on CPU, real run_arm path")
    args = ap.parse_args()

    if args.smoke:
        return smoke()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    vphat = load_vphat()
    t0 = time.time()
    if args.tiny:
        name = "Qwen/Qwen2.5-0.5B-Instruct"
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float32)
        # v_p̂^B is 5120-d; the rehearsal model is 896-d, so slice the direction to fit.
        # This is a PLUMBING rehearsal only and writes to a scratch out-root.
        vphat = vphat[:, :model.config.hidden_size].copy()
    else:
        name = MODEL
        tok = AutoTokenizer.from_pretrained(MODEL)
        model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16,
                                                     device_map="cuda", trust_remote_code=True)
    model.eval()
    from replay_w4 import decoder_layers
    print("model %s loaded in %.1fs | dtype %s | layers %d | d_model %d"
          % (name, time.time() - t0, next(model.parameters()).dtype,
             len(decoder_layers(model)), model.config.hidden_size), flush=True)

    out_root = Path(args.out_root)
    if args.retry_arm:
        arm = ARMS[args.retry_arm]
        run_arm(args.retry_arm, arm, model, tok, torch, vphat, out_root, args.n,
                args.batch, args.max_new, alpha_override=arm["alpha"] / 2.0, tag="_halved")
        return 0
    for key in args.arms:
        run_arm(key, ARMS[key], model, tok, torch, vphat, out_root, args.n,
                args.batch, args.max_new)
    print("\nall arms done in %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
