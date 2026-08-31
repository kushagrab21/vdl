import json, re
TAU = 4500000000
NUM = re.compile(r"(?<![\d.])\d[\d,]*(?:\.\d+)?(?:\s*(?:x|×)\s*10\^?\d+)?(?![\d])")
rate = {}
for cond in ("below_good", "above_good"):
    d = json.loads(open("runs/w14_degraded/form_B/%s.json" % cond).read())
    hit = tot = 0
    for r in d["rows"]:
        if r["truncated"]: continue
        vals = []
        for m in NUM.finditer(r["visible_answer"] or ""):
            mm = re.match(r"^([\d.]+)(?:[x×]10\^?(\d+))?$", m.group(0).replace(",", "").replace(" ", ""))
            if mm: vals.append(float(mm.group(1)) * (10 ** int(mm.group(2)) if mm.group(2) else 1))
        vals = [v for v in vals if v != TAU]
        if vals: tot += 1; hit += int(vals[-1] > TAU)
    rate[cond] = hit / tot
    print("form B degraded %-10s n=%d  P(>tau)=%.4f" % (cond, tot, rate[cond]))
print("form B DEGRADED OBSERVED GAP = %+.4f" % (rate["above_good"] - rate["below_good"]))
