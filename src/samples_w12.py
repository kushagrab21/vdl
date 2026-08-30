"""W12 Step 2 item 7: the flip sample the researcher reads.

Five flipped traces (or all, if fewer), by a fixed rule frozen in PR-008: the flipped
traces in the order they appear in `w12_flips.csv` (arm order above_good, below_good,
then trace index), first five taken.  Each gets its smoothed held-out belief-probe
trajectory drawn as a text plot beside the generated text, with the cause token and the
flip position marked.

  python3 src/samples_w12.py
"""
import csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"
SRC = {"above_good": "runs/w3_frozen/form_B/above_good.json",
       "below_good": "runs/w3_frozen/form_B/below_good.json"}
N_SAMPLE = 5
PLOT_W = 41                       # columns; 0.0 at col 0, 1.0 at col PLOT_W-1


def rows(p):
    with open(p) as fh:
        return list(csv.DictReader(fh))


def main():
    flips = rows(OUT / "w12_flips.csv")
    traj = rows(OUT / "w12_trajectories.csv")
    hl = json.loads((OUT / "w12_headline.json").read_text())
    picked = [f for f in flips if f["flip_pos"] != ""][:N_SAMPLE]
    texts = {a: {r["i"]: r for r in json.loads((ROOT / p).read_text())["rows"]}
             for a, p in SRC.items()}
    by = {}
    for t in traj:
        by.setdefault((t["arm"], t["trace_i"]), []).append(t)

    L = ["# W12 flip sample — belief-probe trajectories beside their traces", "",
         "Fixed rule (PR-008 item 7): the first %d flipped traces in `w12_flips.csv` "
         "order (arm order `above_good, below_good`, then trace index). "
         "**%d flipped traces exist; %d shown.**" % (
             N_SAMPLE, sum(1 for f in flips if f["flip_pos"] != ""), len(picked)), "",
         "The trajectory is the held-out probe's P(p̂ = +1) at the best layer "
         "(**L%s**), smoothed with the frozen 25-token moving average and downsampled "
         "x5.  `|` is 0.5.  `C` marks the first cause token, `F` the flip." % hl["best_layer"],
         "", "A flip is [suggested]-tier by construction (PR-008 item 5): the empirical "
         "label-shuffled false-flip rate on this capture is **%.3f** per trace under the "
         "ordered rule and **%.3f** under the strict rule."
         % (hl["false_flip_empirical_ordered"], hl["false_flip_empirical_strict"]), ""]

    for f in picked:
        arm, ti = f["arm"], f["trace_i"]
        rec = texts[arm][int(ti)]
        pts = sorted(by[(arm, ti)], key=lambda r: int(r["gen_pos"]))
        L += ["---", "", "## %s · trace %s · seed %s · p̂ = %s · n_gen %s"
              % (arm, ti, f["seed"], f["phat"], f["n_gen"]), "",
              "first cause token at gen_pos **%s** · flip at **%s** (to p̂ = %s) · "
              "settle %s · cut point %s · post-flip estimates: **%s** (%s est points)"
              % (f["belief_gen_pos"] or "none", f["flip_pos"], f["flip_to"],
                 f["settle_pos"], f["cut_point"] or "none",
                 f["post_flip_estimates"], f["n_est_post_flip"]), "",
              "```", "gen_pos  0.0%s1.0   P(p̂=+1), smoothed" % (" " * (PLOT_W - 7))]
        bel = int(f["belief_gen_pos"]) if f["belief_gen_pos"] else None
        fl = int(f["flip_pos"])
        for r in pts:
            g, v = int(r["gen_pos"]), float(r["score_smoothed"])
            col = max(0, min(PLOT_W - 1, int(round(v * (PLOT_W - 1)))))
            bar = [" "] * PLOT_W
            bar[(PLOT_W - 1) // 2] = "|"
            bar[col] = "#"
            mark = ""
            if bel is not None and abs(g - bel) < 3:
                mark += " C"
            if abs(g - fl) < 3:
                mark += " F"
            L.append("%7d  %s  %.3f%s" % (g, "".join(bar), v, mark))
        L += ["```", "", "### generated text", "", "```",
              rec["raw_output"].strip(), "```", ""]

    p = OUT / "w12_flip_sample.md"
    p.write_text("\n".join(L) + "\n")
    print("wrote", p, "(%d traces)" % len(picked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
