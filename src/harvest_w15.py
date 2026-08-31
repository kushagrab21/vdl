"""W15 Step 3: the pair harvest — regex screening, cut points, judge nomination, pairing.

PR-011 item 1. Free instruments only until the very last step, which writes the list of
candidates the direction judge is allowed to be spent on.

  python3 src/harvest_w15.py --screen           # regex labels + cut points + nomination
  python3 src/harvest_w15.py --pair             # after judging: confirm, pair, write outputs
"""

import argparse
import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import extract_regex as ex  # noqa: E402
from replay_w4 import belief_span, span_tokens, final_corrected_span  # noqa: E402
from w14_dircheck import believed  # noqa: E402  the V-025 screening instrument, unmodified

MODEL = "Qwen/Qwen2.5-14B-Instruct"
TAU = 4500000000
CUT_BACKOFF = 25                  # PR-011 item 1 / W12's rule, kept
NOMINATE_PER_CLASS = 60           # JC-2: sized to yield 40 pairs at W14's 0.90-0.96 agreement
SEED_NOMINATE = 15061
SEED_PAIR = 15060                 # PR-011 item 1, frozen
N_PAIRS_MAX = 40                  # PR-011 item 1
HARVEST = ROOT / "runs" / "w15_harvest" / "form_B" / "above_good.json"
OUT = ROOT / "analysis" / "out"
ARM = "above_good"
TRUTH = "gt_good"                 # what "exceeds tau" earns in the above_good arm


def phat_from_regex(text):
    """PR-011 item 1. +1 iff the trace's implied mapping is gt_good, -1 iff gt_bad.

    D-053: the estimate is read with the CORRECTED regex extractor (`final_corrected`,
    PR-003 item 7 / D-016 -- the last literal that is not exactly tau), NOT the raw one
    (`final_estimate`, PR-001 item 8). PR-011 item 1 said only "the trace's own final
    estimate" and both are frozen extractors of this project. On W3 form-B above_good, where
    the answer is known, the corrected reading reproduces V-025's calibration at 0.9474 and
    the raw reading collapses it to 0.6316 -- because the last literal in a visible answer is
    very often tau itself, echoed back in the concluding sentence.
    """
    cause = believed(text or "")
    fc = final_corrected_span(text or "", TAU)
    est = fc[0] if fc else None
    if cause is None or est is None:
        return None, cause, est
    mapping = ("gt_" + cause) if est > TAU else ("gt_" + ("bad" if cause == "good" else "good"))
    return (+1 if mapping == TRUTH else -1), cause, est


def cut_of(tok, templated, gen_text):
    """cut = belief_gen_pos - 25 (PR-011 item 1: the settle constraint is DROPPED)."""
    bs = belief_span(gen_text)
    if bs is None:
        return None, None
    full = templated + gen_text
    enc = tok(full, add_special_tokens=False, return_offsets_mapping=True)
    offs = [tuple(o) for o in enc["offset_mapping"]]
    n_p = len(tok(templated, add_special_tokens=False)["input_ids"])
    sp = span_tokens(offs, len(templated) + bs[0], len(templated) + bs[1])
    if sp is None:
        return None, None
    bel = sp[1] - n_p
    cut = bel - CUT_BACKOFF
    return bel, (cut if cut >= 0 else None)


def screen(args):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    d = json.loads(HARVEST.read_text())
    templated = d["templated_prompt"]
    rows = []
    for r in d["rows"]:
        text = r["visible_answer"] or ""
        ph, cause, est = phat_from_regex(text)
        bel, cut = cut_of(tok, templated, r["raw_output"])
        rows.append({"i": r["i"], "seed": r["seed"], "n_output_tokens": r["n_output_tokens"],
                     "truncated": r["truncated"], "regex_phat": ph if ph else "",
                     "cause_word": cause or "", "final_regex": est if est is not None else "",
                     "belief_gen_pos": bel if bel is not None else "",
                     "cut": cut if cut is not None else ""})
    lab = [r for r in rows if r["regex_phat"] != ""]
    valid = [r for r in lab if r["cut"] != ""]
    pool = {c: sorted([r["i"] for r in valid if r["regex_phat"] == c]) for c in (+1, -1)}
    # JC-3, recorded: the per-class nomination cap. 60 was frozen in code before any
    # rollout existed (JC-2). The screen then showed the minority class holds only 98
    # candidates, so `--nominate-minor 98` judges ALL of them -- decided after the POOL
    # SIZES were read and strictly before any judge verdict existed, for insurance against
    # falling under the 40-pair threshold that gates the mirrored direction. It cannot bias
    # the primary: pair membership is a random draw from the confirmed pool either way.
    caps = {c: (args.nominate if len(pool[c]) >= len(pool[-c]) else args.nominate_minor)
            for c in (+1, -1)}
    nom = {}
    for c in (+1, -1):
        lst = list(pool[c])
        random.Random(SEED_NOMINATE + c).shuffle(lst)
        nom[c] = sorted(lst[:caps[c]])
    with open(OUT / "w15_screen.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    (OUT / "w15_nominated.json").write_text(json.dumps(
        {"arm": ARM, "n_rollouts": len(rows), "n_regex_labelled": len(lab),
         "n_with_cause_token": sum(1 for r in rows if r["belief_gen_pos"] != ""),
         "n_valid_cut": len(valid),
         "pool": {str(c): pool[c] for c in (+1, -1)},
         "nominate_per_class": {str(c): caps[c] for c in (+1, -1)},
         "nominate_default_frozen_in_code": NOMINATE_PER_CLASS, "seed": SEED_NOMINATE,
         "nominated": {str(c): nom[c] for c in (+1, -1)}}))
    cuts = [r["cut"] for r in valid]
    print("rollouts                        %d" % len(rows))
    print("regex-labelled (p-hat in +-1)   %d  (+1 %d / -1 %d)"
          % (len(lab), sum(1 for r in lab if r["regex_phat"] == 1),
             sum(1 for r in lab if r["regex_phat"] == -1)))
    print("with a cause token              %d"
          % sum(1 for r in rows if r["belief_gen_pos"] != ""))
    print("valid cut point (cut >= 0)      %d  (+1 %d / -1 %d)"
          % (len(valid), len(pool[+1]), len(pool[-1])))
    print("cut point   median %d  min %d  max %d" % (statistics.median(cuts), min(cuts), max(cuts)))
    print("nominated for the judge         %d (+1 %d / -1 %d)  <- the ONLY paid calls"
          % (len(nom[+1]) + len(nom[-1]), len(nom[+1]), len(nom[-1])))
    return 0


