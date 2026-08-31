"""W15 analysis (PR-011 items 3-6): arms, the primary statistic, RULE C, and the T-row.

  python3 src/analyze_w15.py
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import extract_regex as ex  # noqa: E402
from replay_w4 import final_corrected_span, final_span, parsed_spans  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
TAU = 4500000000
OUT = ROOT / "analysis" / "out"
TRANS = ROOT / "runs" / "w15_transplant"
ARMS = ("SHAM", "SWAP", "SELF", "RAND")
N_BOOT = 10000                      # PR-011 item 4
SEED_BOOT = 15200


# ---------------------------------------------------------------- outcomes

def landing_toward_B(text, b_phat, basis, numcache):
    """Did the reconstructed trace land on B's side? basis in {corr, raw, judge}."""
    if basis == "corr":
        fc = final_corrected_span(text or "", TAU)
        v = fc[0] if fc else None
    elif basis == "raw":
        fs = final_span(text or "")
        v = fs[0] if fs else None
    else:
        v = numcache.get(text or "")
    if v is None:
        return None
    return int((v > TAU) == (b_phat == +1))


def verbalized_toward_B(rec, b_phat):
    """The direction judge on the reconstructed trace. above_good arm: correct <-> +1.
    `unclear` and a missing verdict count as NOT flipped (frozen here; the complete-case
    rate is reported alongside)."""
    d = (rec or {}).get("direction")
    if d not in ("correct", "incorrect"):
        return 0, None
    j = +1 if d == "correct" else -1
    return int(j == b_phat), int(j == b_phat)


def decoded_toward_B(row, theta, sign, tok):
    """The frozen W5 DIRECTION as a 1-D probe at the continuation's est points (JC-1)."""
    proj = row["proj_decode"]
    ids = row.get("continuation_token_ids") or []
    txt = row["continuation_text"]
    if not proj or not ids:
        return None
    enc = tok(txt, add_special_tokens=False, return_offsets_mapping=True)
    offs = [tuple(o) for o in enc["offset_mapping"]]
    if len(enc["input_ids"]) != len(ids):
        offs = offs[:len(ids)]
    picks = []
    for v, s, e, t in parsed_spans(txt):
        idx = [i for i, (a, b) in enumerate(offs) if a < e and b > s and b > a]
        if idx and idx[-1] < len(proj):
            picks.append(proj[idx[-1]])
    if not picks:
        return None
    m = float(np.mean(picks))
    ph = +1 if sign * (m - theta) > 0 else -1
    return int(ph == row["B_phat"])


# ---------------------------------------------------------------- bootstrap

