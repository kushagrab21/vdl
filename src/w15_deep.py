"""JC-4: the DECLARED POST-FREEZE DIAGNOSTIC that bounds W15's frozen null.

NOT PR-011's experiment and never mixed with it. Same 40 pairs, same four arms, same seeds,
same edit, at a cut placed at 40 % of A's generated length instead of 25 tokens before its
first cause-token. It exists because the frozen cut leaves the continuation almost no
surface -- only 6 of 40 reconstructions carry their final literal inside the continuation --
so a null measured there cannot distinguish "the belief is not transplantable" from "the
operation had nothing left to act on".

  python3 src/w15_deep.py
"""
import csv
import json
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))
from replay_w4 import final_corrected_span  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
TAU = 4500000000
OUT = ROOT / "analysis" / "out"
ARMS = ("SHAM", "SWAP", "SELF", "RAND")


def surface(rows_by_arm, n):
    fic = dtxt = dfin = 0
    for i in n:
        s, w = rows_by_arm["SHAM"][i], rows_by_arm["SWAP"][i]
        fc = final_corrected_span(s["visible_answer"] or "", TAU)
        va, full = s["visible_answer"] or "", s["reconstructed"]
        if fc:
            fic += int(full.rfind(va) + fc[1] >= len(s["prefix_text"]))
        dtxt += int(s["continuation_text"] != w["continuation_text"])
        fw = final_corrected_span(w["visible_answer"] or "", TAU)
        dfin += int((fc[0] if fc else None) != (fw[0] if fw else None))
    return fic, dtxt, dfin


def run(path, tag, dirc, numc, out_rows):
    d = json.loads(path.read_text())
    by = {}
    for r in d["rows"]:
        by.setdefault(r["arm"], {})[r["pair_index"]] = r
    n = sorted(by["SHAM"])
    fic, dtxt, dfin = surface(by, n)
    cl = [by["SHAM"][i]["n_continuation_tokens"] for i in n]
    cols, verb = {}, {}
    for a in ARMS:
        y, v = [], []
        for i in n:
            r = by[a][i]
            fc = final_corrected_span(r["visible_answer"] or "", TAU)
            y.append(0 if not fc else int((fc[0] > TAU) == (r["B_phat"] == 1)))
            key = "%s|B|%s%s_%s|%d" % (MODEL, "deep_" if tag == "deep" else "",
                                       r["direction"], a, i)
            jd = (dirc.get(key) or {}).get("direction")
            v.append(0 if jd not in ("correct", "incorrect")
                     else int((+1 if jd == "correct" else -1) == r["B_phat"]))
        cols[a] = np.array(y, float)
        verb[a] = np.array(v, float)
    rng = np.random.default_rng(15200)
    idx = rng.integers(0, len(n), size=(10000, len(n)))
    for label, C in (("landing_regex_corr", cols), ("verbalized", verb)):
        ds = {k: C[k.upper()] - C["SHAM"] for k in ("swap", "self", "rand")}
        ds["swap_minus_rand"] = ds["swap"] - ds["rand"]
        ds["swap_minus_self"] = ds["swap"] - ds["self"]
        for k, v in ds.items():
            b = v[idx].mean(1)
            lo, hi = float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))
            out_rows.append({"run": tag, "outcome": label, "statistic": k, "n_pairs": len(n),
                             "value": round(float(v.mean()), 4), "ci_lo": round(lo, 4),
                             "ci_hi": round(hi, 4),
                             "strictly_positive": int(lo > 0),
                             "excludes_zero": int(lo > 0 or hi < 0)})
    print("[%s] cut rule: %s" % (tag, d.get("cut_rule", "PR-011")))
    print("  pairs %d | median continuation %d tokens (min %d max %d)"
          % (len(n), statistics.median(cl), min(cl), max(cl)))
    print("  SURFACE  final literal inside the continuation %d/%d | SWAP text differs from "
          "SHAM %d/%d | final VALUE differs %d/%d" % (fic, len(n), dtxt, len(n), dfin, len(n)))
    print("  P(toward B) " + "  ".join("%s %.4f" % (a, cols[a].mean()) for a in ARMS))
    print("  verbalized  " + "  ".join("%s %.4f" % (a, verb[a].mean()) for a in ARMS))
    return {"run": tag, "n_pairs": len(n), "final_in_continuation": fic,
            "swap_text_differs": dtxt, "swap_final_value_differs": dfin,
            "median_continuation_tokens": statistics.median(cl)}


if __name__ == "__main__":
    dirc = json.loads((OUT / "w15_direction_cache.json").read_text())
    numc = {}
    rows, surf = [], []
    surf.append(run(ROOT / "runs/w15_transplant/primary.json", "frozen_primary", dirc, numc, rows))
    surf.append(run(ROOT / "runs/w15_transplant_deep/primary.json", "deep", dirc, numc, rows))
    with open(OUT / "w15_deep.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    with open(OUT / "w15_surface.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(surf[0].keys()))
        w.writeheader(); w.writerows(surf)
    print("\n%-14s %-18s %-16s %9s  %s" % ("run", "outcome", "statistic", "value", "95% CI"))
    for r in rows:
        print("%-14s %-18s %-16s %+9.4f  [%+.4f, %+.4f] %s"
              % (r["run"], r["outcome"], r["statistic"], r["value"], r["ci_lo"], r["ci_hi"],
                 "EXCLUDES 0" if r["excludes_zero"] else ""))
    print("\nwrote w15_deep.csv w15_surface.csv")