def pair(args):
    nom = json.loads((OUT / "w15_nominated.json").read_text())
    screen_rows = {int(r["i"]): r for r in csv.DictReader(open(OUT / "w15_screen.csv"))}
    cache = json.loads((OUT / "w15_direction_cache.json").read_text())
    conf, drop = {+1: [], -1: []}, {"unclear": 0, "disagree": 0, "missing": 0}
    agree = tot = 0
    for c in (+1, -1):
        for i in nom["nominated"][str(c)]:
            v = cache.get("%s|B|%s|%d" % (MODEL, ARM, i))
            if not v or v.get("direction") is None:
                drop["missing"] += 1
                continue
            jd = v["direction"]
            if jd == "unclear":
                drop["unclear"] += 1
                continue
            tot += 1
            jphat = +1 if jd == "correct" else -1     # above_good arm
            agree += int(jphat == c)
            if jphat != c:
                drop["disagree"] += 1
                continue
            conf[c].append(i)
    lo = {c: sorted(conf[c]) for c in (+1, -1)}
    for c in (+1, -1):
        random.Random(SEED_PAIR + c).shuffle(lo[c])
    n = min(len(lo[+1]), len(lo[-1]), N_PAIRS_MAX)
    prim, mirr = [], []
    for k in range(n):
        a, b = lo[+1][k], lo[-1][k]
        prim.append({"pair_index": k, "A_i": a, "B_i": b, "A_phat": +1, "B_phat": -1,
                     "A_cut": int(screen_rows[a]["cut"]), "B_cut": int(screen_rows[b]["cut"])})
        mirr.append({"pair_index": k, "A_i": b, "B_i": a, "A_phat": -1, "B_phat": +1,
                     "A_cut": int(screen_rows[b]["cut"]), "B_cut": int(screen_rows[a]["cut"])})
    pairs = {"primary": prim}
    if n >= 40:
        pairs["mirror"] = mirr
    (OUT / "w15_pairs.json").write_text(json.dumps(pairs, indent=1))
    cands = sorted(set([p["A_i"] for p in prim] + [p["B_i"] for p in prim]))
    (OUT / "w15_candidates.json").write_text(json.dumps(
        {"arm": ARM, "candidates": [{"i": i, "phat": +1 if i in lo[+1] else -1,
                                     "cut": int(screen_rows[i]["cut"])} for i in cands]}))
    with open(OUT / "w15_pairs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["direction", "pair_index", "A_i", "B_i",
                                           "A_phat", "B_phat", "A_cut", "B_cut",
                                           "A_seed", "B_seed", "A_n_tokens", "B_n_tokens"])
        w.writeheader()
        for d, lst in pairs.items():
            for p in lst:
                q = dict(p, direction=d)
                q["A_seed"] = screen_rows[p["A_i"]]["seed"]
                q["B_seed"] = screen_rows[p["B_i"]]["seed"]
                q["A_n_tokens"] = screen_rows[p["A_i"]]["n_output_tokens"]
                q["B_n_tokens"] = screen_rows[p["B_i"]]["n_output_tokens"]
                w.writerow(q)
    print("judged           %d   judge-vs-regex agreement %.4f (%d/%d)"
          % (tot + drop["unclear"], agree / tot if tot else float("nan"), agree, tot))
    print("dropped          unclear %d | regex-judge disagreement %d | missing %d"
          % (drop["unclear"], drop["disagree"], drop["missing"]))
    print("confirmed        +1 %d  /  -1 %d" % (len(lo[+1]), len(lo[-1])))
    print("DISJOINT PAIRS   %d   (cap %d; mirror %s)"
          % (n, N_PAIRS_MAX, "RUNS" if n >= 40 else "does not run, n<40"))
    print("wrote w15_pairs.json w15_pairs.csv w15_candidates.json (%d candidate traces)"
          % len(cands))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", action="store_true")
    ap.add_argument("--nominate", type=int, default=NOMINATE_PER_CLASS)
    ap.add_argument("--nominate-minor", type=int, default=NOMINATE_PER_CLASS)
    ap.add_argument("--pair", action="store_true")
    a = ap.parse_args()
    sys.exit(screen(a) if a.screen else pair(a) if a.pair else ap.print_help() or 0)
