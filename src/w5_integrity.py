"""W5 Step 3 acceptance check: do the pod-local activation tensors still tie to the index?

W4's decode check (V-008) established that the STORED span token ids decode to the parsed
literals. It could not establish anything about the three arms whose tensors never reached
the laptop. This file checks the tensors themselves, arm by arm:

  C1  the file's `acts` row count equals the arm index's `n_points`
  C2  for 5 `est` points per arm (fixed rule: every (n_est // 5)-th est point of the arm,
      first 5 taken), the stored span token ids decode to the literal as written in the trace
  C3  the same 5 rows are real activations, not zero padding or NaN: finite everywhere, and
      the row's per-layer L2 norm is reported at layers 0, 23, 47
  C4  the file's sha256, so the tensors the analysis reads are named in the ledger

  python src/w5_integrity.py            # all six arms
  python src/w5_integrity.py --arms A_below_good B_above_good B_below_good
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
POS = ROOT / "analysis" / "out" / "w4_positions"
ACTS = ROOT / "runs" / "w4_acts"
MODEL = "Qwen/Qwen2.5-14B-Instruct"
ARMS = ["A_below_good", "A_above_good", "A_neutral",
        "B_below_good", "B_above_good", "B_baseline"]
N_SAMPLE = 5


def sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", nargs="*", default=ARMS)
    ap.add_argument("--no-sha", action="store_true")
    args = ap.parse_args()

    from safetensors.numpy import load_file
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)

    ok = True
    print("| arm | rows | index n_points | C1 | C2 decode | C3 finite | sha256 |")
    print("|---|---|---|---|---|---|---|")
    detail = []
    for arm in args.arms:
        form, a = arm.split("_", 1)
        idx = json.loads((POS / ("w4_positions_%s_%s.json" % (form, a))).read_text())
        path = ACTS / ("w4_acts_%s_%s.safetensors" % (form, a))
        acts = load_file(str(path))["acts"]
        c1 = acts.shape[0] == idx["n_points"]

        est = [p for p in idx["points"] if p["kind"] == "est"]
        step = max(1, len(est) // N_SAMPLE)
        picked = est[::step][:N_SAMPLE]
        c2 = 0
        for p in picked:
            dec = tok.decode(p["span_token_ids"])
            good = dec.strip() == p["literal"].strip()
            c2 += int(good)
            row = acts[p["row"]].astype(np.float32)
            detail.append((arm, p["trace_i"], p["row"], p["span_token_ids"], dec,
                           p["literal"], good, bool(np.isfinite(row).all()),
                           [round(float(np.linalg.norm(row[l])), 2) for l in (0, 23, 47)]))
        fin = all(d[7] for d in detail if d[0] == arm)
        sh = "-" if args.no_sha else sha256(path)
        ok = ok and c1 and c2 == len(picked) and fin
        print("| %s | %d | %d | %s | %d/%d | %s | %s |"
              % (arm, acts.shape[0], idx["n_points"], "PASS" if c1 else "FAIL",
                 c2, len(picked), "PASS" if fin else "FAIL", sh[:16] + "…"))
        del acts

    print("\nsampled points (C2/C3):")
    print("| arm | trace | row | span token ids | decodes to | literal | == | finite | "
          "L2 @ layers 0/23/47 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for d in detail:
        print("| %s | %d | %d | `%s` | `%s` | `%s` | %s | %s | %s |"
              % (d[0], d[1], d[2], d[3], d[4], d[5], "yes" if d[6] else "**NO**",
                 "yes" if d[7] else "**NO**", "/".join(str(x) for x in d[8])))
    print("\nOVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
