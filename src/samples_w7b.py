"""W7b / PR-006 item 6: the reading obligation.

FIVE full traces per v_p̂ arm, at the fixed indices 0-4 that PR-006 froze before any W7b
token existed. The indices are chosen by position, not by outcome: they are the first five
rows of each arm, i.e. seeds BASE_SEED + offset + 0 … +4.

No direction judge ran in this packet (PR-006 item 3), so no verdict line is printed.

  python3 src/samples_w7b.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import extract_regex as ex  # noqa: E402
from steer_w7 import TAU_B, is_degenerate  # noqa: E402
from steer_w7b import ARMS, VPHAT_ARMS, OUT_ROOT  # noqa: E402
from analyze_w7 import corrected_final, coherent  # noqa: E402

OUT = ROOT / "analysis" / "out" / "w7b_samples"
IDX = [0, 1, 2, 3, 4]                        # FROZEN in PR-006 item 6
CACHE = ROOT / "analysis" / "out" / "w7b_extractions.json"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    import hashlib
    jc = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    written = []
    for key in VPHAT_ARMS:
        p = OUT_ROOT / ("%s.json" % key)
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        L = ["# W7b low-dose steered traces — arm `%s`" % key, "",
             "**Stage-2 follow-up, designed AFTER W7's result (R-011). W7's verdict stands.**",
             "PR-006 item 6. Indices **0-4**, frozen before the data existed.", "",
             "| field | value |", "|---|---|",
             "| condition | %s |" % d["condition"],
             "| injection layer | %s |" % d["layer"],
             "| alpha (in ‖Δμ‖ units) | %+g |" % d["alpha"],
             "| direction | %s |" % d["direction"],
             "| ‖Δμ‖ at L27 | %.6f |" % d["dmu_norm"],
             "| ‖injected vector‖ | %.6f |" % d["delta_norm"],
             "| as a fraction of mean ‖h‖ (111.65) | %.1f %% |" % (100 * d["delta_norm"] / 111.65),
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
            j = jc.get(hashlib.sha1(va.encode()).hexdigest())
            cf = corrected_final(va, TAU_B)
            L += ["---", "",
                  "## index %d · seed %d (batch seed %d, row %d)"
                  % (r["i"], r["seed"], r["seed_block"], r["row_in_batch"]), "",
                  "- finish_reason: `%s` · output tokens: %d · distinct-4-gram ratio: %.3f"
                  % (r["finish_reason"], r["n_output_tokens"], r["ngram4_ratio"]),
                  "- regex final (raw, PR-001 item 8): `%s`" % ex.final_estimate(va),
                  "- regex final (D-016-corrected, PR-003 item 7): `%s`" % cf,
                  "- number judge final (extractor 2): `%s`" % j,
                  "- above tau_B on the corrected basis: **%s**"
                  % (None if cf is None else cf > TAU_B),
                  "- coherent (PR-005 item 4c): **%s** · degenerate: %s "
                  "— *per D-029 this is a statement about well-formedness only*"
                  % (coherent(r, va), is_degenerate(r["raw_output"])), "",
                  "```", r["raw_output"], "```", ""]
        path = OUT / ("%s.md" % key)
        path.write_text("\n".join(L))
        written.append(str(path.relative_to(ROOT)))
        print("wrote %s (%d traces, %d bytes)" % (path, min(len(IDX), len(d["rows"])),
                                                  path.stat().st_size))
    print("\n%d sample files; fixed indices %s (PR-006 item 6)" % (len(written), IDX))
    return 0


if __name__ == "__main__":
    sys.exit(main())