def boot(dsets, n, seed=SEED_BOOT, nboot=N_BOOT):
    """One shared pair-resample index for every statistic in `dsets` (dict name->array)."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(nboot, n))
    return {k: np.asarray(v, dtype=float)[idx].mean(1) for k, v in dsets.items()}


def ci(v):
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def summarise(name, point, bs):
    lo, hi = ci(bs)
    return {"statistic": name, "value": round(point, 4), "ci_lo": round(lo, 4),
            "ci_hi": round(hi, 4), "excludes_zero": int(lo > 0 or hi < 0),
            "strictly_positive": int(lo > 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-decoded", action="store_true")
    a = ap.parse_args()
    numcache = json.loads((OUT / "w15_extractions.json").read_text()).get(MODEL, {}) \
        if (OUT / "w15_extractions.json").exists() else {}
    dirc = json.loads((OUT / "w15_direction_cache.json").read_text()) \
        if (OUT / "w15_direction_cache.json").exists() else {}
    prof = json.loads((OUT / "w15_profiles.json").read_text())
    mp, mm = np.mean(prof["mean"]["1"]), np.mean(prof["mean"]["-1"])
    theta, sign = (mp + mm) / 2.0, (1.0 if mp > mm else -1.0)

    tok = None
    if not a.no_decoded:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODEL)

    arm_rows, prim_rows, rowdump = [], [], []
    for path in sorted(TRANS.glob("*.json")):
        d = json.loads(path.read_text())
        direction = d["direction"]
        by = {}
        for r in d["rows"]:
            by.setdefault(r["arm"], {})[r["pair_index"]] = r
        n = d["n_pairs"]
        Y = {b: {} for b in ("corr", "raw", "judge")}
        V, Vc, D = {}, {}, {}
        for arm in ARMS:
            for b in Y:
                Y[b][arm] = []
            V[arm], Vc[arm], D[arm] = [], [], []
            for pi in range(n):
                r = by[arm][pi]
                for b in Y:
                    Y[b][arm].append(landing_toward_B(r["visible_answer"], r["B_phat"],
                                                      b, numcache))
                key = "%s|B|%s_%s|%d" % (MODEL, direction, arm, pi)
                v, vc = verbalized_toward_B(dirc.get(key), r["B_phat"])
                V[arm].append(v); Vc[arm].append(vc)
                D[arm].append(None if tok is None
                              else decoded_toward_B(r, theta, sign, tok))
            en = [x["edit_norm_mean"] for x in by[arm].values()
                  if x["edit_norm_mean"] is not None]
            arm_rows.append({
                "direction": direction, "arm": arm, "n": n,
                "P_toward_B_regex_corr": round(np.mean([y for y in Y["corr"][arm]
                                                        if y is not None]), 4),
                "P_toward_B_regex_raw": round(np.mean([y for y in Y["raw"][arm]
                                                       if y is not None]), 4),
                "P_toward_B_judge": (round(np.mean([y for y in Y["judge"][arm]
                                                    if y is not None]), 4)
                                     if any(y is not None for y in Y["judge"][arm]) else ""),
                "n_unparsed_corr": sum(1 for y in Y["corr"][arm] if y is None),
                "verbalized_toward_B": round(np.mean(V[arm]), 4),
                "verbalized_completecase": (round(np.mean([x for x in Vc[arm]
                                                           if x is not None]), 4)
                                            if any(x is not None for x in Vc[arm]) else ""),
                "n_verdict_unclear_or_missing": sum(1 for x in Vc[arm] if x is None),
                "decoded_toward_B": (round(np.mean([x for x in D[arm] if x is not None]), 4)
                                     if any(x is not None for x in D[arm]) else ""),
                "n_decoded_estimable": sum(1 for x in D[arm] if x is not None),
                "coherence": round(1.0 - np.mean([x["degenerate"] for x in by[arm].values()]), 4),
                "n_truncated": sum(x["truncated"] for x in by[arm].values()),
                "median_continuation_tokens": int(statistics.median(
                    [x["n_continuation_tokens"] for x in by[arm].values()])),
                "median_ngram4": round(statistics.median(
                    [x["ngram4_ratio"] for x in by[arm].values()]), 4),
                "edit_norm_mean": round(float(np.mean(en)), 4) if en else "",
                "edit_norm_max": (round(max(x["edit_norm_max"] for x in by[arm].values()
                                            if x["edit_norm_max"] is not None), 4)
                                  if en else ""),
            })
        # ---- the primary statistic, rule C ----------------------------------
        for label, src, fill in (("landing_regex_corr", Y["corr"], 0),
                                 ("landing_judge", Y["judge"], 0),
                                 ("verbalized", V, None),
                                 ("decoded", D, None)):
            get = (lambda arm: [fill if x is None else x for x in src[arm]]) if fill is not None \
                else (lambda arm: src[arm])
            try:
                cols = {arm: np.array([0 if x is None else x for x in get(arm)], dtype=float)
                        for arm in ARMS}
            except Exception:
                continue
            if all(np.all(cols[arm] == 0) for arm in ARMS):
                continue
            dsets = {"swap": cols["SWAP"] - cols["SHAM"],
                     "self": cols["SELF"] - cols["SHAM"],
                     "rand": cols["RAND"] - cols["SHAM"]}
            dsets["swap_minus_rand"] = dsets["swap"] - dsets["rand"]
            dsets["swap_minus_self"] = dsets["swap"] - dsets["self"]
            bs = boot(dsets, n)
            for k in ("swap", "self", "rand", "swap_minus_rand", "swap_minus_self"):
                s = summarise(k, float(np.mean(dsets[k])), bs[k])
                s.update({"direction": direction, "outcome": label, "n_pairs": n})
                prim_rows.append(s)
        for arm in ARMS:
            for pi in range(n):
                r = by[arm][pi]
                rowdump.append({"direction": direction, "pair_index": pi, "arm": arm,
                                "A_i": r["A_i"], "B_i": r["B_i"], "B_phat": r["B_phat"],
                                "toward_B_corr": Y["corr"][arm][pi],
                                "toward_B_judge": Y["judge"][arm][pi],
                                "verbalized": V[arm][pi], "decoded": D[arm][pi],
                                "n_continuation_tokens": r["n_continuation_tokens"],
                                "edit_norm_mean": r["edit_norm_mean"]})

    with open(OUT / "w15_arms.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(arm_rows[0].keys()))
        w.writeheader(); w.writerows(arm_rows)
    order = ["direction", "outcome", "n_pairs", "statistic", "value", "ci_lo", "ci_hi",
             "excludes_zero", "strictly_positive"]
    with open(OUT / "w15_primary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=order)
        w.writeheader()
        for r in prim_rows:
            w.writerow({k: r[k] for k in order})
    with open(OUT / "w15_rows.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rowdump[0].keys()))
        w.writeheader(); w.writerows(rowdump)

    # ---- the frozen T-row (PR-011 item 6) --------------------------------------
    def get(direction, outcome, stat):
        for r in prim_rows:
            if (r["direction"], r["outcome"], r["statistic"]) == (direction, outcome, stat):
                return r
        return None

    verdicts = {}
    for direction in sorted({r["direction"] for r in prim_rows}):
        ruleC_land = all((get(direction, "landing_regex_corr", s) or {}).get(
            "strictly_positive") for s in ("swap_minus_rand", "swap_minus_self"))
        ruleC_verb = all((get(direction, "verbalized", s) or {}).get(
            "strictly_positive") for s in ("swap_minus_rand", "swap_minus_self"))
        rand = get(direction, "landing_regex_corr", "rand") or {}
        row = ("T1" if ruleC_land else "T2" if ruleC_verb else
               "T4" if rand.get("excludes_zero") else "T3")
        verdicts[direction] = {"row": row, "ruleC_landing": int(bool(ruleC_land)),
                               "ruleC_verbalized": int(bool(ruleC_verb)),
                               "rand_moves": int(rand.get("excludes_zero", 0)),
                               "delta_swap": (get(direction, "landing_regex_corr", "swap")
                                              or {}).get("value"),
                               "delta_rand": rand.get("value"),
                               "delta_self": (get(direction, "landing_regex_corr", "self")
                                              or {}).get("value")}
    (OUT / "w15_verdict.json").write_text(json.dumps(
        {"theta": theta, "sign": sign, "class_mean_proj": {"1": mp, "-1": mm},
         "verdicts": verdicts}, indent=2))

    print("%-8s %-6s %-18s %8s %18s %s" % ("dir", "arm", "P(toward B) corr", "verb",
                                           "decoded", "coh"))
    for r in arm_rows:
        print("%-8s %-6s %18.4f %8.4f %18s %.3f"
              % (r["direction"], r["arm"], r["P_toward_B_regex_corr"],
                 r["verbalized_toward_B"], r["decoded_toward_B"], r["coherence"]))
    print()
    for r in prim_rows:
        if r["outcome"] == "landing_regex_corr":
            print("%-8s %-16s %-18s %+.4f [%+.4f, %+.4f] %s"
                  % (r["direction"], r["outcome"], r["statistic"], r["value"],
                     r["ci_lo"], r["ci_hi"], "EXCLUDES 0" if r["excludes_zero"] else ""))
    print("\nVERDICT", json.dumps(verdicts, indent=1))
    print("wrote w15_arms.csv w15_primary.csv w15_rows.csv w15_verdict.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
