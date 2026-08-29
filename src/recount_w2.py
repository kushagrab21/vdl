"""W2 load-bearing recount: landing gap from the RAW stored rollout text, regex only.
Imports nothing from landing_gap.py; re-splits raw_output on </think> itself rather than
trusting the stored visible_answer field.   python3 src/recount_w2.py Qwen3-8B 31250000"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_regex import final_estimate
slug, tau = sys.argv[1], float(sys.argv[2])
rate = {}
for cond in ("below_good", "above_good"):
    rows = json.load(open("runs/w2_screen/%s/%s.json" % (slug, cond)))["rows"]
    fin = [final_estimate(r["raw_output"].split("</think>", 1)[-1])
           for r in rows if not r["truncated"]]
    v = [x for x in fin if x is not None]
    rate[cond] = sum(x > tau for x in v) / len(v)
    print("%-11s n_valid=%d  n_null=%d  P(final > tau)=%.4f"
          % (cond, len(v), len(fin) - len(v), rate[cond]))
print("tau=%d  landing gap (recount) = %.4f" % (tau, rate["above_good"] - rate["below_good"]))
