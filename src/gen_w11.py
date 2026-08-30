"""W11 Step 3: the four CLARIFIED arms (PR-007 items 1-2).

Identical machinery to gen_w3.py — same model, same family mode, same sampling constants,
same split_output, same per-arm write-as-it-finishes — with exactly one difference: the
prompt comes from prompts_w11.build_prompt_w11 (W3's prompt + one appended sentence) and
the seed block is new.

  python3 src/gen_w11.py --selftest                       # laptop, no GPU
  python3 src/gen_w11.py --n 200 --tau-a 15300000 --tau-b 4500000000
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

from gen_neutral import BASE_SEED, TEMPERATURE, TOP_P, DEFAULT_MAX_TOKENS, split_output  # noqa: E402
from prompts_w3 import build_prompt_w3  # noqa: E402
from prompts_w11 import build_prompt_w11  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
FAMILY_MODE = "no_think"                       # PR-001 item 3
TAU_A, TAU_B = 15300000, 4500000000            # carried over, PR-007 item 1

# PR-007 item 2. Seed block starts at 64 + 9750 = 9814, contiguous with and disjoint from
# W7b's 9214-9813 (which itself continues W7's 8064-9213). Arms are laid out consecutively
# so the block stays contiguous whatever n is.
SEED_OFFSET_0 = 9750
ARM_ORDER = ["A_below", "A_above", "B_below", "B_above"]
ARM_SPEC = {"A_below": ("A", "below_good"), "A_above": ("A", "above_good"),
            "B_below": ("B", "below_good"), "B_above": ("B", "above_good")}


def arm_offset(arm, n):
    return SEED_OFFSET_0 + n * ARM_ORDER.index(arm)


def run_arm(llm, tok, SamplingParams, arm, n, tau, out_root, max_tokens, vllm_version):
    form, condition = ARM_SPEC[arm]
    off = arm_offset(arm, n)
    t0 = time.time()
    prompt_text = build_prompt_w11(form, condition, tau)
    prompt = tok.apply_chat_template([{"role": "user", "content": prompt_text}],
                                     tokenize=False, add_generation_prompt=True)
    params = [SamplingParams(temperature=TEMPERATURE, top_p=TOP_P, max_tokens=max_tokens,
                             seed=BASE_SEED + off + i) for i in range(n)]
    t_gen = time.time()
    outs = llm.generate([prompt] * n, params)
    gen_secs = time.time() - t_gen

    rows, truncated = [], 0
    for i, o in enumerate(outs):
        out = o.outputs[0]
        reasoning, answer, how = split_output(out.text, FAMILY_MODE)
        is_trunc = out.finish_reason == "length"
        truncated += int(is_trunc)
        rows.append({"i": i, "seed": BASE_SEED + off + i, "raw_output": out.text,
                     "reasoning_text": reasoning, "visible_answer": answer,
                     "split_method": how, "finish_reason": out.finish_reason,
                     "truncated": is_trunc, "n_output_tokens": len(out.token_ids)})

    out_dir = Path(out_root) / ("form_%s" % form)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("%s.json" % condition)
    path.write_text(json.dumps({
        "model": MODEL, "family_mode": FAMILY_MODE, "form": form, "arm": arm,
        "condition": condition, "threshold": tau, "packet": "W11", "clarified": True,
        "threshold_formatted": "{:,}".format(int(tau)),
        "vllm_version": vllm_version, "prompt_text": prompt_text,
        "w3_prompt_text": build_prompt_w3(form, condition, tau),
        "templated_prompt": prompt, "n": n, "base_seed": BASE_SEED, "seed_offset": off,
        "sampling": {"temperature": TEMPERATURE, "top_p": TOP_P, "max_tokens": max_tokens,
                     "seed_rule": "BASE_SEED + %d + i" % off},
        "n_prompt_tokens": len(tok.encode(prompt)),
        "wall_secs_total": round(time.time() - t0, 1),
        "wall_secs_generate": round(gen_secs, 1),
        "n_truncated": truncated, "rows": rows,
    }, indent=2, ensure_ascii=False))

    med = sorted(r["n_output_tokens"] for r in rows)[n // 2]
    print("[%s] form=%s cond=%s n=%d seeds=%d-%d truncated=%d (%.1f%%) gen=%.1fs "
          "median_tokens=%d file=%s"
          % (arm, form, condition, n, BASE_SEED + off, BASE_SEED + off + n - 1,
             truncated, 100.0 * truncated / n, gen_secs, med, path), flush=True)
    return {"arm": arm, "form": form, "condition": condition, "n": n,
            "seed_lo": BASE_SEED + off, "seed_hi": BASE_SEED + off + n - 1,
            "n_truncated": truncated, "median_output_tokens": med,
            "wall_secs_generate": round(gen_secs, 1), "path": str(path)}


def selftest(n):
    """Laptop smoke: prompts, seed disjointness, arm table. No GPU, no API."""
    ok = True

    def chk(good, msg):
        nonlocal ok
        ok &= bool(good)
        print("%s %s" % ("ok  " if good else "FAIL", msg))

    import prompts_w11 as p11
    chk(p11.selftest() == 0, "A1 prompts_w11 selftest passes (16/16)")
    seeds = []
    for arm in ARM_ORDER:
        form, cond = ARM_SPEC[arm]
        off = arm_offset(arm, n)
        seeds.extend(range(BASE_SEED + off, BASE_SEED + off + n))
    chk(len(seeds) == len(set(seeds)) == 4 * n, "A2 %d seeds, all distinct" % (4 * n))
    chk(min(seeds) == 9814 and max(seeds) == 9814 + 4 * n - 1,
        "A3 seed block %d-%d, contiguous" % (min(seeds), max(seeds)))
    chk(min(seeds) > 9813, "A4 disjoint from W7b's 9214-9813 and every earlier block")
    for arm in ARM_ORDER:
        form, cond = ARM_SPEC[arm]
        tau = TAU_A if form == "A" else TAU_B
        w11 = build_prompt_w11(form, cond, tau)
        w3 = build_prompt_w3(form, cond, tau)
        chk(w11.startswith(w3[:w3.index("The threshold is")]) and len(w11) > len(w3),
            "A5 %s prompt is W3's with a suffix inside the bet note" % arm)
        chk(w11.count("To be clear:") == 1, "A6 %s exactly one clarification sentence" % arm)
    ab = build_prompt_w11("A", "above_good", TAU_A)
    be = build_prompt_w11("A", "below_good", TAU_A)
    chk(len(ab) == len(be), "A7 the two conditions' prompts are the same length (symmetric)")
    chk(TAU_A == 15300000 and TAU_B == 4500000000, "A8 tau_A/tau_B carried over from W3")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--tau-a", type=int, default=TAU_A)
    ap.add_argument("--tau-b", type=int, default=TAU_B)
    ap.add_argument("--arms", nargs="*", default=ARM_ORDER, choices=ARM_ORDER)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "w11_clarified"))
    args = ap.parse_args()
    if args.selftest:
        return selftest(args.n)

    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    import vllm

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL)
    llm = LLM(model=MODEL, dtype="bfloat16", gpu_memory_utilization=0.90,
              max_model_len=args.max_tokens, trust_remote_code=True, seed=BASE_SEED)

    summaries = []
    for arm in args.arms:
        form, _ = ARM_SPEC[arm]
        tau = args.tau_a if form == "A" else args.tau_b
        summaries.append(run_arm(llm, tok, SamplingParams, arm, args.n, tau, args.out_root,
                                 args.max_tokens, vllm.__version__))
    print("\nmodel     :", MODEL)
    print("wall secs : %.1f (engine init included)" % (time.time() - t0))
    for s in summaries:
        print(json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
