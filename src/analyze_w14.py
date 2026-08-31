"""W14 analysis: the arm table, the frozen prediction, PR-010 item 6's verdict, and the
three-point dose-response table.

Offline — reads committed run files and the two W14 judge caches, calls no API. The
prediction machinery is imported from analyze_w11, unchanged, so W11's and W14's
predictions come out of the same function at different comprehension inputs.

  python3 src/analyze_w14.py
emits: analysis/out/w14_arms.csv, w14_prediction.csv, w14_dose_response.csv,
       w14_interaction.csv
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import extract_regex as ex          # noqa: E402
import landing_gap as lg            # noqa: E402
import w11_cells as w3c             # noqa: E402
from analyze_w11 import corrected_final, predict, PRED_SEED  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
FORM = "B"
TAU = 4500000000
RUN = ROOT / "runs" / "w14_degraded"
NUM_CACHE = ROOT / "analysis" / "out" / "w14_extractions.json"
DIR_CACHE = ROOT / "analysis" / "out" / "w14_direction_cache.json"
W11_ARMS = ROOT / "analysis" / "out" / "w11_arms.csv"
W11_PRED = ROOT / "analysis" / "out" / "w11_prediction.csv"
OUT = ROOT / "analysis" / "out"
CONDS = ("below_good", "above_good")

# PR-010 item 6: D1/D3 bar. p_a must fall at least 0.10 BELOW W3's form-B rate.
W3_P = {"above_good": 82 / 150, "below_good": 121 / 150}
W3_N = {"above_good": 150, "below_good": 150}
D1_DROP = 0.10
# PR-010 item 5's frozen resolving power, at the achieved comprehension level (filled in
# from w14_power.csv by the nearest p_a on the row's own pb_rule; both alt worlds carried).
POWER_FILE = OUT / "w14_power.csv"


def load():
    num = json.loads(NUM_CACHE.read_text())[MODEL]
    dirc = json.loads(DIR_CACHE.read_text())
    out = {}
    for cond in CONDS:
        d = json.loads((RUN / ("form_%s" % FORM) / ("%s.json" % cond)).read_text())
        recs = []
        for r in d["rows"]:
            v = dirc.get("%s|%s|%s|%d" % (MODEL, FORM, cond, r["i"]), {})
            recs.append({"i": r["i"], "seed": r["seed"], "truncated": r["truncated"],
                         "n_tok": r["n_output_tokens"], "text": r["visible_answer"],
                         "judge": num.get(r["visible_answer"] or ""),
                         "regex": ex.final_estimate(r["visible_answer"]),
                         "corr": corrected_final(r["visible_answer"], TAU),
                         "direction": v.get("direction"), "mentions": v.get("mentions_bet")})
        out[cond] = {"meta": d, "recs": recs}
    return out


def w11_row(arm):
    for r in csv.DictReader(open(W11_ARMS)):
        if r["form"] == FORM and r["arm"] == arm:
            return r
    raise KeyError(arm)


def arm_rows(data):
    rows = []
    for cond in CONDS:
        allr = data[cond]["recs"]
        recs = [r for r in allr if not r["truncated"]]
        elig = [r for r in recs if r["judge"] is not None]
        jud = [r for r in recs if r["direction"] is not None]
        eligj = [r for r in elig if r["direction"] is not None]

        def rate(key, sel):
            v = [r[key] for r in sel if r[key] is not None]
            return (round(sum(x > TAU for x in v) / len(v), 4), len(v)) if v else ("", 0)
        lj, nj = rate("judge", recs)
        lr, nr = rate("regex", recs)
        lc, nc = rate("corr", recs)
        n_corr = sum(1 for r in eligj if r["direction"] == "correct")
        w11 = w11_row(cond)
        rows.append({
            "form": FORM, "arm": cond, "tau": TAU, "n": len(allr),
            "n_truncated": sum(r["truncated"] for r in allr),
            "n_null_judge": sum(1 for r in recs if r["judge"] is None),
            "n_null_regex": sum(1 for r in recs if r["regex"] is None),
            "n_judged_direction": len(jud),
            "mention_rate": round(sum(1 for r in jud if r["mentions"]) / len(jud), 4) if jud else "",
            "n_direction_correct": sum(1 for r in jud if r["direction"] == "correct"),
            "n_direction_incorrect": sum(1 for r in jud if r["direction"] == "incorrect"),
            "n_direction_unclear": sum(1 for r in jud if r["direction"] == "unclear"),
            "direction_correct_rate": round(
                sum(1 for r in jud if r["direction"] == "correct") / len(jud), 4) if jud else "",
            "p_landing_eligible": round(n_corr / len(eligj), 6) if eligj else "",
            "n_landing_eligible": len(elig),
            "n_comprehension_denominator": len(eligj),
            "landing_judge": lj, "n_judge": nj,
            "landing_regex_raw": lr, "n_regex": nr,
            "landing_regex_corrected": lc, "n_corrected": nc,
            "w3_direction_correct_rate": round(W3_P[cond], 4),
            "w11_direction_correct_rate": float(w11["p_landing_eligible"]),
            "comprehension_drop_vs_w3": (round(n_corr / len(eligj) - W3_P[cond], 4)
                                         if eligj else ""),
            "comprehension_drop_vs_w11": (round(n_corr / len(eligj)
                                                - float(w11["p_landing_eligible"]), 4)
                                          if eligj else ""),
            "median_output_tokens": int(np.median([r["n_tok"] for r in allr]))})
    return rows


def power_at(p_a, alt):
    """Nearest pre-frozen grid point on the primary pb_rule, PR-010 item 5."""
    best = None
    for r in csv.DictReader(open(POWER_FILE)):
        if r["pb_rule"] != "offset" or r["alt_world"] != alt or int(r["n_per_arm"]) != 150:
            continue
        d = abs(float(r["p_a"]) - p_a)
        if best is None or d < best[0]:
            best = (d, float(r["distinguishing_power"]), float(r["p_a"]))
    return best[1], best[2]


def main():
    data = load()
    cells = {(r["form"], r["arm"], r["group"]): r["rate"] for r in w3c.cells()}
    ns = {(r["form"], r["arm"], r["group"]): r["n"] for r in w3c.cells()}
    rows = arm_rows(data)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "w14_arms.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    idx = {r["arm"]: r for r in rows}
    a, b = idx["above_good"], idx["below_good"]

    vals = {}
    for cond in CONDS:
        recs = [r for r in data[cond]["recs"] if not r["truncated"]]
        vals[cond] = [r["judge"] for r in recs if r["judge"] is not None]
    gap, pb_, pa_ = lg.gap_stats(vals["below_good"], vals["above_good"], TAU, True)
    lo, hi = lg.bootstrap_ci(vals["below_good"], vals["above_good"], TAU, True)

    rng = np.random.default_rng(PRED_SEED)
    point, plo, phi = predict(FORM, a["p_landing_eligible"], b["p_landing_eligible"],
                              a["n_comprehension_denominator"],
                              b["n_comprehension_denominator"], cells, ns, rng)
    inside = plo <= gap <= phi
    drop_ok = a["comprehension_drop_vs_w3"] <= -D1_DROP
    pw11, grid_pa = power_at(a["p_landing_eligible"], "w11")
    pw3, _ = power_at(a["p_landing_eligible"], "w3")
    if not drop_ok:
        verdict = ("D3 (manipulation failed: p_a did not fall >=%.2f below W3's %.4f); "
                   "VOID for the dose-response question, and reported as such"
                   % (D1_DROP, W3_P["above_good"]))
    elif inside:
        verdict = "D1 (the mixture tracks bidirectionally; dose-response law [measured])"
    else:
        verdict = "D2 (cells not invariant to degradation; see w14_interaction.csv)"
    pred = [{"form": FORM, "tau": TAU, "basis": "judge/strict_gt",
             "p_a_achieved": a["p_landing_eligible"], "p_b_achieved": b["p_landing_eligible"],
             "p_a_w3": a["w3_direction_correct_rate"], "p_b_w3": b["w3_direction_correct_rate"],
             "p_a_w11": a["w11_direction_correct_rate"], "p_b_w11": b["w11_direction_correct_rate"],
             "comprehension_drop_above": a["comprehension_drop_vs_w3"],
             "comprehension_drop_below": b["comprehension_drop_vs_w3"],
             "n_comprehension_above": a["n_comprehension_denominator"],
             "n_comprehension_below": b["n_comprehension_denominator"],
             "landing_above": round(pa_, 4), "landing_below": round(pb_, 4),
             "gap_observed": round(gap, 6), "gap_ci_lo": round(lo, 6), "gap_ci_hi": round(hi, 6),
             "gap_pred": round(point, 6), "pred_lo": round(plo, 6), "pred_hi": round(phi, 6),
             "inside_interval": bool(inside), "d1_drop_met": bool(drop_ok),
             "power_vs_w11_level_alt": pw11, "power_vs_w3_level_alt": pw3,
             "power_grid_p_a": grid_pa, "verdict": verdict}]
    with open(OUT / "w14_prediction.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(pred[0].keys())); w.writeheader(); w.writerows(pred)

    # ---- the three-point dose-response table (PR-010 item 6, emitted regardless) -----
    dose = []
    w11p = {r["form"]: r for r in csv.DictReader(open(W11_PRED))}[FORM]
    w11a = {c: w11_row(c) for c in CONDS}
    points = [
        ("W3 natural", W3_P["above_good"], W3_P["below_good"], W3_N["above_good"],
         W3_N["below_good"], None),
        ("W11 clarified", float(w11a["above_good"]["p_landing_eligible"]),
         float(w11a["below_good"]["p_landing_eligible"]),
         int(w11a["above_good"]["n_comprehension_denominator"]),
         int(w11a["below_good"]["n_comprehension_denominator"]),
         (float(w11p["gap_observed"]), float(w11p["gap_ci_lo"]), float(w11p["gap_ci_hi"]))),
        ("W14 degraded", a["p_landing_eligible"], b["p_landing_eligible"],
         a["n_comprehension_denominator"], b["n_comprehension_denominator"],
         (gap, lo, hi)),
    ]
    for label, p_a, p_b, n_a, n_b, obs in points:
        r2 = np.random.default_rng(PRED_SEED)
        pt, l2, h2 = predict(FORM, p_a, p_b, n_a, n_b, cells, ns, r2)
        if obs is None:                       # W3: the mixture is an identity on its own data
            og = pt
            ol = oh = ""
        else:
            og, ol, oh = obs
        dose.append({"packet": label, "wording": {"W3 natural": "upstream, two positive "
                     "mapping sentences", "W11 clarified": "W3 + one explicit restatement",
                     "W14 degraded": "W3 with the two sentences replaced by a nested-negation "
                     "paraphrase"}[label],
                     "p_a": round(p_a, 4), "p_b": round(p_b, 4), "n_a": n_a, "n_b": n_b,
                     "gap_observed": round(og, 6),
                     "gap_ci_lo": (round(ol, 6) if ol != "" else ""),
                     "gap_ci_hi": (round(oh, 6) if oh != "" else ""),
                     "gap_pred": round(pt, 6), "pred_lo": round(l2, 6), "pred_hi": round(h2, 6),
                     "inside": ("identity" if obs is None else bool(l2 <= og <= h2)),
                     "residual_obs_minus_pred": round(og - pt, 6)})
    with open(OUT / "w14_dose_response.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(dose[0].keys())); w.writeheader(); w.writerows(dose)

    # ---- which cells moved (needed by D2, reported regardless) -----------------------
    inter = []
    sel = {}
    for grp, fn in (("corr", lambda d: d == "correct"), ("ncorr", lambda d: d != "correct")):
        for cond in CONDS:
            recs = [r for r in data[cond]["recs"] if not r["truncated"]
                    and r["judge"] is not None and r["direction"] is not None and fn(r["direction"])]
            v = [r["judge"] for r in recs]
            sel[(grp, cond)] = v
            inter.append({"form": FORM, "group": grp, "arm": cond, "kind": "cell_rate",
                          "n_w14": len(v),
                          "rate_w14": round(sum(x > TAU for x in v) / len(v), 6) if v else "",
                          "n_w3": ns[(FORM, cond, grp)], "rate_w3": cells[(FORM, cond, grp)],
                          "delta": round(sum(x > TAU for x in v) / len(v)
                                         - cells[(FORM, cond, grp)], 6) if v else "",
                          "ci_lo": "", "ci_hi": ""})
    for grp in ("corr", "ncorr"):
        bb, aa = sel[(grp, "below_good")], sel[(grp, "above_good")]
        if bb and aa:
            g, _, _ = lg.gap_stats(bb, aa, TAU, True)
            l3, h3 = lg.bootstrap_ci(bb, aa, TAU, True)
            w3g = cells[(FORM, "above_good", grp)] - cells[(FORM, "below_good", grp)]
            inter.append({"form": FORM, "group": grp, "arm": "both", "kind": "conditional_gap",
                          "n_w14": len(bb) + len(aa), "rate_w14": round(g, 6),
                          "n_w3": ns[(FORM, "above_good", grp)] + ns[(FORM, "below_good", grp)],
                          "rate_w3": round(w3g, 6), "delta": round(g - w3g, 6),
                          "ci_lo": round(l3, 6), "ci_hi": round(h3, 6)})
    with open(OUT / "w14_interaction.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(inter[0].keys())); w.writeheader(); w.writerows(inter)

    for r in rows: print(json.dumps(r))
    print(); print(json.dumps(pred[0], indent=2)); print()
    for r in dose: print(json.dumps(r))
    print()
    for r in inter: print(json.dumps(r))
    print("\nwrote w14_arms.csv w14_prediction.csv w14_dose_response.csv w14_interaction.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
