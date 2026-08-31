"""PR-011 item 8: the load-bearing recount. Delta_swap from the raw continuation files by a
FRESH regex-only extractor. stdlib only; no import from src/.  python3 src/w15_recount.py"""
import json, re, pathlib
TAU, R = 4500000000, pathlib.Path(__file__).resolve().parent.parent / "runs" / "w15_transplant"
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?(?:\s*(?:x|×)\s*10\s*\^?\s*(\d+)|e(\d+))?", re.I)
def last(t):
    out = []
    for m in NUM.finditer(t or ""):
        v = float(re.split("[xe×]", m.group(0), 1)[0].replace(",", "").strip() or 0) * (
            10 ** int(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else 1)
        if v != TAU and v >= 1000: out.append(v)
    return out[-1] if out else None
for path in sorted(R.glob("*.json")):
    d, y = json.loads(path.read_text()), {}
    for r in d["rows"]:
        v = last(r["visible_answer"])
        if v is not None: y.setdefault(r["arm"], {})[r["pair_index"]] = int((v > TAU) == (r["B_phat"] == 1))
    A = ("SHAM", "SWAP", "SELF", "RAND"); n = sorted(set.intersection(*[set(y[a]) for a in A]))
    p = {a: sum(y[a][i] for i in n) / len(n) for a in A}
    print("%-8s n=%d  P(toward B) SHAM/SWAP/SELF/RAND %.4f %.4f %.4f %.4f | D_swap %+.4f "
          "D_self %+.4f D_rand %+.4f swap-rand %+.4f" % ((d["direction"], len(n)) + tuple(
          p[a] for a in A) + tuple(p[a] - p["SHAM"] for a in A[1:]) + (p["SWAP"] - p["RAND"],)))
