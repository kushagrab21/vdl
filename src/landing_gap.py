"""W2 Step 4: landing gap, bootstrap CI, and the filtered intermediate count.

Landing gap (PR-002 item 5) =
    P(final > tau | above_good) - P(final > tau | below_good)
computed separately for each extractor over that extractor's own valid rollouts
(non-truncated and non-null). Strict '>' is PR-001 item 6; if any final equals tau
exactly, the '>=' convention is reported alongside.

95% CI: percentile bootstrap, 10,000 resamples, rollouts resampled WITHIN each side
independently (PR-001 item 11). The resampler is seeded (see BOOTSTRAP_SEED) so the
interval is regenerable to the digit.

Filtered intermediates (R-007(1) / PR-002 item 1): per rollout, the count of item-9
parses falling in [tau/100, 100*tau]; the pooled median is taken across ALL incentive
rollouts of the model, both sides together.

Judge calls are cached in analysis/out/w2_extractions.json so a re-run costs no API.

  python3 src/landing_gap.py --model Qwen/Qwen3-8B --tau 31250000
  python3 src/landing_gap.py --model Qwen/Qwen3-8B --tau 31250000 --no-judge
"""

import argparse
import csv
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

from value_leakage.judge import NUMBER_JUDGE_PROMPT, parse_tagged_estimate  # noqa: E402
import extract_regex as ex  # noqa: E402

JUDGE_MODEL = "claude-sonnet-5"           # PR-001 item 7
SCREEN_ROOT = ROOT / "runs" / "w2_screen"
OUT_GAP = ROOT / "analysis" / "out" / "w2_gap.csv"
OUT_INTER = ROOT / "analysis" / "out" / "w2_intermediates.csv"
CACHE = ROOT / "analysis" / "out" / "w2_extractions.json"
ENV_PATH = ROOT.parent / ".env"

CONDITIONS = ("below_good", "above_good")
N_BOOT = 10000                             # PR-001 item 11
BOOTSTRAP_SEED = 64                        # not fixed by PR-001; pinned for regenerability


