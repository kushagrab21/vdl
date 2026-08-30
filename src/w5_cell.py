"""Ship the v_p-hat ANALYSIS CELL: every `est` point of both above_good arms, all 48 layers.
528 points of 6,668 (7.9%). Written after the frozen analysis completed, so it cannot bias
anything; it exists so v_p-hat and its probes stay reproducible offline once the pod is gone.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, "src")
from safetensors.numpy import load_file, save_file
import direction_w5 as w5

meta, rows = [], []
for form in ("A", "B"):
    idx = w5.load_index(form, "above_good")
    acts = w5.load_acts(form, "above_good")
    verd = w5.verdicts()
    for p in idx["points"]:
        if p["kind"] != "est":
            continue
        v = verd.get((form, "above_good", p["trace_i"]))
        rows.append(acts[p["row"]])
        meta.append({"form": form, "arm": "above_good", "trace_i": p["trace_i"],
                     "row": p["row"], "cell_row": len(rows) - 1, "kind": "est",
                     "token_index": p["token_index"], "value": p["value"],
                     "literal": p["literal"], "verdict": v,
                     "phat": w5.phat_of("above_good", v), "dt": w5.dt_of(p, form)})
    del acts
arr = np.stack(rows).astype(np.float16)
out = Path("runs/w5_subsample")
save_file({"acts": arr}, str(out / "w5_cell.safetensors"),
          metadata={"model": w5.MODEL, "shape": json.dumps(list(arr.shape)),
                    "rule": "every est point of A/above_good and B/above_good, all 48 layers"})
(out / "w5_cell_index.json").write_text(json.dumps(
    {"n_points": len(meta), "shape": list(arr.shape),
     "rule": "every est point of A/above_good and B/above_good, all 48 layers",
     "points": meta}, indent=1))
print("cell", arr.shape, (out / "w5_cell.safetensors").stat().st_size / 1e6, "MB")
