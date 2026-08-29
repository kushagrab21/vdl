"""Smoke B (W0b Step 5): hooks stack, Qwen3-8B, residual stream capture.

De-risks the second way this project dies: a broken hooks stack. W4-W9 need to read
the residual stream at a chosen layer and, later, to write to it during generation.

Stack: plain HF transformers forward hooks (not nnsight). Rationale: one less
abstraction between the ledger and the tensor; transformers is already pulled in by
vLLM so the two stacks cannot drift apart on a version; and the W7-W9 requirement is
a hook that persists across decode steps, which is the native behaviour of a
`register_forward_hook` on a decoder layer.

The tokenizer round-trip is load-bearing for W4: the estimates this project measures
are comma-grouped integers, so if decode(encode(s)) != s for "estimate: 1,234,567"
then position-indexing into a trace is unsafe.

Run on the pod:  python src/smoke_hooks.py
"""

import json
import os
import sys
from pathlib import Path

MODEL = os.environ.get("SMOKE_MODEL", "Qwen/Qwen3-8B")
OUT = Path(__file__).resolve().parent.parent / "runs" / "smoke"
ROUNDTRIP = "estimate: 1,234,567"

PROMPT = ("I need you to estimate a specific quantity. Give me your single most accurate "
          "estimate as a number, not a range. Question: how many black spots are there in "
          "total on all giraffes currently alive in the world today?")


def main():
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)

    # --- tokenizer round-trip, before anything expensive ---
    ids = tok.encode(ROUNDTRIP, add_special_tokens=False)
    back = tok.decode(ids)
    rt_exact = (back == ROUNDTRIP)

    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16, device_map="cuda", trust_remote_code=True)
    model.eval()

    layers = model.model.layers
    n_layers = len(layers)
    mid = n_layers // 2
    hook_point = f"model.model.layers[{mid}]  (decoder layer output = residual stream)"

    captured = {}

    def hook(_module, _args, output):
        # A decoder layer returns either a tensor or a tuple whose [0] is the
        # hidden state; take [0] when it is a tuple.
        hs = output[0] if isinstance(output, tuple) else output
        captured["resid"] = hs.detach()

    handle = layers[mid].register_forward_hook(hook)
    enc = tok(PROMPT, return_tensors="pt").to(model.device)
    with torch.no_grad():
        model(**enc)
    handle.remove()

    resid = captured["resid"]                 # [batch, seq_len, d_model]
    per_token = resid[0]                      # [seq_len, d_model]
    seq_len = enc["input_ids"].shape[1]
    d_model = model.config.hidden_size
    shape_ok = tuple(per_token.shape) == (seq_len, d_model)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "smoke_hooks_qwen3-8b.json"
    path.write_text(json.dumps({
        "model": MODEL,
        "stack": "transformers forward hooks",
        "transformers_version": transformers.__version__,
        "torch_version": torch.__version__,
        "dtype": str(resid.dtype),
        "n_layers": n_layers,
        "hook_layer_index": mid,
        "hook_point": hook_point,
        "captured_shape_with_batch": list(resid.shape),
        "captured_shape_per_token": list(per_token.shape),
        "seq_len_from_tokenizer": seq_len,
        "d_model_from_config": d_model,
        "shape_acceptance": shape_ok,
        "prompt": PROMPT,
        "roundtrip_input": ROUNDTRIP,
        "roundtrip_output": back,
        "roundtrip_exact": rt_exact,
        "roundtrip_token_ids": ids,
        "roundtrip_tokens": [tok.convert_ids_to_tokens(i) for i in ids],
    }, indent=2, ensure_ascii=False))

    print("file                  :", path)
    print("transformers          :", transformers.__version__, "| torch", torch.__version__)
    print("n_layers              :", n_layers, "| hook layer:", mid)
    print("hook point            :", hook_point)
    print("captured shape        :", tuple(resid.shape), "-> per-token", tuple(per_token.shape))
    print("seq_len (tokenizer)   :", seq_len)
    print("d_model (config)      :", d_model)
    print("dtype                 :", resid.dtype)
    print("SHAPE ACCEPTANCE      :", "PASS" if shape_ok else "FAIL")
    print("--- tokenizer round-trip ---")
    print("input  :", repr(ROUNDTRIP))
    print("output :", repr(back))
    print("exact  :", rt_exact)
    if not rt_exact:
        import difflib
        print("DIFF:")
        for line in difflib.ndiff([ROUNDTRIP], [back]):
            print("  " + line)
    print("tokens :", [tok.convert_ids_to_tokens(i) for i in ids])
    return 0 if (shape_ok and rt_exact) else 1


if __name__ == "__main__":
    sys.exit(main())
