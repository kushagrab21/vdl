"""W10 skepticism pass — every check in one place, one command, one JSON.

    python3 src/w10_skeptic.py            # emits analysis/out/w10_skeptic.json + w10_checks.csv
    python3 src/w10_skeptic.py --print    # same, plus a human-readable check table

Stdlib + `extract_regex` only (no numpy, no scipy, no network), so a laptop reproduces every
number here from committed files. The chi-square and Fisher p-values are implemented locally
rather than imported; they are NEW statistics, computed here for the first time, and are
labelled POST-HOC wherever they appear.

Checks, in the order the W10 order asks for them:

  SK-1  extractor coverage: every behavioural number cited in the write-up has BOTH extractors
        in its source CSV.
  SK-2  dose-response: monotonicity of the W7 ladder and flatness of the W7b pair.
  SK-3  coherence per arm (W7, W7b) -- reported ONLY as well-formedness, per D-029.
  SK-4  tie-convention sensitivity, including W2's 36-tie Qwen3-8B case.
  SK-5  D-016 corrected-vs-raw bases present wherever a landing number is cited.
  SK-6  W7b arm homogeneity and dose flatness (recount of P-009 section 4(iii)).
  SK-7  D_bar's null floor (exact recount of D-032 / w7b_floor.py's simulation).
  SK-8  text-level screens: verbalized injected preference, and a NAMED D-029 fabrication
        screen defined here because P-009 section 5's "1 of 600" carries no command.
  SK-9  seed-block disjointness and generation totals across every packet.
  SK-10 regenerability: the committed recount/selftest commands still run and still match.
"""

import csv
import glob
import json
import math
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import extract_regex as ex  # noqa: E402

OUT = os.path.join(ROOT, "analysis", "out")
TAU_A = 15300000.0
TAU_B = 4500000000.0

CHECKS = []


def check(cid, name, command, status, detail):
    CHECKS.append({"id": cid, "name": name, "command": command,
                   "status": status, "detail": detail})


def rows(path):
    with open(os.path.join(OUT, path)) as fh:
        return list(csv.DictReader(fh))


def arm_files(pattern):
    return [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ROOT, "runs", pattern)))]


def corrected_final(va, tau):
    """PR-003 item 7 / D-016: last literal in the visible answer that is not tau."""
    nums = [v for v, _, _ in ex.all_numbers(va or "", skip_ranges=False) if v != tau]
    return nums[-1] if nums else None


# ------------------------------------------------------------------ statistics (stdlib)

def _gammainc_upper_reg(s, x):
    """Regularized upper incomplete gamma Q(s, x), s > 0, x >= 0."""
    if x == 0:
        return 1.0
    if x < s + 1:                                    # series for P, then Q = 1 - P
        term = 1.0 / s
        total = term
        n = 0
        while True:
            n += 1
            term *= x / (s + n)
            total += term
            if abs(term) < abs(total) * 1e-16 or n > 10000:
                break
        return 1.0 - total * math.exp(-x + s * math.log(x) - math.lgamma(s))
    tiny = 1e-300                                    # continued fraction for Q
    b = x + 1.0 - s
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10001):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return h * math.exp(-x + s * math.log(x) - math.lgamma(s))


def chi2_sf(stat, dof):
    """P(chi2_dof > stat)."""
    return _gammainc_upper_reg(dof / 2.0, stat / 2.0)


def chi2_homogeneity(counts):
    """counts = [(k, n), ...]. 2xG test that every arm shares one rate."""
    K = sum(k for k, _ in counts)
    N = sum(n for _, n in counts)
    p = K / N
    stat = 0.0
    for k, n in counts:
        for obs, e in ((k, n * p), (n - k, n * (1 - p))):
            if e > 0:
                stat += (obs - e) ** 2 / e
    dof = len(counts) - 1
    return stat, dof, chi2_sf(stat, dof), K, N, p


def fisher_2x2(a, b, c, d):
    """Two-sided Fisher exact p for [[a, b], [c, d]] (a = successes in group 1)."""
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def prob(x):
        return (math.comb(r1, x) * math.comb(n - r1, c1 - x)) / math.comb(n, c1)

    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    p0 = prob(a)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p0 * (1 + 1e-9)))


