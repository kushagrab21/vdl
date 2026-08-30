"""W12 pre-freeze simulations (R-013 standing rule).

Two decision statistics are frozen by PR-008 and neither may be frozen without a
simulation of it under its OWN null:

  (1) ONSET.  "the earliest bin in alignment (b) where balanced accuracy exceeds its
      null's 95th percentile in TWO consecutive bins at the best layer."  What is
      simulated is the FAMILY-WISE false-onset rate over the whole (layer, bin) grid
      under the global null (no belief signal anywhere).

  (2) FLIP.   "the smoothed (MA-25) held-out trajectory crossing 0.5 with sustained
      change (>=50 tokens each side at margin >=0.1)."  What is simulated is the
      per-trace false-flip rate when the trajectory carries no signal.

Neither sim can use W12's own activations: the whole point of R-013 is that the rule is
frozen before the data exists.  Both are therefore PARAMETRIC, and both are swept over a
grid of nuisance parameters with the WORST cell taken as the operating number.  Sim (2)
is additionally re-run empirically on the real capture after the fact (label-shuffled
probes), and both numbers are reported.

  python3 src/w12_power.py --onset
  python3 src/w12_power.py --flip
  python3 src/w12_power.py            # both, writes analysis/out/w12_power.csv
"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"

N_LAYERS = 8            # {21,23,25,27,29,31,33,35}
N_BINS_B = 12           # -250..+50 in steps of 25
N_PERM = 500            # permutations per (layer, bin), as PR-008 item 3 orders
N_SIM = 20000


def _ar1_field(rng, n_sim, n_layers, n_bins, rho_layer, rho_bin):
    """A Gaussian field over (layer, bin) with separable AR(1) correlation."""
    zl = rng.standard_normal((n_sim, n_layers, n_bins))
    # AR(1) along bins
    if rho_bin:
        for b in range(1, n_bins):
            zl[:, :, b] = rho_bin * zl[:, :, b - 1] + np.sqrt(1 - rho_bin ** 2) * zl[:, :, b]
    if rho_layer:
        for l in range(1, n_layers):
            zl[:, l, :] = rho_layer * zl[:, l - 1, :] + np.sqrt(1 - rho_layer ** 2) * zl[:, l, :]
    return zl


def onset_fwer(rho_layer, rho_bin, k_consec, pct, n_sim=N_SIM, seed=12001,
               n_perm=N_PERM, any_layer=True):
    """P(the criterion fires anywhere) under the global null.

    Each (layer,bin) cell draws an observed statistic and a THRESHOLD from the same
    distribution.  The threshold is the cell's own finite-permutation percentile: with
    n_perm iid null draws, the k-th order statistic (k = ceil(pct*n_perm)) has an exact
    Beta(k, n_perm+1-k) probability-integral distribution, so it is drawn directly
    instead of materialising 500 draws per cell -- identical law, ~500x cheaper, and the
    extra variance of the finite permutation set is therefore INSIDE the number.
    """
    from math import erf, sqrt
    rng = np.random.default_rng(seed)
    k = int(np.ceil(pct * n_perm))
    fires = np.zeros(n_sim, dtype=bool)
    chunk = 2000
    done = 0
    while done < n_sim:
        m = min(chunk, n_sim - done)
        obs = _ar1_field(rng, m, N_LAYERS, N_BINS_B, rho_layer, rho_bin)
        u = rng.beta(k, n_perm + 1 - k, size=(m, N_LAYERS, N_BINS_B))
        q = _ppf(u)
        sig = obs > q                                       # [m, L, B]
        run = sig.copy()
        for s in range(1, k_consec):
            run = run[:, :, :-1] & sig[:, :, s:]
        hit = run.any(axis=2)                               # [m, L]
        fires[done:done + m] = hit.any(axis=1) if any_layer else hit[:, 0]
        done += m
    return float(fires.mean())


def _ppf(u):
    """Standard-normal quantile, stdlib-only (no scipy on the laptop venv)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    u = np.asarray(u, dtype=np.float64)
    out = np.empty_like(u)
    lo, hi = u < 0.02425, u > 1 - 0.02425
    mid = ~(lo | hi)
    q = np.sqrt(-2 * np.log(np.where(lo, u, 0.5)))
    out[lo] = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])[lo] / \
              ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)[lo]
    q = np.sqrt(-2 * np.log(np.where(hi, 1 - u, 0.5)))
    out[hi] = -((((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])[hi] /
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)[hi])
    q = np.where(mid, u, 0.5) - 0.5
    r = q * q
    out[mid] = ((((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q /
                (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1))[mid]
    return out


def flip_rate(phi, sd, n_sim=4000, n_pos=430, win=25, side=50, margin=0.10, seed=12002):
    """Per-trace false-flip rate for a signal-free trajectory.

    The uninformative probe is modelled on the PROBABILITY scale: p_t = 0.5 + e_t with
    e_t an AR(1) process of lag-1 correlation `phi` and marginal sd `sd`, clipped to
    [0,1].  The frozen smoothing (centred moving average, window `win`) is applied, and
    the frozen flip rule is evaluated.
    """
    rng = np.random.default_rng(seed)
    e = rng.standard_normal((n_sim, n_pos))
    for t in range(1, n_pos):
        e[:, t] = phi * e[:, t - 1] + np.sqrt(1 - phi ** 2) * e[:, t]
    p = np.clip(0.5 + sd * e, 0.0, 1.0)
    s = smooth(p, win)
    return float(np.mean(flip_index(s, side, margin) >= 0))


def smooth(p, win=25):
    """Centred moving average, window `win`, shrinking at the edges. Frozen."""
    p = np.atleast_2d(p).astype(np.float64)
    c = np.cumsum(np.pad(p, ((0, 0), (1, 0))), axis=1)
    n = p.shape[1]
    half = win // 2
    lo = np.maximum(np.arange(n) - half, 0)
    hi = np.minimum(np.arange(n) + half + 1, n)
    out = (c[:, hi] - c[:, lo]) / (hi - lo)
    return out


def flip_index(S, side=50, margin=0.10):
    """Vectorised has_flip over rows of S: index of the FIRST flip, or -1. Same rule."""
    S = np.atleast_2d(S)
    n = S.shape[1]
    c = np.cumsum(np.pad(S, ((0, 0), (1, 0))), axis=1)
    idx = np.arange(side, n - side + 1)
    pre = (c[:, idx] - c[:, idx - side]) / side
    post = (c[:, idx + side] - c[:, idx]) / side
    a, b = S[:, idx - 1], S[:, idx]
    up = (a < 0.5) & (b >= 0.5) & (pre <= 0.5 - margin) & (post >= 0.5 + margin)
    dn = (a >= 0.5) & (b < 0.5) & (pre >= 0.5 + margin) & (post <= 0.5 - margin)
    hit = up | dn
    first = np.where(hit.any(axis=1), idx[np.argmax(hit, axis=1)], -1)
    return first


def has_flip(s, side=50, margin=0.10):
    """First frozen FLIP in a smoothed trajectory, or None.

    A flip at index c requires (i) s[c-1] and s[c] on opposite sides of 0.5, (ii) the
    mean of the `side` samples ending at c-1 is on the pre-side by at least `margin`,
    (iii) the mean of the `side` samples starting at c is on the post-side by at least
    `margin`.  Both windows must exist in full.
    """
    s = np.asarray(s)
    n = s.size
    for c in range(side, n - side + 1):
        a, b = s[c - 1], s[c]
        if (a < 0.5) == (b < 0.5):
            continue
        pre = s[c - side:c].mean()
        post = s[c:c + side].mean()
        if b >= 0.5:                       # upward crossing
            if pre <= 0.5 - margin and post >= 0.5 + margin:
                return c
        else:                              # downward crossing
            if pre >= 0.5 + margin and post <= 0.5 - margin:
                return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onset", action="store_true")
    ap.add_argument("--flip", action="store_true")
    a = ap.parse_args()
    both = not (a.onset or a.flip)
    rows = []

    if a.onset or both:
        print("=== SIM 1 · family-wise false-onset rate under the global null ===")
        print("grid: rho_layer x rho_bin ; criterion = k consecutive bins above the "
              "pct-th percentile of 500 permutations, fired if ANY of the 8 layers does\n")
        print("%-9s %-8s %-22s %s" % ("rho_layer", "rho_bin", "criterion", "FWER"))
        for k, pct, name in ((2, 0.95, "2 consec @ p95"), (3, 0.95, "3 consec @ p95"),
                             (2, 0.99, "2 consec @ p99"), (3, 0.99, "3 consec @ p99"),
                             (4, 0.99, "4 consec @ p99"), (3, 0.995, "3 consec @ p99.5"),
                             (4, 0.995, "4 consec @ p99.5")):
            for rl in (0.0, 0.5, 0.8):
                for rb in (0.0, 0.4, 0.7, 0.9):
                    f = onset_fwer(rl, rb, k, pct)
                    print("%-9.1f %-8.1f %-22s %.4f" % (rl, rb, name, f))
                    rows.append({"sim": "onset_fwer", "rho_layer": rl, "rho_bin": rb,
                                 "criterion": name, "value": round(f, 4)})
            worst = max(r["value"] for r in rows if r["criterion"] == name)
            print("  -> WORST CELL for %-16s = %.4f   %s\n"
                  % (name, worst, "PASSES 0.05" if worst <= 0.05 else "FAILS 0.05"))
            rows.append({"sim": "onset_fwer_worst", "rho_layer": "", "rho_bin": "",
                         "criterion": name, "value": round(worst, 4)})

    if a.flip or both:
        print("\n=== SIM 2 · per-trace false-flip rate, signal-free trajectory ===")
        print("MA window 25, side 50, margin 0.10 (all frozen); 430 positions "
              "(form-B mean output length)\n")
        print("%-6s %-6s %s" % ("phi", "sd", "false-flip rate per trace"))
        for side, margin in ((50, 0.10), (50, 0.15), (100, 0.10), (100, 0.15)):
            for phi in (0.90, 0.95, 0.98, 0.99):
                for sd in (0.10, 0.20, 0.30):
                    f = flip_rate(phi, sd, side=side, margin=margin)
                    print("%-6.2f %-6.2f side=%-4d margin=%.2f  %.4f"
                          % (phi, sd, side, margin, f))
                    rows.append({"sim": "false_flip", "rho_layer": phi, "rho_bin": sd,
                                 "criterion": "MA25 side%d margin%.2f" % (side, margin),
                                 "value": round(f, 4)})
        for crit in sorted({r["criterion"] for r in rows if r["sim"] == "false_flip"}):
            w = max(r["value"] for r in rows if r["sim"] == "false_flip"
                    and r["criterion"] == crit)
            print("  -> WORST CELL for %-24s = %.4f" % (crit, w))
            rows.append({"sim": "false_flip_worst", "rho_layer": "", "rho_bin": "",
                         "criterion": crit, "value": round(w, 4)})

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "w12_power.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["sim", "rho_layer", "rho_bin", "criterion", "value"])
        w.writeheader(); w.writerows(rows)
    print("\nwrote", OUT / "w12_power.csv")


if __name__ == "__main__":
    sys.exit(main())
