"""W13 / PR-009: does E-007's p̂ probe survive a targeted trace-length attack?

D-042 established that in the W12 above_good cell a probe whose ONLY feature is trace length
scores 0.6421 balanced accuracy. E-007's number (0.743 at l*=22 / 0.760 at L27, form B,
above_good `est` points) is a probe over points whose COUNT and POSITIONS are functions of the
same length. This file runs the check D-042 named and W12 was not authorised to run.

Everything is computed from files that are already on the laptop:
  runs/w5_subsample/w5_cell.safetensors   the W5 analysis cell, 528 est points x 48 layers
  runs/w5_subsample/w5_cell_index.json    its per-point metadata (incl. the frozen p̂ label)
  runs/w3_frozen/form_B/above_good.json   `n_output_tokens` per trace  -> the length feature

WHAT IS COMPUTED (PR-009 items 1-3)
  full          the W5 probe re-run on the analysis cell -- the reproduction (expect 0.743/0.760)
  length_only   a probe on scalar features {n_gen, n_est_points, mean est-point position},
                no activations at all, on the SAME folds
  stratified    the critical test: n_gen terciles, the activation probe trained AND evaluated
                WITHIN tercile (trace-level splits), averaged over terciles, against a
                within-tercile trace-level label-permutation null, and against the length-only
                probe on the identical folds
  residualized  secondary (reported, not decisive): each activation feature regressed on
                (n_gen, est-point token position) on the TRAINING points, probe the residuals

The probe itself is PR-004's, re-implemented here to the letter (mean-centre and norm-scale on
the training points, SVD basis from the training rows only, L2 logistic with balanced class
weights, per-trace mean predicted probability thresholded at 0.5, balanced accuracy over the
held-out traces, mean over 20 stratified 70/30 trace splits).

  python3 src/w13_lengthcheck.py --smoke        # laptop, synthetic labels, smoke_ outputs
  python3 src/w13_lengthcheck.py                # the real run
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"
SUB = ROOT / "runs" / "w5_subsample"
W3 = ROOT / "runs" / "w3_frozen"

# --- PR-004 frozen hyper-parameters, carried over unchanged ---------------------------
N_PERM = 1000
N_REPEAT = 20
TEST_FRAC = 0.30
C_REG = 1.0
MAX_ITER = 2000
SEED_SPLIT = 0
SEED_PERM = 1234

# --- PR-009 frozen choices ------------------------------------------------------------
FORM = "B"
ARM = "above_good"
PRIMARY_LAYER = 27          # the layer the work order names
LSTAR = 22                  # E-007's l*, co-reported; disagreement with L27 -> PARTIAL
N_STRATA = 3                # terciles by n_gen, rank-based, near-equal sizes
MIN_PER_CLASS = 6           # a stratum with fewer than this of either class is DROPPED
SEED_SIM = 20260831


# =====================================================================================
# data
# =====================================================================================

def n_gen_map(form, arm):
    """Generated-token count per trace, from the frozen W3 rollout file.

    NOTE (D-046): this is `n_output_tokens`, which is exactly 1 greater than the `n_gen`
    column of analysis/out/w12_cutpoints.csv for all 113 shared traces. The offset is
    constant, so no rank-based or logistic use of it is affected.
    """
    d = json.loads((W3 / ("form_%s" % form) / ("%s.json" % arm)).read_text())
    return {r["i"]: r["n_output_tokens"] for r in d["rows"]}


def load_cell(form=FORM, arm=ARM):
    """The labelled est points of one arm of the W5 analysis cell, plus trace-level features."""
    from safetensors.numpy import load_file
    meta = json.loads((SUB / "w5_cell_index.json").read_text())
    acts = load_file(str(SUB / "w5_cell.safetensors"))["acts"]
    pts = [p for p in meta["points"]
           if p["form"] == form and p["arm"] == arm and p["phat"] in (1, -1)]
    X = acts[[p["cell_row"] for p in pts]].astype(np.float32)
    traces = sorted({p["trace_i"] for p in pts})
    tpos = {t: i for i, t in enumerate(traces)}
    tof = np.array([tpos[p["trace_i"]] for p in pts])
    y = np.zeros(len(traces), dtype=np.int8)
    for p in pts:
        y[tpos[p["trace_i"]]] = p["phat"]
    ng = n_gen_map(form, arm)
    n_gen = np.array([ng[t] for t in traces], dtype=np.float64)
    pos = np.array([p["token_index"] for p in pts], dtype=np.float64)
    n_est = np.array([int((tof == i).sum()) for i in range(len(traces))], dtype=np.float64)
    mean_pos = np.array([pos[tof == i].mean() for i in range(len(traces))])
    F = np.stack([n_gen, n_est, mean_pos], axis=1)      # the length-only feature matrix
    return dict(X=X, pts=pts, traces=traces, tof=tof, y=y, F=F, pos=pos,
                n_gen=n_gen, n_est=n_est, mean_pos=mean_pos)


# =====================================================================================
# the probe (PR-004 item 4, re-implemented)
# =====================================================================================

def bacc(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    accs = []
    for c in (+1, -1):
        m = y_true == c
        if not m.any():
            return np.nan
        accs.append((y_pred[m] == c).mean())
    return float(np.mean(accs))


def splits(n_traces, strat, n_repeat=N_REPEAT, seed0=SEED_SPLIT):
    """PR-004's `_splits`: n_repeat 70/30 splits of 0..n_traces-1, stratified by `strat`."""
    out = []
    for r in range(n_repeat):
        rng = np.random.default_rng(seed0 + r)
        te = []
        groups = [np.arange(n_traces)] if strat is None else \
                 [np.where(strat == c)[0] for c in (+1, -1)]
        for idx in groups:
            idx = idx.copy()
            rng.shuffle(idx)
            if idx.size == 0:
                continue
            te.extend(idx[:max(1, int(round(TEST_FRAC * idx.size)))].tolist())
        te = set(te)
        out.append((np.array([i for i in range(n_traces) if i not in te]),
                    np.array(sorted(te))))
    return out


