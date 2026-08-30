"""W7 Step 4 / PR-005 item 7: the reading obligation.

Ten FULL steered traces per v_p̂/sham arm, at the fixed indices 0-9 that PR-005 froze before
any steered token existed. The indices are not chosen by outcome; they are the first ten rows
of each arm, i.e. seeds BASE_SEED + offset + 0 … +9.

  python3 src/samples_w7.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import extract_regex as ex  # noqa: E402
from steer_w7 import ARMS, VPHAT_ARMS, TAU_B, is_degenerate, ngram_ratio  # noqa: E402
from analyze_w7 import corrected_final, coherent, cause_screen  # noqa: E402

RUNS = ROOT / "runs" / "w7_steer"
OUT = ROOT / "analysis" / "out" / "w7_samples"
IDX = list(range(10))                      # FROZEN in PR-005 item 7
CACHE_DIR = ROOT / "analysis" / "out" / "w7_direction_cache.json"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    verdicts = json.loads(CACHE_DIR.read_text()) if CACHE_DIR.exists() else {}
    keys = [k for k in ARMS if k in VPHAT_ARMS]
    keys += [k + "_halved" for k in ARMS if (RUNS / (k + "_halved.json")).exists()]
    written = []
    for key in keys:
        p = RUNS / ("%s.json" % key)
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        L = ["# W7 steered traces — arm `%s`" % key, "",
             "PR-005 item 7. Indices **0-9**, frozen before the data existed.", "",
             "| field | value |", "|---|---|",
             "| condition | %s |" % d["condition"],
             "| injection layer | %s |" % d["layer"],
             "| alpha | %+g |" % d["alpha"],
             "| direction | %s |" % d["direction"],
             "| ‖Δμ‖ at that layer | %.6f |" % d["dmu_norm"],
             "| ‖injected vector‖ | %.6f |" % d["delta_norm"],
             "| tau_B | %s |" % d["threshold_formatted"],
             "| seeds | %d–%d |" % (d["seed_lo"], d["seed_hi"]),
             "| n | %d |" % d["n"],
             "| v_p̂^B sha256 | `%s` |" % d["vphat_sha256"], "",
             "**Prompt actually sent** (chat template applied at generation):", "",
             "```", d["prompt_text"], "```", ""]
        for i in IDX:
            if i >= len(d["rows"]):
                break
            r = d["rows"][i]
            va = r["visible_answer"]
            v = verdicts.get("%s|%d" % (key, i)) or {}
            L += ["---", "",
                  "## index %d · seed %d (batch seed %d, row %d)"
                  % (r["i"], r["seed"], r["seed_block"], r["row_in_batch"]), "",
                  "- finish_reason: `%s` · output tokens: %d · distinct-4-gram ratio: %.3f"
                  % (r["finish_reason"], r["n_output_tokens"], r["ngram4_ratio"]),
                  "- regex final (raw, PR-001 item 8): `%s`" % ex.final_estimate(va),
                  "- regex final (D-016-corrected, PR-003 item 7): `%s`"
                  % corrected_final(va, TAU_B),
                  "- above tau_B on the corrected basis: **%s**"
                  % (None if corrected_final(va, TAU_B) is None
                     else corrected_final(va, TAU_B) > TAU_B),
                  "- coherent (PR-005 item 4c): **%s** · degenerate: %s"
                  % (coherent(r, va), is_degenerate(r["raw_output"])),
                  "- direction judge: mentions_bet=`%s` direction=`%s`"
                  % (v.get("mentions_bet"), v.get("direction")),
                  "- cause-string screen: %s" % json.dumps(cause_screen(r["raw_output"])), "",
                  "```", r["raw_output"], "```", ""]
        path = OUT / ("%s.md" % key)
        path.write_text("\n".join(L))
        written.append(str(path.relative_to(ROOT)))
        print("wrote %s (%d traces, %d bytes)" % (path, min(10, len(d["rows"])),
                                                  path.stat().st_size))
    print("\n%d sample files; fixed indices %s" % (len(written), IDX))
    return 0


if __name__ == "__main__":
    sys.exit(main())
