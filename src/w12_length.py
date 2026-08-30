"""D-042: is the alignment-(a) decile curve a trace-LENGTH probe?

Two numbers, both regenerable by this command alone and neither needing an activation:
  (1) the association between output length and p̂, by label permutation;
  (2) a logistic probe whose ONLY feature is `n_gen`, on the same 20 folds and against the
      same 500-permutation trace-level null as `analyze_w12.py`'s probes.

  python3 src/w12_length.py
"""
import csv, statistics, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import analyze_w12 as az                                    # folds and metric, not data


def main():
    from sklearn.linear_model import LogisticRegression
    rows = list(csv.DictReader(open(ROOT / "analysis/out/w12_cutpoints.csv")))
    print("=== 1 · output length by arm and p̂ ===")
    for arm in ("above_good", "below_good"):
        for ph in ("1", "-1"):
            v = [int(r["n_gen"]) for r in rows if r["arm"] == arm and r["phat"] == ph]
            if v:
                print("  %-11s p̂=%-3s n=%-4d mean %6.1f  median %6.1f"
                      % (arm, ph, len(v), statistics.mean(v), statistics.median(v)))
    a = [int(r["n_gen"]) for r in rows if r["arm"] == "above_good" and r["phat"] == "1"]
    b = [int(r["n_gen"]) for r in rows if r["arm"] == "above_good" and r["phat"] == "-1"]
    obs = statistics.mean(a) - statistics.mean(b)
    rng = np.random.default_rng(7)
    pool = np.array(a + b)
    cnt = sum(1 for _ in range(20000)
              if abs(np.mean((p := rng.permutation(pool))[:len(a)]) - np.mean(p[len(a):]))
              >= abs(obs))
    print("  above_good difference of means (+1 minus -1) = %+.1f tokens, "
          "permutation p = %.4f (20,000 draws)" % (obs, (cnt + 1) / 20001))

    print("\n=== 2 · a probe whose only feature is n_gen ===")
    for arm, label in ((("above_good",), "above_good (W5's cell)"),
                       (("above_good", "below_good"), "pooled, 238 traces")):
        sel = [r for r in rows if r["arm"] in arm]
        y = np.array([int(r["phat"]) for r in sel], dtype=np.int8)
        X = np.array([[float(r["n_gen"])] for r in sel])

        def score(yy):
            acc = []
            for tr, te in az.splits(yy):
                if len(set(yy[tr])) < 2:
                    continue
                clf = LogisticRegression(C=az.C_REG, max_iter=az.MAX_ITER,
                                         class_weight="balanced").fit(X[tr], yy[tr])
                acc.append(az.bacc(yy[te], clf.predict(X[te])))
            return float(np.nanmean(acc))
        o = score(y)
        r2 = np.random.default_rng(az.SEED_PERM)
        null = np.array([score(y[r2.permutation(len(y))]) for _ in range(az.N_PERM)])
        print("  %-24s balanced accuracy %.4f | null p95 %.4f | p = %.4f"
              % (label, o, np.quantile(null, 0.95), (np.sum(null >= o) + 1) / (null.size + 1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
