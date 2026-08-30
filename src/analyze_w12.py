"""W12 Step 2 items 3-7: decodability-vs-position curves, onset, belief-flip
trajectories, and the W13 cut-point table.  Runs pod-side over the W12 capture.

Everything below is frozen by PR-008 before the capture exists.

  UNITS.  Every probe's unit is a TRACE. A (trace, bin) mean residual vector is one row;
          a trace contributes at most one row per (alignment, bin).
  LABEL.  p̂ from the frozen W5 recipe (`direction_w5.phat_of` over the W3 judge cache);
          `unclear` traces are excluded entirely.
  ARM CONFOUND.  Pooling both arms would let a probe reach balanced accuracy 0.912 by
          decoding the PROMPT (arm predicts p̂ that well), which is present from position
          0 and would make "onset" meaningless.  The primary probe therefore ARM-CENTERS:
          within each training fold, each arm's mean row is subtracted from every row of
          that arm (train means only -- no test leakage).  A control probe predicting ARM
          on the same centred rows and the same folds must sit at chance; and the
          above_good-only probe (W5's cell, where the prompt is constant) is reported
          beside the primary as the confound-free robustness reading.

  python3 src/analyze_w12.py --smoke      # laptop: synthetic acts, tiny nulls
  python  src/analyze_w12.py              # the real thing, on the pod
"""
import argparse, csv, json, os, sys, time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import w12_power as pw                                     # noqa: E402

ACTS = ROOT / "runs" / "w12_acts"
OUT = ROOT / "analysis" / "out"
ARMS = ("above_good", "below_good")
LAYERS = (21, 23, 25, 27, 29, 31, 33, 35)

# ---- PR-008 frozen hyper-parameters -------------------------------------------------
N_REPEAT = 20
TEST_FRAC = 0.30
N_PERM = 500
C_REG = 1.0
MAX_ITER = 2000
SEED_SPLIT = 0
SEED_PERM = 12008
N_DECILE = 10
OFF_LO, OFF_HI, OFF_W = -250, 50, 25          # alignment (b)
N_OFFBIN = (OFF_HI - OFF_LO) // OFF_W         # 12
ONSET_K = 4                                    # tightened by the pre-freeze sim
ONSET_PCT = 0.995                              # tightened by the pre-freeze sim
TRAJ_WIN = 25
TRAJ_SIDE = 50
TRAJ_MARGIN = 0.10
TRAJ_SIDE2 = 100                               # secondary, FWER-controlled flip rule
TRAJ_MARGIN2 = 0.15
TRAJ_TRAIN_STRIDE = 5
TRAJ_NCOMP = 128
CUT_BACKOFF = 25                               # cut point >= belief - 25
CUT_MARGIN = 0.10
TRAJ_DOWNSAMPLE = 5


def offbin(off):
    return (off - OFF_LO) // OFF_W if OFF_LO <= off < OFF_HI else None


def bin_label(align, b):
    if align == "a":
        return "decile %d [%.1f,%.1f)" % (b, b / 10, (b + 1) / 10)
    return "[%+d,%+d)" % (OFF_LO + b * OFF_W, OFF_LO + (b + 1) * OFF_W)


# =====================================================================================
# loading / reduction
# =====================================================================================

def load_index():
    return {a: json.loads((ACTS / ("w12_index_%s.json" % a)).read_text()) for a in ARMS}


