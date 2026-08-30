"""W7 load-bearing recount: the primary contrast, from raw steered text, regex only.
Independent of extract_regex.py and of analyze_w7.py.  python3 src/w7_recount.py"""
import json, re, sys
TAU, R = 4500000000.0, "runs/w7_steer/%s.json"
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(billion|million|thousand|trillion)?", re.I)
MUL = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
def finals(arm):
    out = []
    for row in json.load(open(R % arm))["rows"]:
        v = [float(m.group(1).replace(",", "")) * MUL.get((m.group(2) or "").lower(), 1.0)
             for m in NUM.finditer(row["visible_answer"])]
        v = [x for x in v if x != TAU]
        out.append(v[-1] if v else None)
    return out
def p(arm):
    v = [x for x in finals(arm) if x is not None]
    return sum(1 for x in v if x > TAU) / float(len(v)), sum(1 for x in v if x > TAU), len(v)
a, ka, na = p("B_above_L27_ap2"); b, kb, nb = p("B_above_L27_am2"); s, ks, ns = p("B_above_sham")
print("alpha=+2 P(final>tau_B) = %d/%d = %.4f" % (ka, na, a))
print("alpha=-2 P(final>tau_B) = %d/%d = %.4f" % (kb, nb, b))
print("sham     P(final>tau_B) = %d/%d = %.4f" % (ks, ns, s))
print("primary contrast delta_pm = %.4f ; delta_plus = %.4f ; delta_minus = %.4f" % (a - b, a - s, b - s))
