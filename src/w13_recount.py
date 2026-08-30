"""W13's load-bearing recount. FRESH: imports json / sys / numpy / safetensors and NOTHING
from w13_lengthcheck.py, w13_power.py or direction_w5.py. No scikit-learn.

It re-implements, from PR-009's written description alone: the cell selection, the n_gen
lookup, the rank-based terciles, the stratified 70/30 trace splits, the train-only
centre/scale/SVD projection, and the L2 logistic probe (Newton-IRLS on the same convex
objective sklearn minimises, intercept unpenalised, balanced class weights). It prints the
reproduction number and the stratified headline number.

  python3 src/w13_recount.py            # layers 22 and 27
  python3 src/w13_recount.py 27
"""
import json
import sys
from pathlib import Path

import numpy as np
from safetensors.numpy import load_file

R = Path(__file__).resolve().parent.parent
TEST_FRAC, N_REP, C_REG, K = 0.30, 20, 1.0, 3


def logistic(P, y, w_class, iters=60):
    """Newton-IRLS for  0.5||b||^2 + C * sum_i s_i log(1+exp(-y_i(x_i'b + c)))."""
    n, d = P.shape
    A = np.concatenate([P, np.ones((n, 1))], axis=1)
    th = np.zeros(d + 1)
    s = np.array([w_class[int(v)] for v in y])
    pen = np.ones(d + 1)
    pen[-1] = 0.0
    for _ in range(iters):
        z = A @ th
        p = 1.0 / (1.0 + np.exp(-z))
        g = pen * th - C_REG * (A.T @ (s * ((y > 0).astype(float) - p)))
        W = C_REG * s * p * (1 - p) + 1e-9
        H = (A * W[:, None]).T @ A + np.diag(pen)
        step = np.linalg.solve(H, g)
        th -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return th


def bacc(yt, yp):
    return float(np.mean([(yp[yt == c] == c).mean() for c in (1, -1)]))


def residualise(Xl, tof, itr, ite, cov):
    """Remove the least-squares fit of every activation coordinate on [1, n_gen, position],
    estimated on the TRAINING points alone, from both sides."""
    A = np.concatenate([np.ones((len(itr), 1)), cov[itr]], axis=1)
    B = np.concatenate([np.ones((len(ite), 1)), cov[ite]], axis=1)
    W = np.linalg.lstsq(A, Xl[itr], rcond=None)[0]
    R = np.empty((len(itr) + len(ite), Xl.shape[1]), dtype=np.float32)
    R[:len(itr)] = Xl[itr] - A @ W
    R[len(itr):] = Xl[ite] - B @ W
    return R


def evaluate(Xl, tof, y, cov=None):
    """Mean balanced accuracy over 20 stratified 70/30 trace splits, traces as the unit."""
    n = len(y)
    accs = []
    for r in range(N_REP):
        rng = np.random.default_rng(r)
        te = []
        for c in (1, -1):
            idx = np.where(y == c)[0].copy()
            rng.shuffle(idx)
            te.extend(idx[:max(1, int(round(TEST_FRAC * idx.size)))].tolist())
        te = set(te)
        tr = [i for i in range(n) if i not in te]
        itr = np.array([i for i, t in enumerate(tof) if t in set(tr)])
        ite = np.array([i for i, t in enumerate(tof) if t in te])
        if itr.size == 0 or ite.size == 0:
            continue
        if cov is None:
            Atr, Ate = Xl[itr], Xl[ite]
        else:
            R = residualise(Xl, tof, itr, ite, cov)
            Atr, Ate = R[:len(itr)], R[len(itr):]
        mu = Atr.mean(0)
        Z = Atr - mu
        sc = float(np.linalg.norm(Z, axis=1).mean()) or 1.0
        Z /= sc
        _, S, Vt = np.linalg.svd(Z, full_matrices=False)
        Vt = Vt[:int((S > 1e-6 * S[0]).sum())]
        Ptr, Pte = Z @ Vt.T, ((Ate - mu) / sc) @ Vt.T
        utr, ute = tof[itr], tof[ite]
        ytr = y[utr]
        cw = {c: len(ytr) / (2.0 * max(1, (ytr == c).sum())) for c in (1, -1)}
        th = logistic(Ptr, ytr, cw)
        prob = 1.0 / (1.0 + np.exp(-(Pte @ th[:-1] + th[-1])))
        u = np.unique(ute)
        pred = np.array([1 if prob[ute == k].mean() > 0.5 else -1 for k in u])
        accs.append(bacc(y[u], pred))
    return float(np.mean(accs))


def main():
    layers = [int(v) for v in sys.argv[1:]] or [22, 27]
    meta = json.loads((R / "runs/w5_subsample/w5_cell_index.json").read_text())
    acts = load_file(str(R / "runs/w5_subsample/w5_cell.safetensors"))["acts"]
    pts = [p for p in meta["points"]
           if p["form"] == "B" and p["arm"] == "above_good" and p["phat"] in (1, -1)]
    tr_ids = sorted({p["trace_i"] for p in pts})
    pos = {t: i for i, t in enumerate(tr_ids)}
    X = acts[[p["cell_row"] for p in pts]].astype(np.float32)
    tof = np.array([pos[p["trace_i"]] for p in pts])
    y = np.zeros(len(tr_ids), dtype=int)
    for p in pts:
        y[pos[p["trace_i"]]] = p["phat"]

    roll = json.loads((R / "runs/w3_frozen/form_B/above_good.json").read_text())
    ng = {r["i"]: r["n_output_tokens"] for r in roll["rows"]}
    n_gen = np.array([ng[t] for t in tr_ids], dtype=float)

    order = np.lexsort((np.arange(len(n_gen)), n_gen))
    strat = np.empty(len(n_gen), dtype=int)
    for j, ch in enumerate(np.array_split(order, K)):
        strat[ch] = j
    keep = [j for j in range(K)
            if (y[strat == j] == 1).sum() >= 6 and (y[strat == j] == -1).sum() >= 6]

    print("recount | %d est points, %d traces (+1 %d / -1 %d) | terciles kept %s"
          % (len(pts), len(tr_ids), (y == 1).sum(), (y == -1).sum(), keep))
    for j in range(K):
        m = strat == j
        print("   tercile %d  n=%-3d n_gen [%d,%d]  +1 %-3d -1 %-3d%s"
              % (j, m.sum(), n_gen[m].min(), n_gen[m].max(),
                 (y[m] == 1).sum(), (y[m] == -1).sum(), "" if j in keep else "  DROPPED"))

    posn = np.array([p["token_index"] for p in pts], dtype=float)
    for L in layers:
        Xl = np.ascontiguousarray(X[:, L, :])
        full = evaluate(Xl, tof, y)
        out = {}
        for name, resid in (("tercile", False), ("tercile_resid", True)):
            per = []
            for j in keep:
                m = np.where(strat == j)[0]
                loc = {g: i for i, g in enumerate(m)}
                sel = np.array([i for i, t in enumerate(tof) if t in loc])
                Xs = np.ascontiguousarray(Xl[sel])
                tj = np.array([loc[tof[i]] for i in sel])
                cov = np.stack([n_gen[tof[sel]], posn[sel]], axis=1) if resid else None
                per.append(evaluate(Xs, tj, y[m], cov))
            out[name] = (float(np.mean(per)), per)
        print("L%-2d  RECOUNT full %.4f" % (L, full))
        for name in ("tercile", "tercile_resid"):
            v, per = out[name]
            print("      RECOUNT %-14s %.4f   (terciles %s)"
                  % (name, v, " ".join("%.4f" % q for q in per)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