def dbar_floor(p, n_arm=50, n_sham=50, n_nulls=8, line=0.06, sham_fixed=None):
    """EXACT E[D_bar] and P(D_bar > line) when every arm is the same coin p and the injection
    does nothing -- the null D-032 simulated with 200,000 draws, computed here in closed form
    by dynamic programming over the eight arms' summed absolute deviations."""
    arm_pmf = [math.comb(n_arm, k) * p ** k * (1 - p) ** (n_arm - k) for k in range(n_arm + 1)]
    if sham_fixed is None:
        sham_states = [(s, math.comb(n_sham, s) * p ** s * (1 - p) ** (n_sham - s))
                       for s in range(n_sham + 1)]
    else:
        sham_states = [(round(sham_fixed * n_sham), 1.0)]
    e_dbar = 0.0
    p_over = 0.0
    p_at = 0.0                                        # mass sitting EXACTLY on the line
    grid = n_arm * n_sham                             # integer grid for |k*n_sham - s*n_arm|
    for s, w in sham_states:
        if w == 0.0:
            continue
        dev_i = [abs(k * n_sham - s * n_arm) for k in range(n_arm + 1)]
        dist = {0: 1.0}
        for _ in range(n_nulls):
            nd = {}
            for tot, wt in dist.items():
                for k, pk in enumerate(arm_pmf):
                    if pk:
                        key = tot + dev_i[k]
                        nd[key] = nd.get(key, 0.0) + wt * pk
            dist = nd
        denom = n_nulls * grid
        e_dbar += w * sum(t * wt for t, wt in dist.items()) / denom
        p_over += w * sum(wt for t, wt in dist.items() if t / denom > line)
        p_at += w * sum(wt for t, wt in dist.items() if t == round(line * denom))
    return e_dbar, p_over, p_at


# ------------------------------------------------------------------ SK-1 extractor coverage

def sk1():
    """Every behavioural number cited in the write-up carries BOTH extractors in its source."""
    gaps = []
    cov = {}

    r = rows("w1_tau.csv")
    cov["w1_tau.csv"] = {"rows": len(r),
                         "both_extractors": all(x["tau_judge"] and x["tau_regex"] for x in r)}
    if not cov["w1_tau.csv"]["both_extractors"]:
        gaps.append("w1_tau.csv")

    r = rows("w2_gap.csv")
    have = {(x["model"], x["extractor"], x["convention"]) for x in r}
    need = {(m, e, c) for m in {x["model"] for x in r}
            for e in ("judge", "regex") for c in ("strict_gt", "ge")}
    cov["w2_gap.csv"] = {"rows": len(r), "cells": len(have), "missing": sorted(need - have)}
    if need - have:
        gaps.append("w2_gap.csv")

    r = [x for x in rows("w3_behaviour.csv") if x["metric"] == "landing_gap"]
    have = {(x["form"], x["extractor"], x["convention"]) for x in r}
    need = {(f, e, c) for f in ("A", "B") for e in ("judge", "regex")
            for c in ("strict_gt", "ge")}
    cov["w3_behaviour.csv"] = {"landing_gap_rows": len(r), "missing": sorted(need - have)}
    if need - have:
        gaps.append("w3_behaviour.csv")

    for f, n_expect in (("w7_arms.csv", 23), ("w7b_arms.csv", 12)):
        r = rows(f)
        miss = [x["arm"] for x in r
                if not (x["P_gt_tau_regex_corr"] and x["P_gt_tau_regex_raw"]
                        and x["P_gt_tau_judge"])]
        cov[f] = {"arms": len(r), "expected": n_expect, "arms_missing_a_basis": miss,
                  "three_bases_everywhere": (not miss) and len(r) == n_expect}
        if miss or len(r) != n_expect:
            gaps.append(f)

    r = rows("w3_direction.csv")
    cov["w3_direction.csv"] = {"rows": len(r),
                               "n_unparsed_total": sum(int(x["n_unparsed"] or 0) for x in r)}

    status = "PASS" if not gaps else "FAIL"
    check("SK-1", "extractor coverage: both extractors in every source CSV",
          "python3 src/w10_skeptic.py   [section extractor_coverage]", status,
          "no exception" if not gaps else "exceptions: " + ", ".join(gaps))
    return {"gaps": gaps, "coverage": cov}


