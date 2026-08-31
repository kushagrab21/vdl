"""W14 judging: extractor 1 (number judge) and the FROZEN direction judge (PR-003 item 5).

Neither prompt is touched. This module redirects the W11 drivers' cache paths to W14 files
and replaces only the COST ESTIMATOR, because D-040 measured that D-033's direction-judge
constants over-shoot by a third. Per the D-011/D-016/D-027/D-033 discipline no estimator
already in `src/` is patched in place; the corrected constants are named here with their
source entry, and `judge_w11.py` keeps citing D-033 as it always did.

  python3 src/judge_w14.py --estimate
  python3 src/judge_w14.py --run --procs 12
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import direction_judge as dj        # noqa: E402
import judge_w11 as j11             # noqa: E402
import judge_w11_par as jpar        # noqa: E402
from value_leakage.judge import NUMBER_JUDGE_PROMPT  # noqa: E402

RUN_ROOT = ROOT / "runs" / "w14_degraded"
NUM_CACHE = ROOT / "analysis" / "out" / "w14_extractions.json"
DIR_CACHE = ROOT / "analysis" / "out" / "w14_direction_cache.json"
USAGE_OUT = ROOT / "analysis" / "out" / "w14_api_usage.json"

# D-040, superseding D-033. Two different chars/token, because the two prompts are
# different kinds of English.
CPT_NUMBER, OUT_TOK_NUMBER = 2.84, 20.0
CPT_DIRECTION, OUT_TOK_DIRECTION = 3.15, 56.0
PRICE_IN, PRICE_OUT = 3.0, 15.0
PAUSE_USD = 8.0                     # PR-010 item 3


def rows():
    return list(dj.iter_incentive_rows(RUN_ROOT))


def estimate():
    rs = rows()
    d_chars = sum(len(dj.DIRECTION_JUDGE_PROMPT.format(prompt=p, response=v))
                  for _, _, _, p, v, _ in rs)
    j_chars = sum(len(NUMBER_JUDGE_PROMPT.format(llm_text=v or "")) for _, _, _, _, v, _ in rs)
    num = (j_chars / CPT_NUMBER / 1e6 * PRICE_IN + OUT_TOK_NUMBER * len(rs) / 1e6 * PRICE_OUT)
    dirc = (d_chars / CPT_DIRECTION / 1e6 * PRICE_IN
            + OUT_TOK_DIRECTION * len(rs) / 1e6 * PRICE_OUT)
    est = {"n_generations": len(rs), "constants": "D-040 (supersedes D-033)",
           "chars_per_token_number": CPT_NUMBER, "chars_per_token_direction": CPT_DIRECTION,
           "out_tokens_number": OUT_TOK_NUMBER, "out_tokens_direction": OUT_TOK_DIRECTION,
           "number_judge_est_usd": round(num, 3), "direction_judge_est_usd": round(dirc, 3),
           "total_est_usd": round(num + dirc, 3), "pause_line_usd": PAUSE_USD,
           "under_pause_line": bool(num + dirc <= PAUSE_USD)}
    print(json.dumps(est, indent=2))
    return est


# Redirect both drivers at W14's files, then hand off to the W11 parallel transport (D-038)
# with its prompts, model, retry ladder and cache keys untouched.
for m in (j11, jpar):
    m.RUN_ROOT, m.NUM_CACHE, m.DIR_CACHE, m.USAGE_OUT = RUN_ROOT, NUM_CACHE, DIR_CACHE, USAGE_OUT
    m.PAUSE_USD = PAUSE_USD
jpar.estimate, jpar.rows = estimate, rows

if __name__ == "__main__":
    if "--estimate" in sys.argv and "--run" not in sys.argv:
        estimate(); sys.exit(0)
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--estimate"]
    sys.exit(jpar.main())
