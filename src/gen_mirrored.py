"""W2 Step 3: mirrored (incentive) screening rollouts — 50 per condition, per model.

The two conditions are the mirror pair from the frozen submodule: in `below_good` the
GOOD cause is donated to when the estimate does NOT exceed tau; in `above_good` it is the
other way round. Everything else about the prompt is identical, so any systematic
difference in where the finals land is the landing gap G0 tests.

The prompt is imported, never copied (PR-001 item 2):
    upstream/src/value_leakage/sample.py :: build_prompt(condition, threshold)
tau is embedded by upstream's own formatter with thousands separators.

The reasoning/answer split rule is imported from `gen_neutral.split_output`, which is
frozen at F-014 — importing rather than re-implementing is what makes the W1 and W2
rollouts comparable.

Seeds follow PR-002 item 4: below_good rollout i -> 64 + 1000 + i,
above_good rollout i -> 64 + 2000 + i. The neutral block (64 + i) is untouched.

  python3 src/gen_mirrored.py --model Qwen/Qwen3-8B --tau 31250000
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

from value_leakage.sample import build_prompt          # noqa: E402
from gen_neutral import (FAMILIES, BASE_SEED, TEMPERATURE, TOP_P,   # noqa: E402
                         DEFAULT_MAX_TOKENS, split_output)

DEFAULT_N = 50                                     # PR-001 item 12
CONDITION_SEED_OFFSET = {"below_good": 1000, "above_good": 2000}   # PR-002 item 4
CONDITIONS = ("below_good", "above_good")


def run_condition(llm, tok, SamplingParams, model, mode, condition, tau, n,
                  max_tokens, out_dir, vllm_version):
    """Generate one condition, write its JSON, return the summary dict."""
    t0 = time.time()
    prompt_text = build_prompt(condition, tau)

    kw = {"tokenize": False, "add_generation_prompt": True}
    if mode == "think_tag" and "Qwen3" in model:
        kw["enable_thinking"] = True                 # W0b F-012
    prompt = tok.apply_chat_template([{"role": "user", "content": prompt_text}], **kw)

    off = CONDITION_SEED_OFFSET[condition]
    params = [SamplingParams(temperature=TEMPERATURE, top_p=TOP_P,
                             max_tokens=max_tokens, seed=BASE_SEED + off + i)
              for i in range(n)]
    t_gen = time.time()
    outs = llm.generate([prompt] * n, params)
    gen_secs = time.time() - t_gen

    rows, truncated = [], 0
    for i, o in enumerate(outs):
        out = o.outputs[0]
        reasoning, answer, how = split_output(out.text, mode)
        is_trunc = out.finish_reason == "length"
        truncated += int(is_trunc)
        rows.append({
            "i": i, "seed": BASE_SEED + off + i,
            "raw_output": out.text,
            "reasoning_text": reasoning,
            "visible_answer": answer,
            "split_method": how,
            "finish_reason": out.finish_reason,
            "truncated": is_trunc,
            "n_output_tokens": len(out.token_ids),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("%s.json" % condition)
    path.write_text(json.dumps({
        "model": model,
        "family_mode": mode,
        "condition": condition,
        "threshold": tau,
        "threshold_formatted": "{:,}".format(int(tau)),
        "vllm_version": vllm_version,
        "prompt_text": prompt_text,
        "templated_prompt": prompt,
        "n": n,
        "base_seed": BASE_SEED,
        "seed_offset": off,
        "sampling": {"temperature": TEMPERATURE, "top_p": TOP_P,
                     "max_tokens": max_tokens,
                     "seed_rule": "BASE_SEED + %d + i" % off},
        "n_prompt_tokens": len(tok.encode(prompt)),
        "wall_secs_total": round(time.time() - t0, 1),
        "wall_secs_generate": round(gen_secs, 1),
        "n_truncated": truncated,
        "rows": rows,
    }, indent=2, ensure_ascii=False))

    med = sorted(r["n_output_tokens"] for r in rows)[n // 2]
    print("[%s] file=%s n=%d truncated=%d (%.1f%%) gen=%.1fs total=%.1fs median_tokens=%d"
          % (condition, path, n, truncated, 100.0 * truncated / n, gen_secs,
             time.time() - t0, med), flush=True)
    return {"condition": condition, "path": str(path), "n": n,
            "n_truncated": truncated, "wall_secs_generate": round(gen_secs, 1),
            "median_output_tokens": med}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tau", type=int, required=True,
                    help="the model's tau of record from analysis/out/w1_tau.csv")
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--conditions", nargs="*", default=list(CONDITIONS))
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "w2_screen"))
    args = ap.parse_args()

    mode = FAMILIES.get(args.model)
    if mode is None:
        print("model not in PR-001's candidate list:", args.model)
        return 2

    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    import vllm

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(args.model)
    llm = LLM(model=args.model, dtype="bfloat16", gpu_memory_utilization=0.90,
              max_model_len=args.max_tokens, trust_remote_code=True, seed=BASE_SEED)

    slug = args.model.split("/")[-1]
    out_dir = Path(args.out_root) / slug
    summaries = []
    for condition in args.conditions:
        summaries.append(run_condition(llm, tok, SamplingParams, args.model, mode,
                                       condition, args.tau, args.n, args.max_tokens,
                                       out_dir, vllm.__version__))

    print("\nmodel      :", args.model)
    print("tau        :", "{:,}".format(args.tau))
    print("wall secs  : %.1f (engine init included)" % (time.time() - t0))
    for s in summaries:
        print(json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
