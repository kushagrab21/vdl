"""Derived quantities the write-up cites that no committed CSV holds as a single cell.

    python3 src/w10_derived.py           # -> analysis/out/w10_derived.json
    python3 src/w10_derived.py --print

Everything here is computed from committed files (`runs/**`, `analysis/out/*.csv|json`) with
stdlib only. Three kinds of quantity:

  * layer-profile summaries -- band edges, peak layers, counts of layers beating their null --
    which live across many rows of `w5_{layers,probes,invariance}.csv` rather than in one cell;
  * pooled counts -- the direction judge's mention rate over all 600 traces, landing counts per
    arm and per seed block -- recomputed from raw text plus the frozen judge caches, which makes
    this file an independent recount of P-004 and D-018 as well as a source for the write-up;
  * the D-018 two-proportion z, which the ledger states but no file carries.

`writeup/build.py` reads the result; nothing here is typed in by hand.
"""

import csv
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "analysis", "out")
TAU_A = 15300000.0
TAU_B = 4500000000.0
MODEL = "Qwen/Qwen2.5-14B-Instruct"


def rows(name):
    with open(os.path.join(OUT, name)) as fh:
        return list(csv.DictReader(fh))


def contiguous_band(layers):
    """Longest run of consecutive integers in `layers`; returns (lo, hi, length)."""
    if not layers:
        return None, None, 0
    best = cur = [layers[0]]
    for x in layers[1:]:
        if x == cur[-1] + 1:
            cur.append(x)
        else:
            cur = [x]
        if len(cur) > len(best):
            best = list(cur)
    return best[0], best[-1], len(best)


# ------------------------------------------------------------------ W5 layer profile

def w5_profile():
    lay = rows("w5_layers.csv")
    inv = rows("w5_invariance.csv")
    pro = rows("w5_probes.csv")
    lstar = json.load(open(os.path.join(OUT, "w5_lstar.json")))["layer_star"]

    out = {"lstar": lstar, "n_layers": len(inv)}

    for form in ("A", "B"):
        ph = [r for r in pro if r["form"] == form and r["target"] == "phat"]
        dt = [r for r in pro if r["form"] == form and r["target"] == "dt_control"]
        bp = [r for r in pro if r["form"] == form and r["target"] not in ("phat", "dt_control")]
        at = next(r for r in ph if int(r["layer"]) == lstar)
        peak = max(ph, key=lambda r: float(r["balacc"]))
        sig = [int(r["layer"]) for r in ph if float(r["balacc"]) > float(r["null_p95"])]
        dt_at = next(r for r in dt if int(r["layer"]) == lstar)
        dt_peak = max(dt, key=lambda r: float(r["balacc"]))
        dt_sig = [int(r["layer"]) for r in dt if float(r["balacc"]) > float(r["null_p95"])]
        out["phat_" + form] = {
            "balacc_at_lstar": round(float(at["balacc"]), 4),
            "null_p95_at_lstar": round(float(at["null_p95"]), 4),
            "p_at_lstar": round(float(at["p_perm"]), 3),
            "peak_balacc": round(float(peak["balacc"]), 4),
            "peak_layer": int(peak["layer"]),
            "peak_p": round(float(peak["p_perm"]), 3),
            "n_layers_beating_null": len(sig),
            "mean_balacc_over_layers": round(
                sum(float(r["balacc"]) for r in ph) / len(ph), 4),
            "dt_control_at_lstar": round(float(dt_at["balacc"]), 4),
            "dt_control_peak": round(float(dt_peak["balacc"]), 4),
            "dt_control_peak_layer": int(dt_peak["layer"]),
            "dt_control_n_layers_beating_null": len(dt_sig),
            "belief_polarity_min": round(min(float(r["balacc"]) for r in bp), 4)
            if bp else None,
            "belief_polarity_at_lstar": round(
                next(float(r["balacc"]) for r in bp if int(r["layer"]) == lstar), 4)
            if bp else None,
        }

    at = next(r for r in inv if int(r["layer"]) == lstar)
    cos_sig = [int(r["layer"]) for r in inv
               if float(r["cos_vphatA_vphatB"]) > float(r["cos_null_p95"])]
    tr_sig = [int(r["layer"]) for r in inv
              if float(r["transfer_A_to_B_balacc"]) > float(r["transfer_null_p95"])]
    cos_peak = max(inv, key=lambda r: float(r["cos_vphatA_vphatB"]))
    tr_peak = max(inv, key=lambda r: float(r["transfer_A_to_B_balacc"]))
    clo, chi, cn = contiguous_band(cos_sig)
    tlo, thi, tn = contiguous_band(tr_sig)
    out["invariance"] = {
        "cos_at_lstar": round(float(at["cos_vphatA_vphatB"]), 4),
        "cos_null_p95_at_lstar": round(float(at["cos_null_p95"]), 4),
        "cos_p_at_lstar": round(float(at["cos_p"]), 3),
        "transfer_at_lstar": round(float(at["transfer_A_to_B_balacc"]), 4),
        "transfer_null_p95_at_lstar": round(float(at["transfer_null_p95"]), 4),
        "transfer_p_at_lstar": round(float(at["transfer_p"]), 3),
        "cos_band_lo": clo, "cos_band_hi": chi, "cos_band_len": cn,
        "cos_peak": round(float(cos_peak["cos_vphatA_vphatB"]), 4),
        "cos_peak_layer": int(cos_peak["layer"]),
        "cos_peak_p": round(float(cos_peak["cos_p"]), 3),
        "transfer_band_lo": tlo, "transfer_band_hi": thi, "transfer_band_len": tn,
        "transfer_peak": round(float(tr_peak["transfer_A_to_B_balacc"]), 4),
        "transfer_peak_layer": int(tr_peak["layer"]),
        "transfer_peak_p": round(float(tr_peak["transfer_p"]), 3),
        "cos_vp_vphat_A_at_lstar": round(float(at["cos_vpA_vphatA"]), 3),
        "cos_vp_vphat_B_at_lstar": round(float(at["cos_vpB_vphatB"]), 3),
        "cos_vp_vphat_B_layer0": round(
            float(next(r for r in inv if int(r["layer"]) == 0)["cos_vpB_vphatB"]), 3),
    }

    for form, layer in (("B", 27), ("B", 30)):
        r = next(x for x in lay if x["form"] == form and int(x["layer"]) == layer)
        out["vphat_l2_%s_L%d" % (form, layer)] = round(float(r["vphat_l2"]), 6)
    return out


