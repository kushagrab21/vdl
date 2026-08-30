"""W12 addendum, computed AFTER the freeze and labelled descriptive throughout.

Two things PR-008 did not freeze but the work order's acceptance checks ask for:

  (1) ABSOLUTE early bins.  Acceptance check 4 asks for accuracy "at the earliest bins
      (0-25, 25-50 tokens into the trace)".  PR-008's alignment (a) is trace-FRACTION
      deciles, so the absolute-offset bins are computed here, with the identical probe,
      folds and 500-permutation null.  Alignment (c): [0,25), [25,50), [50,75), [75,100).

  (2) The trajectory-score envelope, which is what makes the flip count readable.

  python src/w12_extra.py --procs 32
"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import analyze_w12 as az                                    # noqa: E402

ABS_BINS = [(0, 25), (25, 50), (50, 75), (75, 100)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    idx = az.load_index()
    traces, cells = az.cell_plan(idx)
    # alignment (c): absolute token offset from the start of the generation
    for t in traces:
        for b, (lo, hi) in enumerate(ABS_BINS):
            g = [x for x in range(lo, min(hi, t["n_gen"]))]
            if g:
                cells[(t["u"], "c", b)] = g
    M, keys, kpos, _ = az.reduce_shards(idx, traces, cells)
    sel_all = [t["u"] for t in traces]
    sel_ag = [t["u"] for t in traces if t["arm"] == "above_good"]

    saveN, saveD = az.N_DECILE, az.N_OFFBIN
    az.N_DECILE, az.N_OFFBIN = len(ABS_BINS), 0
    rows = []
    for fam, sel, ctr in (("primary", sel_all, True), ("control_arm", sel_all, True),
                          ("above_good", sel_ag, False)):
        # run_family loops alignments ("a","b"); temporarily relabel "a" -> the abs bins
        orig = az.bin_label
        az.bin_label = lambda al, b: ("[%d,%d) tokens into the trace" % ABS_BINS[b]
                                      if al == "a" else orig(al, b))
        cc = {k: v for k, v in cells.items() if k[1] == "c"}
        kk = {(u, "a", b): kpos[(u, "c", b)] for (u, _, b) in cc}
        r = az.run_family(fam, M, keys, kk, traces, sel, ctr, az.N_PERM, a.procs)
        rows += [dict(x, alignment="c") for x in r if x["alignment"] == "a"]
        az.bin_label = orig
    az.N_DECILE, az.N_OFFBIN = saveN, saveD
    with open(ROOT / "analysis/out/w12_curves_abs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    for r in rows:
        if r["layer"] == 29 or r["family"] == "above_good":
            print("%-12s L%-3s %-34s bacc=%s p=%s null_p95=%s"
                  % (r["family"], r["layer"], r["bin_label"], r["bacc"], r["p_value"],
                     r["null_p95"]))
    print("wrote analysis/out/w12_curves_abs.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
