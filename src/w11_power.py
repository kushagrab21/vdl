"""PR-007 item 5: the PRE-FREEZE noise-floor / resolving-power simulation, under R-013.

The question the design must answer: with comprehension lifted, does the aggregate landing
gap move to where the belief-mixture model says it must (a), or stay where W3 left it (b)?

Two worlds, simulated at the arm level:

  (a) MIXTURE TRUE      true comprehension = P_LIFT in both arms; a trace's landing
                        probability is its cell's W3 rate, chosen by its true belief.
  (b) ANNOTATION TRUE   comprehension label rises to P_LIFT but is a post-hoc annotation:
                        each arm's landing rate stays at its W3 MARGINAL, and the label is
                        drawn independently of landing. The aggregate gap is unchanged.

The decision statistic is PR-007 item 6's: observed gap inside the prediction interval
(C1) or outside it (C2). Two interval definitions are simulated because they are not the
same instrument:

  PI-T  "true-gap" interval — PR-007 item 4 as literally worded: binomial error in the
        four W3 cells and in the achieved comprehension rates ONLY.
  PI-O  "observed-gap" predictive interval — PI-T convolved with the binomial scatter of
        the observed gap itself at n per side. This is the interval an observed number
        should be compared against.

  python3 src/w11_power.py                     # the grid, both intervals
  python3 src/w11_power.py --n 100 --inner 100000 --outer 20000
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CELLS = ROOT / "analysis" / "out" / "w11_w3_cells.csv"
OUT = ROOT / "analysis" / "out" / "w11_power.csv"

SEED = 11007                       # pinned; the sim is regenerable to the digit
P_LIFT = 0.85                      # PR-007 item 5's assumed lifted comprehension
ALPHA = 0.05


def load_cells():
    c, ns = {}, {}
    for r in csv.DictReader(open(CELLS)):
        c[(r["form"], r["arm"], r["group"])] = float(r["rate"])
        ns[(r["form"], r["arm"], r["group"])] = int(r["n"])
    return c, ns


def w3_marginals(form, c, ns):
    """W3's own arm-level landing rates, reconstructed from the cells and W3's own p."""
    out = {}
    for arm in ("below_good", "above_good"):
        n_c, n_n = ns[(form, arm, "corr")], ns[(form, arm, "ncorr")]
        p = n_c / (n_c + n_n)
        out[arm] = p * c[(form, arm, "corr")] + (1 - p) * c[(form, arm, "ncorr")]
    return out


def run(n, cells, ns, rng, n_outer, n_inner):
    res = {}
    K = n_inner
    for form in ("A", "B"):
        c_ac, c_an = cells[(form, "above_good", "corr")], cells[(form, "above_good", "ncorr")]
        c_bc, c_bn = cells[(form, "below_good", "corr")], cells[(form, "below_good", "ncorr")]
        n_ac, n_an = ns[(form, "above_good", "corr")], ns[(form, "above_good", "ncorr")]
        n_bc, n_bn = ns[(form, "below_good", "corr")], ns[(form, "below_good", "ncorr")]
        marg = w3_marginals(form, cells, ns)
        gap_w3 = marg["above_good"] - marg["below_good"]

        # --- inner: K draws of the four W3 cells, shared across outer replicates
        d_ac = rng.binomial(n_ac, c_ac, K) / n_ac
        d_an = rng.binomial(n_an, c_an, K) / n_an
        d_bc = rng.binomial(n_bc, c_bc, K) / n_bc
        d_bn = rng.binomial(n_bn, c_bn, K) / n_bn

        cache = {}

        def bounds(k_a, k_b, mode):
            key = (k_a, k_b, mode)
            if key in cache:
                return cache[key]
            pa = rng.binomial(n, k_a / n, K) / n
            pb = rng.binomial(n, k_b / n, K) / n
            r_a = pa * d_ac + (1 - pa) * d_an
            r_b = pb * d_bc + (1 - pb) * d_bn
            if mode == "PI-O":
                r_a = rng.binomial(n, np.clip(r_a, 0, 1)) / n
                r_b = rng.binomial(n, np.clip(r_b, 0, 1)) / n
            g = r_a - r_b
            out = (float(np.quantile(g, ALPHA / 2)), float(np.quantile(g, 1 - ALPHA / 2)),
                   float(np.mean(pa * d_ac + (1 - pa) * d_an - pb * d_bc - (1 - pb) * d_bn)))
            cache[key] = out
            return out

        for scen in ("a_mixture", "b_annotation"):
            if scen == "a_mixture":
                k_a = rng.binomial(n, P_LIFT, n_outer)
                k_b = rng.binomial(n, P_LIFT, n_outer)
                land_a = rng.binomial(k_a, c_ac) + rng.binomial(n - k_a, c_an)
                land_b = rng.binomial(k_b, c_bc) + rng.binomial(n - k_b, c_bn)
            else:
                k_a = rng.binomial(n, P_LIFT, n_outer)
                k_b = rng.binomial(n, P_LIFT, n_outer)
                land_a = rng.binomial(n, marg["above_good"], n_outer)
                land_b = rng.binomial(n, marg["below_good"], n_outer)
            obs = (land_a - land_b) / n
            for mode in ("PI-T", "PI-O"):
                inside = np.empty(n_outer, dtype=bool)
                for i in range(n_outer):
                    lo, hi, _ = bounds(int(k_a[i]), int(k_b[i]), mode)
                    inside[i] = lo <= obs[i] <= hi
                res[(form, scen, mode)] = {
                    "form": form, "scenario": scen, "interval": mode, "n_per_arm": n,
                    "p_lift": P_LIFT, "gap_w3": round(gap_w3, 6),
                    "mean_obs_gap": round(float(obs.mean()), 6),
                    "mean_gap_pred": round(float(np.mean([bounds(int(a), int(b), mode)[2]
                                                          for a, b in zip(k_a[:200], k_b[:200])])), 6),
                    "P_inside": round(float(inside.mean()), 4),
                    "P_outside": round(float(1 - inside.mean()), 4),
                    "correct_verdict": round(float(inside.mean() if scen == "a_mixture"
                                                   else 1 - inside.mean()), 4)}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="*", default=[100, 150, 200, 300])
    ap.add_argument("--outer", type=int, default=4000)
    ap.add_argument("--inner", type=int, default=100000)
    a = ap.parse_args()
    cells, ns = load_cells()
    rows = []
    for n in a.n:
        rng = np.random.default_rng(SEED + n)
        res = run(n, cells, ns, rng, a.outer, a.inner)
        for form in ("A", "B"):
            for mode in ("PI-T", "PI-O"):
                ra = res[(form, "a_mixture", mode)]
                rb = res[(form, "b_annotation", mode)]
                row = {"n_per_arm": n, "form": form, "interval": mode,
                       "gap_w3": ra["gap_w3"],
                       "mean_obs_gap_if_mixture": ra["mean_obs_gap"],
                       "mean_obs_gap_if_annotation": rb["mean_obs_gap"],
                       "mean_gap_pred": ra["mean_gap_pred"],
                       "P_C1_if_mixture": ra["correct_verdict"],
                       "P_C2_if_annotation": rb["correct_verdict"],
                       "distinguishing_power": round(min(ra["correct_verdict"],
                                                         rb["correct_verdict"]), 4)}
                rows.append(row)
                print(json.dumps(row))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print("\nwrote", OUT)
    print("outer=%d inner=%d seed=%d P_LIFT=%.2f" % (a.outer, a.inner, SEED, P_LIFT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
