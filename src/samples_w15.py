"""PR-011 item 7: 5 SWAP and 5 SHAM continuations at the FROZEN blind indices 0-4.

Indices are the first five pair_index values of the primary direction -- fixed before any
outcome was computed and not chosen after seeing them.

  python3 src/samples_w15.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out" / "w15_samples"
TRANS = ROOT / "runs" / "w15_transplant"
IDX = [0, 1, 2, 3, 4]
TAU = 4500000000


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = json.loads((TRANS / "primary.json").read_text())
    by = {(r["arm"], r["pair_index"]): r for r in d["rows"]}
    for arm in ("SWAP", "SHAM"):
        L = ["# W15 samples — arm `%s`, primary direction, pair indices %s" % (arm, IDX), "",
             "**PR-011 item 7.** The indices were frozen before any outcome was computed.",
             "Each entry shows the teacher-forced prefix (A's own tokens, up to the cut point),",
             "then the continuation this arm generated from the edited state. The prefix is",
             "IDENTICAL across arms for a given pair; only the continuation differs.", "",
             "The threshold is **%s**. A is the p̂=%+d member and B the p̂=%+d member."
             % ("{:,}".format(TAU), d["rows"][0]["A_phat"], d["rows"][0]["B_phat"]), "",
             "---", ""]
        for i in IDX:
            r = by[(arm, i)]
            L += ["## pair %d — A=rollout %d (seed %d), B=rollout %d (seed %d)"
                  % (i, r["A_i"], r["A_seed"], r["B_i"], r["B_seed"]), "",
                  "cut point **%d** of %d prefix tokens · continuation **%d** tokens · "
                  "edit ‖δ‖ mean **%s** · finish `%s`"
                  % (r["cut"], r["n_prefix_tokens"], r["n_continuation_tokens"],
                     "n/a (SHAM)" if r["edit_norm_mean"] is None
                     else "%.4f" % r["edit_norm_mean"], r["finish_reason"]), "",
                  "### The teacher-forced prefix (unchanged text; the edit is in activations)",
                  "", "````", r["prefix_text"], "````", "",
                  "### The continuation this arm generated", "", "````",
                  r["continuation_text"] or "(empty)", "````", "", "---", ""]
        p = OUT / ("w15_%s.md" % arm.lower())
        p.write_text("\n".join(L))
        print("wrote", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
