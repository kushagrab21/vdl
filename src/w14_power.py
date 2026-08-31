"""PR-010 item 5: the PRE-FREEZE simulation for W14, under R-013 as amended (R-015(1)).

W11 pushed comprehension UP and asked whether the gap followed the frozen mixture formula.
W14 pushes it DOWN with degraded wording and asks the same question in the other direction.
The design must be shown, before a token exists, to be able to tell these two worlds apart:

  (a) MIXTURE TRUE       comprehension really falls to (p_a, p_b); a trace lands at its
                         cell's W3 rate, chosen by its true belief. The gap FALLS.
  (b) ANNOTATION TRUE    the comprehension LABEL falls to (p_a, p_b) but landing is
                         untouched: each arm keeps a fixed marginal and the label is drawn
                         independently of landing. The gap does NOT move.
                         --alt w11 : marginals stay at W11's observed form-B rates
                                     (PR-010 item 5 as literally worded: "gap stays at
                                     W11's level")
                         --alt w3  : marginals stay at W3's form-B rates — the HARDER
                                     null, since W14's wording is degraded relative to W3,
                                     not to W11. Reported beside it.

Decision statistic: PR-010 item 4's PI-T interval (binomial error in the four FIXED W3
cells at W3's group sizes, and in the achieved comprehension rates at n) — the same
instrument PR-007 item 4 froze and w11_power.py measured at 0.973 coverage.

p_b under degradation is not free: item 5's grid is over p_a only, so a rule is needed.
Three are simulated and all three are reported (JC-2):
  offset  p_b = p_a + (W3_below - W3_above)   both arms fall by the same amount  [PRIMARY]
  equal   p_b = p_a                           both arms fall to the same level
  fixed   p_b = W3_below                      only the above_good arm degrades

  python3 src/w14_power.py                                   # the full grid
  python3 src/w14_power.py --pa 0.30 0.40 0.50 --n 150 250
  python3 src/w14_power.py --mde-only
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CELLS = ROOT / "analysis" / "out" / "w11_w3_cells.csv"
W11_ARMS = ROOT / "analysis" / "out" / "w11_arms.csv"
OUT = ROOT / "analysis" / "out" / "w14_power.csv"

SEED = 14007
ALPHA = 0.05
FORM = "B"
W3_P = {"above_good": 82 / 150, "below_good": 121 / 150}   # W3 form-B comprehension


def load_cells():
    c, ns = {}, {}
    for r in csv.DictReader(open(CELLS)):
        if r["form"] != FORM:
            continue
        c[(r["arm"], r["group"])] = float(r["rate"])
        ns[(r["arm"], r["group"])] = int(r["n"])
    return c, ns


def marginals(c, ns, source):
    """source='w3' -> W3's own arm landing rates, rebuilt from cells and W3's own p.
       source='w11' -> W11's OBSERVED form-B landing rates, read from w11_arms.csv."""
    if source == "w3":
        out = {}
        for arm in ("below_good", "above_good"):
            p = W3_P[arm]
            out[arm] = p * c[(arm, "corr")] + (1 - p) * c[(arm, "ncorr")]
        return out
    out = {}
    for r in csv.DictReader(open(W11_ARMS)):
        if r["form"] == FORM:
            out[r["arm"]] = float(r["landing_judge"])
    return out


def pb_rule(p_a, rule):
    if rule == "offset":
        return float(np.clip(p_a + (W3_P["below_good"] - W3_P["above_good"]), 0.0, 1.0))
    if rule == "equal":
        return p_a
    return W3_P["below_good"]


def _bounds_factory(c, ns, n, K, rng):
    d = {g: rng.binomial(ns[g], c[g], K) / ns[g]
         for g in (("above_good", "corr"), ("above_good", "ncorr"),
                   ("below_good", "corr"), ("below_good", "ncorr"))}
    cache = {}

    def bounds(k_a, k_b):
        key = (k_a, k_b)
        if key in cache:
            return cache[key]
        pa = rng.binomial(n, k_a / n, K) / n
        pb = rng.binomial(n, k_b / n, K) / n
        g = ((pa * d[("above_good", "corr")] + (1 - pa) * d[("above_good", "ncorr")])
             - (pb * d[("below_good", "corr")] + (1 - pb) * d[("below_good", "ncorr")]))
        cache[key] = (float(np.quantile(g, ALPHA / 2)), float(np.quantile(g, 1 - ALPHA / 2)))
        return cache[key]
    return bounds


def point_gap(c, p_a, p_b):
    return (p_a * c[("above_good", "corr")] + (1 - p_a) * c[("above_good", "ncorr")]
            - p_b * c[("below_good", "corr")] - (1 - p_b) * c[("below_good", "ncorr")])


def run_cell(n, p_a, p_b, c, ns, marg, rng, n_outer, K):
    bounds = _bounds_factory(c, ns, n, K, rng)
    res = {}
    for scen in ("a_mixture", "b_annotation"):
        k_a = rng.binomial(n, p_a, n_outer)
        k_b = rng.binomial(n, p_b, n_outer)
        if scen == "a_mixture":
            land_a = rng.binomial(k_a, c[("above_good", "corr")]) + \
                     rng.binomial(n - k_a, c[("above_good", "ncorr")])
            land_b = rng.binomial(k_b, c[("below_good", "corr")]) + \
                     rng.binomial(n - k_b, c[("below_good", "ncorr")])
        else:
            land_a = rng.binomial(n, marg["above_good"], n_outer)
            land_b = rng.binomial(n, marg["below_good"], n_outer)
        obs = (land_a - land_b) / n
        inside = np.empty(n_outer, dtype=bool)
        for i in range(n_outer):
            lo, hi = bounds(int(k_a[i]), int(k_b[i]))
            inside[i] = lo <= obs[i] <= hi
        res[scen] = (float(inside.mean()), float(obs.mean()))
    lo, hi = bounds(int(round(n * p_a)), int(round(n * p_b)))
    return res, (lo, hi)


