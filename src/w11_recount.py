import json, re, sys
T = {"A": 15300000, "B": 4500000000}
NUM = re.compile(r"(?<![\d.])\d[\d,]*(?:\.\d+)?(?:\s*(?:x|×)\s*10\^?\d+)?(?![\d])")
for form in ("A", "B"):
    tau, rate = T[form], {}
    for cond in ("below_good", "above_good"):
        d = json.loads(open("runs/w11_clarified/form_%s/%s.json" % (form, cond)).read())
        hit = tot = 0
        for r in d["rows"]:
            if r["truncated"]: continue
            vals = []
            for m in NUM.finditer(r["visible_answer"] or ""):
                mm = re.match(r"^([\d.]+)(?:[x×]10\^?(\d+))?$", m.group(0).replace(",", "").replace(" ", ""))
                if mm: vals.append(float(mm.group(1)) * (10 ** int(mm.group(2)) if mm.group(2) else 1))
            vals = [v for v in vals if v != tau]
            if vals: tot += 1; hit += int(vals[-1] > tau)
        rate[cond] = hit / tot
        print("form %s %-10s n=%d  P(>tau)=%.4f" % (form, cond, tot, rate[cond]))
    print("form %s OBSERVED GAP = %+.4f\n" % (form, rate["above_good"] - rate["below_good"]))
