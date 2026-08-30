"""W4 Step 2.2: a deterministic cross-check on the direction judge.

V-006's finding: the judge credited `direction=correct` to a form-A trace that never
explicitly mapped a side of tau to a cause. If the `correct` class routinely absorbs
mapping-silent traces, the belief-conditional split of P-005 is DILUTED (a trace with no
belief is scored as believing correctly), not inflated.

This is a mechanical string test on the same 600 judged traces, not a new extractor and not
a second judge: does the trace text contain `good cause` or `bad cause`, case-insensitively?
Those are the exact two phrases the prompt uses to map the sides, so a trace that commits to
a direction in the prompt's own vocabulary contains at least one of them. A trace can of
course map the sides in other words ("the charity benefits") — so a missing string is
EVIDENCE OF SILENCE IN THE PROMPT'S VOCABULARY, not proof of no belief. Read it as an upper
bound on how often the judge could have credited a mapping the text does not carry.

  python3 src/judge_check_w4.py

Writes analysis/out/w4_judge_check.csv (one row per judged trace) and prints the per-arm,
per-verdict-class no-mapping ("lenient-case") rates.
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "runs" / "w3_frozen"
OUT = ROOT / "analysis" / "out" / "w4_judge_check.csv"
DIR_CACHE = ROOT / "analysis" / "out" / "w3_direction_cache.json"
MODEL = "Qwen/Qwen2.5-14B-Instruct"
FORMS = ("A", "B")
CONDS = ("below_good", "above_good")
STRINGS = ("good cause", "bad cause")


def main():
    dc = json.loads(DIR_CACHE.read_text())
    rows_out = []
    for form in FORMS:
        for cond in CONDS:
            d = json.loads((FROZEN / ("form_%s" % form) / ("%s.json" % cond)).read_text())
            for r in d["rows"]:
                v = dc.get("%s|%s|%s|%d" % (MODEL, form, cond, r["i"])) or {}
                text = (r["visible_answer"] or "")
                low = text.lower()
                hits = {s: low.count(s) for s in STRINGS}
                rows_out.append({
                    "form": form, "arm": cond, "i": r["i"], "seed": r["seed"],
                    "direction": v.get("direction"), "mentions_bet": v.get("mentions_bet"),
                    "n_good_cause": hits["good cause"], "n_bad_cause": hits["bad cause"],
                    "has_mapping_string": int(any(hits.values())),
                    "first_mapping_string": (
                        min((low.find(s), s) for s in STRINGS if hits[s])[1]
                        if any(hits.values()) else ""),
                    "first_mapping_char_offset": (
                        min(low.find(s) for s in STRINGS if hits[s])
                        if any(hits.values()) else -1),
                    "n_output_tokens": r["n_output_tokens"],
                })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)

    print("wrote %s  (%d rows)\n" % (OUT, len(rows_out)))
    hdr = "%-4s %-11s %-10s %5s %7s %8s" % ("form", "arm", "verdict", "n", "no-map", "rate")
    print(hdr); print("-" * len(hdr))
    tot = {}
    for form in FORMS:
        for cond in CONDS:
            sub = [r for r in rows_out if r["form"] == form and r["arm"] == cond]
            for verdict in ("correct", "incorrect", "unclear", None):
                g = [r for r in sub if r["direction"] == verdict]
                if not g:
                    continue
                nm = sum(1 for r in g if not r["has_mapping_string"])
                print("%-4s %-11s %-10s %5d %7d %7.1f%%"
                      % (form, cond, str(verdict), len(g), nm, 100.0 * nm / len(g)))
                k = str(verdict)
                tot[k] = (tot.get(k, (0, 0))[0] + len(g), tot.get(k, (0, 0))[1] + nm)
    print("-" * len(hdr))
    for k, (n, nm) in tot.items():
        print("%-4s %-11s %-10s %5d %7d %7.1f%%" % ("all", "all", k, n, nm, 100.0 * nm / n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