def project(Xl, itr, ite):
    """Label-free part of a fold: centre, scale, SVD basis from the TRAINING rows only."""
    Xtr, Xte = Xl[itr], Xl[ite]
    mu = Xtr.mean(axis=0)
    Z = Xtr - mu
    s = float(np.linalg.norm(Z, axis=1).mean()) or 1.0
    Z = Z / s
    _, S, Vt = np.linalg.svd(Z, full_matrices=False)
    Vt = Vt[:int((S > 1e-6 * S[0]).sum())] if S.size else Vt
    return Z @ Vt.T, ((Xte - mu) / s) @ Vt.T


def fit_score(Ptr, Pte, utr, ute, lab):
    """L2 logistic on the projected training points; per-unit mean probability; bacc."""
    from sklearn.linear_model import LogisticRegression
    ytr = lab[utr]
    if np.unique(ytr).size < 2:
        return np.nan
    clf = LogisticRegression(C=C_REG, max_iter=MAX_ITER, class_weight="balanced")
    clf.fit(Ptr, ytr)
    prob = clf.predict_proba(Pte)[:, list(clf.classes_).index(1)]
    units = np.unique(ute)
    pred = np.array([+1 if prob[ute == u].mean() > 0.5 else -1 for u in units])
    return bacc(lab[units], pred)


def prep_folds(Xl, tof, sp):
    """Cache every fold's projection once; labels never enter, so all permutations reuse it."""
    cache = []
    for tr, te in sp:
        trs, tes = set(tr.tolist()), set(te.tolist())
        itr = np.array([i for i, t in enumerate(tof) if t in trs])
        ite = np.array([i for i, t in enumerate(tof) if t in tes])
        if itr.size == 0 or ite.size == 0:
            continue
        Ptr, Pte = project(Xl, itr, ite)
        cache.append((Ptr, Pte, tof[itr], tof[ite]))
    return cache


def act_bacc(cache, lab):
    return float(np.nanmean([fit_score(a, b, c, d, lab) for a, b, c, d in cache]))


def prep_len_folds(F, sp):
    """The same folds, trace-level scalar features, standardised on the training traces."""
    cache = []
    for tr, te in sp:
        mu, sd = F[tr].mean(axis=0), F[tr].std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
        cache.append(((F[tr] - mu) / sd, (F[te] - mu) / sd, tr, te))
    return cache


def len_bacc(cache, lab):
    from sklearn.linear_model import LogisticRegression
    accs = []
    for Ftr, Fte, tr, te in cache:
        ytr = lab[tr]
        if np.unique(ytr).size < 2:
            accs.append(np.nan)
            continue
        clf = LogisticRegression(C=C_REG, max_iter=MAX_ITER, class_weight="balanced")
        clf.fit(Ftr, ytr)
        accs.append(bacc(lab[te], clf.predict(Fte)))
    return float(np.nanmean(accs))


