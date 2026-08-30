"""W11 judging: extractor 1 (number judge) and the FROZEN direction judge (PR-003 item 5).

Neither prompt is touched — both modules are imported and only their cache paths are
redirected to W11 files, so the instrument that read W3 is the instrument that reads W11.
D-033's constants drive the pre-run estimate, which is printed BEFORE any call and
compared against PR-007 item 3's $10 pause line.

  python3 src/judge_w11.py --estimate
  python3 src/judge_w11.py --run
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import landing_gap as lg          # noqa: E402
import direction_judge as dj      # noqa: E402

RUN_ROOT = ROOT / "runs" / "w11_clarified"
NUM_CACHE = ROOT / "analysis" / "out" / "w11_extractions.json"
DIR_CACHE = ROOT / "analysis" / "out" / "w11_direction_cache.json"
USAGE_OUT = ROOT / "analysis" / "out" / "w11_api_usage.json"
MODEL = "Qwen/Qwen2.5-14B-Instruct"

# D-033: measured on this model's answers under these judge prompts.
CHARS_PER_TOKEN = 2.84
OUT_TOK_NUMBER = 20.0
OUT_TOK_DIRECTION = 117.0
PRICE_IN, PRICE_OUT = 3.0, 15.0
PAUSE_USD = 10.0                  # PR-007 item 3


def rows():
    return list(dj.iter_incentive_rows(RUN_ROOT))


def estimate():
    rs = rows()
    n_chars = sum(len(v or "") for _, _, _, _, v, _ in rs)
    d_chars = sum(len(dj.DIRECTION_JUDGE_PROMPT.format(prompt=p, response=v))
                  for _, _, _, p, v, _ in rs)
    from value_leakage.judge import NUMBER_JUDGE_PROMPT
    j_chars = sum(len(NUMBER_JUDGE_PROMPT.format(llm_text=v or "")) for _, _, _, _, v, _ in rs)
    num = (j_chars / CHARS_PER_TOKEN / 1e6 * PRICE_IN
           + OUT_TOK_NUMBER * len(rs) / 1e6 * PRICE_OUT)
    dirc = (d_chars / CHARS_PER_TOKEN / 1e6 * PRICE_IN
            + OUT_TOK_DIRECTION * len(rs) / 1e6 * PRICE_OUT)
    est = {"n_generations": len(rs), "answer_chars": n_chars,
           "chars_per_token": CHARS_PER_TOKEN,
           "number_judge_est_usd": round(num, 3),
           "direction_judge_est_usd": round(dirc, 3),
           "total_est_usd": round(num + dirc, 3),
           "pause_line_usd": PAUSE_USD,
           "under_pause_line": bool(num + dirc <= PAUSE_USD)}
    print(json.dumps(est, indent=2))
    return est


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    est = estimate()
    if not a.run:
        return 0
    if not est["under_pause_line"]:
        print("PAUSING: projected $%.2f exceeds PR-007 item 3's $%.2f line."
              % (est["total_est_usd"], PAUSE_USD))
        return 2

    rs = rows()
    # ---- extractor 1, the number judge --------------------------------------
    lg.CACHE = NUM_CACHE
    cache_all = json.loads(NUM_CACHE.read_text()) if NUM_CACHE.exists() else {}
    lg._CACHE_OBJ = cache_all
    mc = cache_all.setdefault(MODEL, {})
    vals, u_num = lg.judge_batch([v for _, _, _, _, v, _ in rs], mc, label="w11")
    lg._flush_cache()
    print("number judge: %d calls, in/out %d/%d -> $%.4f"
          % (u_num["calls"], u_num["in"], u_num["out"],
             u_num["in"] / 1e6 * PRICE_IN + u_num["out"] / 1e6 * PRICE_OUT))

    # ---- the FROZEN direction judge -----------------------------------------
    dj.CACHE = DIR_CACHE
    cache = json.loads(DIR_CACHE.read_text()) if DIR_CACHE.exists() else {}
    usage = {"in": 0, "out": 0, "calls": 0}
    for n, (key, form, cond, prompt_text, visible, r) in enumerate(rs):
        if cache.get(key, {}).get("direction") is not None:
            continue
        raw = dj.judge_one(prompt_text, visible, usage)
        mentions, direction = dj.parse_verdict(raw)
        cache[key] = {"form": form, "condition": cond, "i": r["i"],
                      "mentions_bet": mentions, "direction": direction, "raw": raw}
        if (n + 1) % 25 == 0:
            print("  dir %d/%d" % (n + 1, len(rs)), flush=True)
            DIR_CACHE.write_text(json.dumps(cache, indent=2))
    DIR_CACHE.write_text(json.dumps(cache, indent=2))
    c_dir = usage["in"] / 1e6 * PRICE_IN + usage["out"] / 1e6 * PRICE_OUT
    print("direction judge: %d calls, in/out %d/%d -> $%.4f"
          % (usage["calls"], usage["in"], usage["out"], c_dir))

    c_num = u_num["in"] / 1e6 * PRICE_IN + u_num["out"] / 1e6 * PRICE_OUT
    USAGE_OUT.write_text(json.dumps(
        {"estimate": est, "number_judge": dict(u_num, usd=round(c_num, 4)),
         "direction_judge": dict(usage, usd=round(c_dir, 4)),
         "actual_total_usd": round(c_num + c_dir, 4),
         "projection_error_pct": round(100 * (est["total_est_usd"] - (c_num + c_dir))
                                       / (c_num + c_dir), 1)}, indent=2))
    print("\nACTUAL total $%.4f vs projection $%.3f" % (c_num + c_dir, est["total_est_usd"]))
    print("wrote", USAGE_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
