"""W3 load-bearing recount: the form-B landing gap from RAW stored text, regex extractor on
the D-016-corrected basis (PR-003 item 7): the last numeric literal that is NOT exactly tau.
Imports nothing from behaviour_w3.py.    python3 src/recount_w3.py <tau_B>"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_regex import all_numbers
tau = float(sys.argv[1])
rate = {}
for cond in ("below_good", "above_good"):
    rows = json.load(open("runs/w3_frozen/form_B/%s.json" % cond))["rows"]
    fin = []
    for r in rows:
        if r["truncated"]:
            continue
        nums = [v for v, _, _ in all_numbers(r["raw_output"], skip_ranges=False) if v != tau]
        fin.append(nums[-1] if nums else None)
    v = [x for x in fin if x is not None]
    rate[cond] = sum(x > tau for x in v) / len(v)
    print("%-11s n_valid=%d  n_null=%d  P(final > tau)=%.4f"
          % (cond, len(v), len(fin) - len(v), rate[cond]))
print("tau=%d  form-B landing gap (corrected-basis recount) = %.4f"
      % (tau, rate["above_good"] - rate["below_good"]))