def mde(n, p_a, p_b, c, ns, rng, n_outer, K, target=0.80):
    """The smallest displacement of the TRUE aggregate gap away from the mixture
    prediction that this design rejects (falls outside the interval) with `target`
    probability. Displacement is applied to the above_good arm's landing rate."""
    bounds = _bounds_factory(c, ns, n, K, rng)
    base = point_gap(c, p_a, p_b)
    b_marg = p_b * c[("below_good", "corr")] + (1 - p_b) * c[("below_good", "ncorr")]
    for delta in np.arange(0.0, 0.60, 0.01):
        a_rate = float(np.clip(base + b_marg + delta, 0, 1))
        k_a = rng.binomial(n, p_a, n_outer)
        k_b = rng.binomial(n, p_b, n_outer)
        obs = (rng.binomial(n, a_rate, n_outer) - rng.binomial(n, b_marg, n_outer)) / n
        out = 0
        for i in range(n_outer):
            lo, hi = bounds(int(k_a[i]), int(k_b[i]))
            out += not (lo <= obs[i] <= hi)
        if out / n_outer >= target:
            return round(float(delta), 3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pa", type=float, nargs="*", default=[0.30, 0.40, 0.50])
    ap.add_argument("--n", type=int, nargs="*", default=[150, 200, 250, 300])
    ap.add_argument("--rules", nargs="*", default=["offset", "equal", "fixed"])
    ap.add_argument("--alts", nargs="*", default=["w11", "w3"])
    ap.add_argument("--outer", type=int, default=4000)
    ap.add_argument("--inner", type=int, default=100000)
    ap.add_argument("--mde-only", action="store_true")
    a = ap.parse_args()

    c, ns = load_cells()
    margs = {s: marginals(c, ns, s) for s in ("w3", "w11")}
    print("W3 form-B comprehension: above %.4f  below %.4f" % (W3_P["above_good"], W3_P["below_good"]))
    print("marginals w3 : %s" % json.dumps({k: round(v, 4) for k, v in margs["w3"].items()}))
    print("marginals w11: %s" % json.dumps({k: round(v, 4) for k, v in margs["w11"].items()}))
    print("W3 gap %.4f   W11 gap %.4f\n"
          % (margs["w3"]["above_good"] - margs["w3"]["below_good"],
             margs["w11"]["above_good"] - margs["w11"]["below_good"]))

    rows = []
    for n in a.n:
        for p_a in a.pa:
            for rule in a.rules:
                p_b = pb_rule(p_a, rule)
                rng = np.random.default_rng(SEED + n * 100 + int(p_a * 100))
                for alt in a.alts:
                    res, (lo, hi) = run_cell(n, p_a, p_b, c, ns, margs[alt], rng,
                                             a.outer, a.inner)
                    p_in_a = res["a_mixture"][0]
                    p_out_b = 1 - res["b_annotation"][0]
                    row = {"n_per_arm": n, "p_a": p_a, "p_b": round(p_b, 4), "pb_rule": rule,
                           "alt_world": alt,
                           "gap_pred": round(point_gap(c, p_a, p_b), 4),
                           "pred_lo": round(lo, 4), "pred_hi": round(hi, 4),
                           "mean_obs_gap_if_mixture": round(res["a_mixture"][1], 4),
                           "mean_obs_gap_if_annotation": round(res["b_annotation"][1], 4),
                           "P_inside_if_mixture": round(p_in_a, 4),
                           "P_outside_if_annotation": round(p_out_b, 4),
                           "distinguishing_power": round(min(p_in_a, p_out_b), 4)}
                    rows.append(row)
                    print(json.dumps(row))
        print()

    print("=== MDE: smallest true-gap displacement rejected with 0.80 probability ===")
    mdes = []
    for n in a.n:
        for p_a in a.pa:
            rng = np.random.default_rng(SEED + 7 + n)
            p_b = pb_rule(p_a, "offset")
            d = mde(n, p_a, p_b, c, ns, rng, min(a.outer, 2000), a.inner)
            mdes.append({"n_per_arm": n, "p_a": p_a, "p_b": round(p_b, 4),
                         "pb_rule": "offset", "mde_gap_units": d})
            print(json.dumps(mdes[-1]))

    if not a.mde_only:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        (OUT.parent / "w14_power_mde.csv").write_text(
            "n_per_arm,p_a,p_b,pb_rule,mde_gap_units\n"
            + "\n".join("%d,%.2f,%.4f,%s,%s" % (m["n_per_arm"], m["p_a"], m["p_b"],
                                                m["pb_rule"], m["mde_gap_units"])
                        for m in mdes) + "\n")
        print("\nwrote", OUT, "and w14_power_mde.csv")
    print("outer=%d inner=%d seed=%d" % (a.outer, a.inner, SEED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
