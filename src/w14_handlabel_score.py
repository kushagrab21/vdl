"""PR-010 item 3: score the owner's returned hand-label sheet against the sealed key.
RUN ONLY AFTER THE SHEET COMES BACK.   python3 src/w14_handlabel_score.py [sheet.csv]"""
import csv, math, pathlib, sys
OUT = pathlib.Path(__file__).resolve().parent.parent / "analysis" / "out"
key = {r["row_id"]: r["judge_direction"] for r in csv.DictReader(open(OUT / "w14_handlabel_key.csv"))}
sheet = {r["row_id"]: (r["direction"] or "").strip().lower()
         for r in csv.DictReader(open(sys.argv[1] if len(sys.argv) > 1 else OUT / "w14_handlabel_sheet.csv"))}
pairs = [(key[k], sheet[k]) for k in sorted(key) if sheet.get(k) in ("correct", "incorrect", "unclear")]
if not pairs: sys.exit("sheet is unfilled — nothing to score (%d/%d rows have a verdict)" % (0, len(key)))
CLS = ("correct", "incorrect", "unclear")
n = len(pairs); agree = sum(a == b for a, b in pairs)
po = agree / n
pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in CLS)
kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
z, e = 1.959964, 1 - po                      # Wilson 95% upper bound on the disagreement rate
hi = (e + z * z / (2 * n) + z * math.sqrt(e * (1 - e) / n + z * z / (4 * n * n))) / (1 + z * z / n)
print("rows scored %d of %d   overall agreement %.4f (%d/%d)" % (n, len(key), po, agree, n))
print("Cohen's kappa %.4f   (chance agreement %.4f)" % (kappa, pe))
for c in CLS:
    sel = [(a, b) for a, b in pairs if a == c]
    print("  judge=%-9s n=%2d  agreement %s" % (c, len(sel),
          "%.4f" % (sum(a == b for a, b in sel) / len(sel)) if sel else "-"))
for c in CLS:
    sel = [(a, b) for a, b in pairs if b == c]
    print("  human=%-9s n=%2d  agreement %s" % (c, len(sel),
          "%.4f" % (sum(a == b for a, b in sel) / len(sel)) if sel else "-"))
print("\nlabel-noise bound: judge-vs-human disagreement %.4f, 95%% Wilson upper bound %.4f" % (e, hi))
print("NOTE the sample is STRATIFIED 20/15/15 on the judge's own classes, not on the population\n"
      "     (413/49/138 of 600), so these are PER-CLASS rates; a population error rate must be\n"
      "     reweighted by the class marginals before it is quoted.")
