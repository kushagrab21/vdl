"""R-017 / W15 Step 1: the DEGRADED-wording EXTENSION of the blinded hand-label packet.

W14's packet (`w14_handlabel_packet.md`, 50 W3 traces, R01-R50) bounds the direction judge on
NATURAL wording. D-051 showed the judge breaks on the degraded wording, and V-025 demoted the
degraded comprehension coordinate to [suggested] pending human labels. This adds the 20
degraded traces that measure it, built by exactly the W14 procedure:

  * population : the 300 W14 form-B degraded incentive traces (both arms), judged
  * strata     : the stored verdict classes, 8 correct / 6 incorrect / 6 unclear
                 (W14's 20/15/15 shape, scaled to 20 rows)
  * sampling   : without replacement inside each class, seed SEED_PICK, sorted key list
  * order      : shuffled across classes, seed SEED_SHUF
  * blinding   : no verdict, no class count, row ids R51..R70 that encode nothing
  * APPEND     : rows R51-R70 are appended to the EXISTING w14_handlabel_sheet.csv; the
                 W3 rows R01-R50 are re-written byte-identically (verified). The key goes to
                 a SEPARATE addendum file so `w14_handlabel_key.csv` -- never opened -- is
                 not rewritten.

The verdict is read ONLY to stratify and ONLY inside this script; nothing it prints names a
verdict or a row's class.

  python3 src/w15_handlabel_ext.py
  python3 src/w15_handlabel_ext.py --verify     # re-derive and check blindness, no rewrite
"""

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from w14_handlabel import INSTRUCTION  # noqa: E402  the judge's own instruction, verbatim

MODEL = "Qwen/Qwen2.5-14B-Instruct"
RUN = ROOT / "runs" / "w14_degraded"
DIR_CACHE = ROOT / "analysis" / "out" / "w14_direction_cache.json"
OUT = ROOT / "analysis" / "out"
PACKET = OUT / "w15_handlabel_ext_packet.md"
SHEET = OUT / "w14_handlabel_sheet.csv"          # extended in place
KEY_ADD = OUT / "w15_handlabel_key_addendum.csv"  # the W14 key file is NOT touched

# ---- FROZEN (R-017) --------------------------------------------------------
QUOTA = {"correct": 8, "incorrect": 6, "unclear": 6}
SEED_PICK = 15050
SEED_SHUF = 15051
FIRST_ROW = 51
CONDS = ("below_good", "above_good")
# ----------------------------------------------------------------------------


def population():
    cache = json.loads(DIR_CACHE.read_text())
    rows = {}
    for cond in CONDS:
        d = json.loads((RUN / "form_B" / ("%s.json" % cond)).read_text())
        for r in d["rows"]:
            key = "%s|B|%s|%d" % (MODEL, cond, r["i"])
            v = cache.get(key)
            if not v or v.get("direction") is None:
                continue
            rows[key] = {"key": key, "form": "B", "cond": cond, "i": r["i"],
                         "seed": r["seed"], "prompt": d["prompt_text"],
                         "text": (r["visible_answer"] or "").strip(),
                         "_verdict": v["direction"], "_mentions": v["mentions_bet"]}
    return rows


def select(rows):
    by = {c: sorted(k for k, v in rows.items() if v["_verdict"] == c) for c in QUOTA}
    for c, want in QUOTA.items():
        if len(by[c]) < want:
            raise RuntimeError("class %s has %d < %d" % (c, len(by[c]), want))
    picked = []
    for c in sorted(QUOTA):
        picked.extend(random.Random(SEED_PICK + sum(ord(x) for x in c)).sample(by[c], QUOTA[c]))
    random.Random(SEED_SHUF).shuffle(picked)
    return picked