# =====================================================================================
# strata (PR-009 item 3)
# =====================================================================================

def terciles(n_gen, k=N_STRATA):
    """Rank-based, near-equal sizes; ties broken by trace position. Frozen."""
    order = np.lexsort((np.arange(len(n_gen)), n_gen))
    out = np.empty(len(n_gen), dtype=int)
    for j, chunk in enumerate(np.array_split(order, k)):
        out[chunk] = j
    return out


def stratum_keep(strat, y, min_per_class=MIN_PER_CLASS):
    keep = []
    for j in sorted(set(strat.tolist())):
        m = strat == j
        if (y[m] == 1).sum() >= min_per_class and (y[m] == -1).sum() >= min_per_class:
            keep.append(j)
    return keep


# =====================================================================================
# the criterion ladder (PR-009 item 4): three ways to hold length fixed
#
#   tercile        rank-based n_gen terciles; probe trained AND scored within stratum;
#                  null permutes labels within stratum
#   tercile_resid  the same, but every activation coordinate is first regressed on
#                  (n_gen, est-point position) on the TRAINING points and the fit removed --
#                  terciles are coarse, and the pre-freeze sim showed the residual WITHIN-
#                  stratum length variation is what pushes the false-fire rate over nominal
#   matched        each p̂=-1 trace greedily matched to its nearest-n_gen unused p̂=+1 trace;
#                  folds split BY PAIR; the null flips the label WITHIN each pair, which holds
#                  the length distribution exactly fixed under the null
# =====================================================================================

def match_pairs(n_gen, y):
    """Greedy nearest-n_gen matching, minority class first, longest minority trace first."""
    minority = +1 if (y == 1).sum() <= (y == -1).sum() else -1
    mins = [i for i in np.argsort(-n_gen) if y[i] == minority]
    pool = [i for i in range(len(y)) if y[i] != minority]
    pair = np.full(len(y), -1, dtype=int)
    k = 0
    for i in mins:
        if not pool:
            break
        j = min(pool, key=lambda t: (abs(n_gen[t] - n_gen[i]), t))
        pool.remove(j)
        pair[i] = pair[j] = k
        k += 1
    return pair, k


def pair_splits(n_pairs, n_repeat=N_REPEAT, seed0=SEED_SPLIT):
    out = []
    for r in range(n_repeat):
        rng = np.random.default_rng(seed0 + r)
        idx = np.arange(n_pairs)
        rng.shuffle(idx)
        te = set(idx[:max(1, int(round(TEST_FRAC * n_pairs)))].tolist())
        out.append((np.array([i for i in range(n_pairs) if i not in te]),
                    np.array(sorted(te))))
    return out


def _group_cache(Xl, tof, y, F, C, members, sp, resid):
    """Fold caches for one group of traces (a stratum, or the whole matched set)."""
    loc = {g: i for i, g in enumerate(members)}
    sel = np.array([i for i, t in enumerate(tof) if t in loc])
    tj = np.array([loc[tof[i]] for i in sel])
    Xs = np.ascontiguousarray(Xl[sel])
    if resid:
        ac = prep_resid_folds(Xs, tj, sp, C[sel])
    else:
        ac = prep_folds(Xs, tj, sp)
    return ac, prep_len_folds(F[members], sp)


