"""W14 / PR-010 item 7: the reading obligation.

FIVE full traces per degraded arm at the fixed indices 0-4, frozen in PR-010 item 7 before
any W14 token existed. Chosen by position, not by outcome.

  python3 src/samples_w14.py
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import extract_regex as ex  # noqa: E402
from analyze_w14 import TAU, RUN, NUM_CACHE, DIR_CACHE, MODEL, FORM, CONDS  # noqa: E402
from analyze_w11 import corrected_final  # noqa: E402

OUT = ROOT / "analysis" / "out" / "w14_samples"
IDX = [0, 1, 2, 3, 4]                        # FROZEN in PR-010 item 7


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    num = json.loads(NUM_CACHE.read_text())[MODEL] if NUM_CACHE.exists() else {}
    dirc = json.loads(DIR_CACHE.read_text()) if DIR_CACHE.exists() else {}
    written = []
    for cond in CONDS:
        p = RUN / ("form_%s" % FORM) / ("%s.json" % cond)
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        L = ["# W14 degraded traces — form %s, arm `%s`" % (FORM, cond), "",
             "**PR-010 item 7. Indices %s are FROZEN by position, chosen before any W14 "
             "token existed — not by outcome.**" % IDX, "",
             "τ = %s · seeds %d–%d · n = %d · truncated = %d"
             % ("{:,}".format(TAU), d["rows"][0]["seed"], d["rows"][-1]["seed"],
                d["n"], d["n_truncated"]), "",
             "The bet note W3 used:", "", "```", d["replaced_substring"], "```", "",
             "The nested-negation paraphrase this packet replaced it with:", "",
             "```", d["replacement"], "```", "",
             "The whole changed line, and nothing else changed:", "",
             "```", d["prompt_text"].splitlines()[4], "```", "",
             "prompt sha256 `%s`" % hashlib.sha256(d["prompt_text"].encode()).hexdigest()[:16],
             ""]
        for i in IDX:
            r = d["rows"][i]
            v = dirc.get("%s|%s|%s|%d" % (MODEL, FORM, cond, r["i"]), {})
            jv = num.get(r["visible_answer"] or "")
            cv = corrected_final(r["visible_answer"], TAU)
            L += ["---", "", "## index %d (seed %d)" % (r["i"], r["seed"]), "",
                  "| | |", "|---|---|",
                  "| direction judge | mentions=%s **direction=%s** |"
                  % (v.get("mentions_bet"), v.get("direction")),
                  "| final, number judge | %s → %s τ |"
                  % (jv, "ABOVE" if (jv is not None and jv > TAU) else "at-or-below"),
                  "| final, regex raw | %s |" % ex.final_estimate(r["visible_answer"]),
                  "| final, D-016 corrected | %s → %s τ |"
                  % (cv, "ABOVE" if (cv is not None and cv > TAU) else "at-or-below"),
                  "| output tokens | %d |" % r["n_output_tokens"],
                  "| truncated | %s |" % r["truncated"], "",
                  "### visible answer", "", "```",
                  (r["visible_answer"] or "(empty)").strip(), "```", ""]
        path = OUT / ("form_%s_%s.md" % (FORM, cond))
        path.write_text("\n".join(L))
        written.append(str(path))
        print("wrote", path)
    print("\n%d sample files, 5 traces each at frozen indices %s" % (len(written), IDX))
    return 0


if __name__ == "__main__":
    sys.exit(main())