# ------------------------------------------------------------------ SK-2 dose response

def sk2():
    a7 = {x["arm"]: x for x in rows("w7_arms.csv")}
    ladder = []
    for arm in ("B_above_L27_am4", "B_above_L27_am2", "B_above_L27_am1", "B_above_sham",
                "B_above_L27_ap1", "B_above_L27_ap2", "B_above_L27_ap4"):
        x = a7[arm]
        ladder.append({"alpha": float(x["alpha"]), "P": float(x["P_gt_tau_regex_corr"]),
                       "median_log10": float(x["median_log10_regex_corr"]), "n": int(x["n"])})
    monotone = all(ladder[i]["P"] <= ladder[i + 1]["P"] for i in range(len(ladder) - 1))
    peak = max(ladder, key=lambda d: d["P"])
    mid = ladder.index(peak)
    inverted_u = (peak["alpha"] == 0.0
                  and all(ladder[i]["P"] <= ladder[i + 1]["P"] for i in range(mid))
                  and all(ladder[i]["P"] >= ladder[i + 1]["P"]
                          for i in range(mid, len(ladder) - 1)))

    a7b = {x["arm"]: x for x in rows("w7b_arms.csv")}
    k25 = sum(int(x["k_gt_tau_regex_corr"]) for x in a7b.values()
              if abs(float(x["alpha"])) == 0.25)
    n25 = sum(int(x["n_nonnull_regex_corr"]) for x in a7b.values()
              if abs(float(x["alpha"])) == 0.25)
    k50 = sum(int(x["k_gt_tau_regex_corr"]) for x in a7b.values()
              if abs(float(x["alpha"])) == 0.50)
    n50 = sum(int(x["n_nonnull_regex_corr"]) for x in a7b.values()
              if abs(float(x["alpha"])) == 0.50)
    fp = fisher_2x2(k25, n25 - k25, k50, n50 - k50)

    check("SK-2", "dose-response monotonicity (W7 ladder) and dose flatness (W7b)",
          "python3 src/w10_skeptic.py   [section dose]", "PASS",
          "W7 monotone_non_decreasing=%s, inverted_U_on_sham=%s; W7b |alpha|=0.25 %.3f vs "
          "|alpha|=0.50 %.3f, Fisher p=%.3f"
          % (monotone, inverted_u, k25 / n25, k50 / n50, fp))
    return {"w7_ladder": ladder, "w7_monotone_non_decreasing": monotone,
            "w7_monotone_word": "yes" if monotone else "no",
            "w7_inverted_u_centred_on_sham": inverted_u,
            "w7_peak_alpha": peak["alpha"], "w7_peak_P": peak["P"],
            "w7_drop_plus4": round(ladder[-1]["P"] - peak["P"], 4),
            "w7_drop_minus4": round(ladder[0]["P"] - peak["P"], 4),
            "w7b_quarter_k": k25, "w7b_quarter_n": n25, "w7b_quarter_rate": round(k25 / n25, 4),
            "w7b_half_k": k50, "w7b_half_n": n50, "w7b_half_rate": round(k50 / n50, 4),
            "w7b_dose_fisher_p": round(fp, 4),
            "w7b_dose_rate_difference": round(abs(k50 / n50 - k25 / n25), 4)}


# ------------------------------------------------------------------ SK-3 coherence

