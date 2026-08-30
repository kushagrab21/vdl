"""Offline recount of v_p̂(ℓ*) from the shipped analysis cell (`runs/w5_subsample/w5_cell*`),
compared against the shipped tensor. Uses only files that left the pod, so it stays runnable
after the pod is terminated.

  python3 src/w5_recount.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import direction_w5 as w5  # noqa: E402


def main():
    from safetensors.numpy import load_file
    meta = json.loads((w5.SUB / "w5_cell_index.json").read_text())
    acts = load_file(str(w5.SUB / "w5_cell.safetensors"))["acts"]
    lstar = json.loads((w5.OUT / "w5_lstar.json").read_text())["layer_star"]
    ok = True
    for form in ("A", "B"):
        pts = []
        for m in meta["points"]:
            if m["form"] == form and m["phat"] in (1, -1):
                q = dict(m)
                q["row_local"] = m["cell_row"]
                pts.append(q)
        X = acts[:, lstar, :].astype(np.float32)[:, None, :]
        M, mt = w5.stratum_means(pts, X, [("above_good", p["trace_i"]) for p in pts])
        lab = {p["trace_i"]: p["phat"] for p in pts}
        v, counts, used = w5.contrast(M, mt, [lab[m["key"][1]] for m in mt])
        ref = load_file(str(w5.VEC / ("w5_vphat_%s.safetensors" % form)))["vphat"][lstar]
        c = w5.cos(v[0], ref)
        ok = ok and c > 0.9
        print("form %s | l*=%d | cell est points %d over %d traces | strata %s used %d "
              "| cos(recount, shipped) = %.6f"
              % (form, lstar, len(pts), len({p["trace_i"] for p in pts}), counts, used, c))
    print("RECOUNT:", "PASS (>0.9 both forms)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