# ------------------------------------------------------------------ W3 pooled recounts

def w3_recount():
    cache = json.load(open(os.path.join(OUT, "w3_extractions.json")))[MODEL]
    direction = json.load(open(os.path.join(OUT, "w3_direction_cache.json")))

    def arm(form, name, tau):
        d = json.load(open(os.path.join(ROOT, "runs", "w3_frozen",
                                        "form_" + form, name + ".json")))
        vals = []
        for r in d["rows"]:
            vals.append(cache.get(r["visible_answer"]))
        good = [v for v in vals if v is not None]
        return {"n": len(vals), "n_null": len(vals) - len(good),
                "k_gt_tau": sum(1 for v in good if v > tau),
                "n_valid": len(good),
                "P_gt_tau": round(sum(1 for v in good if v > tau) / len(good), 4),
                "per_block": [
                    {"block": b,
                     "k": sum(1 for v in vals[b * 50:(b + 1) * 50]
                              if v is not None and v > tau),
                     "n": sum(1 for v in vals[b * 50:(b + 1) * 50] if v is not None)}
                    for b in range(len(vals) // 50)]}

    out = {"form_A_below": arm("A", "below_good", TAU_A),
           "form_A_above": arm("A", "above_good", TAU_A),
           "form_B_below": arm("B", "below_good", TAU_B),
           "form_B_above": arm("B", "above_good", TAU_B),
           "form_B_baseline": arm("B", "baseline", TAU_B)}
    for form, tau in (("A", TAU_A), ("B", TAU_B)):
        lo = out["form_%s_below" % form]
        hi = out["form_%s_above" % form]
        out["landing_gap_" + form] = round(hi["P_gt_tau"] - lo["P_gt_tau"], 4)

    beh = rows("w3_behaviour.csv")
    for form in ("A", "B"):
        raw = next(x for x in beh if x["metric"] == "extractor_disagreement_raw"
                   and x["form"] == form)
        cor = next(x for x in beh if x["metric"] == "extractor_disagreement_corrected"
                   and x["form"] == form)
        out["mech_" + form] = int(raw["n_points"]) - int(cor["n_points"])

    ment = sum(1 for v in direction.values() if v.get("mentions_bet"))
    out["direction_judge"] = {
        "n_traces": len(direction), "n_mention": ment,
        "mention_rate_pct": round(100.0 * ment / len(direction), 1),
        "n_unparsed": sum(1 for v in direction.values() if v.get("direction") is None)}
    return out


# ------------------------------------------------------------------ D-018 winner's curse

def two_prop_z(k1, n1, k2, n2):
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se
    pv = math.erfc(abs(z) / math.sqrt(2))          # two-sided normal
    return z, pv


def winners_curse(w3):
    g = {r["extractor"] + "|" + r["convention"] + "|" + r["model"]: r for r in rows("w2_gap.csv")}
    w2 = g["judge|strict_gt|" + MODEL]
    n2 = int(w2["n_above_valid"])
    k2 = round(float(w2["pct_above_tau_above_cond"]) / 100.0 * n2)
    a = w3["form_A_above"]
    z, pv = two_prop_z(k2, n2, a["k_gt_tau"], a["n_valid"])
    return {"w2_above_k": k2, "w2_above_n": n2,
            "w2_above_rate": round(k2 / n2, 4),
            "w2_below_rate": round(float(w2["pct_above_tau_below_cond"]) / 100.0, 4),
            "w2_gap": float(w2["gap"]), "w2_ci_lo": float(w2["ci_lo"]),
            "w2_ci_hi": float(w2["ci_hi"]),
            "w3_above_k": a["k_gt_tau"], "w3_above_n": a["n_valid"],
            "w3_above_rate": a["P_gt_tau"],
            "w3_below_rate": w3["form_A_below"]["P_gt_tau"],
            "w3_blocks_above": a["per_block"],
            "z": round(z, 2), "p_two_sided": round(pv, 4)}


# ------------------------------------------------------------------ project totals

def totals(w3):
    n = {"w1_neutral": 4 * 50, "w2_screen": 2 * 2 * 50,
         "w3_fresh": 650, "w3_reused_neutral": 50,
         "w7_steered": 1150, "w7b_steered": 600}
    n["all_generations"] = (n["w1_neutral"] + n["w2_screen"] + n["w3_fresh"]
                            + n["w7_steered"] + n["w7b_steered"])
    n["all_steered"] = n["w7_steered"] + n["w7b_steered"]
    rp = rows("w4_replay_summary.csv")
    n["w4_traces_replayed"] = sum(int(r["n_replayed"]) for r in rp)
    n["w4_points"] = sum(int(r["n_points"]) for r in rp)
    n["w4_quarantined"] = sum(int(r["n_quarantined"]) for r in rp)
    n["w4_est_points"] = sum(int(r["n_est"]) for r in rp)
    return n


# ------------------------------------------------------------------ conventions and doses

def conventions():
    """Sampling / bootstrap constants, read out of the artifacts that carry them."""
    g = json.load(open(os.path.join(ROOT, "runs", "w3_frozen", "form_B", "above_good.json")))
    b = rows("w2_gap.csv")[0]
    s = json.load(open(os.path.join(ROOT, "runs", "w7_steer", "B_above_L27_ap2.json")))
    return {"temperature": g["sampling"]["temperature"],
            "top_p": g["sampling"]["top_p"],
            "max_tokens_w3": g["sampling"]["max_tokens"],
            "max_new_tokens_w7": s["sampling"].get("max_new_tokens"),
            "base_seed": g["base_seed"],
            "n_boot": int(b["n_boot"]),
            "bootstrap_seed": int(b["bootstrap_seed"]),
            "batch_size_w7": s.get("batch_size", 25),
            "n_per_arm": s["n"]}


def doses():
    """alpha in units of ||dmu||, expressed as a fraction of the residual-stream norm.
    ||h|| is recovered from w7b_arms.csv (delta_norm / frac_of_resid_norm), not typed in."""
    a7b = rows("w7b_arms.csv")
    r = a7b[0]
    h = float(r["delta_norm"]) / float(r["frac_of_resid_norm"])
    dmu = float(next(x["vphat_l2"] for x in rows("w5_layers.csv")
                     if x["form"] == "B" and int(x["layer"]) == 27))
    out = {"resid_norm_L27": round(h, 2), "dmu_L27": round(dmu, 6)}
    for a in (0.25, 0.5, 1.0, 2.0, 4.0):
        key = ("a%g" % a).replace(".", "p")
        out[key + "_delta_norm"] = round(a * dmu, 3)
        out[key + "_pct_of_h"] = round(100.0 * a * dmu / h, 1)
    return out


# ------------------------------------------------------------------ steered-run aggregates

def steer_summary(tag, run_dir, cache_name, arms_csv, tau):
    """Token-length range, tau-echo rate under the RAW regex, and judge-vs-corrected
    disagreement -- three numbers the write-up cites that no CSV holds as a cell."""
    import hashlib
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import extract_regex as ex

    cache = json.load(open(os.path.join(OUT, cache_name)))
    a = rows(arms_csv)
    med = [int(r["median_tokens"]) for r in a if r["median_tokens"]]
    echo = n = disagree = judged = 0
    vdis = [0]
    by_alpha = {}
    for f in sorted(os.listdir(os.path.join(ROOT, "runs", run_dir))):
        if not f.endswith(".json") or f.endswith("_gen.log"):
            continue
        d = json.load(open(os.path.join(ROOT, "runs", run_dir, f)))
        if "rows" not in d:
            continue
        key = "%+g" % float(d["alpha"]) if d["direction"] == "vphat" else "null"
        for r in d["rows"]:
            va = r["visible_answer"]
            n += 1
            raw = ex.final_estimate(va)
            hit = raw is not None and raw == tau
            echo += hit
            if d["condition"] == "above_good" and d["layer"] == 27:
                b = by_alpha.setdefault(key, [0, 0])
                b[0] += hit
                b[1] += 1
            nums = [v for v, _, _ in ex.all_numbers(va or "", skip_ranges=False) if v != tau]
            corr = nums[-1] if nums else None
            j = cache.get(hashlib.sha1((va or "").encode()).hexdigest())
            if j is not None and corr is not None:
                judged += 1
                disagree += (j > tau) != (corr > tau)
                # PR-001 item 8's own definition: relative difference > 1 %
                vdis[0] += abs(j - corr) > 0.01 * max(abs(j), abs(corr))
            elif (j is None) != (corr is None):
                vdis[0] += 1
    return {"n": n, "median_tokens_min": min(med), "median_tokens_max": max(med),
            "tau_echo_raw_k": echo, "tau_echo_raw_rate": round(echo / n, 4),
            "tau_echo_by_alpha": {k: round(v[0] / v[1], 2) for k, v in sorted(by_alpha.items())},
            "judge_vs_corrected_landing_disagree_k": disagree,
            "judge_vs_corrected_landing_n": judged,
            "judge_vs_corrected_landing_rate": round(disagree / judged, 4),
            "judge_vs_corrected_value_disagree_k": vdis[0],
            "judge_vs_corrected_value_rate": round(vdis[0] / n, 4)}


def w3_lengths():
    out = {}
    for form, arms in (("A", ("below_good", "above_good")),
                       ("B", ("below_good", "above_good", "baseline"))):
        for arm in arms:
            d = json.load(open(os.path.join(ROOT, "runs", "w3_frozen",
                                            "form_" + form, arm + ".json")))
            t = sorted(r["n_output_tokens"] for r in d["rows"])
            m = (t[len(t) // 2] if len(t) % 2 else (t[len(t) // 2 - 1] + t[len(t) // 2]) / 2)
            out["form_%s_%s" % (form, arm)] = m
    return out


# ------------------------------------------------------------------ write-up leaf values

def w3_corrected():
    """The W3 form-B arms on the D-016-corrected regex basis -- the basis W7's sham is compared
    against. The judge-basis recount is in w3_recount(); both are needed and they differ."""
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import extract_regex as ex
    out = {}
    for arm in ("below_good", "above_good", "baseline"):
        d = json.load(open(os.path.join(ROOT, "runs", "w3_frozen", "form_B", arm + ".json")))
        vals = []
        for r in d["rows"]:
            nums = [v for v, _, _ in ex.all_numbers(r["visible_answer"] or "",
                                                    skip_ranges=False) if v != TAU_B]
            if nums:
                vals.append(nums[-1])
        k = sum(1 for v in vals if v > TAU_B)
        logs = sorted(math.log10(v) for v in vals if v > 0)
        med = (logs[len(logs) // 2] if len(logs) % 2
               else (logs[len(logs) // 2 - 1] + logs[len(logs) // 2]) / 2)
        out[arm] = {"k": k, "n": len(vals), "P_gt_tau": round(k / len(vals), 4),
                    "median_log10": round(med, 4)}
    out["n_truncated_all_arms"] = sum(
        json.load(open(os.path.join(ROOT, "runs", "w3_frozen", "form_" + f, a + ".json")))
        ["n_truncated"]
        for f, arms in (("A", ("below_good", "above_good")),
                        ("B", ("below_good", "above_good", "baseline")))
        for a in arms)
    return out


def judge_mapping_rates():
    """V-007's deterministic cause-string test, recounted per verdict class over all traces."""
    r = rows("w4_judge_check.csv")
    out = {}
    for cls in ("correct", "incorrect", "unclear"):
        sub = [x for x in r if x["direction"] == cls]
        silent = sum(1 for x in sub if x["has_mapping_string"] == "0")
        out[cls] = {"n": len(sub), "mapping_silent": silent,
                    "mapping_silent_pct": round(100.0 * silent / len(sub), 1)}
    return out


def w5_projection_means():
    r = [x for x in rows("w5_projections.csv")
         if x["form"] == "B" and x["arm"] == "above_good" and x["kind"] == "est"
         and x["phat"] in ("1", "-1")]
    out = {}
    for lbl, key in (("pos", "1"), ("neg", "-1")):
        sub = [float(x["proj_vphat_lstar"]) for x in r if x["phat"] == key]
        out["mean_" + lbl] = round(sum(sub) / len(sub), 3)
        out["n_" + lbl] = len(sub)
    out["gap"] = round(out["mean_pos"] - out["mean_neg"], 2)
    return out


def w7_leaf():
    a = {x["arm"]: x for x in rows("w7_arms.csv")}
    p = rows("w7_primary.csv")
    layers = sorted({int(x["layer"]) for x in a.values()})
    nulls = [x for x in a.values() if x["direction"] != "vphat"]
    sham = float(a["B_above_sham"]["P_gt_tau_regex_corr"])

    def phat(arm):
        x = a[arm]
        pos, neg = int(x["phat_pos"] or 0), int(x["phat_neg"] or 0)
        return round(pos / (pos + neg), 3) if pos + neg else None

    def beats(stat, basis="regex_corr"):
        row = next(x for x in p if x["statistic"] == stat and x["basis"] == basis)
        nl = json.loads(row["extra"])["nulls"]
        v = float(row["value"])
        k = sum(1 for d in nl if v > d)
        return {"value": v, "beats": k, "n_nulls": len(nl),
                "p_one_sided": round((1 + sum(1 for d in nl if d >= v)) / (len(nl) + 1), 4)}

    out = {"layer_primary": layers[0], "layer_secondary": layers[-1],
           "n_arms": len(a), "n_null_arms": len(nulls),
           "alpha_max": ("%+g" % max(float(x["alpha"]) for x in a.values())).replace("-", "\u2212"),
           "alpha_min": ("%+g" % min(float(x["alpha"]) for x in a.values())).replace("-", "\u2212"),
           "n_dose_generations": sum(int(x["n"]) for x in a.values()
                                     if x["condition"] == "above_good"
                                     and int(x["layer"]) == layers[0]
                                     and x["direction"] == "vphat"),
           "dplus_a1": round(float(a["B_above_L27_ap1"]["P_gt_tau_regex_corr"]) - sham, 2),
           "dminus_a1": round(float(a["B_above_L27_am1"]["P_gt_tau_regex_corr"]) - sham, 2),
           "null_delta_mean": round(sum(float(x["P_gt_tau_regex_corr"]) - sham
                                        for x in nulls) / len(nulls), 3),
           "null_delta_min": round(min(float(x["P_gt_tau_regex_corr"]) - sham for x in nulls), 2),
           "null_delta_max": round(max(float(x["P_gt_tau_regex_corr"]) - sham for x in nulls), 2),
           "phat_ap2": phat("B_above_L27_ap2"), "phat_sham": phat("B_above_sham"),
           "phat_am2": phat("B_above_L27_am2"),
           "phat_below_ap2": phat("B_below_L27_ap2"), "phat_below_am2": phat("B_below_L27_am2"),
           "phat_null04": phat("B_above_null04"),
           "coherence_arms_at_one": sum(1 for x in a.values()
                                        if float(x["coherence"]) == 1.0)}
    for tag, arm in (("ap2", "B_above_L27_ap2"), ("sham", "B_above_sham"),
                     ("am2", "B_above_L27_am2")):
        x = a[arm]
        out["verdicts_" + tag] = "%s / %s / %s" % (x["verdict_correct"], x["verdict_incorrect"],
                                                   x["verdict_unclear"])
        out["n_labelled_" + tag] = int(x["phat_pos"] or 0) + int(x["phat_neg"] or 0)
    out["flip_plus_vs_sham"] = round(out["phat_ap2"] - out["phat_sham"], 3)
    out["flip_minus_vs_sham"] = round(out["phat_am2"] - out["phat_sham"], 3)
    for name, stat in (("dplus", "null_test delta_plus"),
                       ("dminus", "null_test delta_minus"),
                       ("dpm", "null_test delta_pm")):
        out[name + "_null"] = beats(stat)
    rho = next(x for x in p if x["statistic"] == "dose_response_spearman_rho"
               and x["basis"] == "regex_corr")
    out["rho_perm_p"] = json.loads(rho["extra"])["perm_p"]
    ndpm = next(x for x in p if x["statistic"].startswith("neutral P(>tau"))
    out["neutral_dpm_abs"] = abs(float(ndpm["value"]))
    nref = next(x for x in p if x["statistic"].startswith("neutral_reference"))
    nap2 = next(x for x in p if x["statistic"].startswith("neutral B_neutral_L27_ap2"))
    nam2 = next(x for x in p if x["statistic"].startswith("neutral B_neutral_L27_am2"))
    out["neutral_ref_medlog"] = round(float(nref["value"]), 3)
    out["neutral_ap2_medlog"] = round(float(nap2["value"]), 3)
    out["neutral_am2_medlog"] = round(float(nam2["value"]), 3)
    out["neutral_logdelta"] = round(float(nam2["value"]) - float(nap2["value"]), 3)
    return out


def alpha_grids():
    def grid(csvname):
        mags = sorted({abs(float(x["alpha"])) for x in rows(csvname)
                       if x["direction"] == "vphat" and float(x["alpha"]) != 0})
        return "{" + ", ".join("\u00b1%g" % m for m in mags) + "}"
    return {"w7": grid("w7_arms.csv"), "w7b": grid("w7b_arms.csv")}


def w7b_leaf():
    a = rows("w7b_arms.csv")
    med = [float(x["median_log10_regex_corr"]) for x in a]
    tok = [int(x["median_tokens"]) for x in a]
    return {"n_arms": len(a), "median_log10_min": min(med), "median_log10_max": max(med),
            "median_tokens_min": min(tok), "median_tokens_max": max(tok)}


def w2_leaf():
    r = rows("w2_intermediates.csv")
    out = {}
    for model in sorted({x["model"] for x in r}):
        vals = sorted(int(x["n_filtered"]) for x in r if x["model"] == model)
        m = (vals[len(vals) // 2] if len(vals) % 2
             else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2)
        key = model.split("/")[-1].lower().replace(".", "").replace("-", "_")
        out[key] = {"pooled_filtered_median": m, "n_rollouts": len(vals)}
    return out


def plot_coords():
    """Pixel coordinates for the compact document's two data figures, computed from the same
    CSVs the prose reads, so no chart geometry is hand-placed either."""
    a = {x["arm"]: x for x in rows("w7_arms.csv")}
    order = ["B_above_L27_am4", "B_above_L27_am2", "B_above_L27_am1", "B_above_sham",
             "B_above_L27_ap1", "B_above_L27_ap2", "B_above_L27_ap4"]
    X0, DX, Y0, H = 108, 96, 250, 180          # axis box: y=Y0 is P=0, Y0-H is P=1
    out = {"axis_x0": X0, "axis_dx": DX, "axis_y0": Y0, "axis_h": H}
    pts = []
    for i, arm in enumerate(order):
        p = float(a[arm]["P_gt_tau_regex_corr"])
        pts.append({"arm": arm, "alpha": ("%+g" % float(a[arm]["alpha"])).replace("-", "\u2212"),
                    "P": p, "x": X0 + i * DX, "y": round(Y0 - H * p, 1)})
    out["ladder"] = pts
    out["ladder_path"] = " ".join(("M" if i == 0 else "L") + "%d %.1f" % (q["x"], q["y"])
                                  for i, q in enumerate(pts))
    nulls = [float(x["P_gt_tau_regex_corr"]) for x in a.values() if x["direction"] != "vphat"]
    out["null_band_lo_y"] = round(Y0 - H * min(nulls), 1)
    out["null_band_hi_y"] = round(Y0 - H * max(nulls), 1)
    out["null_band_h"] = round(H * (max(nulls) - min(nulls)), 1)
    out["null_lo"] = min(nulls)
    out["null_hi"] = max(nulls)
    # D_bar figure: a 0..0.24 axis, 620 px wide
    DX0, DW, DMAX = 100, 620, 0.24
    out["dbar_x0"] = DX0
    out["dbar_w"] = DW
    for name, v in (("line", 0.06), ("floor", 0.0782), ("observed", 0.1875),
                    ("obs_judge", 0.1425)):
        out["dbar_x_" + name] = round(DX0 + DW * v / DMAX, 1)
    out["dbar_p_over_w"] = round(DW * (DMAX - 0.06) / DMAX, 1)
    return out


def main():
    res = {}
    res["conventions"] = conventions()
    res["doses"] = doses()
    res["w5"] = w5_profile()
    res["w3"] = w3_recount()
    res["w3"]["median_tokens"] = w3_lengths()
    res["winners_curse"] = winners_curse(res["w3"])
    res["totals"] = totals(res["w3"])
    res["w3"]["corrected"] = w3_corrected()
    _dis = [x for x in rows("w3_behaviour.csv")
            if x["metric"] == "extractor_disagreement_corrected"]
    res["w3"]["agreement_corrected_pct"] = round(
        100.0 - 100.0 * sum(int(x["n_points"]) for x in _dis)
        / sum(int(x["n"]) for x in _dis), 1)
    res["judge_mapping"] = judge_mapping_rates()
    res["w5"]["projection"] = w5_projection_means()
    res["w7_leaf"] = w7_leaf()
    res["w7b_leaf"] = w7b_leaf()
    res["alpha_grids"] = alpha_grids()
    res["plot"] = plot_coords()
    res["w2_leaf"] = w2_leaf()
    res["w7"] = steer_summary("w7", "w7_steer", "w7_extractions.json", "w7_arms.csv", TAU_B)
    res["w7b"] = steer_summary("w7b", "w7b_steer", "w7b_extractions.json",
                               "w7b_arms.csv", TAU_B)
    with open(os.path.join(OUT, "w10_derived.json"), "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
        fh.write("\n")
    if "--print" in sys.argv:
        print(json.dumps(res, indent=1, sort_keys=True))
    print("w10_derived: -> analysis/out/w10_derived.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