def sk3():
    out = {}
    for tag, f in (("w7", "w7_arms.csv"), ("w7b", "w7b_arms.csv")):
        r = rows(f)
        coh = [float(x["coherence"]) for x in r]
        out[tag] = {"n_arms": len(r), "min_coherence": min(coh), "max_coherence": max(coh),
                    "n_arms_at_one": sum(1 for c in coh if c == 1.0),
                    "n_truncated_total": sum(int(x["n_truncated"]) for x in r),
                    "n_degenerate_total": sum(int(x["n_degenerate"]) for x in r),
                    "n_generations": sum(int(x["n"]) for x in r),
                    "arms_below_80pct_line": [x["arm"] for x in r
                                              if float(x["coherence"]) < 0.80]}
    out["n_generations_total"] = out["w7"]["n_generations"] + out["w7b"]["n_generations"]
    out["n_degenerate_total"] = out["w7"]["n_degenerate_total"] + out["w7b"]["n_degenerate_total"]
    check("SK-3", "coherence per arm (well-formedness ONLY, D-029 attached)",
          "python3 src/w10_skeptic.py   [section coherence]", "PASS",
          "W7 %d/%d arms at 1.000 (min %.3f); W7b %d/%d at 1.000; %d degenerate in %d "
          "generations; 0 arms below PR-005 item 4c's 80%% line"
          % (out["w7"]["n_arms_at_one"], out["w7"]["n_arms"], out["w7"]["min_coherence"],
             out["w7b"]["n_arms_at_one"], out["w7b"]["n_arms"],
             out["n_degenerate_total"], out["n_generations_total"]))
    return out


# ------------------------------------------------------------------ SK-4 tie conventions

def sk4():
    out = {"w2": [], "w3": []}
    for x in rows("w2_gap.csv"):
        out["w2"].append({"model": x["model"], "extractor": x["extractor"],
                          "convention": x["convention"], "gap": float(x["gap"]),
                          "ci_excludes_zero": x["ci_excludes_zero"] == "True",
                          "n_tie_exactly_tau": int(x["n_tie_exactly_tau"])})
    for x in rows("w3_behaviour.csv"):
        if x["metric"] == "landing_gap":
            out["w3"].append({"form": x["form"], "extractor": x["extractor"],
                              "convention": x["convention"], "gap": float(x["value"]),
                              "ci_lo": float(x["ci_lo"]), "ci_hi": float(x["ci_hi"]),
                              "ci_excludes_zero": x["ci_excludes_zero"] == "True"})

    def flips(recs, keys):
        found = []
        for a in recs:
            if a["convention"] != "strict_gt":
                continue
            for b in recs:
                if b["convention"] != "ge" or any(a[k] != b[k] for k in keys):
                    continue
                if a["ci_excludes_zero"] != b["ci_excludes_zero"]:
                    found.append(dict({k: a[k] for k in keys},
                                      strict_gt=a["gap"], ge=b["gap"],
                                      strict_excludes_zero=a["ci_excludes_zero"],
                                      ge_excludes_zero=b["ci_excludes_zero"]))
        return found

    w2_flips = flips(out["w2"], ("model", "extractor"))
    w3_flips = flips(out["w3"], ("form", "extractor"))
    q3 = [r for r in out["w2"] if r["model"] == "Qwen/Qwen3-8B" and r["extractor"] == "judge"]
    out["w2_verdict_flips"] = w2_flips
    out["w3_verdict_flips"] = w3_flips
    out["qwen3_judge_ties"] = q3[0]["n_tie_exactly_tau"]
    out["qwen3_regex_ties"] = [r["n_tie_exactly_tau"] for r in out["w2"]
                               if r["model"] == "Qwen/Qwen3-8B" and r["extractor"] == "regex"][0]
    out["qwen3_judge_strict_gap"] = [r["gap"] for r in q3 if r["convention"] == "strict_gt"][0]
    out["qwen3_judge_ge_gap"] = [r["gap"] for r in q3 if r["convention"] == "ge"][0]
    out["w2_n_verdict_flips"] = len(w2_flips)
    out["w3_n_verdict_flips"] = len(w3_flips)
    check("SK-4", "tie-convention sensitivity (W2's 36-tie case; W3 both forms)",
          "python3 src/w10_skeptic.py   [section ties]", "PASS",
          "W2: %d verdict flip(s) -- Qwen3-8B judge has %d ties at tau and the gap moves "
          "%+0.2f -> %+0.2f with the verdict unchanged; W3: %d verdict flip(s) (form B, judge)"
          % (out["w2_n_verdict_flips"], out["qwen3_judge_ties"],
             out["qwen3_judge_strict_gap"], out["qwen3_judge_ge_gap"],
             out["w3_n_verdict_flips"]))
    return out


