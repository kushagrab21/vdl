"""W14 Step 4: the two DEGRADED form-B arms (PR-010 items 1-2).

Identical machinery to gen_w3.py / gen_w11.py — same model, same family mode, same
sampling constants, same split_output, same per-arm write-as-it-finishes — with exactly
two differences: the prompt comes from prompts_w14.build_prompt_w14 (W3 form B with the
two mapping sentences replaced by their nested-negation paraphrase) and the seed block is
new and disjoint.

  python3 src/gen_w14.py --selftest --n 150      # laptop, no GPU
  python3 src/gen_w14.py --n 150 --tau-b 4500000000
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
from prompts_w14 import build_prompt_w14, ORIGINAL, DEGRADED  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
FAMILY_MODE = "no_think"                       # PR-001 item 3
TAU_B = 4500000000                             # PR-010 item 2: unchanged

# PR-010 item 2. New seed block: 64 + 10350 = 10414, contiguous with and disjoint from
# W11's 9814-10413 (which continues W7b's 9214-9813 and W7's 8064-9213).
SEED_OFFSET_0 = 10350
ARM_ORDER = ["B_below", "B_above"]
ARM_SPEC = {"B_below": ("B", "below_good"), "B_above": ("B", "above_good")}


def arm_offset(arm, n):
    return SEED_OFFSET_0 + n * ARM_ORDER.index(arm)


def run_arm(llm, tok, SamplingParams, arm, n, tau, out_root, max_tokens, vllm_version):
    form, condition = ARM_SPEC[arm]
    off = arm_offset(arm, n)
    t0 = time.time()
    prompt_text = build_prompt_w14(condition, tau)
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
        "condition": condition, "threshold": tau, "packet": "W14", "degraded": True,
        "threshold_formatted": "{:,}".format(int(tau)),
        "vllm_version": vllm_version, "prompt_text": prompt_text,
        "w3_prompt_text": build_prompt_w3(form, condition, tau),
        "w11_prompt_text": build_prompt_w11(form, condition, tau),
        "replaced_substring": ORIGINAL[condition], "replacement": DEGRADED[condition],
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

    import prompts_w14 as p14
    chk(p14.selftest() == 0, "C1 prompts_w14 selftest passes (17/17, truth table included)")
    seeds = []
    for arm in ARM_ORDER:
        off = arm_offset(arm, n)
        seeds.extend(range(BASE_SEED + off, BASE_SEED + off + n))
    chk(len(seeds) == len(set(seeds)) == 2 * n, "C2 %d seeds, all distinct" % (2 * n))
    chk(min(seeds) == 10414 and max(seeds) == 10414 + 2 * n - 1,
        "C3 seed block %d-%d, contiguous" % (min(seeds), max(seeds)))
    chk(min(seeds) > 10413, "C4 disjoint from W11's 9814-10413 and every earlier block")
    for arm in ARM_ORDER:
        form, cond = ARM_SPEC[arm]
        w14 = build_prompt_w14(cond, TAU_B)
        w3 = build_prompt_w3(form, cond, TAU_B)
        chk(w14 == w3.replace(ORIGINAL[cond], DEGRADED[cond]),
            "C5 %s prompt is W3's with exactly the frozen substring swapped" % arm)
        chk(w14.count("Unless your estimate fails to exceed") == 1,
            "C6 %s exactly one degraded mapping sentence" % arm)
        chk("To be clear:" not in w14, "C7 %s carries none of W11's clarification" % arm)
    ab, be = build_prompt_w14("above_good", TAU_B), build_prompt_w14("below_good", TAU_B)
    chk(len(ab) == len(be), "C8 the two arms' prompts are the same length (symmetric)")
    chk(TAU_B == 4500000000, "C9 tau_B carried over from W3/W11")
    chk(ARM_ORDER == ["B_below", "B_above"] and len(ARM_SPEC) == 2,
        "C10 form B only, two arms (PR-010 item 1)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--tau-b", type=int, default=TAU_B)
    ap.add_argument("--arms", nargs="*", default=ARM_ORDER, choices=ARM_ORDER)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "w14_degraded"))
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
        summaries.append(run_arm(llm, tok, SamplingParams, arm, args.n, args.tau_b,
                                 args.out_root, args.max_tokens, vllm.__version__))
    print("\nmodel     :", MODEL)
    print("wall secs : %.1f (engine init included)" % (time.time() - t0))
    for s in summaries:
        print(json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