def variant_stat(Xl, tof, y, F, C, n_gen, variant, n_perm, seed=SEED_PERM):
    """Observed statistic, the length-only baseline on the IDENTICAL folds, and the null."""
    rng = np.random.default_rng(seed)
    groups, perm = [], None

    if variant in ("tercile", "tercile_resid"):
        strat = terciles(n_gen)
        keep = stratum_keep(strat, y)
        if not keep:
            return None
        for j in keep:
            m = np.where(strat == j)[0]
            sp = splits(len(m), y[m])
            ac, lcache = _group_cache(Xl, tof, y, F, C, m, sp,
                                      variant == "tercile_resid")
            groups.append(dict(m=m, y=y[m], ac=ac, lc=lcache))

        def perm(rg):
            return [g["y"][rg.permutation(g["y"].size)] for g in groups]

    elif variant == "resid_full":
        m = np.arange(len(y))
        sp = splits(len(y), y)
        ac, lcache = _group_cache(Xl, tof, y, F, C, m, sp, True)
        groups.append(dict(m=m, y=y.copy(), ac=ac, lc=lcache))

        def perm(rg):
            return [y[rg.permutation(y.size)]]

    elif variant == "matched":
        pair, k = match_pairs(n_gen, y)
        if k < 2 * MIN_PER_CLASS:
            return None
        m = np.array([i for i in range(len(y)) if pair[i] >= 0])
        pid = pair[m]
        sp_pairs = pair_splits(k)
        sp = [(np.where(np.isin(pid, tr))[0], np.where(np.isin(pid, te))[0])
              for tr, te in sp_pairs]
        ac, lcache = _group_cache(Xl, tof, y, F, C, m, sp, False)
        groups.append(dict(m=m, y=y[m], ac=ac, lc=lcache))
        pid_local = pid

        def perm(rg):
            yy = y[m].copy()
            flip = rg.random(k) < 0.5
            for q in range(k):
                if flip[q]:
                    yy[pid_local == q] *= -1
            return [yy]
    else:
        raise ValueError(variant)

    obs = [act_bacc(g["ac"], g["y"]) for g in groups]
    base = [len_bacc(g["lc"], g["y"]) for g in groups]
    stat = float(np.mean(obs))
    null = np.empty(n_perm)
    for t in range(n_perm):
        labs = perm(rng)
        null[t] = float(np.mean([act_bacc(g["ac"], lb) for g, lb in zip(groups, labs)]))
    return dict(stat=stat, base=float(np.mean(base)), null=null, n_groups=len(groups),
                per_obs=obs, per_base=base,
                n_traces=int(sum(len(g["m"]) for g in groups)),
                n_pos=int(sum((g["y"] == 1).sum() for g in groups)),
                n_neg=int(sum((g["y"] == -1).sum() for g in groups)))


# =====================================================================================
# residualization (PR-009 item 3, secondary)
# =====================================================================================

def residual_project(Xl, itr, ite, C):
    """Regress every activation coordinate on [1, n_gen, token_pos] using TRAINING points,
    subtract the fit from both sides, then run the normal centre/scale/SVD projection."""
    A = np.concatenate([np.ones((len(itr), 1)), C[itr]], axis=1)
    B = np.concatenate([np.ones((len(ite), 1)), C[ite]], axis=1)
    W, *_ = np.linalg.lstsq(A, Xl[itr], rcond=None)
    R = np.empty((len(itr) + len(ite), Xl.shape[1]), dtype=np.float32)
    R[:len(itr)] = Xl[itr] - A @ W
    R[len(itr):] = Xl[ite] - B @ W
    return project(R, np.arange(len(itr)), np.arange(len(itr), len(R)))


def prep_resid_folds(Xl, tof, sp, C):
    cache = []
    for tr, te in sp:
        trs, tes = set(tr.tolist()), set(te.tolist())
        itr = np.array([i for i, t in enumerate(tof) if t in trs])
        ite = np.array([i for i, t in enumerate(tof) if t in tes])
        Ptr, Pte = residual_project(Xl, itr, ite, C)
        cache.append((Ptr, Pte, tof[itr], tof[ite]))
    return cache


# =====================================================================================
# main
# =====================================================================================

def perm_labels(y, n_perm, seed=SEED_PERM):
    rng = np.random.default_rng(seed)
    return [y[rng.permutation(y.size)] for _ in range(n_perm)]


LADDER = ("tercile", "tercile_resid", "resid_full", "matched")
PRIMARY_VARIANT = "tercile_resid"   # frozen by PR-009 item 4's pre-freeze ladder


