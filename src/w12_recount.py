"""W12 load-bearing recount.  Fresh script, deliberately independent.

Recomputes, OFFLINE from the 5% audit subsample alone, the alignment-(b) bin that
contains the belief-formation onset at the best layer.  Imports json / sys / numpy and
NOTHING from this packet's analysis code: the p̂ recipe, the binning, the split, the
logistic probe (plain gradient descent, no sklearn) and the permutation null are all
re-implemented here from the ledger's description.

  python3 src/w12_recount.py <best_layer>
"""
import json, sys
from pathlib import Path
import numpy as np
from safetensors.numpy import load_file

R = Path(__file__).resolve().parent.parent
A = R / "runs" / "w12_acts"
LAYERS = [21, 23, 25, 27, 29, 31, 33, 35]


def phat(arm, v):
    if v not in ("correct", "incorrect"):
        return None
    return (1 if v == "correct" else -1) * (1 if arm == "above_good" else -1)


def fit(X, y, iters=300, lr=0.5, lam=1.0):
    w, b = np.zeros(X.shape[1]), 0.0
    t = (y > 0).astype(float)
    cw = np.where(y > 0, 0.5 / max(t.mean(), 1e-9), 0.5 / max(1 - t.mean(), 1e-9))
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = X.T @ (cw * (p - t)) / len(y) + lam * w / len(y)
        w -= lr * g
        b -= lr * float((cw * (p - t)).mean())
    return w, b


def main():
    best = int(sys.argv[1]); li = LAYERS.index(best)
    verd = {}
    for k, r in json.loads((R / "analysis/out/w3_direction_cache.json").read_text()).items():
        m, f, a, i = k.split("|")
        if f == "B":
            verd[(a, int(i))] = r["direction"]
    Xc, yc, bc = [], [], []
    for arm in ("above_good", "below_good"):
        idx = json.loads((A / ("w12_index_%s.json" % arm)).read_text())
        sub = json.loads((A / ("w12_sub_index_%s.json" % arm)).read_text())["rows"]
        acts = load_file(str(A / ("w12_sub_%s.safetensors" % arm)))["acts"][:, li, :]
        pos = {}
        for r, (ti, g) in enumerate(sub):
            pos.setdefault(ti, []).append((g, r))
        for t in idx["traces"]:
            ph = phat(arm, verd.get((arm, t["trace_i"])))
            if ph is None or t["belief_gen_pos"] is None:
                continue
            for g, r in pos.get(t["trace_i"], []):
                o = g - t["belief_gen_pos"]
                if -250 <= o < 50:
                    Xc.append((arm, t["trace_i"], (o + 250) // 25, r, ph))
    for arm in ("above_good", "below_good"):
        pass
    # (trace, bin) means
    acts = {a: load_file(str(A / ("w12_sub_%s.safetensors" % a)))["acts"][:, li, :]
            for a in ("above_good", "below_good")}
    cells = {}
    for arm, ti, b, r, ph in Xc:
        cells.setdefault((arm, ti, b, ph), []).append(acts[arm][r])
    print("best layer L%d | %d (trace,bin) cells from the 5%% subsample" % (best, len(cells)))
    rng = np.random.default_rng(4242)
    out = []
    for b in range(12):
        ks = [k for k in cells if k[2] == b]
        X = np.stack([np.mean(cells[k], axis=0) for k in ks]).astype(np.float64)
        y = np.array([k[3] for k in ks])
        arm = np.array([0 if k[0] == "above_good" else 1 for k in ks])
        if (y > 0).sum() < 3 or (y < 0).sum() < 3:
            out.append((b, float("nan"), float("nan"))); continue
        accs, nulls = [], []
        for rep in range(20):
            rs = np.random.default_rng(rep)
            te = np.concatenate([rs.permutation(np.where(y == c)[0])[
                :max(1, int(round(0.3 * (y == c).sum())))] for c in (1, -1)])
            tr = np.setdiff1d(np.arange(len(y)), te)
            Z = X.copy()
            for c in (0, 1):
                m = tr[arm[tr] == c]
                if m.size:
                    Z[arm == c] -= Z[m].mean(0)
            mu = Z[tr].mean(0); Z -= mu
            s = np.linalg.norm(Z[tr], axis=1).mean() or 1.0; Z /= s
            U, S, Vt = np.linalg.svd(Z[tr], full_matrices=False)
            V = Vt[:(S > 1e-8 * S[0]).sum()]
            P, Q = Z[tr] @ V.T, Z[te] @ V.T
            for j in range(41):
                yy = y if j == 0 else y[rng.permutation(len(y))]
                if len(set(yy[tr])) < 2:
                    continue
                w, c0 = fit(P, yy[tr])
                pr = np.where(Q @ w + c0 > 0, 1, -1)
                a = np.mean([(pr[yy[te] == c] == c).mean() for c in (1, -1)
                             if (yy[te] == c).any()])
                (accs if j == 0 else nulls).append(a)
        out.append((b, float(np.mean(accs)), float(np.quantile(nulls, 0.995))))
    print("\n bin  offset            bacc    null p99.5   sig")
    sig = []
    for b, a, q in out:
        s = a == a and q == q and a > q
        sig.append(s)
        print("  %2d  [%+4d,%+4d)   %6s   %6s     %s"
              % (b, -250 + 25 * b, -225 + 25 * b,
                 "%.4f" % a if a == a else "  --", "%.4f" % q if q == q else "  --",
                 "*" if s else ""))
    on = next((b for b in range(9) if all(sig[b:b + 4])), None)
    print("\nRECOUNT onset bin = %s" % ("[%+d,%+d)" % (-250 + 25 * on, -225 + 25 * on)
                                        if on is not None else "NONE"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