def build(picked, rows):
    L = ["# W15 hand-label packet, EXTENSION — 20 further traces, blind", "",
         "**R-017.** This is an *extension* of the 50-trace packet you already have",
         "(`w14_handlabel_packet.md`, rows `R01`–`R50`). Those 50 traces measure the automated",
         "direction judge on the project's **natural** wording. These 20 measure it on the",
         "**reworded** prompts of the last experiment, where there is specific reason to think",
         "the judge is less reliable — which is exactly why a human reading is wanted.", "",
         "**The task and the instruction are identical to the first packet.** The 20 entries",
         "below are real traces. The machine's verdicts have been removed and are not",
         "recoverable from anything in this file, from `w14_handlabel_sheet.csv`, or from the",
         "row ids — those are shuffled and encode nothing. A sealed key exists at",
         "`analysis/out/w15_handlabel_key_addendum.csv`; **please do not open it before the",
         "sheet is returned.**", "",
         "## What to do", "",
         "`analysis/out/w14_handlabel_sheet.csv` now has **70** rows: your original `R01`–`R50`",
         "plus `R51`–`R70` for this packet. If you have already filled `R01`–`R50`, those",
         "answers are untouched — fill the new rows and send the one sheet back.", "",
         "**Read each prompt carefully.** The prompts in this packet are worded differently",
         "from the ones in the first packet, and the difference is the point.", "",
         "## The instruction (identical to the one the automated judge is given)", "",
         INSTRUCTION, "",
         "Each entry below shows the **exact prompt** the model answered and its **full",
         "response**. Judge the response against the prompt shown with it — the two arms",
         "point in opposite directions and both appear here.", "",
         "---", ""]
    sheet = []
    for n, key in enumerate(picked, FIRST_ROW):
        r = rows[key]
        rid = "R%02d" % n
        L += ["## %s" % rid, "",
              "### The prompt this response answered", "", "````", r["prompt"], "````", "",
              "### The response", "", "````", r["text"] or "(empty)", "````", "",
              "### Your labels — copy into the sheet, row `%s`" % rid, "",
              "| field | options | your answer |", "|---|---|---|",
              "| `mentions_bet` | yes / no | |",
              "| `direction` | correct / incorrect / unclear | |", "",
              "---", ""]
        sheet.append({"row_id": rid, "mentions_bet": "", "direction": "", "notes": ""})
    return "\n".join(L), sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    rows = population()
    picked = select(rows)
    body, sheet = build(picked, rows)

    old = list(csv.DictReader(open(SHEET)))
    old_ids = [r["row_id"] for r in old]
    already = [r for r in old if r["row_id"] in {s["row_id"] for s in sheet}]

    # ---- blindness checks, the four W14 structural ones, plus two append-specific ----
    blocks = re.findall(r"### Your labels.*?\n\n(\| field \|.*?)\n\n---", body, re.S)
    tmpl = {b for b in blocks}
    leaks = [t for t in ("judge_direction", "judge_mentions_bet", "cache_key", "_verdict")
             if t in body]
    empty = all(r["mentions_bet"] == "" and r["direction"] == "" for r in sheet)
    fences = sum(1 for k in picked if "````" in rows[k]["text"])
    prior_intact = old_ids == ["R%02d" % n for n in range(1, 51)] and not already
    ok = (len(tmpl) == 1 and len(blocks) == sum(QUOTA.values()) and not leaks and empty
          and fences == 0 and prior_intact)
    assert len(picked) == len(set(picked)) == sum(QUOTA.values()), "picked set malformed"

    if not a.verify:
        PACKET.write_text(body)
        before = SHEET.read_bytes()
        with open(SHEET, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["row_id", "mentions_bet", "direction", "notes"])
            w.writeheader(); w.writerows(old); w.writerows(sheet)
        after_head = SHEET.read_bytes()[:len(before)]
        assert after_head == before, "the R01-R50 block was not rewritten byte-identically"
        with open(KEY_ADD, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["row_id", "cache_key", "form", "arm", "i",
                                               "seed", "judge_mentions_bet", "judge_direction"])
            w.writeheader()
            for n, key in enumerate(picked, FIRST_ROW):
                r = rows[key]
                w.writerow({"row_id": "R%02d" % n, "cache_key": key, "form": r["form"],
                            "arm": r["cond"], "i": r["i"], "seed": r["seed"],
                            "judge_mentions_bet": r["_mentions"],
                            "judge_direction": r["_verdict"]})
    print("population (W14 degraded, judged)   : %d traces" % len(rows))
    print("rows in extension                   : %d  (%s-%s)"
          % (len(picked), sheet[0]["row_id"], sheet[-1]["row_id"]))
    print("quota (frozen in R-017 reading)     : %d strata, %d rows total"
          % (len(QUOTA), sum(QUOTA.values())))
    print("seeds                               : pick %d, shuffle %d" % (SEED_PICK, SEED_SHUF))
    print("blindness  identical label blocks     : %d distinct of %d entries (must be 1)"
          % (len(tmpl), len(blocks)))
    print("blindness  key field names in packet  : %s (must be none)" % (leaks or "none"))
    print("blindness  sheet answer columns empty : %s" % empty)
    print("blindness  traces that break the fence: %d (must be 0)" % fences)
    print("append     R01-R50 present and unclaimed by this extension : %s" % prior_intact)
    print("packet sha256 %s" % hashlib.sha256(body.encode()).hexdigest()[:16])
    print("wrote" if not a.verify else "verified", PACKET, SHEET, KEY_ADD)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