def one_layer(arg):
    (L, X, tof, y, F, C, n_gen, n_perm, sp_full, decisive, variants) = arg
    Xl = np.ascontiguousarray(X[:, L, :])
    res = []

    # --- the reproduction: E-007's own probe, unchanged --------------------------------
    cache = prep_folds(Xl, tof, sp_full)
    obs = act_bacc(cache, y)
    null = np.array([act_bacc(cache, lab) for lab in perm_labels(y, n_perm)])
    res.append(dict(layer=L, scope="full", stratum="all", n_traces=len(y),
                    n_pos=int((y == 1).sum()), n_neg=int((y == -1).sum()),
                    n_points=len(tof), accuracy=obs, null_mean=float(null.mean()),
                    null_p95=float(np.quantile(null, 0.95)),
                    p_perm=float((np.sum(null >= obs) + 1) / (null.size + 1))))

    # --- the ladder rungs -------------------------------------------------------------
    for v in variants:
        V = variant_stat(Xl, tof, y, F, C, n_gen, v, n_perm)
        if V is None:
            res.append(dict(layer=L, scope=v, stratum="all", accuracy=float("nan"),
                            n_traces=0))
            continue
        res.append(dict(layer=L, scope=v, stratum="all", n_traces=V["n_traces"],
                        n_pos=V["n_pos"], n_neg=V["n_neg"], n_points=len(tof),
                        accuracy=V["stat"], null_mean=float(V["null"].mean()),
                        null_p95=float(np.quantile(V["null"], 0.95)),
                        p_perm=float((np.sum(V["null"] >= V["stat"]) + 1)
                                     / (V["null"].size + 1)),
                        baseline_acc=V["base"]))
        for g in range(V["n_groups"]):
            res.append(dict(layer=L, scope=v + "_group", stratum=str(g),
                            accuracy=V["per_obs"][g], baseline_acc=V["per_base"][g]))

    # --- residualization, secondary and not decisive (full cell, no stratification) ----
    if decisive:
        rc = prep_resid_folds(Xl, tof, sp_full, C)
        ro = act_bacc(rc, y)
        rn = np.array([act_bacc(rc, lab) for lab in perm_labels(y, n_perm)])
        res.append(dict(layer=L, scope="residualized", stratum="all", n_traces=len(y),
                        n_pos=int((y == 1).sum()), n_neg=int((y == -1).sum()),
                        n_points=len(tof), accuracy=ro, null_mean=float(rn.mean()),
                        null_p95=float(np.quantile(rn, 0.95)),
                        p_perm=float((np.sum(rn >= ro) + 1) / (rn.size + 1))))
    return res


COLS = ["layer", "scope", "stratum", "n_traces", "n_pos", "n_neg", "n_points", "accuracy",
        "null_mean", "null_p95", "p_perm", "baseline_acc", "baseline_null_p95", "baseline_p",
        "n_perm", "n_repeat"]


def run_all(X, tof, y, F, D, layers, n_perm, procs):
    """One complete pass: length-only baseline, then every layer's cells. Returns rows."""
    strat = terciles(D["n_gen"])
    keep = stratum_keep(strat, y)
    dropped = [j for j in sorted(set(strat.tolist())) if j not in keep]
    pair, npair = match_pairs(D["n_gen"], y)
    print("terciles (rank-based on n_gen):")
    for j in sorted(set(strat.tolist())):
        m = strat == j
        print("  %d  n=%-4d n_gen [%d, %d]  +1 %-3d  -1 %-3d%s"
              % (j, m.sum(), D["n_gen"][m].min(), D["n_gen"][m].max(),
                 (y[m] == 1).sum(), (y[m] == -1).sum(),
                 "" if j in keep else "   <-- DROPPED (< %d of a class)" % MIN_PER_CLASS))
    if dropped:
        print("  strata dropped: %s" % dropped)
    md = np.abs(np.array([D["n_gen"][pair == q][0] - D["n_gen"][pair == q][1]
                          for q in range(npair)])) if npair else np.array([0.0])
    print("  matched pairs: %d (median |n_gen difference| %.1f, max %.0f)"
          % (npair, np.median(md), md.max()))

    sp_full = splits(len(y), y)
    lc = prep_len_folds(F, sp_full)
    lo = len_bacc(lc, y)
    ln = np.array([len_bacc(lc, lab) for lab in perm_labels(y, n_perm)])
    print("length-only baseline (full cell, no activations): %.4f | null p95 %.4f | p %.4f"
          % (lo, np.quantile(ln, 0.95), (np.sum(ln >= lo) + 1) / (ln.size + 1)))

    C = np.stack([D["n_gen"][tof], D["pos"]], axis=1)
    jobs = [(L, X, tof, y, F, C, D["n_gen"], n_perm, sp_full, L in (LSTAR, PRIMARY_LAYER),
             LADDER if L in (LSTAR, PRIMARY_LAYER) else (PRIMARY_VARIANT,))
            for L in layers]
    t0 = time.time()
    if procs > 1 and len(jobs) > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(procs) as pool:
            out = pool.map(one_layer, jobs, chunksize=1)
    else:
        out = [one_layer(j) for j in jobs]
    print("%d layer(s) done in %.0fs" % (len(jobs), time.time() - t0))

    rows = [dict(layer=-1, scope="length_only", stratum="all", n_traces=len(y),
                 n_pos=int((y == 1).sum()), n_neg=int((y == -1).sum()), n_points=len(tof),
                 accuracy=lo, null_mean=float(ln.mean()),
                 null_p95=float(np.quantile(ln, 0.95)),
                 p_perm=float((np.sum(ln >= lo) + 1) / (ln.size + 1)))]
    for r in out:
        rows.extend(r)
    for r in rows:
        r.setdefault("n_perm", n_perm)
        r.setdefault("n_repeat", N_REPEAT)
    return rows


