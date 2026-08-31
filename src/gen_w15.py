"""W15 Step 3: the pair harvest — ~1,000 fresh form-B above_good rollouts (PR-011 item 1).

Identical machinery to gen_w3.py / gen_w11.py / gen_w14.py — same model, same family mode,
same PR-001 sampling constants, same split_output — with exactly two differences: only the
form-B `above_good` arm is generated, and the seed block is new and disjoint.

The wording is W3's NATURAL wording, unmodified: build_prompt_w3("B","above_good",tau).
Neither W11's clarification nor W14's degradation is present, which is what makes the
direction judge a valid instrument here (V-025).

  python3 src/gen_w15.py --selftest --n 1000     # laptop, no GPU
  python3 src/gen_w15.py --n 1000
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
from prompts_w14 import build_prompt_w14  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
FAMILY_MODE = "no_think"
TAU_B = 4500000000
FORM = "B"
CONDITION = "above_good"
SEED_OFFSET_0 = 10650          # PR-011 item 1: seeds 10714.. , after W14's 10414-10713


def run(llm, tok, SamplingParams, n, tau, out_root, max_tokens, vllm_version, chunk):
    off = SEED_OFFSET_0
    t0 = time.time()
    prompt_text = build_prompt_w3(FORM, CONDITION, tau)
    prompt = tok.apply_chat_template([{"role": "user", "content": prompt_text}],
                                     tokenize=False, add_generation_prompt=True)
    rows, truncated, gen_secs = [], 0, 0.0
    for lo in range(0, n, chunk):
        hi = min(lo + chunk, n)
        params = [SamplingParams(temperature=TEMPERATURE, top_p=TOP_P, max_tokens=max_tokens,
                                 seed=BASE_SEED + off + i) for i in range(lo, hi)]
        t = time.time()
        outs = llm.generate([prompt] * (hi - lo), params)
        gen_secs += time.time() - t
        for k, o in enumerate(outs):
            i = lo + k
            out = o.outputs[0]
            reasoning, answer, how = split_output(out.text, FAMILY_MODE)
            is_trunc = out.finish_reason == "length"
            truncated += int(is_trunc)
            rows.append({"i": i, "seed": BASE_SEED + off + i, "raw_output": out.text,
                         "reasoning_text": reasoning, "visible_answer": answer,
                         "split_method": how, "finish_reason": out.finish_reason,
                         "truncated": is_trunc, "n_output_tokens": len(out.token_ids)})
        print("  chunk %d-%d done (%.1fs cumulative gen)" % (lo, hi - 1, gen_secs), flush=True)

    out_dir = Path(out_root) / ("form_%s" % FORM)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("%s.json" % CONDITION)
    path.write_text(json.dumps({
        "model": MODEL, "family_mode": FAMILY_MODE, "form": FORM, "arm": "B_above_harvest",
        "condition": CONDITION, "threshold": tau, "packet": "W15",
        "pre_registration": "PR-011", "wording": "natural (W3 form B, unmodified)",
        "threshold_formatted": "{:,}".format(int(tau)),
        "vllm_version": vllm_version, "prompt_text": prompt_text,
        "w11_prompt_text": build_prompt_w11(FORM, CONDITION, tau),
        "w14_prompt_text": build_prompt_w14(CONDITION, tau),
        "templated_prompt": prompt, "n": n, "base_seed": BASE_SEED, "seed_offset": off,
        "sampling": {"temperature": TEMPERATURE, "top_p": TOP_P, "max_tokens": max_tokens,
                     "seed_rule": "BASE_SEED + %d + i" % off},
        "n_prompt_tokens": len(tok.encode(prompt)),
        "wall_secs_total": round(time.time() - t0, 1),
        "wall_secs_generate": round(gen_secs, 1),
        "n_truncated": truncated, "rows": rows,
    }, indent=2, ensure_ascii=False))
    med = sorted(r["n_output_tokens"] for r in rows)[n // 2]
    print("[harvest] form=B cond=%s n=%d seeds=%d-%d truncated=%d (%.1f%%) gen=%.1fs "
          "median_tokens=%d file=%s"
          % (CONDITION, n, BASE_SEED + off, BASE_SEED + off + n - 1, truncated,
             100.0 * truncated / n, gen_secs, med, path), flush=True)
    return path


def run_hf(n, tau, out_root, out_dir_max_new, batch):
    """D-054 fallback: the same rollouts through HF `generate` instead of vLLM.

    The pod's driver (570.172.08 / CUDA 12.8) is older than the CUDA 13 runtime the frozen
    vLLM 0.28.0 stack is built against, so vLLM's engine cannot init on this machine. The
    container's own torch 2.8.0+cu128 matches the driver, so the harvest is generated with
    HF `generate` -- the SAME path W7/W7b/W12 used and the same path W15's transplant must
    use anyway. PR-001's sampling constants are unchanged; only the seeding granularity is
    (torch.manual_seed per batch, W7's rule), which is declared as a deviation.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16,
                                                 device_map="cuda", trust_remote_code=True)
    model.eval()
    print("model loaded in %.1fs" % (time.time() - t0), flush=True)
    prompt_text = build_prompt_w3(FORM, CONDITION, tau)
    templated = tok.apply_chat_template([{"role": "user", "content": prompt_text}],
                                        tokenize=False, add_generation_prompt=True)
    enc = tok([templated], return_tensors="pt", add_special_tokens=False)
    n_prompt = int(enc["input_ids"].shape[1])
    eos_ids = set()
    gc = getattr(model, "generation_config", None)
    e = getattr(gc, "eos_token_id", None) if gc is not None else None
    for x in (e if isinstance(e, (list, tuple)) else [e]) + [tok.eos_token_id]:
        if x is not None:
            eos_ids.add(int(x))
    off = SEED_OFFSET_0
    rows, truncated, gen_secs = [], 0, 0.0
    for b0 in range(0, n, batch):
        bs = min(batch, n - b0)
        block_seed = BASE_SEED + off + b0
        torch.manual_seed(block_seed)
        ids = enc["input_ids"].repeat(bs, 1).to(model.device)
        am = enc["attention_mask"].repeat(bs, 1).to(model.device)
        t = time.time()
        with torch.no_grad():
            out = model.generate(input_ids=ids, attention_mask=am, do_sample=True,
                                 temperature=TEMPERATURE, top_p=TOP_P,
                                 max_new_tokens=out_dir_max_new,
                                 pad_token_id=tok.pad_token_id or tok.eos_token_id)
        gen_secs += time.time() - t
        gen = out[:, n_prompt:]
        for r in range(bs):
            toks = gen[r].tolist()
            hit = [k for k, x in enumerate(toks) if x in eos_ids]
            ntok, finish = (hit[0] + 1, "stop") if hit else (len(toks), "length")
            text = tok.decode(toks[:ntok], skip_special_tokens=True)
            reasoning, answer, how = split_output(text, FAMILY_MODE)
            truncated += int(finish == "length")
            rows.append({"i": b0 + r, "seed": BASE_SEED + off + b0 + r,
                         "seed_block": block_seed, "row_in_batch": r,
                         "raw_output": text, "reasoning_text": reasoning,
                         "visible_answer": answer, "split_method": how,
                         "finish_reason": finish, "truncated": finish == "length",
                         "n_output_tokens": ntok})
        print("  batch %d-%d done (%.0fs cumulative gen)" % (b0, b0 + bs - 1, gen_secs),
              flush=True)
    out_dir = Path(out_root) / ("form_%s" % FORM)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("%s.json" % CONDITION)
    path.write_text(json.dumps({
        "model": MODEL, "family_mode": FAMILY_MODE, "form": FORM, "arm": "B_above_harvest",
        "condition": CONDITION, "threshold": tau, "packet": "W15",
        "pre_registration": "PR-011", "wording": "natural (W3 form B, unmodified)",
        "backend": "hf_generate (D-054 fallback; vLLM unusable on this pod's driver)",
        "threshold_formatted": "{:,}".format(int(tau)),
        "prompt_text": prompt_text,
        "w11_prompt_text": build_prompt_w11(FORM, CONDITION, tau),
        "w14_prompt_text": build_prompt_w14(CONDITION, tau),
        "templated_prompt": templated, "n": n, "base_seed": BASE_SEED, "seed_offset": off,
        "sampling": {"temperature": TEMPERATURE, "top_p": TOP_P,
                     "max_new_tokens": out_dir_max_new, "batch": batch,
                     "seed_rule": "torch.manual_seed(BASE_SEED + %d + batch_start)" % off},
        "n_prompt_tokens": n_prompt,
        "wall_secs_total": round(time.time() - t0, 1),
        "wall_secs_generate": round(gen_secs, 1),
        "n_truncated": truncated, "rows": rows,
    }, indent=2, ensure_ascii=False))
    med = sorted(r["n_output_tokens"] for r in rows)[n // 2]
    print("[harvest-hf] n=%d seeds=%d-%d truncated=%d gen=%.0fs median_tokens=%d file=%s"
          % (n, BASE_SEED + off, BASE_SEED + off + n - 1, truncated, gen_secs, med, path),
          flush=True)
    return path


def selftest(n):
    ok = True

    def chk(good, msg):
        nonlocal ok
        ok &= bool(good)
        print("%s %s" % ("ok  " if good else "FAIL", msg))

    seeds = list(range(BASE_SEED + SEED_OFFSET_0, BASE_SEED + SEED_OFFSET_0 + n))
    chk(len(seeds) == len(set(seeds)) == n, "H1 %d seeds, all distinct" % n)
    chk(min(seeds) == 10714, "H2 seed block starts at 10714 (PR-011 item 1)")
    chk(min(seeds) > 10713, "H3 disjoint from W14's 10414-10713 and every earlier block")
    p = build_prompt_w3(FORM, CONDITION, TAU_B)
    chk(p == build_prompt_w3("B", "above_good", TAU_B), "H4 prompt is W3 form B above_good")
    chk("To be clear:" not in p, "H5 carries none of W11's clarification")
    chk("Unless your estimate fails to exceed" not in p,
        "H6 carries none of W14's degradation")
    chk(p != build_prompt_w11(FORM, CONDITION, TAU_B), "H7 differs from W11's wording")
    chk(p != build_prompt_w14(CONDITION, TAU_B), "H8 differs from W14's wording")
    chk("Note: I have a bet" in p, "H9 the upstream bet paragraph is present")
    chk(TAU_B == 4500000000, "H10 tau_B carried over from W3/W11/W14")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--tau-b", type=int, default=TAU_B)
    ap.add_argument("--chunk", type=int, default=250)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "w15_harvest"))
    ap.add_argument("--hf", action="store_true", help="D-054: HF generate instead of vLLM")
    ap.add_argument("--hf-batch", type=int, default=100)
    ap.add_argument("--hf-max-new", type=int, default=2048)
    args = ap.parse_args()
    if args.selftest:
        return selftest(args.n)
    if args.hf:
        run_hf(args.n, args.tau_b, args.out_root, args.hf_max_new, args.hf_batch)
        return 0

    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    import vllm

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL)
    llm = LLM(model=MODEL, dtype="bfloat16", gpu_memory_utilization=0.90,
              max_model_len=args.max_tokens, trust_remote_code=True, seed=BASE_SEED)
    run(llm, tok, SamplingParams, args.n, args.tau_b, args.out_root, args.max_tokens,
        vllm.__version__, args.chunk)
    print("\nmodel     :", MODEL)
    print("wall secs : %.1f (engine init included)" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
