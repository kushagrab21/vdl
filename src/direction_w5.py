"""W5: the believed-direction vector v_p̂, layer profile, probes with nulls, invariance.

Implements PR-004 exactly and nothing else. Every rule below is frozen in PR-004 before this
file was run on any activation; the commit that carries PR-004 also carries this file.

WHAT IS COMPUTED
  v_p̂(form, layer)  trace-weighted, d_t-stratified difference in means between believed-above
                    (p̂=+1) and believed-below (p̂=-1) traces, over `est` points, WITHIN the
                    above_good arm only (the one cell where both p̂ classes have n>=14).
  v_p (form, layer) the original prompt-side direction: above_good arm minus below_good arm,
                    all traces with `est` points, same trace weighting and d_t stratification.
  probes            per layer, per form: L2 logistic regression on `est` points predicting p̂,
                    split BY TRACE, scored on held-out traces, against a 1000-draw trace-level
                    label-permutation null. Positive control: the same probe for d_t.
  timing split      the same held-out traces scored separately on their est points BEFORE and
                    AFTER the trace's first "good cause"/"bad cause" token.
  invariance        cos(v_p̂^A, v_p̂^B) per layer vs a 1000-draw label-shuffled null, and
                    probe transfer A -> B.
  belief control    at `belief` points, probe the matched string's polarity. Apparatus sanity.

WHY THE SVD STEP IS NOT A MODELLING CHOICE
  d_model is 5120 and a training fold holds ~66 points. For L2-penalised linear logistic
  regression the fitted weight vector provably lies in the span of the training rows, so
  projecting onto an orthonormal basis of that span (rank r <= n_train) changes no fitted
  decision value at all — it only makes ~4M permutation fits affordable. The basis is built
  from the TRAINING rows only and never sees a label, so it is identical for the observed fit
  and for all 1000 permutations of a fold.

  python3 src/direction_w5.py --smoke              # form A only, tiny nulls, no projections
  python  src/direction_w5.py                      # the real thing, on the pod
  python3 src/direction_w5.py --recount-subsample   # laptop: v_p̂(l*) from the 10% subsample
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"
POS = OUT / "w4_positions"
ACTS = ROOT / "runs" / "w4_acts"
VEC = OUT / "w5_vectors"
SUB = ROOT / "runs" / "w5_subsample"

MODEL = "Qwen/Qwen2.5-14B-Instruct"
TAU = {"A": 15300000, "B": 4500000000}
CACHE = OUT / "w3_direction_cache.json"

# Arm order defines the GLOBAL point index (identical to replay_w4.ARMS). The 10% subsample
# rule is "every 10th point of that index", so this list must not be reordered.
ARMS = [("A", "below_good"), ("A", "above_good"), ("A", "neutral"),
        ("B", "below_good"), ("B", "above_good"), ("B", "baseline")]

# --- PR-004 frozen hyper-parameters ---------------------------------------------------
N_PERM = 1000          # label permutations behind every null
N_REPEAT = 20          # stratified 70/30 trace splits; the reported metric is their mean
TEST_FRAC = 0.30
C_REG = 1.0            # sklearn default; L2, lbfgs, class_weight="balanced"
MAX_ITER = 2000
SEED_SPLIT = 0         # split rng seeds are SEED_SPLIT + repeat index
SEED_PERM = 1234       # every permutation set is drawn from this seed
SUBSAMPLE_STRIDE = 10  # every 10th point of the global index


# =====================================================================================
# loading
# =====================================================================================

def load_index(form, arm):
    return json.loads((POS / ("w4_positions_%s_%s.json" % (form, arm))).read_text())


def load_acts(form, arm):
    from safetensors.numpy import load_file
    return load_file(str(ACTS / ("w4_acts_%s_%s.safetensors" % (form, arm))))["acts"]


def verdicts():
    """{(form, arm, trace_i): 'correct'|'incorrect'|'unclear'} from the frozen W3 judge cache."""
    raw = json.loads(CACHE.read_text())
    out = {}
    for key, rec in raw.items():
        model, form, arm, i = key.split("|")
        if model != MODEL:
            continue
        out[(form, arm, int(i))] = rec["direction"]
    return out


def phat_of(arm, verdict):
    """PR-004 item 1. p̂ = +1 believes ABOVE is favoured, -1 believes BELOW. unclear -> None."""
    if verdict not in ("correct", "incorrect"):
        return None
    if arm == "above_good":
        return +1 if verdict == "correct" else -1
    if arm == "below_good":
        return -1 if verdict == "correct" else +1
    return None


def dt_of(point, form):
    """The est literal's side of tau. `est` points can never equal tau (those are tau_echo)."""
    return +1 if point["value"] > TAU[form] else -1