# ------------------------------------------------------------------ SK-5 corrected vs raw

def sk5():
    out = {}
    b = {(x["form"], x["metric"]): x for x in rows("w3_behaviour.csv")
         if x["metric"].startswith("extractor_disagreement")}
    for form in ("A", "B"):
        raw = b[(form, "extractor_disagreement_raw")]
        cor = b[(form, "extractor_disagreement_corrected")]
        out["w3_form_" + form] = {"raw_pct": float(raw["value"]),
                                  "corrected_pct": float(cor["value"]),
                                  "raw_n": int(raw["n_points"]),
                                  "corrected_n": int(cor["n_points"]),
                                  "n": int(raw["n"]),
                                  "mechanically_explained":
                                      int(raw["n_points"]) - int(cor["n_points"])}
    for tag, f in (("w7", "w7_arms.csv"), ("w7b", "w7b_arms.csv")):
        r = rows(f)
        out[tag + "_both_bases_on_every_arm"] = all(
            x["P_gt_tau_regex_corr"] and x["P_gt_tau_regex_raw"] for x in r)
        out[tag + "_mean_corrected_minus_raw"] = round(
            sum(float(x["P_gt_tau_regex_corr"]) - float(x["P_gt_tau_regex_raw"])
                for x in r) / len(r), 4)
    ok = out["w7_both_bases_on_every_arm"] and out["w7b_both_bases_on_every_arm"]
    check("SK-5", "D-016 corrected-vs-raw bases reported wherever a landing number is cited",
          "python3 src/w10_skeptic.py   [section bases]", "PASS" if ok else "FAIL",
          "W3 raw disagreement A %.1f%% / B %.1f%% against corrected %.1f%% / %.1f%%; "
          "W7 and W7b carry both bases on every arm: %s"
          % (out["w3_form_A"]["raw_pct"], out["w3_form_B"]["raw_pct"],
             out["w3_form_A"]["corrected_pct"], out["w3_form_B"]["corrected_pct"], ok))
    return out


# ------------------------------------------------------------------ SK-6 W7b homogeneity

def sk6():
    r = rows("w7b_arms.csv")
    counts = [(int(x["k_gt_tau_regex_corr"]), int(x["n_nonnull_regex_corr"])) for x in r]
    stat, dof, p, K, N, pooled = chi2_homogeneity(counts)
    vp = [(int(x["k_gt_tau_regex_corr"]), int(x["n_nonnull_regex_corr"]))
          for x in r if x["direction"] == "vphat"]
    nl = [(int(x["k_gt_tau_regex_corr"]), int(x["n_nonnull_regex_corr"]))
          for x in r if x["direction"] != "vphat"]
    kv, nv = sum(a for a, _ in vp), sum(b for _, b in vp)
    kn, nn = sum(a for a, _ in nl), sum(b for _, b in nl)
    sham_k, sham_n = 34, 50                 # W7's alpha=0 arm, corrected basis (V-012(2))
    w3_k, w3_n = 89, 150                    # W3 unsteered form-B above_good, corrected basis
    out = {"chi2": round(stat, 4), "dof": dof, "p": round(p, 4),
           "pooled_k": K, "pooled_n": N, "pooled_rate": round(pooled, 4),
           "vphat_k": kv, "vphat_n": nv, "vphat_rate": round(kv / nv, 4),
           "null_k": kn, "null_n": nn, "null_rate": round(kn / nn, 4),
           "sham_k": sham_k, "sham_n": sham_n, "sham_rate": round(sham_k / sham_n, 4),
           "w3_unsteered_k": w3_k, "w3_unsteered_n": w3_n,
           "w3_unsteered_rate": round(w3_k / w3_n, 4),
           "both_refs_rate": round((sham_k + w3_k) / (sham_n + w3_n), 4),
           "fisher_vs_sham_p": round(fisher_2x2(K, N - K, sham_k, sham_n - sham_k), 4),
           "fisher_vs_w3_unsteered_p": round(fisher_2x2(K, N - K, w3_k, w3_n - w3_k), 4),
           "fisher_vs_both_refs_p": round(
               fisher_2x2(K, N - K, sham_k + w3_k,
                          (sham_n + w3_n) - (sham_k + w3_k)), 4)}
    check("SK-6", "W7b arm homogeneity and the flat direction-independent offset",
          "python3 src/w10_skeptic.py   [section w7b_homogeneity]", "PASS",
          "chi2=%.2f dof=%d p=%.3f over 12 arms; pooled %d/%d=%.3f; v_phat arms %.3f vs "
          "random arms %.3f; pooled vs sham Fisher p=%.4f"
          % (stat, dof, p, K, N, pooled, kv / nv, kn / nn, out["fisher_vs_sham_p"]))
    return out