def cell_plan(idx):
    """Every (trace, alignment, bin) cell and which gen_pos belong to it."""
    traces, cells = [], {}
    for a in ARMS:
        for t in idx[a]["traces"]:
            if t["phat"] is None:
                continue
            u = len(traces)
            traces.append({"u": u, "arm": a, **{k: t[k] for k in
                          ("trace_i", "seed", "n_gen", "phat", "belief_gen_pos",
                           "row_first", "row_last", "verdict")},
                           "est": t["est"]})
            n = t["n_gen"]
            for g in range(n):
                b = min(N_DECILE - 1, (g * N_DECILE) // n)
                cells.setdefault((u, "a", b), []).append(g)
            if t["belief_gen_pos"] is not None:
                for g in range(n):
                    b = offbin(g - t["belief_gen_pos"])
                    if b is not None:
                        cells.setdefault((u, "b", b), []).append(g)
    return traces, cells


def reduce_shards(idx, traces, cells, best_layer_idx=None, only_P=False):
    """Pass over the shards. Returns (M, keys) with M[cell, layer, d] the mean residual
    of that (trace, alignment, bin) cell, and -- if best_layer_idx is given -- also the
    per-position matrix at that layer, [n_rows_total, d]."""
    from safetensors.numpy import load_file
    keys = sorted(cells)
    kpos = {k: i for i, k in enumerate(keys)}
    # per-trace list of (row of M, generated positions) — derived from `cells` itself, so
    # any alignment present in `cells` is reduced, not just the two PR-008 freezes.
    tcells = {}
    for k, g in cells.items():
        tcells.setdefault(k[0], []).append((kpos[k], np.array(g)))
    d = 5120
    M = None
    P = {}
    by_arm = {}
    for t in traces:
        by_arm.setdefault(t["arm"], []).append(t)
    for a in ARMS:
        shards = sorted(ACTS.glob("w12_acts_%s_*.safetensors" % a))
        off = 0
        want = {t["row_first"]: t for t in by_arm.get(a, [])}
        for sp in shards:
            A = load_file(str(sp))["acts"]                  # [n,8,d]
            if M is None:
                d = A.shape[2]
                M = np.zeros((len(keys), len(LAYERS), d), dtype=np.float32)
            hi = off + A.shape[0]
            for r0, t in want.items():
                if not (off <= r0 < hi):
                    continue
                assert t["row_last"] < hi, "trace %s straddles shards" % t["trace_i"]
                sl = A[r0 - off:t["row_last"] - off + 1].astype(np.float32)
                if not only_P:
                    for ki, g in tcells.get(t["u"], []):
                        M[ki] = sl[g].mean(axis=0)
                if best_layer_idx is not None:
                    P[t["u"]] = sl[:, best_layer_idx, :].astype(np.float16)
            off = hi
    return M, keys, kpos, P


# =====================================================================================
# the probe
# =====================================================================================

def splits(y, n_repeat=N_REPEAT, seed0=SEED_SPLIT):
    out = []
    n = len(y)
    for r in range(n_repeat):
        rng = np.random.default_rng(seed0 + r)
        te = []
        for c in (+1, -1):
            i = np.where(y == c)[0].copy()
            rng.shuffle(i)
            te.extend(i[:max(1, int(round(TEST_FRAC * i.size)))].tolist())
        te = set(te)
        out.append((np.array([i for i in range(n) if i not in te]), np.array(sorted(te))))
    return out


def bacc(y, p):
    y, p = np.asarray(y), np.asarray(p)
    a = []
    for c in (+1, -1):
        m = y == c
        if not m.any():
            return np.nan
        a.append((p[m] == c).mean())
    return float(np.mean(a))


def _cell_job(arg):
    """One (layer, alignment, bin) cell: observed + N_PERM permutations over N_REPEAT
    splits.  `labels` is [1+n_perm, n_units]; row 0 observed."""
    X, arm_code, labels, center, n_perm = arg
    from sklearn.linear_model import LogisticRegression
    y = labels[0]
    n = len(y)
    if n < 8 or (y == 1).sum() < 3 or (y == -1).sum() < 3:
        return np.nan, np.array([]), n, int((y == 1).sum()), int((y == -1).sum())
    acc = np.full((labels.shape[0], N_REPEAT), np.nan, dtype=np.float32)
    for r, (tr, te) in enumerate(splits(y)):
        Z = X.copy()
        if center:                                # arm-centre on TRAIN rows only
            for c in np.unique(arm_code):
                m_tr = tr[arm_code[tr] == c]
                if m_tr.size:
                    Z[arm_code == c] -= Z[m_tr].mean(axis=0)
        mu = Z[tr].mean(axis=0)
        Ztr = Z[tr] - mu
        sc = float(np.linalg.norm(Ztr, axis=1).mean()) or 1.0
        Ztr /= sc
        _, S, Vt = np.linalg.svd(Ztr, full_matrices=False)
        Vt = Vt[:int((S > 1e-6 * S[0]).sum())] if S.size else Vt
        Ptr, Pte = Ztr @ Vt.T, ((Z[te] - mu) / sc) @ Vt.T
        for j in range(labels.shape[0]):
            lab = labels[j]
            if np.unique(lab[tr]).size < 2:
                continue
            clf = LogisticRegression(C=C_REG, max_iter=MAX_ITER, class_weight="balanced")
            clf.fit(Ptr, lab[tr])
            acc[j, r] = bacc(lab[te], clf.predict(Pte))
    null = np.nanmean(acc[1:], axis=1) if labels.shape[0] > 1 else np.array([])
    return float(np.nanmean(acc[0])), null, n, int((y == 1).sum()), int((y == -1).sum())


def label_matrix(y, n_perm, seed=SEED_PERM):
    rng = np.random.default_rng(seed)
    y = np.asarray(y, dtype=np.int8)
    return np.stack([y] + [y[rng.permutation(y.size)] for _ in range(n_perm)])


def run_family(name, M, keys, kpos, traces, sel_u, center, n_perm, procs):
    """All (layer, alignment, bin) cells for one probe family."""
    ylab = np.array([traces[u]["phat"] if name != "control_arm"
                     else (+1 if traces[u]["arm"] == "above_good" else -1)
                     for u in sel_u], dtype=np.int8)
    armc = np.array([0 if traces[u]["arm"] == "above_good" else 1 for u in sel_u])
    pos = {u: i for i, u in enumerate(sel_u)}
    jobs, meta = [], []
    for li in range(len(LAYERS)):
        for al in ("a", "b"):
            for b in range(N_DECILE if al == "a" else N_OFFBIN):
                rows = [(pos[u], kpos[(u, al, b)]) for u in sel_u if (u, al, b) in kpos]
                if len(rows) < 8:
                    continue
                ui = np.array([r[0] for r in rows])
                X = M[np.array([r[1] for r in rows]), li, :]
                lab = label_matrix(ylab[ui], n_perm)
                jobs.append((X, armc[ui], lab, center, n_perm))
                meta.append((LAYERS[li], al, b))
    t0 = time.time()
    if procs > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(procs) as pool:
            res = pool.map(_cell_job, jobs, chunksize=1)
    else:
        res = [_cell_job(j) for j in jobs]
    print("  %-14s %4d cells in %.1f s" % (name, len(jobs), time.time() - t0), flush=True)
    rows = []
    for (layer, al, b), (obs, null, n, npos, nneg) in zip(meta, res):
        r = {"family": name, "layer": layer, "alignment": al, "bin": b,
             "bin_label": bin_label(al, b), "n_traces": n, "n_pos": npos, "n_neg": nneg,
             "bacc": round(obs, 4) if obs == obs else ""}
        for p in (0.95, 0.99, 0.995):
            r["null_p%s" % str(p).replace("0.", "")] = (
                round(float(np.quantile(null, p)), 4) if null.size else "")
        r["null_mean"] = round(float(np.mean(null)), 4) if null.size else ""
        r["p_value"] = (round(float((np.sum(null >= obs) + 1) / (null.size + 1)), 4)
                        if null.size and obs == obs else "")
        rows.append(r)
    return rows


def onset_of(rows, family, layer, k=ONSET_K, pct=ONSET_PCT):
    col = "null_p%s" % str(pct).replace("0.", "")
    sel = {r["bin"]: r for r in rows if r["family"] == family
           and r["layer"] == layer and r["alignment"] == "b"}
    sig = [b in sel and sel[b]["bacc"] != "" and sel[b]["bacc"] > sel[b][col]
           for b in range(N_OFFBIN)]
    for b in range(N_OFFBIN - k + 1):
        if all(sig[b:b + k]):
            return b, sig
    return None, sig


# =====================================================================================
# trajectories, flips, cut points
# =====================================================================================

def trajectories(P, traces, sel_u, n_shuffle=5, procs=1, seed=SEED_PERM):
    """Held-out P(p̂=+1) at every generated position of every selected trace, at the best
    layer.  Training rows: every TRAJ_TRAIN_STRIDE-th position of the training traces,
    arm-centred on training rows.  Scoring rows: every position of the held-out traces.
    Each trace's trajectory is the mean over the repeats in which it was held out.
    Returns (scores, shuffled_scores) with scores[u] a float array of length n_gen."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.decomposition import TruncatedSVD
    y = np.array([traces[u]["phat"] for u in sel_u], dtype=np.int8)
    armc = np.array([0 if traces[u]["arm"] == "above_good" else 1 for u in sel_u])
    rng = np.random.default_rng(seed)
    shuf = [y[rng.permutation(y.size)] for _ in range(n_shuffle)]
    acc = {u: np.zeros(traces[u]["n_gen"]) for u in sel_u}
    cnt = {u: np.zeros(traces[u]["n_gen"]) for u in sel_u}
    sacc = [{u: np.zeros(traces[u]["n_gen"]) for u in sel_u} for _ in range(n_shuffle)]
    for r, (tr, te) in enumerate(splits(y)):
        Xtr, ytr, atr = [], [], []
        for i in tr:
            u = sel_u[i]
            g = np.arange(0, traces[u]["n_gen"], TRAJ_TRAIN_STRIDE)
            Xtr.append(P[u][g].astype(np.float32))
            ytr.append(np.full(g.size, i))
            atr.append(np.full(g.size, armc[i]))
        Xtr = np.concatenate(Xtr); ytr = np.concatenate(ytr); atr = np.concatenate(atr)
        means = {c: Xtr[atr == c].mean(axis=0) for c in np.unique(atr)}
        for c, m in means.items():
            Xtr[atr == c] -= m
        mu = Xtr.mean(axis=0)
        Xtr -= mu
        sc = float(np.linalg.norm(Xtr, axis=1).mean()) or 1.0
        Xtr /= sc
        sv = TruncatedSVD(n_components=min(TRAJ_NCOMP, Xtr.shape[1] - 1), random_state=0)
        Ptr = sv.fit_transform(Xtr)
        for lab, sink in [(y, acc)] + [(s, sacc[k]) for k, s in enumerate(shuf)]:
            clf = LogisticRegression(C=C_REG, max_iter=MAX_ITER, class_weight="balanced")
            clf.fit(Ptr, lab[ytr])
            k1 = list(clf.classes_).index(1)
            for i in te:
                u = sel_u[i]
                Z = P[u].astype(np.float32) - means[armc[i]] - mu
                pr = clf.predict_proba(sv.transform(Z / sc))[:, k1]
                sink[u] += pr
                if sink is acc:
                    cnt[u] += 1
    out = {u: acc[u] / np.maximum(cnt[u], 1) for u in sel_u}
    outs = [{u: s[u] / np.maximum(cnt[u], 1) for u in sel_u} for s in sacc]
    return out, outs


def flips_of(smoothed, side, margin):
    f = pw.flip_index(smoothed[None, :], side=side, margin=margin)[0]
    return int(f) if f >= 0 else None


def settle_pos(s, margin=CUT_MARGIN):
    """First position t such that |s[u] - s[-1]| <= margin for every u >= t."""
    d = np.abs(s - s[-1]) > margin
    idx = np.where(d)[0]
    return (int(idx[-1]) + 1) if idx.size else 0


# =====================================================================================
# driver
# =====================================================================================

def synth(traces, cells, keys, kpos, sel_u, seed=7):
    """--smoke only: activations with a planted belief signal that switches on 100 tokens
    before the cause token, so the whole pipeline can be exercised on the laptop."""
    rng = np.random.default_rng(seed)
    d = 64
    v = rng.standard_normal(d); v /= np.linalg.norm(v)
    arm_v = rng.standard_normal(d); arm_v /= np.linalg.norm(arm_v)
    M = rng.standard_normal((len(keys), len(LAYERS), d)).astype(np.float32)
    P = {}
    for u in sel_u:
        t = traces[u]
        bel = t["belief_gen_pos"]
        g = np.arange(t["n_gen"])
        on = (g >= (bel - 100)) if bel is not None else (g >= 0.6 * t["n_gen"])
        X = rng.standard_normal((t["n_gen"], d)).astype(np.float32)
        X += np.outer(on * t["phat"] * 1.2, v)
        X += np.outer(np.ones(t["n_gen"]) * (1 if t["arm"] == "above_good" else -1) * 3.0,
                      arm_v)
        P[u] = X.astype(np.float16)
        for al in ("a", "b"):
            for b in range(N_DECILE if al == "a" else N_OFFBIN):
                gg = cells.get((u, al, b))
                if gg:
                    M[kpos[(u, al, b)]] = np.tile(X[np.array(gg)].mean(axis=0),
                                                  (len(LAYERS), 1))
    return M, P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()
    n_perm = 40 if a.smoke else N_PERM
    n_shuf = 2 if a.smoke else 5
    OUT.mkdir(parents=True, exist_ok=True)

    idx = load_index()
    traces, cells = cell_plan(idx)
    keys = sorted(cells)
    kpos = {k: i for i, k in enumerate(keys)}
    sel_all = [t["u"] for t in traces]
    sel_ag = [t["u"] for t in traces if t["arm"] == "above_good"]
    n_bel = sum(1 for t in traces if t["belief_gen_pos"] is not None)
    print("labelled traces %d (above_good %d) | with cause-token %d | no cause-token %d "
          "(alignment (a) only, counted)" % (len(traces), len(sel_ag), n_bel,
                                             len(traces) - n_bel), flush=True)

    if a.smoke:
        M, P = synth(traces, cells, keys, kpos, sel_all)
        best_li = 0
    else:
        M, keys, kpos, _ = reduce_shards(idx, traces, cells)
        best_li = None

    # ---- curves ---------------------------------------------------------------------
    rows = []
    rows += run_family("primary", M, keys, kpos, traces, sel_all, True, n_perm, a.procs)
    rows += run_family("control_arm", M, keys, kpos, traces, sel_all, True, n_perm, a.procs)
    rows += run_family("above_good", M, keys, kpos, traces, sel_ag, False, n_perm, a.procs)

    # ---- best layer: argmax mean alignment-(a) balanced accuracy, primary family ------
    lay_mean = {}
    for L in LAYERS:
        v = [r["bacc"] for r in rows if r["family"] == "primary" and r["layer"] == L
             and r["alignment"] == "a" and r["bacc"] != ""]
        lay_mean[L] = float(np.mean(v)) if v else float("nan")
    best_layer = max(lay_mean, key=lambda L: lay_mean[L])
    best_li = LAYERS.index(best_layer)
    print("layer means (alignment a, primary):",
          {L: round(v, 4) for L, v in lay_mean.items()}, "-> BEST", best_layer, flush=True)

    onsets = {}
    for fam in ("primary", "above_good", "control_arm"):
        b, sig = onset_of(rows, fam, best_layer)
        onsets[fam] = {"bin": b, "bin_label": bin_label("b", b) if b is not None else "",
                       "sig": sig}
        print("onset[%s] = %s  sig=%s" % (fam, onsets[fam]["bin_label"] or "NONE",
                                          "".join("1" if s else "0" for s in sig)))

    with open(OUT / "w12_curves.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ---- trajectories at the best layer ---------------------------------------------
    if not a.smoke:
        _, _, _, P = reduce_shards(idx, traces, cells, best_layer_idx=best_li,
                                   only_P=True)
    traj, traj_shuf = trajectories(P, traces, sel_all, n_shuffle=n_shuf, seed=SEED_PERM)
    sm = {u: pw.smooth(traj[u][None, :], TRAJ_WIN)[0] for u in sel_all}
    sm_shuf = [{u: pw.smooth(s[u][None, :], TRAJ_WIN)[0] for u in sel_all}
               for s in traj_shuf]

    frows, trows = [], []
    for u in sel_all:
        t = traces[u]
        s = sm[u]
        f1 = flips_of(s, TRAJ_SIDE, TRAJ_MARGIN)
        f2 = flips_of(s, TRAJ_SIDE2, TRAJ_MARGIN2)
        post = ""
        if f1 is not None:
            new_side = +1 if s[f1] >= 0.5 else -1
            ests = [e for e in t["est"] if e["gen_pos"] >= f1]
            toward = sum(1 for e in ests
                         if (+1 if e["value"] > idx[t["arm"]]["tau"] else -1) == new_side)
            post = ("toward" if ests and toward * 2 > len(ests) else
                    "away" if ests and toward * 2 < len(ests) else
                    "tied" if ests else "no_post_est")
        st = settle_pos(s)
        cut = min((t["belief_gen_pos"] - CUT_BACKOFF) if t["belief_gen_pos"] is not None
                  else -1, st - 1)
        frows.append({"arm": t["arm"], "trace_i": t["trace_i"], "seed": t["seed"],
                      "phat": t["phat"], "n_gen": t["n_gen"],
                      "belief_gen_pos": t["belief_gen_pos"] if t["belief_gen_pos"]
                      is not None else "",
                      "flip_pos": f1 if f1 is not None else "",
                      "flip_pos_strict": f2 if f2 is not None else "",
                      "flip_to": ("+1" if f1 is not None and s[f1] >= 0.5 else
                                  "-1" if f1 is not None else ""),
                      "n_est_post_flip": len([e for e in t["est"] if f1 is not None
                                              and e["gen_pos"] >= f1]),
                      "post_flip_estimates": post,
                      "score_start": round(float(s[0]), 4),
                      "score_end": round(float(s[-1]), 4),
                      "settle_pos": st,
                      "cut_point": cut if cut >= 0 else ""})
        for g in range(0, t["n_gen"], TRAJ_DOWNSAMPLE):
            trows.append({"arm": t["arm"], "trace_i": t["trace_i"], "gen_pos": g,
                          "offset_to_cause": (g - t["belief_gen_pos"])
                          if t["belief_gen_pos"] is not None else "",
                          "phat": t["phat"], "score_smoothed": round(float(s[g]), 4)})

    n_flip = sum(1 for r in frows if r["flip_pos"] != "")
    n_flip2 = sum(1 for r in frows if r["flip_pos_strict"] != "")
    ff = [np.mean([flips_of(S[u], TRAJ_SIDE, TRAJ_MARGIN) is not None for u in sel_all])
          for S in sm_shuf]
    ff2 = [np.mean([flips_of(S[u], TRAJ_SIDE2, TRAJ_MARGIN2) is not None for u in sel_all])
           for S in sm_shuf]
    print("flips: %d/%d (ordered rule) | %d/%d (strict rule) | empirical label-shuffled "
          "false-flip rate %.4f / %.4f" % (n_flip, len(frows), n_flip2, len(frows),
                                           float(np.mean(ff)), float(np.mean(ff2))))

    with open(OUT / "w12_flips.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(frows[0].keys()))
        w.writeheader(); w.writerows(frows)
    with open(OUT / "w12_trajectories.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trows[0].keys()))
        w.writeheader(); w.writerows(trows)

    # ---- cut points and W13 pairs ----------------------------------------------------
    crows = []
    for r in frows:
        crows.append({k: r[k] for k in ("arm", "trace_i", "seed", "phat", "n_gen",
                                        "belief_gen_pos", "settle_pos", "cut_point")})
    valid = [r for r in crows if r["cut_point"] != ""]
    pairs = disjoint = 0
    for arm in ARMS:
        p = [r for r in valid if r["arm"] == arm and r["phat"] == 1]
        m = [r for r in valid if r["arm"] == arm and r["phat"] == -1]
        pairs += len(p) * len(m)
        disjoint += min(len(p), len(m))
        print("pairs %s: %d(+1) x %d(-1) = %d possible, %d disjoint"
              % (arm, len(p), len(m), len(p) * len(m), min(len(p), len(m))))
    with open(OUT / "w12_cutpoints.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(crows[0].keys()))
        w.writeheader(); w.writerows(crows)

    json.dump({"best_layer": best_layer, "layer_means_alignment_a": lay_mean,
               "onset": {k: {"bin": v["bin"], "bin_label": v["bin_label"],
                             "sig": v["sig"]} for k, v in onsets.items()},
               "onset_rule": {"k_consecutive": ONSET_K, "percentile": ONSET_PCT},
               "n_traces_labelled": len(traces), "n_with_cause_token": n_bel,
               "n_flips_ordered_rule": n_flip, "n_flips_strict_rule": n_flip2,
               "false_flip_empirical_ordered": float(np.mean(ff)),
               "false_flip_empirical_strict": float(np.mean(ff2)),
               "n_valid_cutpoints": len(valid), "n_w13_pairs_possible": pairs,
               "n_w13_pairs_disjoint": disjoint,
               "post_flip": {k: sum(1 for r in frows if r["post_flip_estimates"] == k)
                             for k in ("toward", "away", "tied", "no_post_est")}},
              open(OUT / "w12_headline.json", "w"), indent=1)
    print("\nwrote w12_curves.csv w12_trajectories.csv w12_flips.csv w12_cutpoints.csv "
          "w12_headline.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