def verdict(rows, L, variant=None):
    variant = variant or PRIMARY_VARIANT
    f = [r for r in rows if r["layer"] == L and r["scope"] == "full"]
    s = [r for r in rows if r["layer"] == L and r["scope"] == variant]
    if not f or not s:
        return None
    s, f = s[0], f[0]
    beats_null = s["accuracy"] > s["null_p95"]
    beats_base = s["accuracy"] > s["baseline_acc"]
    print("L%-2d %-14s full %.4f (p %.4f) | stat %.4f  null p95 %.4f  "
          "baseline-same-folds %.4f  -> null:%s baseline:%s"
          % (L, variant, f["accuracy"], f["p_perm"], s["accuracy"], s["null_p95"],
             s["baseline_acc"],
             "PASS" if beats_null else "fail", "PASS" if beats_base else "fail"))
    return beats_null and beats_base


def write_rows(rows, path):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--layers", default="")
    a = ap.parse_args()

    D = load_cell()
    X, tof, F = D["X"], D["tof"], D["F"]
    layers = [int(v) for v in a.layers.split(",")] if a.layers else list(range(X.shape[1]))

    if not a.smoke:
        rows = run_all(X, tof, D["y"], F, D, layers, N_PERM, a.procs)
        write_rows(rows, OUT / "w13_lengthcheck.csv")
        print()
        for L in (LSTAR, PRIMARY_LAYER):
            for v in LADDER:
                verdict(rows, L, v)
        return 0

    # ---- R-015(2): the smoke path writes ONLY to smoke_-prefixed files ----------------
    # Two synthetic worlds on the real activation geometry, both at the primary layer:
    #   (A) labels are a pure function of length  -> the stratified test MUST refuse them
    #   (B) labels carry a planted activation signal orthogonal to the length channel
    #       -> the stratified test MUST keep them
    rng = np.random.default_rng(SEED_SIM)
    layers = [PRIMARY_LAYER]
    n_perm = 60
    allrows = []

    yA = np.where(D["n_gen"] > np.median(D["n_gen"]), -1, 1).astype(np.int8)
    print("\n=== SMOKE A - pure-length labels (median split on n_gen) ===")
    rA = run_all(X, tof, yA, F, D, layers, n_perm, a.procs)
    okA = verdict(rA, PRIMARY_LAYER) is False
    for r in rA:
        r["scope"] = "smokeA_" + r["scope"]
    allrows += rA

    yB = np.where(rng.random(len(D["y"])) < 0.5, 1, -1).astype(np.int8)
    u = rng.normal(size=X.shape[2]).astype(np.float32)
    u /= np.linalg.norm(u)
    scale = float(np.linalg.norm(X[:, PRIMARY_LAYER, :], axis=1).mean())
    XB = X.copy()
    XB[:, PRIMARY_LAYER, :] += np.float32(0.30 * scale) * yB[tof][:, None] * u[None, :]
    print("\n=== SMOKE B - planted belief signal (0.30 x mean row norm), labels independent "
          "of length ===")
    rB = run_all(XB, tof, yB, F, D, layers, n_perm, a.procs)
    okB = verdict(rB, PRIMARY_LAYER) is True
    for r in rB:
        r["scope"] = "smokeB_" + r["scope"]
    allrows += rB

    write_rows(allrows, OUT / "smoke_w13_lengthcheck.csv")
    print("\nSMOKE A (must NOT fire): %s\nSMOKE B (must fire):     %s\nSMOKE %s"
          % ("PASS" if okA else "FAIL", "PASS" if okB else "FAIL",
             "PASS" if (okA and okB) else "FAIL"))
    return 0 if (okA and okB) else 1


if __name__ == "__main__":
    sys.exit(main())
