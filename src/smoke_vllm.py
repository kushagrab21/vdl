"""Smoke A (W0b Step 5): vLLM generation stack, Qwen3-8B, thinking mode.

De-risks the first of the two ways this project dies: a broken bulk-generation stack.
W1-W3 depend on (a) vLLM loading an arbitrary HF model and (b) the thinking segment
being separable from the visible answer, because the trajectory judge reads the trace
and the estimate judge reads the answer.

Deliberately NOT the giraffe prompt: a Fermi warm-up that cannot contaminate the real
experiment's data.

Run on the pod:  python src/smoke_vllm.py
"""

import json
import os
import sys
from pathlib import Path

MODEL = os.environ.get("SMOKE_MODEL", "Qwen/Qwen3-8B")
# The W0b order suggested ~1500. At 1500 Qwen3-8B was still inside its <think> block
# when it hit the cap (finish_reason=length, no closing tag), so the acceptance check
# could not be evaluated. 8000 lets a Fermi trace close. Upstream's API runs used
# 64000; W1-W3 must budget accordingly.
MAX_TOKENS = int(os.environ.get("SMOKE_MAX_TOKENS", "8000"))
OUT = Path(__file__).resolve().parent.parent / "runs" / "smoke"
QUESTION = ("How many piano tuners are there in Chicago? Give a single number as your "
            "final answer, with brief justification.")


def main():
    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    import vllm

    tok = AutoTokenizer.from_pretrained(MODEL)

    # Qwen3 gates its reasoning trace through the chat template's `enable_thinking`
    # flag. True (the Qwen3 default) leaves the model free to open a <think> block;
    # False makes the template prefill an empty one. W1 depends on this switch.
    prompt = tok.apply_chat_template(
        [{"role": "user", "content": QUESTION}],
        tokenize=False, add_generation_prompt=True, enable_thinking=True)

    llm = LLM(model=MODEL, dtype="bfloat16", gpu_memory_utilization=0.90,
              max_model_len=16384, trust_remote_code=True)
    params = SamplingParams(temperature=0.7, top_p=0.8, top_k=20, max_tokens=MAX_TOKENS)

    out = llm.generate([prompt], params)[0].outputs[0]
    text = out.text

    # The model emits <think>…</think> then the visible answer.
    if "</think>" in text:
        head, answer = text.split("</think>", 1)
        thinking = head.replace("<think>", "").strip()
        split_method = "</think> delimiter in generated text"
    else:
        thinking, answer, split_method = "", text, "NO </think> FOUND"

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "smoke_vllm_qwen3-8b.json"
    path.write_text(json.dumps({
        "model": MODEL,
        "vllm_version": vllm.__version__,
        "question": QUESTION,
        "templated_prompt": prompt,
        "enable_thinking": True,
        "sampling": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "max_tokens": MAX_TOKENS},
        "raw_output": text,
        "thinking": thinking,
        "answer": answer.strip(),
        "split_method": split_method,
        "finish_reason": out.finish_reason,
        "n_prompt_tokens": len(tok.encode(prompt)),
        "n_output_tokens": len(out.token_ids),
    }, indent=2, ensure_ascii=False))

    ok = bool(thinking.strip()) and thinking.strip() != answer.strip()
    print("file                  :", path)
    print("vllm version          :", vllm.__version__)
    print("thinking chars        :", len(thinking))
    print("answer chars          :", len(answer.strip()))
    print("split method          :", split_method)
    print("finish_reason         :", out.finish_reason)
    print("ACCEPTANCE (non-empty thinking, distinct from answer):", "PASS" if ok else "FAIL")
    print("--- first 10 lines of thinking segment ---")
    for line in thinking.splitlines()[:10]:
        print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
