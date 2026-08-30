"""W11, form B: what the frozen prediction WOULD have said, as a function of comprehension.

**THIS IS NOT PR-007's TEST, AND IT IS SUPERSEDED.** Written while D-039's API credit
exhaustion had left form B's direction judge unrun, to bound what the prediction could
have said. The owner topped the account up and the judge completed, so the verdict of
record is the MEASURED one in `w11_prediction.csv` (form B, C1). This file is kept as a
sensitivity analysis only: it shows how gap_pred moves with assumed comprehension, which
is what W12 needs for sizing. Every row is conditional on an assumption, not a measurement.

  python3 src/w11_sensitivity.py   -> analysis/out/w11_sensitivity.csv
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import w11_cells as w3c              # noqa: E402
from analyze_w11 import predict      # noqa: E402

OUT = ROOT / "analysis" / "out" / "w11_sensitivity.csv"
GAP_OBS = {"A": 0.186667, "B": 0.286667}     # analysis/out/w11_prediction.csv
N = 150
# The comprehension pairs form A actually achieved, plus a grid around them.
GRID = [(0.90, 0.98), (0.85, 0.85), (0.80, 0.90), (0.90, 0.90), (0.95, 0.95),
        (0.75, 0.85), (0.70, 0.85), (0.5467, 0.8067)]   # last = W3's own rates


def main():
    cells = {(r["form"], r["arm"], r["group"]): r["rate"] for r in w3c.cells()}
    ns = {(r["form"], r["arm"], r["group"]): r["n"] for r in w3c.cells()}
    rng = np.random.default_rng(11007)
    rows = []
    for form in ("A", "B"):
        for p_a, p_b in GRID:
            pt, lo, hi = predict(form, p_a, p_b, N, N, cells, ns, rng)
            rows.append({"form": form, "assumed_p_a": p_a, "assumed_p_b": p_b,
                         "gap_pred": round(pt, 6), "pred_lo": round(lo, 6),
                         "pred_hi": round(hi, 6),
                         "gap_observed": GAP_OBS[form],
                         "observed_inside": bool(lo <= GAP_OBS[form] <= hi),
                         "note": "CONDITIONAL ON AN ASSUMPTION — not PR-007's test"})
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    for r in rows:
        print("form %s  p_a=%.4f p_b=%.4f -> pred %+.4f [%+.4f, %+.4f]   obs %+.4f  inside=%s"
              % (r["form"], r["assumed_p_a"], r["assumed_p_b"], r["gap_pred"],
                 r["pred_lo"], r["pred_hi"], r["gap_observed"], r["observed_inside"]))
    print("\nwrote", OUT)
    print("NOT A VERDICT: PR-007 item 6 needs MEASURED p_a, p_b. D-039 blocked form B's.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