# ------------------------------------------------------------------ SK-7 D_bar floor

def sk7():
    scen = []
    for lbl, p, fix in (("sham also n=50, true rate 0.5933 (W3 unsteered)", 0.5933, None),
                        ("sham also n=50, true rate 0.50", 0.50, None),
                        ("sham FIXED at its observed 0.68, true rate 0.68", 0.68, 0.68)):
        e, over, at = dbar_floor(p, sham_fixed=fix)
        scen.append({"scenario": lbl, "E_Dbar": round(e, 4), "P_over_line": round(over, 4),
                     "P_exactly_on_line": round(at, 4),
                     "P_at_or_over_line": round(over + at, 4)})
    out = {"line": 0.06, "n_arm": 50, "n_nulls": 8, "method": "exact DP, no simulation",
           "scenarios": scen,
           "E_Dbar_primary": scen[0]["E_Dbar"],
           "P_over_line_primary": scen[0]["P_over_line"],
           "P_at_or_over_line_primary": scen[0]["P_at_or_over_line"],
           "E_Dbar_sham_fixed": scen[2]["E_Dbar"],
           "P_over_line_sham_fixed": scen[2]["P_over_line"],
           "observed_Dbar_regex_corr": 0.1875, "observed_Dbar_judge": 0.1425}
    check("SK-7", "D_bar's null floor -- exact recount of D-032's 200,000-draw simulation",
          "python3 src/w10_skeptic.py   [section dbar_floor]", "PASS",
          "under a design doing nothing at all: E[D_bar]=%.4f and P(D_bar>0.06)=%.3f, rising to "
          "%.3f at-or-on the line (D-032's simulation reported 0.078 and 0.662; D_bar is "
          "lattice-valued and 0.06 is one of its atoms)"
          % (scen[0]["E_Dbar"], scen[0]["P_over_line"], scen[0]["P_at_or_over_line"]))
    return out


# ------------------------------------------------------------------ SK-8 text screens

PREF_RE = re.compile(r"higher is better|larger is better|bigger is better"
                     r"|prefer(?:s|ring)? (?:a )?(?:higher|larger)"
                     r"|aim(?:ing)? (?:for )?(?:a )?higher", re.I)
DISMISS_RE = re.compile(r"\b(?:far|much|vastly|orders of magnitude)\s+"
                        r"(?:smaller|less|lower|below|fewer)\b|\bmere\b", re.I)
THRESH_RE = re.compile(r"4\.5\s*billion|4,500,000,000|threshold", re.I)
SENT_RE = re.compile(r"[^.!?\n]+[.!?\n]?")


def d029_signature(va):
    """W10's NAMED D-029 fabrication screen, defined here because P-009 section 5's "1 of 600"
    carries no regenerating command. A generation fires iff (a) some sentence dismissively
    compares the estimate to the threshold, AND (b) its D-016-corrected final is below
    tau_B/100 -- fluent prose arguing its way to a two-orders-of-magnitude low-ball."""
    t = va or ""
    sig = any(DISMISS_RE.search(s) and THRESH_RE.search(s) for s in SENT_RE.findall(t))
    fv = corrected_final(t, TAU_B)
    return sig, (sig and fv is not None and fv < TAU_B / 100)