# =====================================================================================
# trace-weighted, d_t-stratified difference in means  (PR-004 item 2)
# =====================================================================================

def stratum_means(points, acts, keys):
    """Mean activation per (trace key, d_t stratum). Returns (M[n,L,d], meta[n]).

    A trace whose est literals straddle tau contributes to BOTH strata, which is what
    "average within each stratum, then average strata" requires.
    """
    buckets = {}
    for k, p in enumerate(points):
        buckets.setdefault((keys[k], p["dt"]), []).append(p["row_local"])
    meta, rows = [], []
    for (key, s), idxs in sorted(buckets.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        meta.append({"key": key, "dt": s, "n_points": len(idxs)})
        rows.append(acts[idxs].astype(np.float32).mean(axis=0))
    return np.stack(rows), meta


def contrast_weights(meta, labels, strata=(+1, -1)):
    """Row weights w with w @ M = the stratified, trace-weighted (+1 minus -1) contrast.
    Also returns the per-stratum (n_pos, n_neg) trace counts."""
    w = np.zeros(len(meta), dtype=np.float32)
    counts, used = {}, 0
    for s in strata:
        pos = [i for i, m in enumerate(meta) if m["dt"] == s and labels[i] == +1]
        neg = [i for i, m in enumerate(meta) if m["dt"] == s and labels[i] == -1]
        counts[s] = (len(pos), len(neg))
        if not pos or not neg:
            continue
        used += 1
        w[pos] += 1.0 / len(pos)
        w[neg] -= 1.0 / len(neg)
    if used == 0:
        raise RuntimeError("no d_t stratum has both p-hat classes")
    return w / used, counts, used


def contrast(M, meta, labels):
    w, counts, used = contrast_weights(meta, labels)
    v = (w @ M.reshape(len(meta), -1)).reshape(M.shape[1], M.shape[2])
    return v, counts, used


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# =====================================================================================
# probes  (PR-004 item 4)
#
# Units. A probe's scoring unit is a TRACE for the p̂ and belief-polarity targets and a
# POINT for the d_t control (d_t varies within a trace, so a trace has no single d_t).
# `unit_of_point` maps every point to its unit; the label vector is always aligned to the
# unit list, which makes the observed labelling and a permuted labelling the same object.
# =====================================================================================

def _bacc(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    accs = []
    for c in (+1, -1):
        m = y_true == c
        if not m.any():
            return np.nan
        accs.append((y_pred[m] == c).mean())
    return float(np.mean(accs))


def _splits(n_traces, strat, n_repeat, seed0):
    """n_repeat 70/30 splits of the trace list (positions 0..n_traces-1), stratified by
    `strat` when it is given."""
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


def _layer_job(arg):
    """Every fit for ONE layer: the observed labelling plus N_PERM permutations, over
    N_REPEAT splits. `labels` is [1 + n_perm, n_units]; row 0 is the observed labelling."""
    (Xl, trace_of_point, unit_of_point, n_traces, strat, labels, n_repeat, seed0,
     sub_names, sub_masks) = arg
    from sklearn.linear_model import LogisticRegression
    keys = ("all",) + tuple(sub_names)
    n_lab = labels.shape[0]
    acc = np.full((n_lab, n_repeat), np.nan, dtype=np.float32)
    acc_sub = {k: np.full(n_repeat, np.nan, dtype=np.float32) for k in sub_names}
    n_units_seen = {k: [] for k in keys}

    for r, (tr, te) in enumerate(_splits(n_traces, strat, n_repeat, seed0)):
        tr_set, te_set = set(tr.tolist()), set(te.tolist())
        itr = np.array([i for i, t in enumerate(trace_of_point) if t in tr_set])
        ite = np.array([i for i, t in enumerate(trace_of_point) if t in te_set])
        if itr.size == 0 or ite.size == 0:
            continue
        Xtr, Xte = Xl[itr], Xl[ite]
        mu = Xtr.mean(axis=0)
        Ztr = Xtr - mu
        scale = float(np.linalg.norm(Ztr, axis=1).mean()) or 1.0
        Ztr = Ztr / scale
        _, S, Vt = np.linalg.svd(Ztr, full_matrices=False)
        Vt = Vt[:int((S > 1e-6 * S[0]).sum())] if S.size else Vt
        Ptr, Pte = Ztr @ Vt.T, ((Xte - mu) / scale) @ Vt.T
        utr, ute = unit_of_point[itr], unit_of_point[ite]
        masks = {k: sub_masks[k][ite] for k in sub_names}
        te_units = np.unique(ute)
        n_units_seen["all"].append(len(te_units))
        for k in sub_names:
            n_units_seen[k].append(len(np.unique(ute[masks[k]])))

        for j in range(n_lab):
            lab = labels[j]
            ytr = lab[utr]
            if np.unique(ytr).size < 2:
                continue
            clf = LogisticRegression(C=C_REG, max_iter=MAX_ITER, class_weight="balanced")
            clf.fit(Ptr, ytr)
            prob = clf.predict_proba(Pte)[:, list(clf.classes_).index(1)]
            wanted = [("all", np.ones(len(prob), bool))] if j else \
                     [("all", np.ones(len(prob), bool))] + [(k, masks[k]) for k in sub_names]
            for name, mask in wanted:
                sel = np.where(mask)[0]
                if sel.size == 0:
                    continue
                units = np.unique(ute[sel])
                pred = np.array([+1 if prob[sel[ute[sel] == u]].mean() > 0.5 else -1
                                 for u in units])
                b = _bacc(lab[units], pred)
                if name == "all":
                    acc[j, r] = b
                else:
                    acc_sub[name][r] = b

    obs = {"all": float(np.nanmean(acc[0]))}
    for k in sub_names:
        obs[k] = float(np.nanmean(acc_sub[k]))
    null = np.nanmean(acc[1:], axis=1) if n_lab > 1 else np.array([])
    return obs, null, {k: (float(np.mean(v)) if v else 0.0) for k, v in n_units_seen.items()}


def probe_curve(X, trace_of_point, unit_of_point, n_traces, strat, labels, n_layers,
                sub_masks, n_repeat, procs=1):
    sub_names = tuple(sub_masks)
    jobs = [(np.ascontiguousarray(X[:, l, :], dtype=np.float32), trace_of_point,
             unit_of_point, n_traces, strat, labels, n_repeat, SEED_SPLIT, sub_names,
             sub_masks) for l in range(n_layers)]
    if procs and procs > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(procs) as pool:
            return pool.map(_layer_job, jobs, chunksize=1)
    return [_layer_job(j) for j in jobs]


def label_matrix(observed, n_perm, seed=SEED_PERM):
    """[1+n_perm, n_units] int8; row 0 observed, the rest permutations of it."""
    base = np.asarray(observed, dtype=np.int8)
    rng = np.random.default_rng(seed)
    rows = [base] + [base[rng.permutation(base.size)] for _ in range(n_perm)]
    return np.stack(rows)


# =====================================================================================
# assembling the packet
# =====================================================================================

def gather(form, arms, kinds, verd, need_label):
    """Point records for the wanted arms/kinds, with derived p̂ / d_t fields."""
    out = {}
    for arm in arms:
        idx = load_index(form, arm)
        pts = []
        for p in idx["points"]:
            if p["kind"] not in kinds:
                continue
            v = verd.get((form, arm, p["trace_i"]))
            ph = phat_of(arm, v)
            if need_label and ph is None:
                continue
            q = dict(p)
            q["row_local"] = p["row"]
            q["arm"] = arm
            q["phat"] = ph
            q["verdict"] = v
            q["dt"] = dt_of(p, form) if p["kind"] in ("est", "est_offwin") else 0
            pts.append(q)
        out[arm] = (idx, pts)
    return out


def belief_tokens(form, arm):
    return {p["trace_i"]: p["token_index"]
            for p in load_index(form, arm)["points"] if p["kind"] == "belief"}


def per_form(form, verd, n_perm, n_rep, procs, vphat_only=False):
    print("\n===== form %s =====" % form, flush=True)
    t = time.time()

    # ---- v_p̂ : est points, above_good only, p̂-labelled traces ----------------------
    _, pts = gather(form, ["above_good"], {"est"}, verd, need_label=True)["above_good"]
    A = load_acts(form, "above_good")
    X = A[np.array([p["row_local"] for p in pts])].astype(np.float32)
    n_layers, d_model = X.shape[1], X.shape[2]
    for k, p in enumerate(pts):
        p["row_local"] = k
    traces = sorted({p["trace_i"] for p in pts})
    tpos = {t: i for i, t in enumerate(traces)}
    keys = [("above_good", p["trace_i"]) for p in pts]
    M, meta = stratum_means(pts, X, keys)
    y_trace = np.array([[p["phat"] for p in pts if p["trace_i"] == t][0] for t in traces],
                       dtype=np.int8)
    v_phat, strata_n, n_used = contrast(M, meta, [y_trace[tpos[m["key"][1]]] for m in meta])
    print("v_phat: %d est points, %d traces (+1 %d / -1 %d), strata %s, strata used %d"
          % (len(pts), len(traces), int((y_trace == 1).sum()), int((y_trace == -1).sum()),
             strata_n, n_used), flush=True)

    # ---- p̂ probe -------------------------------------------------------------------
    tof = np.array([tpos[p["trace_i"]] for p in pts])
    bel = belief_tokens(form, "above_good")
    before = np.array([(p["trace_i"] not in bel) or (p["token_index"] < bel[p["trace_i"]])
                       for p in pts])
    labels = label_matrix(y_trace, n_perm)
    cur = probe_curve(X, tof, tof, len(traces), y_trace, labels, n_layers,
                      {"before": before, "after": ~before}, n_rep, procs)
    print("  p̂ probe done  %.0fs" % (time.time() - t), flush=True)

    # ---- d_t positive control (point-level units) ------------------------------------
    dt_lab = label_matrix(np.array([p["dt"] for p in pts], dtype=np.int8), n_perm)
    cur_dt = probe_curve(X, tof, np.arange(len(pts)), len(traces), None, dt_lab, n_layers,
                         {}, n_rep, procs)
    print("  d_t control done  %.0fs" % (time.time() - t), flush=True)

    if vphat_only:      # --smoke on a laptop that holds only the above_good arm
        del A
        return dict(v_phat=v_phat, v_p=v_phat * 0, strata_n=strata_n, strata_p={},
                    cur=cur, cur_dt=cur_dt, cur_bel=cur_dt, M=M, meta=meta, X=X, tof=tof,
                    y_trace=y_trace, traces=traces, tpos=tpos, n_layers=n_layers,
                    d_model=d_model, n_points=len(pts), n_bel=0,
                    n_before=int(before.sum()), n_after=int((~before).sum()))

    # ---- v_p : above_good vs below_good, every trace with est points ------------------
    gp = gather(form, ["above_good", "below_good"], {"est"}, verd, need_label=False)
    Bl = load_acts(form, "below_good")
    pts_p, parts, off = [], [], 0
    for arm, src in (("above_good", A), ("below_good", Bl)):
        pl = gp[arm][1]
        parts.append(src[np.array([p["row_local"] for p in pl])].astype(np.float32))
        for k, p in enumerate(pl):
            p["row_local"] = off + k
        pts_p.extend(pl)
        off += len(pl)
    Xp = np.concatenate(parts, axis=0)
    del parts
    keys_p = [(p["arm"], p["trace_i"]) for p in pts_p]
    Mp, meta_p = stratum_means(pts_p, Xp, keys_p)
    v_p, strata_p, _ = contrast(Mp, meta_p,
                                [+1 if m["key"][0] == "above_good" else -1 for m in meta_p])
    del Xp, Mp

    # ---- belief-point polarity control ------------------------------------------------
    gb = gather(form, ["above_good", "below_good"], {"belief"}, verd, need_label=False)
    bpts, parts, off = [], [], 0
    for arm, src in (("above_good", A), ("below_good", Bl)):
        pl = gb[arm][1]
        parts.append(src[np.array([p["row_local"] for p in pl])].astype(np.float32))
        for k, p in enumerate(pl):
            p["row_local"] = off + k
            p["pol"] = +1 if p["literal"].lower().strip() == "good cause" else -1
        bpts.extend(pl)
        off += len(pl)
    Xb = np.concatenate(parts, axis=0)
    del parts, Bl, A
    bkeys = sorted({(p["arm"], p["trace_i"]) for p in bpts})
    bpos = {k: i for i, k in enumerate(bkeys)}
    btof = np.array([bpos[(p["arm"], p["trace_i"])] for p in bpts])
    bly = np.zeros(len(bkeys), dtype=np.int8)
    for p in bpts:
        bly[bpos[(p["arm"], p["trace_i"])]] = p["pol"]
    cur_bel = probe_curve(Xb, btof, btof, len(bkeys), bly, label_matrix(bly, n_perm),
                          n_layers, {}, n_rep, procs)
    del Xb
    print("  belief control done  %.0fs  (n=%d points)" % (time.time() - t, len(bpts)),
          flush=True)

    return dict(v_phat=v_phat, v_p=v_p, strata_n=strata_n, strata_p=strata_p, cur=cur,
                cur_dt=cur_dt, cur_bel=cur_bel, M=M, meta=meta, X=X, tof=tof,
                y_trace=y_trace, traces=traces, tpos=tpos, n_layers=n_layers,
                d_model=d_model, n_points=len(pts), n_bel=len(bpts),
                n_before=int(before.sum()), n_after=int((~before).sum()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--procs", type=int, default=min(48, max(1, (os.cpu_count() or 4) - 2)))
    ap.add_argument("--recount-subsample", action="store_true")
    ap.add_argument("--layer-star", type=int, default=None)
    args = ap.parse_args()
    if args.recount_subsample:
        return recount_subsample(args.layer_star)

    n_perm = 20 if args.smoke else N_PERM
    n_rep = 3 if args.smoke else N_REPEAT
    forms = ["A"] if args.smoke else ["A", "B"]
    VEC.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    verd = verdicts()
    store = {f: per_form(f, verd, n_perm, n_rep, args.procs, vphat_only=args.smoke)
             for f in forms}

    # ---- PR-004 item 3: l* = argmax form-A p̂ probe balanced accuracy, ties -> lowest --
    accA = np.array([c[0]["all"] for c in store["A"]["cur"]])
    lstar = int(np.nanargmax(accA))
    print("\nl* = %d   (form-A p̂ balanced accuracy %.4f, null p95 %.4f)"
          % (lstar, accA[lstar], np.nanpercentile(store["A"]["cur"][lstar][1], 95)), flush=True)

    inv = {}
    if len(forms) == 2:
        nl = store["A"]["n_layers"]
        vA, vB = store["A"]["v_phat"], store["B"]["v_phat"]
        inv["cos"] = np.array([cos(vA[l], vB[l]) for l in range(nl)])
        rng = np.random.default_rng(SEED_PERM)
        flat = {f: store[f]["M"].reshape(len(store[f]["meta"]), -1) for f in ("A", "B")}
        nullc = np.zeros((n_perm, nl), dtype=np.float32)
        for j in range(n_perm):
            vs = {}
            for f in ("A", "B"):
                s = store[f]
                perm = s["y_trace"][rng.permutation(s["y_trace"].size)]
                w, _, _ = contrast_weights(s["meta"],
                                           [perm[s["tpos"][m["key"][1]]] for m in s["meta"]])
                vs[f] = (w @ flat[f]).reshape(nl, -1)
            nullc[j] = [cos(vs["A"][l], vs["B"][l]) for l in range(nl)]
        inv["cos_null_p95"] = np.percentile(nullc, 95, axis=0)
        inv["cos_null_mean"] = nullc.mean(axis=0)
        inv["cos_p"] = np.array([(1 + (nullc[:, l] >= inv["cos"][l]).sum()) / (n_perm + 1)
                                 for l in range(nl)])
        print("cos(v_p̂^A, v_p̂^B) at l*=%d: %.4f  (null mean %.4f, p95 %.4f, p=%.4f)"
              % (lstar, inv["cos"][lstar], inv["cos_null_mean"][lstar],
                 inv["cos_null_p95"][lstar], inv["cos_p"][lstar]), flush=True)
        inv.update(transfer(store, n_perm))
        print("transfer A->B at l*: %.4f  (null p95 %.4f, p=%.4f)"
              % (inv["transfer"][lstar], inv["transfer_p95"][lstar],
                 inv["transfer_p"][lstar]), flush=True)

    write_csvs(store, inv, lstar, forms, n_perm, n_rep)

    from safetensors.numpy import save_file
    for form in forms:
        for name, v in (("vphat", store[form]["v_phat"]), ("vp", store[form]["v_p"])):
            path = VEC / ("w5_%s_%s.safetensors" % (name, form))
            save_file({name: v.astype(np.float32)}, str(path),
                      metadata={"model": MODEL, "form": form, "kind": name,
                                "layer_star": str(lstar), "shape": json.dumps(list(v.shape)),
                                "rule": "PR-004 item 2 (vphat) / item 5 (vp)"})
            print("wrote %s  %d bytes" % (path.name, path.stat().st_size), flush=True)

    if not args.smoke:
        projections_and_subsample(store, lstar, verd)

    (OUT / "w5_lstar.json").write_text(json.dumps(
        {"layer_star": lstar, "rule": "argmax form-A p̂ probe balanced accuracy, ties->lowest",
         "form_A_balacc": float(accA[lstar]), "n_perm": n_perm, "n_repeat": n_rep,
         "n_layers": int(store["A"]["n_layers"]), "d_model": int(store["A"]["d_model"])},
        indent=1))
    print("\nDONE  l*=%d  %.0fs" % (lstar, time.time() - t0))
    return 0


def transfer(store, n_perm):
    """PR-004 item 5: train the p̂ probe on ALL form-A est points, test on form-B traces."""
    from sklearn.linear_model import LogisticRegression
    nl = store["A"]["n_layers"]
    yB = store["B"]["y_trace"]
    tofB = store["B"]["tof"]
    rng = np.random.default_rng(SEED_PERM)
    permsB = np.stack([yB] + [yB[rng.permutation(yB.size)] for _ in range(n_perm)])
    acc, p95, pv = [], [], []
    for l in range(nl):
        Xa = np.ascontiguousarray(store["A"]["X"][:, l, :], dtype=np.float32)
        Xb = np.ascontiguousarray(store["B"]["X"][:, l, :], dtype=np.float32)
        mu = Xa.mean(axis=0)
        Za = Xa - mu
        sc = float(np.linalg.norm(Za, axis=1).mean()) or 1.0
        Za /= sc
        _, S, Vt = np.linalg.svd(Za, full_matrices=False)
        Vt = Vt[:int((S > 1e-6 * S[0]).sum())]
        clf = LogisticRegression(C=C_REG, max_iter=MAX_ITER, class_weight="balanced")
        clf.fit(Za @ Vt.T, store["A"]["y_trace"][store["A"]["tof"]])
        prob = clf.predict_proba(((Xb - mu) / sc) @ Vt.T)[:, list(clf.classes_).index(1)]
        units = np.unique(tofB)
        pred = np.array([+1 if prob[tofB == u].mean() > 0.5 else -1 for u in units])
        vals = np.array([_bacc(permsB[j][units], pred) for j in range(permsB.shape[0])])
        acc.append(float(vals[0]))
        p95.append(float(np.nanpercentile(vals[1:], 95)))
        pv.append(float((1 + np.sum(vals[1:] >= vals[0])) / (permsB.shape[0])))
    return {"transfer": np.array(acc), "transfer_p95": np.array(p95),
            "transfer_p": np.array(pv)}


def write_csvs(store, inv, lstar, forms, n_perm, n_rep):
    nl = store[forms[0]]["n_layers"]
    with open(OUT / "w5_layers.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["form", "layer", "vphat_l2", "vp_l2", "cos_vp_vphat",
                    "probe_balacc_phat", "probe_null_p95", "is_layer_star"])
        for form in forms:
            s = store[form]
            for l in range(nl):
                obs, null, _ = s["cur"][l]
                w.writerow([form, l, "%.6f" % np.linalg.norm(s["v_phat"][l]),
                            "%.6f" % np.linalg.norm(s["v_p"][l]),
                            "%.6f" % cos(s["v_p"][l], s["v_phat"][l]),
                            "%.6f" % obs["all"],
                            "%.6f" % (np.nanpercentile(null, 95) if null.size else float("nan")),
                            int(l == lstar)])

    with open(OUT / "w5_strata.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["form", "contrast", "dt_stratum", "n_traces_pos", "n_traces_neg"])
        for form in forms:
            for tag, cts in (("vphat", store[form]["strata_n"]), ("vp", store[form]["strata_p"])):
                for s, (p, n) in sorted(cts.items(), reverse=True):
                    w.writerow([form, tag, "+1" if s > 0 else "-1", p, n])

    with open(OUT / "w5_probes.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["form", "target", "layer", "balacc", "balacc_before", "balacc_after",
                    "null_mean", "null_p95", "p_perm", "n_test_units",
                    "n_test_units_before", "n_test_units_after", "n_perm", "n_repeat"])
        for form in forms:
            s = store[form]
            for l in range(nl):
                for tag, cur in (("phat", s["cur"]), ("dt_control", s["cur_dt"]),
                                 ("belief_polarity", s["cur_bel"])):
                    obs, null, nu = cur[l]
                    p = ((1 + np.sum(null >= obs["all"])) / (null.size + 1)) if null.size else ""
                    w.writerow([form, tag, l, "%.6f" % obs["all"],
                                "%.6f" % obs["before"] if "before" in obs else "",
                                "%.6f" % obs["after"] if "after" in obs else "",
                                "%.6f" % np.nanmean(null) if null.size else "",
                                "%.6f" % np.nanpercentile(null, 95) if null.size else "",
                                "%.6f" % p if p != "" else "", nu.get("all", ""),
                                nu.get("before", ""), nu.get("after", ""), n_perm, n_rep])

    if inv:
        with open(OUT / "w5_invariance.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["layer", "cos_vphatA_vphatB", "cos_null_mean", "cos_null_p95",
                        "cos_p", "transfer_A_to_B_balacc", "transfer_null_p95", "transfer_p",
                        "cos_vpA_vphatA", "cos_vpB_vphatB", "is_layer_star"])
            for l in range(nl):
                w.writerow([l, "%.6f" % inv["cos"][l], "%.6f" % inv["cos_null_mean"][l],
                            "%.6f" % inv["cos_null_p95"][l], "%.6f" % inv["cos_p"][l],
                            "%.6f" % inv["transfer"][l], "%.6f" % inv["transfer_p95"][l],
                            "%.6f" % inv["transfer_p"][l],
                            "%.6f" % cos(store["A"]["v_p"][l], store["A"]["v_phat"][l]),
                            "%.6f" % cos(store["B"]["v_p"][l], store["B"]["v_phat"][l]),
                            int(l == lstar)])
    print("wrote w5_layers.csv w5_strata.csv w5_probes.csv w5_invariance.csv", flush=True)


def projections_and_subsample(store, lstar, verd):
    """Per-point scalars onto v_p̂(l*) for EVERY captured point, plus the 10% subsample."""
    SUB.mkdir(parents=True, exist_ok=True)
    rows, keep_acts, keep_meta, gidx = [], [], [], 0
    for form, arm in ARMS:
        idx = load_index(form, arm)
        A = load_acts(form, arm)
        vph, vp = store[form]["v_phat"][lstar], store[form]["v_p"][lstar]
        sl = A[:, lstar, :].astype(np.float32)
        pr1 = sl @ (vph / np.linalg.norm(vph))
        pr2 = sl @ (vp / np.linalg.norm(vp))
        for k, p in enumerate(idx["points"]):
            v = verd.get((form, arm, p["trace_i"]))
            ph = phat_of(arm, v)
            rows.append([form, arm, p["trace_i"], p["row"], gidx, p["kind"],
                         p["token_index"], p["value"] if p["value"] is not None else "",
                         dt_of(p, form) if p["kind"] in ("est", "est_offwin") else "",
                         v or "", ph if ph is not None else "",
                         "%.6f" % pr1[k], "%.6f" % pr2[k]])
            if gidx % SUBSAMPLE_STRIDE == 0:
                keep_acts.append(A[k])
                keep_meta.append({"global_index": gidx, "form": form, "arm": arm,
                                  "trace_i": p["trace_i"], "row": p["row"], "kind": p["kind"],
                                  "token_index": p["token_index"], "value": p["value"],
                                  "literal": p["literal"], "verdict": v, "phat": ph,
                                  "dt": dt_of(p, form) if p["kind"] in
                                  ("est", "est_offwin") else None})
            gidx += 1
        del A, sl
    with open(OUT / "w5_projections.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["form", "arm", "trace_i", "row", "global_index", "kind", "token_index",
                    "value", "dt", "verdict", "phat", "proj_vphat_lstar", "proj_vp_lstar"])
        w.writerows(rows)
    from safetensors.numpy import save_file
    arr = np.stack(keep_acts).astype(np.float16)
    save_file({"acts": arr}, str(SUB / "w5_subsample.safetensors"),
              metadata={"model": MODEL, "stride": str(SUBSAMPLE_STRIDE),
                        "rule": "every %dth point of the global index (arm order = ARMS)"
                                % SUBSAMPLE_STRIDE, "layer_star": str(lstar),
                        "shape": json.dumps(list(arr.shape))})
    (SUB / "w5_subsample_index.json").write_text(json.dumps(
        {"stride": SUBSAMPLE_STRIDE, "layer_star": lstar, "n_points": len(keep_meta),
         "n_points_total": gidx, "shape": list(arr.shape), "points": keep_meta}, indent=1))
    print("wrote w5_projections.csv (%d rows); subsample %s = %.1f MB"
          % (len(rows), arr.shape, (SUB / "w5_subsample.safetensors").stat().st_size / 1e6),
          flush=True)


def recount_subsample(lstar_arg):
    """PR-004 item 7: rebuild v_p̂(l*) from the shipped 10% subsample alone and cosine it
    against the shipped tensor. Laptop-side, no pod, no full tensors."""
    from safetensors.numpy import load_file
    meta = json.loads((SUB / "w5_subsample_index.json").read_text())
    lstar = meta["layer_star"] if lstar_arg is None else lstar_arg
    acts = load_file(str(SUB / "w5_subsample.safetensors"))["acts"]
    for form in ("A", "B"):
        pts = []
        for k, m in enumerate(meta["points"]):
            if (m["form"] == form and m["arm"] == "above_good" and m["kind"] == "est"
                    and m["phat"] in (1, -1)):
                q = dict(m)
                q["row_local"] = k
                pts.append(q)
        ref = load_file(str(VEC / ("w5_vphat_%s.safetensors" % form)))["vphat"][lstar]
        if not pts:
            print("form %s: the subsample holds no labelled above_good est point" % form)
            continue
        X = acts[:, lstar, :].astype(np.float32)[:, None, :]
        M, mt = stratum_means(pts, X, [("above_good", p["trace_i"]) for p in pts])
        lab = {p["trace_i"]: p["phat"] for p in pts}
        try:
            v, counts, used = contrast(M, mt, [lab[m["key"][1]] for m in mt])
        except RuntimeError as e:
            print("form %s: %s (points %d, traces %d)"
                  % (form, e, len(pts), len({p["trace_i"] for p in pts})))
            continue
        print("form %s | l*=%d | subsample est points %d over %d traces | strata used %d %s "
              "| cos(recount, shipped) = %.4f"
              % (form, lstar, len(pts), len({p["trace_i"] for p in pts}), used, counts,
                 cos(v[0], ref)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
