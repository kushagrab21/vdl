"""PR-007 item 4: the four W3 conditional cell rates the frozen prediction is built on.

w3_direction.csv stores only the conditional GAP per group, not the two rates it is a
difference of, so the cells are recomputed here from the same committed sources the W3
row was computed from — the frozen direction-judge cache and the frozen number-judge
extraction cache — under exactly behaviour_w3.py's filter (non-truncated rows, non-null
judge final, strict '>').

Self-check: the gaps this reproduces must equal w3_direction.csv's `value` field, and the
group sizes must equal its n_below_in_group / n_above_in_group.

  python3 src/w11_cells.py          # -> analysis/out/w11_w3_cells.csv, and the check
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "Qwen/Qwen2.5-14B-Instruct"
TAU = {"A": 15300000, "B": 4500000000}
FROZEN = ROOT / "runs" / "w3_frozen"
DIR_CACHE = ROOT / "analysis" / "out" / "w3_direction_cache.json"
EXTRACTIONS = ROOT / "analysis" / "out" / "w3_extractions.json"
W3_DIRECTION = ROOT / "analysis" / "out" / "w3_direction.csv"
OUT = ROOT / "analysis" / "out" / "w11_w3_cells.csv"


def cells():
    dc = json.loads(DIR_CACHE.read_text())
    ex = json.loads(EXTRACTIONS.read_text())[MODEL]
    rows = []
    for form in ("A", "B"):
        tau = TAU[form]
        for cond in ("below_good", "above_good"):
            data = json.loads((FROZEN / ("form_%s" % form) / ("%s.json" % cond)).read_text())
            keep = [r for r in data["rows"] if not r["truncated"]]
            for grp in ("corr", "ncorr"):
                n = above = 0
                for r in keep:
                    v = dc.get("%s|%s|%s|%d" % (MODEL, form, cond, r["i"]))
                    if not v:
                        continue
                    if (v["direction"] == "correct") != (grp == "corr"):
                        continue
                    jv = ex.get(r["visible_answer"] or "")
                    if jv is None:
                        continue
                    n += 1
                    above += int(jv > tau)
                rows.append({"form": form, "arm": cond, "group": grp, "n": n,
                             "n_above_tau": above, "rate": round(above / n, 6)})
    return rows


def check(rows):
    """The reproduced gaps must match w3_direction.csv to the digit."""
    want = {}
    for r in csv.DictReader(open(W3_DIRECTION)):
        if r["metric"] in ("direction_correct", "direction_not_correct"):
            want[(r["form"], r["metric"])] = (float(r["value"]), int(r["n_below_in_group"]),
                                              int(r["n_above_in_group"]))
    ok = True
    idx = {(r["form"], r["arm"], r["group"]): r for r in rows}
    for form in ("A", "B"):
        for grp, metric in (("corr", "direction_correct"), ("ncorr", "direction_not_correct")):
            b, a = idx[(form, "below_good", grp)], idx[(form, "above_good", grp)]
            gap = a["rate"] - b["rate"]
            w_gap, w_nb, w_na = want[(form, metric)]
            good = abs(gap - w_gap) < 5e-6 and b["n"] == w_nb and a["n"] == w_na
            ok &= good
            print("%s form %s %-20s gap %+.6f vs csv %+.6f  n_below %d/%d  n_above %d/%d"
                  % ("ok  " if good else "FAIL", form, metric, gap, w_gap,
                     b["n"], w_nb, a["n"], w_na))
    return ok


def self_prediction():
    """Pre-freeze sanity check: with p_a, p_b set to W3's OWN achieved comprehension, the
    mixture formula must reproduce W3's own aggregate landing gap to the digit. If it does
    not, the formula or the filter is wrong before any W11 token exists."""
    rows = {(r["form"], r["arm"], r["group"]): r for r in cells()}
    want = {}
    for r in csv.DictReader(open(ROOT / "analysis" / "out" / "w3_behaviour.csv")):
        if (r["metric"] == "landing_gap" and r["extractor"] == "judge"
                and r["convention"] == "strict_gt"):
            want[r["form"]] = float(r["value"])
    ok = True
    for form in ("A", "B"):
        m = {}
        for arm in ("below_good", "above_good"):
            c, nc = rows[(form, arm, "corr")], rows[(form, arm, "ncorr")]
            p = c["n"] / (c["n"] + nc["n"])
            m[arm] = p * c["rate"] + (1 - p) * nc["rate"]
        gap = m["above_good"] - m["below_good"]
        good = abs(gap - want[form]) < 1e-4
        ok &= good
        print("%s form %s mixture-reconstructed gap %+.6f vs w3_behaviour.csv %+.6f "
              "(below %.4f above %.4f)"
              % ("ok  " if good else "FAIL", form, gap, want[form],
                 m["below_good"], m["above_good"]))
    return ok


if __name__ == "__main__":
    rows = cells()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    for r in rows:
        print(json.dumps(r))
    print("\nwrote", OUT, "\n")
    ok = check(rows)
    print()
    ok &= self_prediction()
    sys.exit(0 if ok else 1)