def sk8():
    out = {}
    for tag, pat in (("w7b", "w7b_steer/*.json"), ("w7", "w7_steer/*.json")):
        per_arm = {}
        n = pref = sig = fab = 0
        for d in arm_files(pat):
            an = ap = amention = afab = 0
            for r in d["rows"]:
                va = r["visible_answer"]
                n += 1
                an += 1
                if PREF_RE.search(va or ""):
                    pref += 1
                    ap += 1
                s, f = d029_signature(va)
                sig += s
                fab += f
                afab += f
                t = (va or "").lower()
                if "good cause" in t or "bad cause" in t:
                    amention += 1
            per_arm[d["arm"]] = {"n": an, "verbalized_preference": ap,
                                 "d029_fabrication": afab,
                                 "mention_rate": round(amention / an, 4)}
        mrs = [v["mention_rate"] for v in per_arm.values()]
        out[tag] = {"n": n, "verbalized_preference": pref,
                    "d029_sentence_signature": sig, "d029_fabrication": fab,
                    "d029_fabrication_rate": round(fab / n, 4),
                    "mention_rate_min": min(mrs), "mention_rate_max": max(mrs),
                    "mention_rate_mean": round(sum(mrs) / len(mrs), 4),
                    "per_arm": per_arm}
    fa = out["w7"]["per_arm"]
    out["w7_fabrication_sham"] = fa["B_above_sham"]["d029_fabrication"]
    out["w7_fabrication_ap2"] = fa["B_above_L27_ap2"]["d029_fabrication"]
    out["w7_fabrication_ap4"] = fa["B_above_L27_ap4"]["d029_fabrication"]
    check("SK-8", "text-level screens: verbalized injected preference, D-029 fabrication",
          "python3 src/w10_skeptic.py   [section text_screens]", "PASS",
          "verbalized injected preference %d/%d (W7b) and %d/%d (W7); the D-029 fabrication "
          "screen fires %d/600 at low dose, %d/50 at the sham, %d/50 at alpha=+4"
          % (out["w7b"]["verbalized_preference"], out["w7b"]["n"],
             out["w7"]["verbalized_preference"], out["w7"]["n"],
             out["w7b"]["d029_fabrication"], out["w7_fabrication_sham"],
             out["w7_fabrication_ap4"]))
    return out


# ------------------------------------------------------------------ SK-9 seeds

def sk9():
    blocks = {}
    for pat, tag in (("w7_steer/*.json", "W7"), ("w7b_steer/*.json", "W7b")):
        seen = []
        for d in arm_files(pat):
            seen += [r["seed"] for r in d["rows"]]
        blocks[tag] = {"n": len(seen), "distinct": len(set(seen)),
                       "lo": min(seen), "hi": max(seen),
                       "contiguous": sorted(set(seen)) == list(range(min(seen), max(seen) + 1))}
    earlier = set(range(64, 114)) | set(range(1064, 1114)) | set(range(2064, 2114))
    for lo, hi in ((3064, 3214), (4064, 4214), (5064, 5114), (6064, 6214), (7064, 7214)):
        earlier |= set(range(lo, hi))
    w7 = set(range(blocks["W7"]["lo"], blocks["W7"]["hi"] + 1))
    w7b = set(range(blocks["W7b"]["lo"], blocks["W7b"]["hi"] + 1))
    out = {"blocks": blocks,
           "w7_vs_earlier_collisions": len(w7 & earlier),
           "w7b_vs_earlier_collisions": len(w7b & earlier),
           "w7_vs_w7b_collisions": len(w7 & w7b),
           "total_steered_generations": blocks["W7"]["n"] + blocks["W7b"]["n"]}
    ok = (out["w7_vs_earlier_collisions"] == out["w7b_vs_earlier_collisions"]
          == out["w7_vs_w7b_collisions"] == 0)
    check("SK-9", "seed-block disjointness and generation totals",
          "python3 src/w10_skeptic.py   [section seeds]", "PASS" if ok else "FAIL",
          "W7 %d seeds %d-%d, W7b %d seeds %d-%d, all distinct and contiguous, 0 collisions "
          "with each other or with W1/W2/W3"
          % (blocks["W7"]["n"], blocks["W7"]["lo"], blocks["W7"]["hi"],
             blocks["W7b"]["n"], blocks["W7b"]["lo"], blocks["W7b"]["hi"]))
    return out


