"""W4 Step 2.1: the supplementary direction-judge validation sample.

The W3 sample (`w3_direction_sample.md`) showed ten form-A verdicts at fixed indices 0-4 per
condition. The researcher's audit (V-006) found 5/6 read verdicts unambiguous, one lenient
`correct`, and — the reason this file exists — that **the `incorrect` class is unvalidated
and load-bearing**: the belief-conditional decomposition (P-005) and the whole of R-009's
pivot 2 rest on `incorrect`/`unclear` traces genuinely believing the opposite direction.

SELECTION RULE (fixed here, in code, before any verdict or trace content was read):

  (a) for each of the four form x incentive-condition cells, the FIRST FIVE rollout indices
      in ascending index order whose STORED verdict is `direction=incorrect`;
  (b) additionally, for each form's `above_good` arm, the FIRST FIVE indices in ascending
      order whose stored verdict is `direction=correct`, SKIPPING any index already printed
      in `w3_direction_sample.md` (form A, both conditions, indices 0-4).

Rule (b)'s skip-list is the W3 *direction* sample only — that is the sample whose verdicts
the researcher has already read. The W3 *trace* sample (form B, indices 0/10/20/30/40)
carried no verdicts and is not skipped. Runner judgment call, reported.

A cell with fewer than five qualifying rollouts prints every one it has and says so; that
shortfall is itself data (form A `below_good` has zero `incorrect` verdicts in P-005).

  python3 src/samples_w4.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import extract_regex as ex  # noqa: E402

FROZEN = ROOT / "runs" / "w3_frozen"
OUT = ROOT / "analysis" / "out" / "w4_direction_sample2.md"
DIR_CACHE = ROOT / "analysis" / "out" / "w3_direction_cache.json"
MODEL = "Qwen/Qwen2.5-14B-Instruct"
FORMS = ("A", "B")
CONDS = ("below_good", "above_good")
N_WANT = 5
# Already printed in analysis/out/w3_direction_sample.md (form A, both conditions, 0-4).
W3_SHOWN = {("A", "below_good"): set(range(5)), ("A", "above_good"): set(range(5))}
TAU = {"A": 15300000, "B": 4500000000}


def fmt(v):
    if v is None:
        return "None"
    return ("%d" % v) if float(v).is_integer() else ("%g" % v)


def select(rows, dc, form, cond, verdict, skip):
    """Rule (a)/(b): first N_WANT indices in ascending order with this stored verdict."""
    out = []
    for i in sorted(rows):
        if i in skip:
            continue
        v = dc.get("%s|%s|%s|%d" % (MODEL, form, cond, i))
        if v and v.get("direction") == verdict:
            out.append(i)
            if len(out) == N_WANT:
                break
    return out


def block(r, v, form, cond, idx, tau):
    raw = ex.intermediates(r["reasoning_text"])
    fin = ex.final_estimate(r["visible_answer"])
    corrected = [x for x, _, _ in ex.all_numbers(r["visible_answer"] or "", skip_ranges=False)
                 if x != tau]
    lower = (r["visible_answer"] or "").lower()
    mapping = [s for s in ("good cause", "bad cause") if s in lower]
    return [
        "### form %s · %s · rollout %d (seed %d)" % (form, cond, idx, r["seed"]), "",
        "**Judge verdict:** `mentions_bet=%s` · `direction=%s`"
        % (v.get("mentions_bet"), v.get("direction")), "",
        "**Mechanical cross-check:** explicit cause-mapping string in the trace: %s"
        % ("`" + "`, `".join(mapping) + "`" if mapping else "**NONE**"), "",
        "`finish_reason=%s` · `truncated=%s` · %d output tokens · final (frozen PR-001 item 8) "
        "`%s`%s · final (D-016-corrected basis) `%s`"
        % (r["finish_reason"], r["truncated"], r["n_output_tokens"], fmt(fin),
           "  **[= τ exactly]**" if fin == tau else "",
           fmt(corrected[-1] if corrected else None)), "",
        "**Parsed intermediates (%d):** %s"
        % (len(raw), ", ".join(fmt(x) + (" **[τ-ECHO]**" if x == tau else "") for x in raw)
           or "(none)"), "",
        "<details><summary>judge raw reply</summary>", "",
        "```", v.get("raw", "(not judged)"), "```", "", "</details>", "",
        "**The trace the judge read, in full:**", "",
        "```", r["visible_answer"] or "(empty)", "```", "",
    ]


def main():
    dc = json.loads(DIR_CACHE.read_text())
    body, counts = [], []
    for form in FORMS:
        for cond in CONDS:
            d = json.loads((FROZEN / ("form_%s" % form) / ("%s.json" % cond)).read_text())
            rows = {r["i"]: r for r in d["rows"]}
            for verdict, use_skip in (("incorrect", False), ("correct", True)):
                if verdict == "correct" and cond != "above_good":
                    continue
                skip = W3_SHOWN.get((form, cond), set()) if use_skip else set()
                picked = select(rows, dc, form, cond, verdict, skip)
                n_tot = sum(1 for i in rows
                            if (dc.get("%s|%s|%s|%d" % (MODEL, form, cond, i)) or {}
                                ).get("direction") == verdict)
                counts.append({"form": form, "cond": cond, "verdict": verdict,
                               "n_in_arm": n_tot, "n_printed": len(picked),
                               "indices": picked,
                               "short": len(picked) < N_WANT,
                               "skipped": sorted(skip) if use_skip else []})
                body += ["", "---", "",
                         "## form %s · `%s` · stored verdict `%s`" % (form, cond, verdict), "",
                         "%d of %d rollouts in this arm carry this verdict; %s."
                         % (n_tot, len(rows),
                            ("printing the first %d by ascending index" % len(picked))
                            if picked else "**NOTHING TO PRINT — this cell is empty**"),
                         ("" if not use_skip else
                          "Indices %s were already printed in the W3 direction sample and are "
                          "skipped by rule (b)." % sorted(skip)),
                         ("**FEWER THAN %d QUALIFYING ROLLOUTS EXIST** — printed %d. That "
                          "shortfall is itself data." % (N_WANT, len(picked))
                          if len(picked) < N_WANT else ""),
                         "", "Prompt these traces answered (threshold rendered `%s`):"
                         % d["threshold_formatted"], "",
                         "```", d["prompt_text"], "```", ""]
                for i in picked:
                    body += block(rows[i], dc["%s|%s|%s|%d" % (MODEL, form, cond, i)],
                                  form, cond, i, TAU[form])
    head = ["# W4 supplementary direction-judge validation sample", "",
            "V-006 recorded that the judge's **`incorrect` class is unvalidated and "
            "load-bearing**, and that the `correct` class may absorb mapping-silent traces.",
            "This sample exists to let the researcher read both classes directly.", "",
            "**Selection rule — fixed in `src/samples_w4.py` before any verdict or trace "
            "content was read** (see the module docstring, which states the rule and the "
            "one judgment call in it):", "",
            "1. per form x incentive condition: the first five ascending indices with stored "
            "`direction=incorrect`;",
            "2. per form's `above_good`: the first five ascending indices with stored "
            "`direction=correct`, skipping indices 0-4 of form A already printed in "
            "`w3_direction_sample.md`.", "",
            "Each block also carries the **mechanical cause-mapping cross-check** of "
            "`src/judge_check_w4.py` (does the trace contain `good cause` / `bad cause`, "
            "case-insensitive) so the lenient-case question V-006 raised can be read off "
            "each trace, plus both final-estimate bases (frozen PR-001 item 8 and the "
            "D-016-corrected basis).", "",
            "Generated by `python3 src/samples_w4.py`.", "", "## Cells selected", "",
            "| form | condition | verdict | in arm | printed | indices |",
            "|---|---|---|---|---|---|"]
    for c in counts:
        head.append("| %s | `%s` | `%s` | %d | %d%s | %s |"
                    % (c["form"], c["cond"], c["verdict"], c["n_in_arm"], c["n_printed"],
                       " **(short)**" if c["short"] else "",
                       ", ".join(str(i) for i in c["indices"]) or "—"))
    OUT.write_text("\n".join(head + body))
    print("wrote", OUT)
    for c in counts:
        print(json.dumps(c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