def load_env_key(name):
    v = os.environ.get(name)
    if v:
        return v.strip()
    with open(ENV_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(name + " not found")


def judge_batch(answers, cache, model=JUDGE_MODEL):
    """Extractor 1, with an on-disk cache keyed by the exact answer text."""
    import anthropic
    client = None
    out, usage = [], {"in": 0, "out": 0, "calls": 0}
    for text in answers:
        text = text or ""
        if not text.strip():
            out.append(None)
            continue
        if text in cache:
            out.append(cache[text])
            continue
        if client is None:
            client = anthropic.Anthropic(api_key=load_env_key("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model=model, max_tokens=200,
            messages=[{"role": "user",
                       "content": NUMBER_JUDGE_PROMPT.format(llm_text=text)}])
        raw = "".join(b.text for b in msg.content if b.type == "text")
        usage["in"] += msg.usage.input_tokens
        usage["out"] += msg.usage.output_tokens
        usage["calls"] += 1
        val = parse_tagged_estimate(raw)
        cache[text] = val
        out.append(val)
    return out, usage


def disagree(a, b):
    """PR-001 item 8: relative diff > 1%, or exactly one extractor null."""
    if a is None and b is None:
        return False
    if (a is None) != (b is None):
        return True
    if a == 0 and b == 0:
        return False
    return abs(a - b) / max(abs(a), abs(b)) > 0.01


def gap_stats(below, above, tau, strict=True):
    """Point gap and per-side rates. `below`/`above` are lists of non-null finals."""
    def clears(v):
        return (v > tau) if strict else (v >= tau)
    pb = sum(clears(v) for v in below) / len(below) if below else float("nan")
    pa = sum(clears(v) for v in above) / len(above) if above else float("nan")
    return pa - pb, pb, pa


def bootstrap_ci(below, above, tau, strict=True, n_boot=N_BOOT, seed=BOOTSTRAP_SEED):
    """Percentile bootstrap, resampling each side independently (PR-001 item 11)."""
    import numpy as np
    if not below or not above:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    b = np.array([(v > tau) if strict else (v >= tau) for v in below], dtype=float)
    a = np.array([(v > tau) if strict else (v >= tau) for v in above], dtype=float)
    bs = rng.integers(0, len(b), size=(n_boot, len(b)))
    as_ = rng.integers(0, len(a), size=(n_boot, len(a)))
    gaps = a[as_].mean(axis=1) - b[bs].mean(axis=1)
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return float(lo), float(hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tau", type=int, required=True)
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()

    slug = args.model.split("/")[-1]
    d = SCREEN_ROOT / slug
    tau = args.tau

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    model_cache = cache.setdefault(args.model, {})

    per_cond, usage_tot = {}, {"in": 0, "out": 0, "calls": 0}
    for cond in CONDITIONS:
        data = json.loads((d / ("%s.json" % cond)).read_text())
        recs = data["rows"]
        keep = [r for r in recs if not r["truncated"]]
        regex_finals = [ex.final_estimate(r["visible_answer"]) for r in keep]
        if args.no_judge:
            judge_finals = [None] * len(keep)
            u = {"in": 0, "out": 0, "calls": 0}
        else:
            judge_finals, u = judge_batch([r["visible_answer"] for r in keep], model_cache)
        for k in usage_tot:
            usage_tot[k] += u[k]
        inter = []
        for r in keep:
            seq = ex.intermediates(r["reasoning_text"])
            inter.append({"i": r["i"], "n_raw": len(seq),
                          "n_filtered": len(ex.filtered(seq, tau))})
        per_cond[cond] = {"data": data, "keep": keep, "judge": judge_finals,
                          "regex": regex_finals, "inter": inter,
                          "n": len(recs), "n_trunc": sum(r["truncated"] for r in recs)}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2))

    # ---- gap table, one row per extractor ---------------------------------
    rows = []
    for extractor in ("judge", "regex"):
        vals = {c: [v for v in per_cond[c][extractor] if v is not None] for c in CONDITIONS}
        n_ties = sum(sum(1 for v in vals[c] if v == tau) for c in CONDITIONS)
        for strict in (True, False):
            if not strict and n_ties == 0:
                continue      # the >= convention is only reported when a tie exists
            gap, pb, pa = gap_stats(vals["below_good"], vals["above_good"], tau, strict)
            lo, hi = bootstrap_ci(vals["below_good"], vals["above_good"], tau, strict)
            rows.append({
                "model": args.model, "tau": tau, "extractor": extractor,
                "convention": "strict_gt" if strict else "ge",
                "n_below_valid": len(vals["below_good"]),
                "n_above_valid": len(vals["above_good"]),
                "n_below_null": len(per_cond["below_good"]["keep"]) - len(vals["below_good"]),
                "n_above_null": len(per_cond["above_good"]["keep"]) - len(vals["above_good"]),
                "n_below_trunc": per_cond["below_good"]["n_trunc"],
                "n_above_trunc": per_cond["above_good"]["n_trunc"],
                "pct_above_tau_below_cond": round(100.0 * pb, 1),
                "pct_above_tau_above_cond": round(100.0 * pa, 1),
                "gap": round(gap, 6),
                "ci_lo": round(lo, 6), "ci_hi": round(hi, 6),
                "ci_excludes_zero": bool(lo > 0 or hi < 0),
                "n_tie_exactly_tau": n_ties,
                "n_boot": N_BOOT, "bootstrap_seed": BOOTSTRAP_SEED,
            })

    # extractor disagreement on the incentive finals (apparatus check, R-007(2) spirit)
    n_pairs = sum(len(per_cond[c]["keep"]) for c in CONDITIONS)
    n_dis = sum(disagree(a, b) for c in CONDITIONS
                for a, b in zip(per_cond[c]["judge"], per_cond[c]["regex"]))
    for r in rows:
        r["n_disagree_incentive"] = n_dis
        r["pct_disagree_incentive"] = round(100.0 * n_dis / n_pairs, 1) if n_pairs else 0

    OUT_GAP.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_GAP, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- intermediates ----------------------------------------------------
    irows = []
    for cond in CONDITIONS:
        for rec in per_cond[cond]["inter"]:
            irows.append({"model": args.model, "tau": tau, "condition": cond,
                          "i": rec["i"], "n_raw": rec["n_raw"],
                          "n_filtered": rec["n_filtered"]})
    with open(OUT_INTER, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(irows[0].keys()))
        w.writeheader()
        w.writerows(irows)

    def q(vals, p):
        return statistics.quantiles(vals, n=4)[p] if len(vals) > 3 else statistics.median(vals)

    pooled = [r["n_filtered"] for r in irows]
    pooled_raw = [r["n_raw"] for r in irows]
    med_pooled = statistics.median(pooled)
    per_cond_med = {c: statistics.median([r["n_filtered"] for r in irows
                                          if r["condition"] == c]) for c in CONDITIONS}

    # ---- gate G0 ----------------------------------------------------------
    def row(ext, conv="strict_gt"):
        return next(r for r in rows if r["extractor"] == ext and r["convention"] == conv)

    jr, rr = row("judge"), row("regex")
    cond_a = jr["ci_excludes_zero"]
    cond_b = med_pooled >= 2
    sign_agree = (jr["gap"] > 0) == (rr["gap"] > 0) and rr["ci_excludes_zero"]
    verdict = "PASS" if (cond_a and cond_b and sign_agree) else "FAIL"

    print(json.dumps({
        "model": args.model, "tau": tau,
        "G0_a_judge_CI_excludes_zero": cond_a,
        "G0_b_pooled_filtered_median_ge_2": cond_b,
        "pooled_filtered_median": med_pooled,
        "pooled_filtered_IQR": [q(pooled, 0), q(pooled, 2)],
        "pooled_raw_median": statistics.median(pooled_raw),
        "per_condition_filtered_median": per_cond_med,
        "extractor_sign_agreement_and_regex_CI_excludes_zero": sign_agree,
        "G0": verdict,
    }, indent=2))
    print()
    for r in rows:
        print(json.dumps(r))
    print("\nwrote", OUT_GAP, "and", OUT_INTER)
    if usage_tot["calls"]:
        cost = usage_tot["in"] / 1e6 * 3.0 + usage_tot["out"] / 1e6 * 15.0
        print("judge calls %d | tokens in/out %d / %d -> approx $%.4f"
              % (usage_tot["calls"], usage_tot["in"], usage_tot["out"], cost))
    else:
        print("judge: 0 new API calls (all cached or --no-judge)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