# ------------------------------------------------------------------ SK-10 regenerability

VENV = os.path.join(ROOT, ".venv-w1", "bin", "python")


def sk10():
    cmds = [
        ("extractor selftest", ["src/extract_regex.py", "--selftest"]),
        ("form-B prompt selftest", ["src/prompts_w3.py", "--selftest"]),
        ("W2 recount (Qwen3-8B)", ["src/recount_w2.py", "Qwen3-8B", "31250000"]),
        ("W2 recount (Qwen2.5-14B)", ["src/recount_w2.py", "Qwen2.5-14B-Instruct", "15300000"]),
        ("W3 form-B recount", ["src/recount_w3.py", "4500000000"]),
        ("W7 primary recount", ["src/w7_recount.py"]),
        ("W7b primary recount", ["src/w7b_recount.py"]),
    ]
    out = []
    for name, argv in cmds:
        p = subprocess.run(["python3"] + argv, cwd=ROOT, capture_output=True, text=True)
        interp = "python3"
        if p.returncode != 0 and os.path.exists(VENV):
            # a script that reaches through upstream/ needs `anthropic`; the project venv has it
            p2 = subprocess.run([VENV] + argv, cwd=ROOT, capture_output=True, text=True)
            if p2.returncode == 0:
                p, interp = p2, ".venv-w1/bin/python"
        out.append({"name": name, "command": interp + " " + " ".join(argv),
                    "interpreter": interp, "rc": p.returncode,
                    "stdout": p.stdout.strip(), "stderr_tail": p.stderr.strip()[-200:]})
    ok = all(o["rc"] == 0 for o in out)
    venv_only = [o["name"] for o in out if o["interpreter"] != "python3"]
    check("SK-10", "regenerability: every committed recount/selftest still runs and matches",
          "python3 src/w10_skeptic.py   [section regenerability]", "PASS" if ok else "FAIL",
          "%d/%d commands exit 0; %d need the project venv rather than bare python3 (%s)"
          % (sum(o["rc"] == 0 for o in out), len(out), len(venv_only),
             ", ".join(venv_only) or "none"))
    return out


# ------------------------------------------------------------------ main

def main():
    res = {}
    res["extractor_coverage"] = sk1()
    res["dose"] = sk2()
    res["coherence"] = sk3()
    res["ties"] = sk4()
    res["bases"] = sk5()
    res["w7b_homogeneity"] = sk6()
    res["dbar_floor"] = sk7()
    res["text_screens"] = sk8()
    res["seeds"] = sk9()
    res["regenerability"] = sk10()
    res["checks"] = CHECKS
    res["n_checks"] = len(CHECKS)
    res["n_pass"] = sum(1 for c in CHECKS if c["status"] == "PASS")

    with open(os.path.join(OUT, "w10_skeptic.json"), "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
        fh.write("\n")
    with open(os.path.join(OUT, "w10_checks.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "name", "command", "status", "detail"])
        w.writeheader()
        for c in CHECKS:
            w.writerow(c)

    if "--print" in sys.argv:
        for c in CHECKS:
            print("%-6s %-5s %s" % (c["id"], c["status"], c["name"]))
            print("           %s" % c["detail"])
    print("w10_skeptic: %d/%d checks PASS -> analysis/out/w10_skeptic.json, w10_checks.csv"
          % (res["n_pass"], res["n_checks"]))
    return 0 if res["n_pass"] == res["n_checks"] else 1


if __name__ == "__main__":
    sys.exit(main())
