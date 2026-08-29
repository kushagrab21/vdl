"""W1 Step 4: 50 neutral (baseline, no-bet) rollouts per candidate model.

Neutral only. No incentive condition is generated in this packet, so PR-001 can be
calibrated on these traces without reading any data it governs.

The prompt is upstream's BASELINE, imported from the frozen submodule rather than
copied, so it cannot drift:
    upstream/src/value_leakage/sample.py :: build_prompt("baseline", None)

  python src/gen_neutral.py --model Qwen/Qwen3-8B
  python src/gen_neutral.py --model Qwen/Qwen3-8B --n 50 --max-tokens 32768
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "upstream" / "src"))

from value_leakage.sample import build_prompt  # noqa: E402  (path set above)

# PR-001 item 3: how reasoning text and visible answer are separated, per family.
#   "think_tag"  — the model emits <think>…</think>, then the visible answer.
#   "no_think"   — no reasoning segment; the whole visible output is the reasoning text
#                  AND the answer is extracted from that same text.
FAMILIES = {
    "Qwen/Qwen3-8B":                              "think_tag",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B":    "think_tag",
    "deepseek-ai/DeepSeek-R1-Distill-Llama-8B":   "think_tag",
    "Qwen/Qwen2.5-14B-Instruct":                  "no_think",
    "google/gemma-2-9b-it":                       "no_think",
}

BASE_SEED = 64          # PR-001 item 4
DEFAULT_N = 50
DEFAULT_MAX_TOKENS = 32768   # PR-001 item 5
TEMPERATURE = 1.0       # PR-001 item 4 — upstream-effective, see PR-001 note
TOP_P = 1.0


def split_output(text, mode):
    """Return (reasoning_text, visible_answer, split_method) per PR-001 item 3."""
    if mode == "think_tag":
        if "</think>" in text:
            head, answer = text.split("</think>", 1)
            return head.replace("<think>", "").strip(), answer.strip(), "</think>"
        # Opened but never closed => the rollout is a truncation; keep the text so the
        # truncation can be inspected, but there is no visible answer.
        if "<think>" in text:
            return text.replace("<think>", "").strip(), "", "unclosed <think>"
        # Some R1-distill templates pre-open the block, so the tag never appears in the
        # generated text; treat the whole thing as reasoning with no separable answer.
        return text.strip(), "", "no think tag emitted"
    return text.strip(), text.strip(), "no_think family (reasoning == answer)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "w1_neutral"))
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
    prompt_text = build_prompt("baseline", None)

    kw = {"tokenize": False, "add_generation_prompt": True}
    if mode == "think_tag" and "Qwen3" in args.model:
        kw["enable_thinking"] = True     # verified in W0b F-012
    prompt = tok.apply_chat_template([{"role": "user", "content": prompt_text}], **kw)

    llm = LLM(model=args.model, dtype="bfloat16", gpu_memory_utilization=0.90,
              max_model_len=args.max_tokens, trust_remote_code=True, seed=BASE_SEED)

    # PR-001 item 4: rollout i uses seed BASE_SEED + i. vLLM takes a per-request seed on
    # SamplingParams, so each rollout carries its own and the set is reproducible even if
    # the batch is re-ordered.
    params = [SamplingParams(temperature=TEMPERATURE, top_p=TOP_P,
                             max_tokens=args.max_tokens, seed=BASE_SEED + i)
              for i in range(args.n)]
    t_gen = time.time()
    outs = llm.generate([prompt] * args.n, params)
    gen_secs = time.time() - t_gen

    rows, truncated = [], 0
    for i, o in enumerate(outs):
        out = o.outputs[0]
        reasoning, answer, how = split_output(out.text, mode)
        is_trunc = out.finish_reason == "length"
        truncated += int(is_trunc)
        rows.append({
            "i": i, "seed": BASE_SEED + i,
            "raw_output": out.text,
            "reasoning_text": reasoning,
            "visible_answer": answer,
            "split_method": how,
            "finish_reason": out.finish_reason,
            "truncated": is_trunc,
            "n_output_tokens": len(out.token_ids),
        })

    slug = args.model.split("/")[-1]
    out_dir = Path(args.out_root) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "neutral.json"
    path.write_text(json.dumps({
        "model": args.model,
        "family_mode": mode,
        "condition": "baseline",
        "vllm_version": vllm.__version__,
        "prompt_text": prompt_text,
        "templated_prompt": prompt,
        "n": args.n,
        "base_seed": BASE_SEED,
        "sampling": {"temperature": TEMPERATURE, "top_p": TOP_P,
                     "max_tokens": args.max_tokens, "seed_rule": "BASE_SEED + i"},
        "n_prompt_tokens": len(tok.encode(prompt)),
        "wall_secs_total": round(time.time() - t0, 1),
        "wall_secs_generate": round(gen_secs, 1),
        "n_truncated": truncated,
        "rows": rows,
    }, indent=2, ensure_ascii=False))

    print("model          :", args.model)
    print("file           :", path)
    print("n              :", args.n)
    print("truncated      :", truncated, "(%.1f%%)" % (100.0 * truncated / args.n))
    print("wall secs      : total %.1f | generate %.1f" % (time.time() - t0, gen_secs))
    print("median tokens  :", sorted(r["n_output_tokens"] for r in rows)[args.n // 2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
