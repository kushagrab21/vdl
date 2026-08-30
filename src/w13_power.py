"""PR-009 item 4 · the R-013-as-amended (R-015(1)) pre-freeze simulations for W13.

R-013 required a null simulation. R-015(1) amends it: every pre-freeze simulation must cover
the null AND a calibrated alternative, and state the minimum detectable effect. This file does
all three for the ONE statistic W13 freezes -- the stratified incremental-validity test.

  world A, PURE LENGTH   labels are generated from trace length alone, calibrated so the
                         length-only probe reaches the observed 0.642. The activations are the
                         REAL analysis cell, so every position/length channel D-042 identified
                         is present at full strength. The stratified test must fire <= 5%.
  world B, GENUINE BELIEF the same length->label association PLUS a belief signal planted along
                         the real v_p̂(L27) direction, calibrated so the FULL-cell probe reaches
                         the observed 0.743 WITH the length channel also present. That makes the
                         planted belief component the SMALLEST one consistent with E-007, so the
                         reported power is a lower bound. The test must fire >= 80%.
  MDE                    the smallest planted signal -- reported as the full-cell balanced
                         accuracy it produces -- at which the test fires >= 80%.

JUDGMENT CALL (JC-1, declared in PR-009): the sims run on the REAL activations with SYNTHETIC
labels. No real p̂ label is read by this file. Using real activations is the point: an
isotropic-Gaussian sim would understate the false-fire rate, because the false-fire risk comes
precisely from the real residual stream's position/length structure.

  python3 src/w13_power.py --smoke     # tiny grid, smoke_ output
  python3 src/w13_power.py             # the real sims -> analysis/out/w13_sims.csv
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import w13_lengthcheck as lc                      # folds, probe, strata -- not data

OUT = ROOT / "analysis" / "out"

TARGET_LENGTH_BACC = 0.642     # D-042, the observed length-only number
TARGET_FULL_BACC = 0.743       # E-007, the observed number at l*
PRIOR_POS = 79.0 / 109.0       # the observed class prior of the cell (a covariate, not a label)
N_PERM_SIM = 150               # permutations behind each simulated replicate's null
N_REP_WORLD = 200              # replicates per headline world
N_REP_MDE = 60                # replicates per MDE grid point
SEED = 20260831
QUANTILES = (0.95, 0.975, 0.99)   # the criterion ladder, priced in the same sims


def draw_labels(rng, z, b, prior=PRIOR_POS):
    """P(y=+1) = sigmoid(a - b*z(n_gen)); a set so E[P(+1)] matches the observed prior."""
    a = np.log(prior / (1 - prior))
    p = 1.0 / (1.0 + np.exp(-(a - b * z)))
    return np.where(rng.random(z.size) < p, 1, -1).astype(np.int8)


def one_rep(arg):
    """One simulated dataset: draw labels, optionally plant signal, run one ladder rung."""
    (seed, b, s, Xl, tof, F, n_gen, strat, z, u, C, crit, variant) = arg
    rng = np.random.default_rng(seed)
    y = draw_labels(rng, z, b)
    Xs = Xl if s == 0.0 else Xl + np.float32(s) * y[tof][:, None] * u[None, :]

    sp_full = lc.splits(len(y), y)
    lo = lc.len_bacc(lc.prep_len_folds(F, sp_full), y)
    full = lc.act_bacc(lc.prep_folds(Xs, tof, sp_full), y)

    V = lc.variant_stat(Xs, tof, y, F, C, n_gen, variant,
                        0 if crit is not None else N_PERM_SIM, seed=seed + 77)
    if V is None:
        return dict(ok=False)
    q = ({k: crit for k in QUANTILES} if crit is not None
         else {k: float(np.quantile(V["null"], k)) for k in QUANTILES})
    out = dict(ok=True, n_keep=V["n_groups"], length_bacc=lo, full_bacc=full,
               strat_bacc=V["stat"], base_same_folds=V["base"], null_p95=q[0.95],
               fires=bool(V["stat"] > q[0.95] and V["stat"] > V["base"]))
    for k in QUANTILES:
        out["fires_q%d" % round(k * 1000)] = bool(V["stat"] > q[k] and V["stat"] > V["base"])
    return out


def run_world(pool, seeds, b, s, ctx, crit=None, variant="tercile"):
    jobs = [(sd, b, s) + ctx + (crit, variant) for sd in seeds]
    res = pool.map(one_rep, jobs, chunksize=1) if pool else [one_rep(j) for j in jobs]
    return [r for r in res if r["ok"]]


def summarise(tag, res):
    f = np.mean([r["fires"] for r in res])
    d = {"fire_rate_q%d" % round(k * 1000):
         float(np.mean([r["fires_q%d" % round(k * 1000)] for r in res])) for k in QUANTILES}
    return dict(world=tag, n_rep=len(res), fire_rate=float(f), **d,
                mean_length_bacc=float(np.mean([r["length_bacc"] for r in res])),
                mean_full_bacc=float(np.mean([r["full_bacc"] for r in res])),
                mean_strat_bacc=float(np.mean([r["strat_bacc"] for r in res])),
                mean_base_same_folds=float(np.mean([r["base_same_folds"] for r in res])),
                mean_null_p95=float(np.mean([r["null_p95"] for r in res])),
                mean_n_strata_kept=float(np.mean([r["n_keep"] for r in res])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--variants", default="tercile")
    ap.add_argument("--no-mde", action="store_true")
    ap.add_argument("--force-rung", default="")   # rung,quantile for the MDE sweep
    ap.add_argument("--mde-only", action="store_true")
    a = ap.parse_args()
    t0 = time.time()

    D = lc.load_cell()
    Xl = np.ascontiguousarray(D["X"][:, lc.PRIMARY_LAYER, :])
    tof, F, n_gen = D["tof"], D["F"], D["n_gen"]
    strat = lc.terciles(n_gen)
    z = (n_gen - n_gen.mean()) / n_gen.std()
    from safetensors.numpy import load_file
    u = load_file(str(OUT / "w5_vectors" / "w5_vphat_B.safetensors"))["vphat"][
        lc.PRIMARY_LAYER].astype(np.float32)
    u = u / np.linalg.norm(u)
    norm = float(np.linalg.norm(Xl, axis=1).mean())

    n_cal = 6 if a.smoke else 30
    n_world = 12 if a.smoke else N_REP_WORLD
    n_mde = 8 if a.smoke else N_REP_MDE
    C = np.stack([n_gen[tof], D["pos"]], axis=1)
    ctx = (Xl, tof, F, n_gen, strat, z, u, C)

    pool = None
    if a.procs > 1:
        import multiprocessing as mp
        pool = mp.get_context("fork").Pool(a.procs)

    rows = []
    # ---- calibration 1: b, so the length-only probe hits 0.642 -----------------------
    print("=== calibration 1 - length->label strength b ===")
    bgrid = [0.3, 0.5, 0.7, 0.9, 1.1, 1.4] if not a.smoke else [0.5, 0.9]
    cal = []
    for b in bgrid:
        r = run_world(pool, range(SEED, SEED + n_cal), b, 0.0, ctx, crit=0.5)
        v = float(np.mean([x["length_bacc"] for x in r]))
        cal.append((b, v))
        rows.append(dict(kind="calib_b", param=b, value=v, n=len(r)))
        print("  b=%.2f  length-only bacc %.4f" % (b, v))
    B = min(cal, key=lambda t: abs(t[1] - TARGET_LENGTH_BACC))[0]
    print("  -> b = %.2f  (target %.3f)" % (B, TARGET_LENGTH_BACC))

    # ---- calibration 2: s, so the FULL-cell activation probe hits 0.743 --------------
    print("=== calibration 2 - planted belief strength s (x mean row norm) ===")
    sgrid = ([0.0, 0.02, 0.04, 0.06, 0.09, 0.13, 0.18]
             if not a.smoke else [0.0, 0.06])
    cal2 = []
    for g in sgrid:
        r = run_world(pool, range(SEED + 1000, SEED + 1000 + n_cal), B, g * norm, ctx,
                      crit=0.5)
        v = float(np.mean([x["full_bacc"] for x in r]))
        cal2.append((g, v))
        rows.append(dict(kind="calib_s", param=g, value=v, n=len(r)))
        print("  s=%.3f  full-cell bacc %.4f" % (g, v))
    S = min(cal2, key=lambda t: abs(t[1] - TARGET_FULL_BACC))[0]
    print("  -> s = %.3f  (target %.3f)" % (S, TARGET_FULL_BACC))

    # ---- the ladder: world A (false fire, must be <= 0.05) and world B (power, >= 0.80)
    chosen = None
    for variant in ([] if a.mde_only else a.variants.split(",")):
        print("=== rung '%s' - world A, PURE LENGTH (false-fire; must be <= 0.05) ===" % variant)
        rA = run_world(pool, range(SEED + 2000, SEED + 2000 + n_world), B, 0.0, ctx,
                       variant=variant)
        sA = summarise("pure_length", rA)
        sA.update(b=B, s=0.0, variant=variant)
        rows.append(dict(kind="world", **sA))
        print("  " + " | ".join("%s %.4f" % (k, v) for k, v in sA.items()
                                if isinstance(v, float)))

        print("=== rung '%s' - world B, GENUINE BELIEF (power; must be >= 0.80) ===" % variant)
        rB = run_world(pool, range(SEED + 3000, SEED + 3000 + n_world), B, S * norm, ctx,
                       variant=variant)
        sB = summarise("genuine_belief", rB)
        sB.update(b=B, s=S, variant=variant)
        rows.append(dict(kind="world", **sB))
        print("  " + " | ".join("%s %.4f" % (k, v) for k, v in sB.items()
                                if isinstance(v, float)))

        for q in QUANTILES:
            k = "fire_rate_q%d" % round(q * 1000)
            ok = sA[k] <= 0.05 and sB[k] >= 0.80
            print("   ladder rung %-14s @ q%.3f : false-fire %.3f  power %.3f  -> %s"
                  % (variant, q, sA[k], sB[k], "ACCEPTABLE" if ok else "rejected"))
            if ok and chosen is None:
                chosen = (variant, q, sA[k], sB[k])
    print("CHOSEN RUNG: %s" % ("NONE - no rung meets both gates" if chosen is None else
                               "%s @ q%.3f (false-fire %.3f, power %.3f)" % chosen))

    if a.force_rung:
        v, q = a.force_rung.split(",")
        chosen = (v, float(q), float("nan"), float("nan"))
        print("MDE rung FORCED to %s @ q%s (PR-009 item 4's frozen rung)" % (v, q))

    # ---- MDE sweep for the chosen rung ------------------------------------------------
    if chosen and not a.no_mde:
        cv, cq = chosen[0], chosen[1]
        qk = "fires_q%d" % round(cq * 1000)
        print("=== MDE sweep, rung %s @ q%.3f (per-replicate nulls) ===" % (cv, cq))
        grid = [0.0, 0.02, 0.03, 0.045, 0.06, 0.09] if not a.smoke else [0.0, 0.06]
        mde = None
        for g in grid:
            r = run_world(pool, range(SEED + 4000, SEED + 4000 + n_mde), B, g * norm, ctx,
                          variant=cv)
            f = float(np.mean([x[qk] for x in r]))
            fb = float(np.mean([x["full_bacc"] for x in r]))
            sb = float(np.mean([x["strat_bacc"] for x in r]))
            rows.append(dict(kind="mde", variant=cv, param=g, value=f, full_bacc=fb,
                             strat_bacc=sb, n=len(r)))
            print("  s=%.3f  full-cell bacc %.4f  stratified %.4f  fire rate %.3f"
                  % (g, fb, sb, f))
            if mde is None and f >= 0.80:
                mde = (g, fb, sb, f)
        print("  MDE: %s" % ("not reached on this grid" if mde is None else
                             "s=%.3f, i.e. a full-cell balanced accuracy of %.3f "
                             "(stratified %.3f), fire rate %.2f" % mde))

    if pool:
        pool.close()
    cols = sorted({k for r in rows for k in r})
    path = OUT / ("smoke_w13_sims.csv" if a.smoke else "w13_sims.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("wrote %s  (%.0fs)" % (path, time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
