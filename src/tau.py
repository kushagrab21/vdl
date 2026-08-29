"""W1 Step 5: run both extractors over the neutral rollouts and compute each model's tau.

Extractor 1 is upstream's NUMBER_JUDGE_PROMPT driven through the Anthropic API; the prompt
text and its parser are imported from the frozen submodule, never retyped.
Extractor 2 is src/extract_regex.py.

tau of record (PR-001 item 10) = median of JUDGE-extracted finals over non-truncated,
non-null rollouts, using upstream's rule: int(round(percentile 50)).

  python3 src/tau.py                  # judge + regex, writes analysis/out/w1_tau.csv
  python3 src/tau.py --no-judge       # regex only (no API spend)
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "upstream" / "src"))
sys.path.insert(0, str(ROOT / "src"))

from value_leakage.judge import NUMBER_JUDGE_PROMPT, parse_tagged_estimate  # noqa: E402
import extract_regex as ex  # noqa: E402

JUDGE_MODEL = "claude-sonnet-5"      # PR-001 item 7: pinned judge id
NEUTRAL_ROOT = ROOT / "runs" / "w1_neutral"
OUT_CSV = ROOT / "analysis" / "out" / "w1_tau.csv"
OUT_JSON = ROOT / "analysis" / "out" / "w1_extractions.json"
ENV_PATH = ROOT.parent / ".env"


def load_env_key(name):
    v = os.environ.get(name)
    if v:
        return v.strip()
    with open(ENV_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(name + " not found")


def judge_batch(answers, model=JUDGE_MODEL, max_concurrent=20):
    """Extractor 1. Returns a list of float|None, aligned with `answers`."""
    import anthropic
    client = anthropic.Anthropic(api_key=load_env_key("ANTHROPIC_API_KEY"))
    out, usage = [], {"in": 0, "out": 0}
    for text in answers:
        if not (text or "").strip():
            out.append(None)
            continue
        msg = client.messages.create(
            model=model, max_tokens=200,
            messages=[{"role": "user",
                       "content": NUMBER_JUDGE_PROMPT.format(llm_text=text)}])
        raw = "".join(b.text for b in msg.content if b.type == "text")
        usage["in"] += msg.usage.input_tokens
        usage["out"] += msg.usage.output_tokens
        out.append(parse_tagged_estimate(raw))
    return out, usage


def upstream_tau(values):
    """upstream run.py::compute_threshold — int(round(percentile 50))."""
    if not values:
        return None
    import numpy as np
    return int(round(float(np.percentile(values, 50))))


def disagree(a, b):
    """PR-001 item 8 disagreement: relative diff > 1%, or exactly one extractor null."""
    if a is None and b is None:
        return False
    if (a is None) != (b is None):
        return True
    if a == 0 and b == 0:
        return False
    return abs(a - b) / max(abs(a), abs(b)) > 0.01


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--models", nargs="*", default=None)
    args = ap.parse_args()

    dirs = sorted(d for d in NEUTRAL_ROOT.iterdir() if d.is_dir()) if NEUTRAL_ROOT.exists() else []
    if args.models:
        dirs = [d for d in dirs if d.name in args.models]
    if not dirs:
        print("no neutral runs under", NEUTRAL_ROOT)
        return 1

    rows, dump, total_usage = [], {}, {"in": 0, "out": 0}
    for d in dirs:
        data = json.loads((d / "neutral.json").read_text())
        model, recs = data["model"], data["rows"]
        n = len(recs)
        n_trunc = sum(r["truncated"] for r in recs)
        keep = [r for r in recs if not r["truncated"]]

        regex_finals = [ex.final_estimate(r["visible_answer"]) for r in keep]
        if args.no_judge:
            judge_finals = [None] * len(keep)
            usage = {"in": 0, "out": 0}
        else:
            judge_finals, usage = judge_batch([r["visible_answer"] for r in keep])
        total_usage["in"] += usage["in"]
        total_usage["out"] += usage["out"]

        jv = [v for v in judge_finals if v is not None]
        rv = [v for v in regex_finals if v is not None]
        n_dis = sum(disagree(a, b) for a, b in zip(judge_finals, regex_finals))

        inter_counts, inter_counts_filt = [], []
        tau_j = upstream_tau(jv)
        for r in keep:
            seq = ex.intermediates(r["reasoning_text"])
            inter_counts.append(len(seq))
            inter_counts_filt.append(len(ex.filtered(seq, tau_j)))

        def q(vals, p):
            return statistics.quantiles(vals, n=4)[p] if len(vals) > 3 else (
                statistics.median(vals) if vals else 0)

        rows.append({
            "model": model,
            "n": n,
            "n_truncated": n_trunc,
            "pct_truncated": round(100.0 * n_trunc / n, 1) if n else 0,
            "n_valid_judge": len(jv),
            "n_null_judge": len(keep) - len(jv),
            "n_valid_regex": len(rv),
            "n_null_regex": len(keep) - len(rv),
            "tau_judge": tau_j,
            "tau_regex": upstream_tau(rv),
            "n_disagree": n_dis,
            "pct_disagree": round(100.0 * n_dis / len(keep), 1) if keep else 0,
            "median_intermediates": statistics.median(inter_counts) if inter_counts else 0,
            "iqr_lo_intermediates": q(inter_counts, 0),
            "iqr_hi_intermediates": q(inter_counts, 2),
            "median_intermediates_filtered": (statistics.median(inter_counts_filt)
                                              if inter_counts_filt else 0),
            "flag_lt40_valid": len(jv) < 40,
        })
        dump[model] = [{"i": r["i"], "judge": j, "regex": g,
                        "n_intermediates": len(ex.intermediates(r["reasoning_text"]))}
                       for r, j, g in zip(keep, judge_finals, regex_finals)]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    OUT_JSON.write_text(json.dumps(dump, indent=2))

    for r in rows:
        print(json.dumps(r))
    print("\nwrote", OUT_CSV)
    if not args.no_judge:
        # Sonnet pricing: $3 / MTok in, $15 / MTok out.
        cost = total_usage["in"] / 1e6 * 3.0 + total_usage["out"] / 1e6 * 15.0
        print("judge tokens in/out: %d / %d  -> approx $%.4f"
              % (total_usage["in"], total_usage["out"], cost))
    return 0


if __name__ == "__main__":
    sys.exit(main())
