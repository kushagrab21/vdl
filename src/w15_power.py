"""PR-011 item 5 / R-013-as-amended: the pre-freeze simulations for the W15 transplant.

Two worlds, both simulated BEFORE any W15 token exists.

  NULL        the transplant does nothing a generic perturbation would not do. SWAP, SELF and
              RAND all sit at the same landing rate, offset from SHAM by delta_gen and jittered
              by an arm-level term. Both are CALIBRATED FROM W7b: its 12 perturbed arms pooled
              P(>tau)=0.4750 against the reused alpha=0 sham's 0.6800 (delta_gen = -0.2050 in
              the "lands above" coordinate) with an across-arm sd of 0.0862, of which
              sqrt(0.0862^2 - 0.0706^2) = 0.0495 is over and above binomial.

  ALTERNATIVE belief-upstream is true and the swapped state carries landing: SWAP additionally
              moves toward B's side by delta_true, whose headline value is the belief-conditional
              gap +0.45 (E-005, form B).

Two structural facts of THIS design are in both worlds:

  q0          P(the continuation lands on B's side | SHAM). A is the p-hat=+1 member, so B's
              side is BELOW, and W3's form-B above_good/corr cell lands above at 0.7927:
              q0 = 0.2073. (Mirror: A is the p-hat=-1 member, B's side is ABOVE, q0 = 0.2794.)
  lam         the LOCKED fraction: traces whose `final` literal is already emitted before the
              cut point, where no edit downstream of the cut can move the landing. Measured on
              W3 form-B above_good at the W15 cut rule: see --lam-measured.

Statistic and rule are the ones PR-011 freezes: Delta_a = P(lands toward B | a) - P(... | SHAM),
95 % percentile bootstrap over PAIRS (one resample index shared by every statistic), and the
landing half of row T1 fires only when CI(Delta_swap), CI(Delta_swap - Delta_rand) and
CI(Delta_swap - Delta_self) all exclude zero.

  python3 src/w15_power.py --lam-measured
  python3 src/w15_power.py --grid
  python3 src/w15_power.py --mde --n 40
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"

# ---- calibration constants, all from committed files -------------------------------
Q0_PRIMARY = 1.0 - 0.792683          # w11_w3_cells.csv  B/above_good/corr
Q0_MIRROR = 0.279412                 # w11_w3_cells.csv  B/above_good/ncorr
DELTA_GEN = 0.4750 - 0.6800          # w7b_arms.csv pooled vs w7_arms.csv B_above_sham
SIGMA_ARM = 0.0495                   # w7b across-arm sd net of binomial
GAP_BELIEF = 0.4456                  # w3_direction.csv form B direction_correct gap
CUT_BACKOFF = 25                     # W12's rule, kept
N_BOOT = 1000                        # sim-side bootstrap (the analysis uses 10,000)
N_REP = 1000
SEED = 15011


def measured_lam():
    """The locked fraction on W3 form-B above_good under the W15 cut rule (loosened: the
    settle-position constraint is dropped, so a cut point is valid iff belief_gen_pos >= 25)."""
    d = json.loads((OUT / "w4_positions" / "w4_positions_B_above_good.json").read_text())
    by = {}
    for p in d["points"]:
        by.setdefault(p["trace_i"], []).append(p)
    n_valid = n_locked = 0
    for ps in by.values():
        eop = [p for p in ps if p["kind"] == "end_of_prompt"]
        bel = [p for p in ps if p["kind"] == "belief"]
        fin = [p for p in ps if p["kind"] == "final"]
        if not (eop and bel and fin):
            continue
        npr = eop[0]["token_index"] + 1
        cut = bel[0]["token_index"] - npr - CUT_BACKOFF
        if cut < 0:
            continue
        n_valid += 1
        n_locked += int(fin[0]["token_index"] - npr < cut)
    return n_locked / n_valid, n_valid, n_locked


def one_world(rng, n_pairs, q0, lam, delta_true, delta_gen, sigma_arm, n_rep, n_boot):
    """Returns a dict of firing rates for the three candidate rules plus E[Delta_swap]."""
    fire_t1 = fire_swap = fire_rand = fire_c = 0
    dsw = np.empty(n_rep)
    for r in range(n_rep):
        e = rng.normal(0.0, sigma_arm, size=3)            # swap, self, rand
        m = np.array([q0,                                  # SHAM
                      q0 + delta_gen + e[0] + delta_true,  # SWAP
                      q0 + delta_gen + e[1],               # SELF
                      q0 + delta_gen + e[2]])              # RAND
        m = np.clip(m, 0.01, 0.99)
        locked = rng.random(n_pairs) < lam
        shared = (rng.random(n_pairs) < q0).astype(np.int8)
        runl = np.clip((m - lam * q0) / (1.0 - lam), 0.0, 1.0) if lam < 1 else m * 0
        y = np.empty((4, n_pairs), dtype=np.int8)
        for a in range(4):
            free = (rng.random(n_pairs) < runl[a]).astype(np.int8)
            y[a] = np.where(locked, shared, free)
        d_swap = (y[1] - y[0]).astype(np.float64)
        d_self = (y[2] - y[0]).astype(np.float64)
        d_rand = (y[3] - y[0]).astype(np.float64)
        idx = rng.integers(0, n_pairs, size=(n_boot, n_pairs))
        bs, bl, br = d_swap[idx].mean(1), d_self[idx].mean(1), d_rand[idx].mean(1)
        ci = lambda v: (np.percentile(v, 2.5), np.percentile(v, 97.5))
        ex = lambda lo_hi: lo_hi[0] > 0 or lo_hi[1] < 0
        f_s, f_sr, f_ss = ex(ci(bs)), ex(ci(bs - br)), ex(ci(bs - bl))
        # RULE C (contrast-only, signed): both contrasts positive and clear of zero.
        pos = (np.percentile(bs - br, 2.5) > 0) and (np.percentile(bs - bl, 2.5) > 0)
        fire_t1 += int(f_s and f_sr and f_ss)
        fire_c += int(pos)
        fire_swap += int(f_s)
        fire_rand += int(ex(ci(br)))
        dsw[r] = d_swap.mean()
    return {"t1_all3": fire_t1 / n_rep, "ruleC_contrast_only": fire_c / n_rep,
            "swap_alone": fire_swap / n_rep, "rand_alone": fire_rand / n_rep,
            "mean_delta_swap": float(dsw.mean())}


def grid(args, lam):
    rows = []
    ns = args.ns
    deltas = [0.0] + args.deltas
    for direction, q0 in (("primary", Q0_PRIMARY), ("mirror", Q0_MIRROR)):
      for dg in args.dgens:
        for n in ns:
            for dt in deltas:
                rng = np.random.default_rng(SEED + n * 97 + int(dt * 1000)
                                            + int(abs(dg) * 10000)
                                            + (0 if direction == "primary" else 7))
                sgn = +1.0 if direction == "primary" else -1.0
                # delta_gen is a shift in "lands ABOVE"; B's side is BELOW in the primary
                # direction and ABOVE in the mirror, so its sign flips between them.
                res = one_world(rng, n, q0, lam, dt, -sgn * dg,
                                args.sigma, args.reps, N_BOOT)
                rows.append({"direction": direction, "world": "null" if dt == 0 else "alt",
                             "n_pairs": n, "delta_true": round(dt, 4), "lam": round(lam, 4),
                             "q0": round(q0, 4), "delta_gen_applied": round(-sgn * dg, 4),
                             "sigma_arm": args.sigma,
                             "fire_T1_all3": round(res["t1_all3"], 4),
                             "fire_ruleC_contrast_only": round(res["ruleC_contrast_only"], 4),
                             "fire_swap_alone": round(res["swap_alone"], 4),
                             "fire_rand_alone": round(res["rand_alone"], 4),
                             "mean_delta_swap": round(res["mean_delta_swap"], 4)})
                print("%-8s %-4s dgen=%+.3f n=%-3d delta=%.3f -> T1(all3) %.3f | "
                      "ruleC %.3f | swap-alone %.3f | rand-alone %.3f | E[D_swap] %+.3f"
                      % (direction, rows[-1]["world"], -sgn * dg, n, dt, res["t1_all3"],
                         res["ruleC_contrast_only"], res["swap_alone"], res["rand_alone"],
                         res["mean_delta_swap"]), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lam-measured", action="store_true")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--mde", action="store_true")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--ns", type=int, nargs="*", default=[25, 40, 60])
    ap.add_argument("--deltas", type=float, nargs="*",
                    default=[0.10, 0.20, 0.30, GAP_BELIEF, 0.5133])
    ap.add_argument("--sigma", type=float, default=SIGMA_ARM)
    ap.add_argument("--dgens", type=float, nargs="*", default=[DELTA_GEN, -0.10, 0.0])
    ap.add_argument("--lam", type=float, default=None)
    ap.add_argument("--reps", type=int, default=N_REP)
    a = ap.parse_args()

    lam_m, n_valid, n_locked = measured_lam()
    lam = a.lam if a.lam is not None else lam_m
    print("locked fraction lam (final literal precedes the cut point) = %d/%d = %.4f"
          % (n_locked, n_valid, lam_m))
    print("q0 primary %.4f | q0 mirror %.4f | delta_gen %.4f | sigma_arm %.4f | lam used %.4f"
          % (Q0_PRIMARY, Q0_MIRROR, DELTA_GEN, a.sigma, lam))
    if a.lam_measured and not (a.grid or a.mde):
        return 0

    rows = []
    if a.grid:
        rows = grid(a, lam)
        with open(OUT / "w15_power.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print("wrote", OUT / "w15_power.csv")
    if a.mde:
        print("\nMDE search, primary direction, n=%d pairs, lam=%.4f" % (a.n, lam))
        mrows = []
        for dt in [0.05 * k for k in range(0, 13)]:
            for direction, q0, sgn in (("primary", Q0_PRIMARY, +1.0),
                                       ("mirror", Q0_MIRROR, -1.0)):
                rng = np.random.default_rng(SEED + 5000 + int(dt * 1000) + int(sgn) * 3)
                res = one_world(rng, a.n, q0, lam, dt, -sgn * DELTA_GEN,
                                a.sigma, a.reps, N_BOOT)
                mrows.append({"direction": direction, "n_pairs": a.n,
                              "delta_true": round(dt, 4),
                              "power_T1_all3": round(res["t1_all3"], 4),
                              "power_ruleC": round(res["ruleC_contrast_only"], 4),
                              "power_swap_alone": round(res["swap_alone"], 4)})
                print("  %-8s delta_true %.2f -> T1(all3) %.3f  ruleC %.3f  (swap alone %.3f)"
                      % (direction, dt, res["t1_all3"], res["ruleC_contrast_only"],
                         res["swap_alone"]))
        with open(OUT / "w15_power_mde.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(mrows[0].keys()))
            w.writeheader(); w.writerows(mrows)
        print("wrote", OUT / "w15_power_mde.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
