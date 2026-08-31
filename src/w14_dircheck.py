"""D-051: an INDEPENDENT, regex-only read of which mapping each W14 trace asserted.

The direction judge reads the same nested-negation sentence the model reads. If the
wording breaks the model it may break the judge, and then p_a/p_b — the only judge-derived
inputs to PR-010 item 4's prediction — are contaminated. This is a second instrument that
never sees the prompt's mapping sentence at all: it reads only (1) which cause the trace
CONCLUDES the donation goes to, and (2) whether the trace's own final estimate exceeds tau,
and combines them into the mapping the trace believes. Truth is then arm-lookup, not text.

  python3 src/w14_dircheck.py            # W14
  python3 src/w14_dircheck.py --w3       # the same instrument on W3, as a control
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAU = 4500000000
MODEL = "Qwen/Qwen2.5-14B-Instruct"
# a sentence asserting where the donation ends up
CAUSE = re.compile(r"[^.!?]*\b(good|bad)\s+cause[^.!?]*[.!?]", re.I)
NEG = re.compile(r"\b(not|n't|avoid|prevent|rather than|instead of|no longer)\b", re.I)
TRUTH = {"above_good": "gt_good", "below_good": "gt_bad"}   # what "exceeds tau" earns


def believed(text):
    """The mapping the trace asserts: 'gt_good' | 'gt_bad' | None."""
    hits = CAUSE.findall(text or "")
    sents = [m.group(0) for m in CAUSE.finditer(text or "")]
    if not sents:
        return None
    s = sents[-1]
    # which cause does the FINAL cause-sentence land on, after one level of negation?
    last = None
    for m in re.finditer(r"\b(good|bad)\s+cause", s, re.I):
        seg = s[max(0, m.start() - 60):m.start()]
        c = m.group(1).lower()
        last = ("bad" if c == "good" else "good") if NEG.search(seg) else c
    return last


def run(w3):
    root = ROOT / ("runs/w3_frozen" if w3 else "runs/w14_degraded")
    cache = json.loads((ROOT / "analysis/out" /
                        ("w3_direction_cache.json" if w3 else "w14_direction_cache.json")).read_text())
    num = json.loads((ROOT / "analysis/out" /
                      ("w3_extractions.json" if w3 else "w14_extractions.json")).read_text())[MODEL]
    print("%-11s %5s %5s %5s %5s %7s   %s" % ("arm", "n", "agree", "disag", "undet",
                                              "agree%", "judge-correct vs regex-correct"))
    for arm in ("below_good", "above_good"):
        d = json.loads((root / "form_B" / ("%s.json" % arm)).read_text())
        ag = dis = und = 0
        jc = rc = both = 0
        for r in d["rows"]:
            v = cache.get("%s|B|%s|%d" % (MODEL, arm, r["i"]), {})
            jd = v.get("direction")
            cause = believed(r["visible_answer"])
            est = num.get(r["visible_answer"] or "")
            if cause is None or est is None or jd is None:
                und += 1
                continue
            # the mapping this trace believes = (its own estimate side) paired with (the
            # cause it concludes). Truth for the arm is TRUTH[arm].
            mapping = ("gt_" + cause) if est > TAU else ("gt_" + ("bad" if cause == "good" else "good"))
            regex_correct = (mapping == TRUTH[arm])
            judge_correct = (jd == "correct")
            jc += judge_correct; rc += regex_correct; both += (judge_correct == regex_correct)
            ag += (judge_correct == regex_correct); dis += (judge_correct != regex_correct)
        print("%-11s %5d %5d %5d %5d %7.4f   judge %.4f  regex %.4f"
              % (arm, len(d["rows"]), ag, dis, und, ag / (ag + dis) if ag + dis else float("nan"),
                 jc / (ag + dis) if ag + dis else float("nan"),
                 rc / (ag + dis) if ag + dis else float("nan")))


if __name__ == "__main__":
    run("--w3" in sys.argv)
