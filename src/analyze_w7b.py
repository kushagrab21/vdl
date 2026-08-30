"""W7b Step 4: extract, number-judge, and compute the PR-006 statistics from the low-dose arms.

Laptop-side over `runs/w7b_steer/*.json` plus the REUSED W7 sham
`runs/w7_steer/B_above_sham.json` (PR-006 item 2). Nothing here touches a GPU.

  python3 src/analyze_w7b.py --estimate   # D-027-corrected API projection, no calls
  python3 src/analyze_w7b.py --run        # number judge + all PR-006 item 4 statistics
  python3 src/analyze_w7b.py --no-judge   # regex-only pass

Extractors (PR-006 item 3):
  regex_raw   PR-001 item 8, frozen and unpatched          — printed, never a verdict
  regex_corr  PR-003 item 7 / D-016                        — PRIMARY REPORTING BASIS
  judge       PR-001 item 7's pinned claude-sonnet-5       — SECOND EXTRACTOR, all 600 finals

NO direction judge (PR-006 item 3, frozen for cost control). No verbalized-belief statistic
is computed for W7b.

The API projection uses D-027's CORRECTED constants — 3.2 chars/token in, 20.5 out tokens per
number-judge call — not the 4.0/20.0 estimator that under-shot W7's bill by 53 %. Per D-027 the
estimator in `analyze_w7.py` is deliberately left unpatched; this module carries the correction
explicitly so both numbers stay visible.
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import numpy as np  # noqa: E402
import extract_regex as ex  # noqa: E402
from steer_w7 import is_degenerate  # noqa: E402
from steer_w7b import (ARMS, VPHAT_ARMS, NULL_ARM_PAIRS, NULL_SEEDS_7B, TAU_B,  # noqa: E402
                       PRIMARY_POS, PRIMARY_NEG, SHAM_REUSED, OUT_ROOT)
from analyze_w7 import (corrected_final, coherent, rate, boot_diff, run_pool,  # noqa: E402
                        PRICE_IN, PRICE_OUT, JUDGE_MODEL, N_BOOT, BOOT_SEED, PROCS)

OUT = ROOT / "analysis" / "out"
CACHE_NUM = OUT / "w7b_extractions.json"
CACHE_W7 = OUT / "w7_extractions.json"          # read-only; holds the reused sham's finals
SHAM_KEY = "B_above_sham(REUSED from W7)"
CHARS_PER_TOKEN = 3.2                            # D-027 correction to 4.0
OUT_TOK_PER_CALL = 20.5                          # D-027: measured 23,587 / 1,150 on W7
D_BAR_LINE = 0.06                                # PR-006 item 5


def load():
    """The 12 W7b arms in PR-006 item 2 order, then the reused W7 sham."""
    recs = {}
    for key in ARMS:
        p = OUT_ROOT / ("%s.json" % key)
        if p.exists():
            recs[key] = json.loads(p.read_text())
    if SHAM_REUSED.exists():
        recs[SHAM_KEY] = json.loads(SHAM_REUSED.read_text())
    for d in recs.values():
        for r in d["rows"]:
            va = r["visible_answer"]
            r["regex_raw"] = ex.final_estimate(va)
            r["regex_corr"] = corrected_final(va, TAU_B)
            r["coherent"] = coherent(r, va)
    return recs


def estimate_api(recs):
    """PR-006 item 9: projection from the ACTUAL generated text, D-027-corrected constants."""
    from value_leakage.judge import NUMBER_JUDGE_PROMPT
    texts = [r["visible_answer"] for k, d in recs.items() if k != SHAM_KEY for r in d["rows"]]
    chars = sum(len(NUMBER_JUDGE_PROMPT.format(llm_text=t)) for t in texts)
    tin_corr, tin_old = chars / CHARS_PER_TOKEN, chars / 4.0
    tout_corr, tout_old = OUT_TOK_PER_CALL * len(texts), 20.0 * len(texts)
    usd = lambda i, o: i / 1e6 * PRICE_IN + o / 1e6 * PRICE_OUT
    return {"n_number_judge": len(texts), "n_direction_judge": 0,
            "chars": chars,
            "corrected_D027": {"chars_per_token": CHARS_PER_TOKEN,
                               "out_tokens_per_call": OUT_TOK_PER_CALL,
                               "est_input_tokens": int(tin_corr),
                               "est_output_tokens": int(tout_corr),
                               "est_usd": round(usd(tin_corr, tout_corr), 3)},
            "uncorrected_W7_estimator": {"chars_per_token": 4.0, "out_tokens_per_call": 20.0,
                                         "est_input_tokens": int(tin_old),
                                         "est_output_tokens": int(tout_old),
                                         "est_usd": round(usd(tin_old, tout_old), 3)},
            "est_usd": round(usd(tin_corr, tout_corr), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--max-usd", type=float, default=4.0)      # PR-006 item 9 pause line
    ap.add_argument("--procs", type=int, default=PROCS)
    args = ap.parse_args()

    recs = load()
    n_new = sum(len(d["rows"]) for k, d in recs.items() if k != SHAM_KEY)
    print("W7b arms loaded: %d (+ %s)  new generations: %d"
          % (len(recs) - (SHAM_KEY in recs), SHAM_KEY if SHAM_KEY in recs else "NO SHAM", n_new))
    est = estimate_api(recs)
    print(json.dumps(est, indent=2))
    if args.estimate:
        return 0
    if not args.no_judge and est["est_usd"] > args.max_usd:
        print("\nPAUSE: D-027-corrected projection $%.2f exceeds the PR-006 item 9 line of $%.2f"
              % (est["est_usd"], args.max_usd))
        return 3

    # ---- number judge on every final, cached by text hash; the W7 cache covers the sham
    usage = {"in": 0, "out": 0, "calls": 0}
    cache = json.loads(CACHE_NUM.read_text()) if CACHE_NUM.exists() else {}
    old = json.loads(CACHE_W7.read_text()) if CACHE_W7.exists() else {}
    for d in recs.values():
        for r in d["rows"]:
            r["_h"] = hashlib.sha1(r["visible_answer"].encode()).hexdigest()
    if not args.no_judge:
        jobs, want = [], set()
        for k, d in recs.items():
            for r in d["rows"]:
                h = r["_h"]
                if h not in cache and h not in old and h not in want and r["visible_answer"].strip():
                    want.add(h)
                    jobs.append(("number", h, r["visible_answer"]))
        print("number judge: %d unique texts to call (%d cached here, %d in the W7 cache)"
              % (len(jobs), len(cache), len(old)))
        got, usage = run_pool(jobs, "number", args.procs)
        cache.update(got)
        CACHE_NUM.write_text(json.dumps(cache, indent=2))
    for d in recs.values():
        for r in d["rows"]:
            r["judge"] = cache.get(r["_h"], old.get(r["_h"]))

    usd = usage["in"] / 1e6 * PRICE_IN + usage["out"] / 1e6 * PRICE_OUT
    print("\nAPI this run: %d calls, in %d / out %d tokens, $%.4f"
          % (usage["calls"], usage["in"], usage["out"], usd))
    (OUT / "w7b_api_usage.json").write_text(json.dumps(
        {"number_judge": usage, "direction_judge": {"in": 0, "out": 0, "calls": 0,
                                                    "note": "NOT RUN — PR-006 item 3"},
         "usd_this_run": round(usd, 4), "model": JUDGE_MODEL,
         "price_in_per_mtok": PRICE_IN, "price_out_per_mtok": PRICE_OUT,
         "projection": est}, indent=2))

    # ---------------------------------------------------------------- w7b_arms.csv (12 rows)
    order = list(ARMS)
    rows_csv = []
    for k in order:
        if k not in recs:
            continue
        d, rs = recs[k], recs[k]["rows"]
        n = len(rs)
        p_raw = rate([r["regex_raw"] for r in rs])
        p_cor = rate([r["regex_corr"] for r in rs])
        p_jud = rate([r["judge"] for r in rs])
        fin = [x for x in (r["regex_corr"] for r in rs) if x is not None]
        rows_csv.append({
            "arm": k, "condition": d["condition"], "layer": d["layer"], "alpha": d["alpha"],
            "direction": d["direction"], "null_seed": d["null_seed"],
            "delta_norm": round(d["delta_norm"], 4),
            "frac_of_resid_norm": round(d["delta_norm"] / 111.65, 4),
            "n": n, "n_truncated": d["n_truncated"], "n_degenerate": d["n_degenerate"],
            "coherence": round(sum(r["coherent"] for r in rs) / n, 4),
            "n_regex_null": p_cor[3], "n_judge_null": p_jud[3],
            "P_gt_tau_regex_corr": None if p_cor[0] is None else round(p_cor[0], 4),
            "P_gt_tau_regex_raw": None if p_raw[0] is None else round(p_raw[0], 4),
            "P_gt_tau_judge": None if p_jud[0] is None else round(p_jud[0], 4),
            "k_gt_tau_regex_corr": p_cor[1], "n_nonnull_regex_corr": p_cor[2],
            "median_final_regex_corr": None if not fin else float(np.median(fin)),
            "median_log10_regex_corr": None if not fin else round(
                float(np.median(np.log10(np.maximum(fin, 1.0)))), 4),
            "median_tokens": int(np.median([r["n_output_tokens"] for r in rs])),
            "seed_lo": d["seed_lo"], "seed_hi": d["seed_hi"],
        })
    with open(OUT / "w7b_arms.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]))
        w.writeheader()
        w.writerows(rows_csv)
    print("wrote %s (%d rows)" % (OUT / "w7b_arms.csv", len(rows_csv)))

    # ---------------------------------------------------------------- w7b_primary.csv
    out_rows = []

    def add(stat, basis, value, lo=None, hi=None, note="", extra=None):
        out_rows.append({"statistic": stat, "basis": basis,
                         "value": None if value is None else round(value, 6),
                         "ci_lo": None if lo is None else round(lo, 6),
                         "ci_hi": None if hi is None else round(hi, 6),
                         "extra": "" if extra is None else json.dumps(extra), "note": note})

    fin_of = lambda k, b="regex_corr": [r[b] for r in recs[k]["rows"]]
    verdict = {}
    for basis in ("regex_corr", "judge"):
        if SHAM_KEY in recs:
            ps = rate(fin_of(SHAM_KEY, basis))
            add("sham P(>tau_B)  [REUSED W7 arm, seeds 8664-8713]", basis, ps[0], None, None,
                "PR-006 item 2: W7's alpha=0 control, NOT regenerated; %d/%d" % (ps[1], ps[2]))

        # 1 — the primary contrast
        dpm, lo, hi = boot_diff(fin_of(PRIMARY_POS, basis), fin_of(PRIMARY_NEG, basis))
        add("primary delta_pm  P(+0.5)-P(-0.5)", basis, dpm, lo, hi,
            "PR-006 item 4.1; 10000-resample percentile bootstrap, seed 64")
        verdict[basis] = {"dpm": dpm, "lo": lo, "hi": hi}

        # 4 — the descriptive quarter-dose pair
        q, qlo, qhi = boot_diff(fin_of("B7b_above_L27_ap025", basis),
                                fin_of("B7b_above_L27_am025", basis))
        add("descriptive delta_pm  P(+0.25)-P(-0.25)", basis, q, qlo, qhi,
            "PR-006 item 4.4 — DESCRIPTIVE, enters no verdict")

        # 2 — the four null delta_pm
        njs = []
        for j, (kp, km) in enumerate(NULL_ARM_PAIRS):
            if kp not in recs or km not in recs:
                continue
            dj, jlo, jhi = boot_diff(fin_of(kp, basis), fin_of(km, basis))
            njs.append(dj)
            add("null delta_pm_%02d (seed %d)" % (10 + j, NULL_SEEDS_7B[j]), basis, dj, jlo, jhi,
                "PR-006 item 4.2 — random equal-norm direction, same +-0.5 contrast")
        if njs:
            add("null delta_pm spread", basis, float(np.mean(njs)), min(njs), max(njs),
                "mean / min / max over the 4 random directions",
                extra={"nulls": [round(x, 6) for x in njs]})
            if dpm is not None:
                beat = sum(1 for x in njs if abs(dpm) > abs(x))
                add("|delta_pm(v_phat)| vs |null delta_pm|", basis, abs(dpm), None, None,
                    "beats %d/%d random directions in absolute size (descriptive: PR-006's "
                    "verdict is the CI, not a null-beating count)" % (beat, len(njs)))

        # 3 — the distortion check
        if SHAM_KEY in recs:
            psh = rate(fin_of(SHAM_KEY, basis))[0]
            devs = []
            for kp, km in NULL_ARM_PAIRS:
                for k in (kp, km):
                    if k in recs:
                        devs.append(abs(rate(fin_of(k, basis))[0] - psh))
            dbar = float(np.mean(devs))
            add("D_bar  mean |P_arm - P_sham| over the 8 null arms", basis, dbar,
                min(devs), max(devs),
                "PR-006 item 4.3; line is %.2f; min/max in ci columns" % D_BAR_LINE,
                extra={"devs": [round(x, 4) for x in devs]})
            verdict[basis]["dbar"] = dbar

    # ---- which interpretation row fires (PR-006 item 5), on the PRIMARY basis
    v = verdict["regex_corr"]
    dbar, lo, hi = v.get("dbar"), v["lo"], v["hi"]
    if dbar is None:
        row, txt = "UNRESOLVED", "no sham available"
    elif dbar > D_BAR_LINE:
        row, txt = ("row 3", "D_bar = %.4f > %.2f: even alpha=0.5 distorts; the dose ladder "
                             "ends here by R-011; bounding, not tested further"
                    % (dbar, D_BAR_LINE))
    elif lo is not None and (lo > 0 or hi < 0):
        row, txt = ("row 1", "D_bar = %.4f <= %.2f and delta_pm CI [%.4f, %.4f] EXCLUDES 0: a "
                             "direction-specific causal effect exists at non-distorting doses "
                             "[measured]; sign reported as found" % (dbar, D_BAR_LINE, lo, hi))
    else:
        row, txt = ("row 2", "D_bar = %.4f <= %.2f and delta_pm CI [%.4f, %.4f] INCLUDES 0: no "
                             "directional effect at non-distorting doses [measured]; the "
                             "strongest form of the causal null" % (dbar, D_BAR_LINE, lo, hi))
    add("PR-006 item 5 interpretation row FIRED", "regex_corr", None, None, None,
        "%s — %s" % (row, txt))
    print("\nPR-006 item 5: %s\n  %s" % (row, txt))

    with open(OUT / "w7b_primary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["statistic", "basis", "value", "ci_lo", "ci_hi",
                                           "extra", "note"])
        w.writeheader()
        w.writerows(out_rows)
    print("wrote", OUT / "w7b_primary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
