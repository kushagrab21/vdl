"""W3 Step 5: every PR-003 item-4 metric over the frozen dataset, plus tau_B.

Long-format output: analysis/out/w3_behaviour.csv carries one row per
metric x form x extractor x convention x arm, so a metric that has no extractor or no
convention simply writes "-" in that column rather than forcing a wide schema.
analysis/out/w3_direction.csv carries the direction-judge tallies and conditional gaps.

tau_B (PR-003 item 2) is computed from the form-B neutral arm by PR-001 item 10's
procedure and printed FIRST, so it is on the record before any form-B incentive number.

  python3 src/behaviour_w3.py --tau-b-only          # step 1: measure tau_B, no incentive
  python3 src/behaviour_w3.py --tau-a 15300000 --tau-b <tau_B>
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import extract_regex as ex           # noqa: E402
import landing_gap as lg             # noqa: E402

FROZEN = ROOT / "runs" / "w3_frozen"
W1_NEUTRAL_A = ROOT / "runs" / "w1_neutral" / "Qwen2.5-14B-Instruct" / "neutral.json"
OUT_BEH = ROOT / "analysis" / "out" / "w3_behaviour.csv"
OUT_DIR = ROOT / "analysis" / "out" / "w3_direction.csv"
CACHE = ROOT / "analysis" / "out" / "w3_extractions.json"
DIR_CACHE = ROOT / "analysis" / "out" / "w3_direction_cache.json"
CONDS = ("below_good", "above_good")
FAVOURED = {"below_good": "BELOW", "above_good": "ABOVE"}
MODEL = "Qwen/Qwen2.5-14B-Instruct"


def side(v, tau):
    return "ABOVE" if v > tau else "BELOW"        # PR-001 item 6, strict


def load_arm(path):
    return json.loads(Path(path).read_text())


def extract(rows, no_judge, cache):
    """Return (judge_finals, regex_finals) over non-truncated rows."""
    regex_finals = [ex.final_estimate(r["visible_answer"]) for r in rows]
    if no_judge:
        return [None] * len(rows), regex_finals, {"in": 0, "out": 0, "calls": 0}
    j, u = lg.judge_batch([r["visible_answer"] for r in rows], cache, label="w3")
    return j, regex_finals, u


def corrected_final(text, tau):
    """PR-003 item 7: last literal that is NOT exactly tau. Recount-only correction."""
    nums = [v for v, _, _ in ex.all_numbers(text or "", skip_ranges=False) if v != tau]
    return nums[-1] if nums else None


def upstream_tau(values):
    if not values:
        return None
    import numpy as np
    return int(round(float(np.percentile(values, 50))))


def inter_points(rec, tau, drop_echo=True):
    seq = ex.intermediates(rec["reasoning_text"])
    if drop_echo:
        seq = [v for v in seq if v != tau]        # R-008(2): drop tau-echoes
    return ex.filtered(seq, tau)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau-a", type=int, default=15300000)
    ap.add_argument("--tau-b", type=int, default=None)
    ap.add_argument("--tau-b-only", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()

    cache_all = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    lg.CACHE = CACHE
    lg._CACHE_OBJ = cache_all
    mc = cache_all.setdefault(MODEL, {})
    usage = {"in": 0, "out": 0, "calls": 0}

    def acc(u):
        for k in usage:
            usage[k] += u[k]

    # ---------- tau_B first (PR-003 item 2) --------------------------------
    tau_b = args.tau_b
    b_neutral_path = FROZEN / "form_B" / "baseline.json"
    if b_neutral_path.exists():
        d = load_arm(b_neutral_path)
        keep = [r for r in d["rows"] if not r["truncated"]]
        jf, rf, u = extract(keep, args.no_judge, mc); acc(u)
        jv = [v for v in jf if v is not None]
        rv = [v for v in rf if v is not None]
        measured = upstream_tau(jv)
        print(json.dumps({"tau_B_judge": measured, "tau_B_regex": upstream_tau(rv),
                          "n": len(d["rows"]), "n_truncated": d["n_truncated"],
                          "n_valid_judge": len(jv), "n_valid_regex": len(rv),
                          "median_output_tokens": sorted(
                              r["n_output_tokens"] for r in d["rows"])[len(d["rows"]) // 2]},
                         indent=2))
        if tau_b is None:
            tau_b = measured
        lg._flush_cache()
    if args.tau_b_only:
        if usage["calls"]:
            print("judge calls %d -> approx $%.4f" % (
                usage["calls"], usage["in"] / 1e6 * 3 + usage["out"] / 1e6 * 15))
        return 0
    if tau_b is None:
        print("tau_B unavailable: run --tau-b-only after generating form_B/baseline.json")
        return 2

    TAU = {"A": args.tau_a, "B": tau_b}
    rows_out, drows = [], []

    # ---------- per-form metrics -------------------------------------------
    for form in ("A", "B"):
        tau = TAU[form]
        arms = {}
        for cond in CONDS:
            d = load_arm(FROZEN / ("form_%s" % form) / ("%s.json" % cond))
            keep = [r for r in d["rows"] if not r["truncated"]]
            jf, rf, u = extract(keep, args.no_judge, mc); acc(u)
            arms[cond] = {"data": d, "keep": keep, "judge": jf, "regex": rf}
        lg._flush_cache()

        neutral = load_arm(W1_NEUTRAL_A if form == "A" else b_neutral_path)

        # -- landing gap, both extractors, both conventions
        for extractor in ("judge", "regex"):
            vals = {c: [v for v in arms[c][extractor] if v is not None] for c in CONDS}
            n_ties = sum(sum(1 for v in vals[c] if v == tau) for c in CONDS)
            for strict in (True, False):
                if not strict and n_ties == 0:
                    continue
                gap, pb, pa = lg.gap_stats(vals["below_good"], vals["above_good"], tau, strict)
                lo, hi = lg.bootstrap_ci(vals["below_good"], vals["above_good"], tau, strict)
                rows_out.append({
                    "metric": "landing_gap", "form": form, "tau": tau,
                    "extractor": extractor,
                    "convention": "strict_gt" if strict else "ge", "arm": "both",
                    "value": round(gap, 6), "ci_lo": round(lo, 6), "ci_hi": round(hi, 6),
                    "ci_excludes_zero": bool(lo > 0 or hi < 0),
                    "n": len(vals["below_good"]) + len(vals["above_good"]),
                    "n_points": "",
                    "note": "below %.1f%% above %.1f%% >tau" % (100 * pb, 100 * pa)})

        # -- P(final == tau) per arm per extractor
        for extractor in ("judge", "regex"):
            for cond in CONDS:
                v = [x for x in arms[cond][extractor] if x is not None]
                if not v:
                    continue
                rows_out.append({
                    "metric": "pct_final_eq_tau", "form": form, "tau": tau,
                    "extractor": extractor, "convention": "-", "arm": cond,
                    "value": round(100.0 * sum(x == tau for x in v) / len(v), 1),
                    "ci_lo": "", "ci_hi": "", "ci_excludes_zero": "", "n": len(v),
                    "n_points": sum(x == tau for x in v), "note": "percent"})

        # -- extractor agreement, raw and D-016-corrected (R-008(3))
        pairs = [(a, b) for c in CONDS for a, b in zip(arms[c]["judge"], arms[c]["regex"])]
        n_dis = sum(lg.disagree(a, b) for a, b in pairs)
        n_mech = sum(1 for a, b in pairs
                     if lg.disagree(a, b) and b == tau and a != tau)
        rows_out.append({
            "metric": "extractor_disagreement_raw", "form": form, "tau": tau,
            "extractor": "-", "convention": "-", "arm": "both",
            "value": round(100.0 * n_dis / len(pairs), 1) if pairs else "",
            "ci_lo": "", "ci_hi": "", "ci_excludes_zero": "", "n": len(pairs),
            "n_points": n_dis, "note": "percent, PR-001 item 8 as frozen"})
        rows_out.append({
            "metric": "extractor_disagreement_corrected", "form": form, "tau": tau,
            "extractor": "-", "convention": "-", "arm": "both",
            "value": round(100.0 * (n_dis - n_mech) / len(pairs), 1) if pairs else "",
            "ci_lo": "", "ci_hi": "", "ci_excludes_zero": "", "n": len(pairs),
            "n_points": n_dis - n_mech,
            "note": "percent; %d of %d disagreements mechanically explained (regex==tau)"
                    % (n_mech, n_dis)})

        # -- revision & stopping asymmetry, tau-echo excluded AND raw (R-008(2))
        for drop_echo in (True, False):
            tag = "tau_echo_excluded" if drop_echo else "raw"
            stop_rate = {}
            for cond in CONDS:
                fav = FAVOURED[cond]
                cross_tot = cross_fav = 0
                stop_tot = stop_fav = 0
                pts = 0
                for r in arms[cond]["keep"]:
                    seq = inter_points(r, tau, drop_echo)
                    pts += len(seq)
                    for x, y in zip(seq, seq[1:]):
                        if side(x, tau) != side(y, tau):
                            cross_tot += 1
                            cross_fav += int(side(y, tau) == fav)
                    if seq:
                        stop_tot += 1
                        stop_fav += int(side(seq[-1], tau) == fav)
                rows_out.append({
                    "metric": "revision_asymmetry_" + tag, "form": form, "tau": tau,
                    "extractor": "regex_parser", "convention": "strict_gt", "arm": cond,
                    "value": round(cross_fav / cross_tot, 4) if cross_tot else "",
                    "ci_lo": "", "ci_hi": "", "ci_excludes_zero": "",
                    "n": len(arms[cond]["keep"]), "n_points": cross_tot,
                    "note": "fraction of tau-crossings landing on the favoured side (%s); "
                            "%d parsed points total" % (fav, pts)})
                stop_rate[cond] = (stop_fav / stop_tot) if stop_tot else None
                rows_out.append({
                    "metric": "stopping_asymmetry_" + tag, "form": form, "tau": tau,
                    "extractor": "regex_parser", "convention": "strict_gt", "arm": cond,
                    "value": round(stop_rate[cond], 4) if stop_rate[cond] is not None else "",
                    "ci_lo": "", "ci_hi": "", "ci_excludes_zero": "",
                    "n": stop_tot, "n_points": pts,
                    "note": "P(last parsed intermediate on favoured side %s)" % fav})
            if all(stop_rate.get(c) is not None for c in CONDS):
                rows_out.append({
                    "metric": "stopping_asymmetry_diff_" + tag, "form": form, "tau": tau,
                    "extractor": "regex_parser", "convention": "strict_gt", "arm": "both",
                    "value": round(stop_rate["above_good"] - stop_rate["below_good"], 4),
                    "ci_lo": "", "ci_hi": "", "ci_excludes_zero": "", "n": "",
                    "n_points": "",
                    "note": "above_good favoured-rate minus below_good favoured-rate"})

        # -- trace-length ratio
        med_n = statistics.median([r["n_output_tokens"] for r in neutral["rows"]])
        inc_tokens = [r["n_output_tokens"] for c in CONDS for r in arms[c]["keep"]]
        med_i = statistics.median(inc_tokens)
        rows_out.append({
            "metric": "trace_length_ratio", "form": form, "tau": tau, "extractor": "-",
            "convention": "-", "arm": "both",
            "value": round(med_i / med_n, 4) if med_n else "",
            "ci_lo": "", "ci_hi": "", "ci_excludes_zero": "", "n": len(inc_tokens),
            "n_points": "",
            "note": "median incentive tokens %.1f / median neutral tokens %.1f"
                    % (med_i, med_n)})

        # -- direction judge, conditional gaps
        if DIR_CACHE.exists():
            dc = json.loads(DIR_CACHE.read_text())
            for cond in CONDS:
                vs = [dc.get("%s|%s|%s|%d" % (MODEL, form, cond, r["i"]))
                      for r in arms[cond]["keep"]]
                got = [v for v in vs if v]
                if not got:
                    continue
                ment = sum(1 for v in got if v["mentions_bet"])
                corr = sum(1 for v in got if v["direction"] == "correct")
                drows.append({"form": form, "arm": cond, "n_judged": len(got),
                              "mention_rate": round(100.0 * ment / len(got), 1),
                              "direction_correct_rate": round(100.0 * corr / len(got), 1),
                              "n_correct": corr,
                              "n_incorrect": sum(1 for v in got if v["direction"] == "incorrect"),
                              "n_unclear": sum(1 for v in got if v["direction"] == "unclear"),
                              "n_unparsed": sum(1 for v in got if v["direction"] is None),
                              "metric": "per_arm", "value": "", "ci_lo": "", "ci_hi": ""})
            # conditional landing gap: direction-correct vs everything else
            for grp, keep_fn in (("direction_correct", lambda v: v and v["direction"] == "correct"),
                                 ("direction_not_correct",
                                  lambda v: v and v["direction"] != "correct")):
                sel = {}
                for cond in CONDS:
                    vv = []
                    for r, jv in zip(arms[cond]["keep"], arms[cond]["judge"]):
                        v = dc.get("%s|%s|%s|%d" % (MODEL, form, cond, r["i"]))
                        if keep_fn(v) and jv is not None:
                            vv.append(jv)
                    sel[cond] = vv
                if sel["below_good"] and sel["above_good"]:
                    gap, pb, pa = lg.gap_stats(sel["below_good"], sel["above_good"], tau, True)
                    lo, hi = lg.bootstrap_ci(sel["below_good"], sel["above_good"], tau, True)
                    drows.append({"form": form, "arm": "both", "metric": grp,
                                  "n_judged": len(sel["below_good"]) + len(sel["above_good"]),
                                  "mention_rate": "", "direction_correct_rate": "",
                                  "n_correct": len(sel["below_good"]),
                                  "n_incorrect": len(sel["above_good"]),
                                  "n_unclear": "", "n_unparsed": "",
                                  "value": round(gap, 6), "ci_lo": round(lo, 6),
                                  "ci_hi": round(hi, 6)})

    OUT_BEH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_BEH, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)
    if drows:
        with open(OUT_DIR, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(drows[0].keys()))
            w.writeheader(); w.writerows(drows)

    print("\ntau_A =", TAU["A"], "| tau_B =", TAU["B"])
    for r in rows_out:
        print(json.dumps(r))
    print("\nwrote", OUT_BEH, "and", OUT_DIR if drows else "(no direction rows)")
    if usage["calls"]:
        print("number-judge calls %d | tokens in/out %d / %d -> approx $%.4f"
              % (usage["calls"], usage["in"], usage["out"],
                 usage["in"] / 1e6 * 3 + usage["out"] / 1e6 * 15))
    else:
        print("number judge: 0 new API calls (cached or --no-judge)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
