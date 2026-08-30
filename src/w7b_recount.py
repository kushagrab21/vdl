"""W7b load-bearing recount (PR-006 item 8): Delta_pm(v_phat) from raw text, regex only.
Imports nothing from the analysis path.   python3 src/w7b_recount.py"""
import json, re, sys
TAU, R = 4500000000.0, "runs/w7b_steer/B7b_above_L27_%s.json"
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(billion|million|thousand|trillion)?", re.I)
MUL = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
def p(path):
    hit = tot = 0
    for row in json.load(open(path))["rows"]:
        v = [float(m.group(1).replace(",", "")) * MUL.get((m.group(2) or "").lower(), 1.0)
             for m in NUM.finditer(row["visible_answer"])]
        v = [x for x in v if x != TAU]
        if v: tot += 1; hit += v[-1] > TAU
    return hit / float(tot), hit, tot
A = {k: p(R % k) for k in ("ap05", "ap025", "am025", "am05")}
A["sham(REUSED W7 alpha=0)"] = p("runs/w7_steer/B_above_sham.json")
for k, (v, h, n) in A.items():
    print("%-24s P(final>tau_B) = %2d/%d = %.4f" % (k, h, n, v))
print("PRIMARY  delta_pm(v_phat) = P(+0.50) - P(-0.50) = %+.4f" % (A["ap05"][0] - A["am05"][0]))
print("descrip. delta_pm(v_phat) = P(+0.25) - P(-0.25) = %+.4f" % (A["ap025"][0] - A["am025"][0]))
