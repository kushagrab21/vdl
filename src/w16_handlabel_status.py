"""W16: is the owner's hand-label sheet filled? Sheet only -- NEVER opens a key file.

    python3 src/w16_handlabel_status.py

`w14_handlabel_score.py` loads the sealed key at import time, so it cannot be used to ask this
question without opening the key. This does the same check over the sheet alone, stdlib only,
and exits 0 if the sheet is unfilled (R-018's fallback applies) / 1 if it is filled (score it).
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(ROOT, "analysis", "out", "w14_handlabel_sheet.csv")

rows = list(csv.DictReader(open(SHEET)))
cols = [c for c in ("mentions_bet", "direction") if c in (rows[0] if rows else {})]
filled = {c: sum(1 for r in rows if (r[c] or "").strip()) for c in cols}
print("sheet: %s" % os.path.relpath(SHEET, ROOT))
print("rows : %d" % len(rows))
for c in cols:
    print("  %-13s filled %d of %d" % (c, filled[c], len(rows)))
any_filled = any(filled.values())
print("VERDICT: %s" % ("SHEET FILLED - run src/w14_handlabel_score.py" if any_filled
                       else "SHEET UNFILLED - R-018 fallback applies; do not run the scorer"))
sys.exit(1 if any_filled else 0)
