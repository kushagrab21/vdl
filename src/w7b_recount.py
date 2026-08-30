"""W7b load-bearing recount (PR-006 item 8): Delta_pm(v_phat) from raw text, regex only.
Imports nothing from the analysis path.   python3 src/w7b_recount.py"""
import json, re, sys
TAU, R = 4500000000.0, "runs/w7b_steer/%s.json"
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(billion|million|thousand|trillion)?", re.I)
MUL = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
def p(path):
    hit = tot = 0
    for row in json.load(open(path))["rows"]:
        v = [float(m.group(1).replace(",", "")) * MUL.get((m.group(2) or "").lower(), 1.0)
             for m in NUM.finditer(row["visible_answer"])]
        v = [x for x in v if x != TAU]
        if v:
            tot += 1
            hit += v[-1] > TAU
    return hit / float(tot), hit, tot
a, ka, na = p(R % "B7b_above_L27_ap05"); b, kb, nb = p(R % "B7b_above_L27_am05")
q, kq, nq = p(R % "B7b_above_L27_ap025"); r, kr, nr = p(R % "B7b_above_L27_am025")
s, ks, ns = p("runs/w7_steer/B_above_sham.json")
print("alpha=+0.50  P(final>tau_B) = %d/%d = %.4f" % (ka, na, a))
print("alpha=-0.50  P(final>tau_B) = %d/%d = %.4f" % (kb, nb, b))
print("alpha=+0.25  P(final>tau_B) = %d/%d = %.4f" % (kq, nq, q))
print("alpha=-0.25  P(final>tau_B) = %d/%d = %.4f" % (kr, nr, r))
print("sham (REUSED W7 alpha=0)     = %d/%d = %.4f" % (ks, ns, s))
print("PRIMARY delta_pm(v_phat) = P(+0.5) - P(-0.5) = %.4f  [quarter-dose pair %.4f]" % (a - b, q - r))
