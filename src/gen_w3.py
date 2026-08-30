"""W3 Step 4: the frozen behavioural dataset for Qwen2.5-14B-Instruct.

PR-003 item 3's arms, one vLLM engine for the whole packet. Each arm is written and
reported as it finishes so it can be rsync'd without waiting for the rest.

Form A is upstream's giraffe task verbatim; form B is the crocodile reskin built from
upstream's own template strings (src/prompts_w3.py). The reasoning/answer split is
gen_neutral.split_output, frozen at F-014 — imported, never re-implemented, so W1/W2/W3
rollouts stay comparable.

  python3 src/gen_w3.py --tau-a 15300000                     # all arms except B-incentive
  python3 src/gen_w3.py --tau-a 15300000 --tau-b <tau_B> --arms B_below B_above
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

MODEL = "Qwen/Qwen2.5-14B-Instruct"
FAMILY_MODE = "no_think"                      # PR-001 item 3
N_NEUTRAL, N_INCENTIVE = 50, 150              # PR-003 item 3

# (arm key) -> (form, condition, n, seed offset). Seeds are BASE_SEED + offset + i,
# continuing PR-001 item 4 / PR-002 item 4. Blocks are 1000 apart and none collides with
# W1 (64-113) or W2 (1064-2113).
ARMS = {
    "A_below":   ("A", "below_good", N_INCENTIVE, 3000),
    "A_above":   ("A", "above_good", N_INCENTIVE, 4000),
    "B_neutral": ("B", "baseline",   N_NEUTRAL,   5000),
    "B_below":   ("B", "below_good", N_INCENTIVE, 6000),
    "B_above":   ("B", "above_good", N_INCENTIVE, 7000),
}
DEFAULT_ARMS = ["A_below", "A_above", "B_neutral"]


def run_arm(llm, tok, SamplingParams, arm, tau, out_root, max_tokens, vllm_version):
    form, condition, n, off = ARMS[arm]
    t0 = time.time()
    prompt_text = build_prompt_w3(form, condition, tau)
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
        "condition": condition, "threshold": tau,
        "threshold_formatted": None if tau is None else "{:,}".format(int(tau)),
        "vllm_version": vllm_version, "prompt_text": prompt_text,
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau-a", type=int, default=15300000)
    ap.add_argument("--tau-b", type=int, default=None)
    ap.add_argument("--arms", nargs="*", default=DEFAULT_ARMS, choices=list(ARMS))
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "w3_frozen"))
    args = ap.parse_args()

    for arm in args.arms:
        form, condition, _, _ = ARMS[arm]
        if condition != "baseline" and form == "B" and args.tau_b is None:
            print("arm %s needs --tau-b (PR-003 item 2: tau_B is measured first)" % arm)
            return 2

    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    import vllm

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL)
    llm = LLM(model=MODEL, dtype="bfloat16", gpu_memory_utilization=0.90,
              max_model_len=args.max_tokens, trust_remote_code=True, seed=BASE_SEED)

    summaries = []
    for arm in args.arms:
        form, condition, _, _ = ARMS[arm]
        tau = None if condition == "baseline" else (args.tau_a if form == "A" else args.tau_b)
        summaries.append(run_arm(llm, tok, SamplingParams, arm, tau, args.out_root,
                                 args.max_tokens, vllm.__version__))

    print("\nmodel     :", MODEL)
    print("wall secs : %.1f (engine init included)" % (time.time() - t0))
    for s in summaries:
        print(json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
