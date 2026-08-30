"""W7b diagnostic (POST-HOC, labelled): what is D_bar's null floor at n=50?

PR-006 item 4.3 defines D_bar = mean over the 8 null arms of |P_arm - P_sham|, and item 5
puts the distortion line at 0.06. Both arms of every such difference are n=50 binomials, so
D_bar has a NON-ZERO expectation even when the injection does nothing at all. This script
measures that floor by simulation, under the exact design PR-006 froze.

It changes NO verdict: PR-006 item 5 row 3 fired on the frozen statistic and stands. This is
the bug-first / instruction-flaw check that standing constraint 7 requires.

  python3 src/w7b_floor.py
"""
import sys
import numpy as np

N_ARM, N_SHAM, N_NULLS, N_SIM, SEED = 50, 50, 8, 200000, 64
LINE = 0.06


def floor(p, sham_fixed=None, seed=SEED):
    """E[D_bar] and P(D_bar > LINE) when EVERY arm is the same coin p (zero real effect)."""
    rng = np.random.default_rng(seed)
    nulls = rng.binomial(N_ARM, p, size=(N_SIM, N_NULLS)) / N_ARM
    sham = (np.full(N_SIM, sham_fixed) if sham_fixed is not None
            else rng.binomial(N_SHAM, p, size=N_SIM) / N_SHAM)
    d = np.abs(nulls - sham[:, None]).mean(1)
    return d.mean(), float((d > LINE).mean()), np.percentile(d, [2.5, 50, 97.5])


print("D_bar null floor — every arm the SAME coin, i.e. the injection does nothing.")
print("%d simulations, n=%d per arm, %d null arms, line = %.2f\n" % (N_SIM, N_ARM, N_NULLS, LINE))
print("%-46s %8s %10s %26s" % ("scenario", "E[D_bar]", "P(>line)", "95% interval of D_bar"))
for lbl, p, fix in (
        ("sham also n=50, true rate p=0.59 (W3 unsteered)", 0.5933, None),
        ("sham also n=50, true rate p=0.50", 0.50, None),
        ("sham FIXED at its observed 0.68, true p=0.68", 0.68, 0.68),
        ("sham FIXED at 0.68, true p=0.4925 (observed nulls)", 0.4925, 0.68)):
    e, pr, iv = floor(p, fix)
    print("%-46s %8.4f %9.1f%% [%.4f, %.4f] med %.4f" % (lbl, e, 100 * pr, iv[0], iv[2], iv[1]))

print("\nObserved D_bar = 0.1875 (8 null arms vs the REUSED sham at 0.68).")
obs = np.array([0.58, 0.38, 0.48, 0.52, 0.60, 0.32, 0.54, 0.52])
print("Observed null arms: %s  mean %.4f  (%d/400 landings)"
      % (list(obs), obs.mean(), int(round(obs.sum() * 50))))
print("Same D_bar recomputed against W3's UNSTEERED n=150 reference 0.5933: %.4f"
      % np.abs(obs - 0.5933).mean())
print("Same D_bar recomputed against the 8 null arms' own mean %.4f: %.4f"
      % (obs.mean(), np.abs(obs - obs.mean()).mean()))

# --------------------------------------------------------------------- part 2 (POST-HOC)
# Are the 12 W7b arms mutually consistent with ONE common landing rate? And does that rate
# differ from the alpha=0 references? Neither question is pre-registered; both are labelled.
from scipy import stats  # noqa: E402

k = {"ap05": 23, "ap025": 23, "am025": 24, "am05": 18,
     "n10p": 29, "n10m": 19, "n11p": 24, "n11m": 26,
     "n12p": 30, "n12m": 16, "n13p": 27, "n13m": 26}
print("\n" + "=" * 78)
print("POST-HOC (labelled; changes no verdict): homogeneity and the alpha=0 references\n")
K = np.array(list(k.values()))
tab = np.array([K, 50 - K])
chi2, p, dof, _ = stats.chi2_contingency(tab)
print("12 W7b arms, homogeneity of P(final>tau_B): chi2=%.2f dof=%d p=%.4f  -> %s"
      % (chi2, dof, p, "consistent with ONE common rate" if p > 0.05 else "arms differ"))
print("   pooled W7b: %d/600 = %.4f" % (K.sum(), K.sum() / 600.0))
for lbl, kk, nn in (("v_phat arms only (4)", 23 + 23 + 24 + 18, 200),
                    ("null arms only (8)", 29 + 19 + 24 + 26 + 30 + 16 + 27 + 26, 400),
                    ("|alpha|=0.25 arms (2)", 23 + 24, 100),
                    ("|alpha|=0.50 arms (10)", K.sum() - 47, 500)):
    print("   %-24s %3d/%3d = %.4f" % (lbl, kk, nn, kk / float(nn)))
print()
for lbl, k0, n0 in (("W7 sham (alpha=0, hook installed)", 34, 50),
                    ("W3 unsteered form-B above_good", 89, 150),
                    ("both alpha=0 references pooled", 123, 200)):
    res = stats.fisher_exact([[K.sum(), 600 - K.sum()], [k0, n0 - k0]])
    print("W7b pooled %.4f  vs  %-34s %.4f   Fisher p=%.4f"
          % (K.sum() / 600.0, lbl, k0 / float(n0), res.pvalue))
r = stats.fisher_exact([[47, 53], [K.sum() - 47, 500 - (K.sum() - 47)]])
print("\ndose gradient inside W7b: |alpha|=0.25 (%.4f) vs |alpha|=0.50 (%.4f)  Fisher p=%.4f"
      % (47 / 100.0, (K.sum() - 47) / 500.0, r.pvalue))
