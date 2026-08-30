"""W11 analysis: the arm table, the frozen prediction, and PR-007 item 6's verdict.

Offline — reads committed run files and the two W11 judge caches, calls no API.

  python3 src/analyze_w11.py
emits: analysis/out/w11_arms.csv, analysis/out/w11_prediction.csv,
       analysis/out/w11_interaction.csv
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

MODEL = "Qwen/Qwen2.5-14B-Instruct"
TAU = {"A": 15300000, "B": 4500000000}
RUN = ROOT / "runs" / "w11_clarified"
NUM_CACHE = ROOT / "analysis" / "out" / "w11_extractions.json"
DIR_CACHE = ROOT / "analysis" / "out" / "w11_direction_cache.json"
OUT_ARMS = ROOT / "analysis" / "out" / "w11_arms.csv"
OUT_PRED = ROOT / "analysis" / "out" / "w11_prediction.csv"
OUT_INTER = ROOT / "analysis" / "out" / "w11_interaction.csv"
CONDS = ("below_good", "above_good")

N_PRED_DRAWS = 100000               # PR-007 item 4
PRED_SEED = 11007                   # PR-007 item 4
W3_P = {("A", "above_good"): 80 / 149, ("A", "below_good"): 129 / 150,
        ("B", "above_good"): 82 / 150, ("B", "below_good"): 121 / 150}
C1_LIFT = 0.15                      # PR-007 item 6
# PR-007 item 5: form A's C1/C2 verdict is declared NOT RUN before the data.
TEST_FORMS = ("B",)
POWER = {"A": 0.486, "B": 0.851}


def corrected_final(text, tau):
    """PR-003 item 7 / D-016: last literal that is not exactly tau."""
    nums = [v for v, _, _ in ex.all_numbers(text or "", skip_ranges=False) if v != tau]
    return nums[-1] if nums else None


def load():
    num = json.loads(NUM_CACHE.read_text())[MODEL]
    dirc = json.loads(DIR_CACHE.read_text())
    out = {}
    for form in ("A", "B"):
        for cond in CONDS:
            d = json.loads((RUN / ("form_%s" % form) / ("%s.json" % cond)).read_text())
            recs = []
            for r in d["rows"]:
                v = dirc.get("%s|%s|%s|%d" % (MODEL, form, cond, r["i"]), {})
                recs.append({
                    "i": r["i"], "seed": r["seed"], "truncated": r["truncated"],
                    "n_tok": r["n_output_tokens"], "text": r["visible_answer"],
                    "judge": num.get(r["visible_answer"] or ""),
                    "regex": ex.final_estimate(r["visible_answer"]),
                    "corr": corrected_final(r["visible_answer"], TAU[form]),
                    "direction": v.get("direction"), "mentions": v.get("mentions_bet")})
            out[(form, cond)] = {"meta": d, "recs": recs}
    return out


def arm_rows(data):
    rows = []
    for form in ("A", "B"):
        tau = TAU[form]
        for cond in CONDS:
            recs = [r for r in data[(form, cond)]["recs"] if not r["truncated"]]
            allr = data[(form, cond)]["recs"]
            elig = [r for r in recs if r["judge"] is not None]
            jud = [r for r in recs if r["direction"] is not None]
            def rate(key, sel):
                v = [r[key] for r in sel if r[key] is not None]
                return (round(sum(x > tau for x in v) / len(v), 4), len(v)) if v else ("", 0)
            lj, nj = rate("judge", recs)
            lr, nr = rate("regex", recs)
            lc, nc = rate("corr", recs)
            # D-039: the direction judge did not complete. Comprehension is measured over
            # traces that are BOTH judged and landing-eligible; that set is the denominator.
            eligj = [r for r in elig if r["direction"] is not None]
            n_corr = sum(1 for r in eligj if r["direction"] == "correct")
            rows.append({
                "form": form, "arm": cond, "tau": tau, "n": len(allr),
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
                "w3_direction_correct_rate": round(W3_P[(form, cond)], 4),
                "comprehension_lift": (round(n_corr / len(eligj) - W3_P[(form, cond)], 4)
                                       if eligj else ""),
                "median_output_tokens": int(np.median([r["n_tok"] for r in allr]))})
    return rows


def predict(form, p_a, p_b, n_a, n_b, cells, ns, rng):
    """PR-007 item 4: gap_pred and its interval, W3 cells FIXED, binomial error in both."""
    def draw(arm, grp):
        return rng.binomial(ns[(form, arm, grp)], cells[(form, arm, grp)],
                            N_PRED_DRAWS) / ns[(form, arm, grp)]
    d_ac, d_an = draw("above_good", "corr"), draw("above_good", "ncorr")
    d_bc, d_bn = draw("below_good", "corr"), draw("below_good", "ncorr")
    pa = rng.binomial(n_a, p_a, N_PRED_DRAWS) / n_a
    pb = rng.binomial(n_b, p_b, N_PRED_DRAWS) / n_b
    g = (pa * d_ac + (1 - pa) * d_an) - (pb * d_bc + (1 - pb) * d_bn)
    point = (p_a * cells[(form, "above_good", "corr")]
             + (1 - p_a) * cells[(form, "above_good", "ncorr")]
             - p_b * cells[(form, "below_good", "corr")]
             - (1 - p_b) * cells[(form, "below_good", "ncorr")])
    return point, float(np.quantile(g, 0.025)), float(np.quantile(g, 0.975))


def main():
    data = load()
    cells = {(r["form"], r["arm"], r["group"]): r["rate"] for r in w3c.cells()}
    ns = {(r["form"], r["arm"], r["group"]): r["n"] for r in w3c.cells()}
    rows = arm_rows(data)
    OUT_ARMS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_ARMS, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    idx = {(r["form"], r["arm"]): r for r in rows}

    rng = np.random.default_rng(PRED_SEED)
    preds = []
    for form in ("A", "B"):
        tau = TAU[form]
        a, b = idx[(form, "above_good")], idx[(form, "below_good")]
        vals = {}
        for cond in CONDS:
            recs = [r for r in data[(form, cond)]["recs"] if not r["truncated"]]
            vals[cond] = [r["judge"] for r in recs if r["judge"] is not None]
        gap, pb_, pa_ = lg.gap_stats(vals["below_good"], vals["above_good"], tau, True)
        lo, hi = lg.bootstrap_ci(vals["below_good"], vals["above_good"], tau, True)
        if a["p_landing_eligible"] == "" or b["p_landing_eligible"] == "":
            point = plo = phi = float("nan")
        else:
            point, plo, phi = predict(form, a["p_landing_eligible"], b["p_landing_eligible"],
                                      a["n_comprehension_denominator"],
                                      b["n_comprehension_denominator"], cells, ns, rng)
        measured = (a["comprehension_lift"] != "" and b["comprehension_lift"] != "")
        lift_ok = measured and (a["comprehension_lift"] >= C1_LIFT)
        inside = (plo <= gap <= phi) if measured else None
        if not measured:
            verdict = ("BLOCKED — direction judge incomplete for this form (D-039); "
                       "comprehension unmeasured, so C1/C2/C3 cannot be evaluated")
        elif not lift_ok:
            verdict = "C3 (manipulation failed; void for the mixture question)"
        elif form not in TEST_FORMS:
            verdict = "NOT RUN (PR-007 item 5) — descriptive: %s" % ("inside" if inside else "outside")
        else:
            verdict = "C1 (mixture survives)" if inside else "C2 (cells moved; mixture incomplete)"
        preds.append({
            "form": form, "tau": tau, "basis": "judge/strict_gt",
            "p_a_achieved": a["p_landing_eligible"], "p_b_achieved": b["p_landing_eligible"],
            "p_a_w3": a["w3_direction_correct_rate"], "p_b_w3": b["w3_direction_correct_rate"],
            "comprehension_lift_above": a["comprehension_lift"],
            "comprehension_lift_below": b["comprehension_lift"],
            "n_comprehension_above": a["n_comprehension_denominator"],
            "n_comprehension_below": b["n_comprehension_denominator"],
            "landing_above": round(pa_, 4), "landing_below": round(pb_, 4),
            "gap_observed": round(gap, 6), "gap_ci_lo": round(lo, 6), "gap_ci_hi": round(hi, 6),
            "gap_pred": round(point, 6), "pred_lo": round(plo, 6), "pred_hi": round(phi, 6),
            "inside_interval": ("" if inside is None else bool(inside)),
            "c1_lift_met": bool(lift_ok),
            "distinguishing_power": POWER[form], "verdict": verdict})
    with open(OUT_PRED, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(preds[0].keys())); w.writeheader(); w.writerows(preds)

    # ---- secondary, descriptive: did the cells themselves move? -------------
    inter = []
    for form in ("A", "B"):
        tau = TAU[form]
        sel = {}
        for grp, fn in (("corr", lambda d: d == "correct"), ("ncorr", lambda d: d != "correct")):
            for cond in CONDS:
                recs = [r for r in data[(form, cond)]["recs"]
                        if not r["truncated"] and r["judge"] is not None
                        and r["direction"] is not None and fn(r["direction"])]
                v = [r["judge"] for r in recs]
                sel[(grp, cond)] = v
                inter.append({"form": form, "group": grp, "arm": cond, "kind": "cell_rate",
                              "n_w11": len(v),
                              "rate_w11": round(sum(x > tau for x in v) / len(v), 6) if v else "",
                              "n_w3": ns[(form, cond, grp)], "rate_w3": cells[(form, cond, grp)],
                              "delta": round(sum(x > tau for x in v) / len(v)
                                             - cells[(form, cond, grp)], 6) if v else "",
                              "ci_lo": "", "ci_hi": ""})
        for grp in ("corr", "ncorr"):
            bb, aa = sel[(grp, "below_good")], sel[(grp, "above_good")]
            if bb and aa:
                g, _, _ = lg.gap_stats(bb, aa, tau, True)
                lo, hi = lg.bootstrap_ci(bb, aa, tau, True)
                w3g = cells[(form, "above_good", grp)] - cells[(form, "below_good", grp)]
                inter.append({"form": form, "group": grp, "arm": "both",
                              "kind": "conditional_gap", "n_w11": len(bb) + len(aa),
                              "rate_w11": round(g, 6),
                              "n_w3": ns[(form, "above_good", grp)] + ns[(form, "below_good", grp)],
                              "rate_w3": round(w3g, 6), "delta": round(g - w3g, 6),
                              "ci_lo": round(lo, 6), "ci_hi": round(hi, 6)})
    with open(OUT_INTER, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(inter[0].keys())); w.writeheader(); w.writerows(inter)

    for r in rows: print(json.dumps(r))
    print()
    for r in preds: print(json.dumps(r, indent=2))
    print()
    for r in inter: print(json.dumps(r))
    print("\nwrote", OUT_ARMS, OUT_PRED, OUT_INTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
