"""W15 judging (PR-011 items 1 and 3). PROMPTS AND MODEL UNCHANGED.

Two phases, each with its own cache and its own pre-run projection:

  --phase harvest   the FROZEN direction judge on the NOMINATED harvest rollouts only.
                    R-017's "judge spend only on candidates" is implemented here: the regex
                    screen decides who is called, and nothing else in the 1,000 is.
  --phase cont      the direction judge AND the number judge on the RECONSTRUCTED traces
                    (A's prefix + the arm's continuation) of every transplant arm.

Transport is judge_w11_par's (D-038), untouched. Cost constants are D-040's, as in W14 --
D-052's 522 output tokens/call was a DEGRADED-wording artefact and W15 is natural wording.

  python3 src/judge_w15.py --phase harvest --estimate
  python3 src/judge_w15.py --phase harvest --run --procs 12
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import direction_judge as dj                        # noqa: E402
import judge_w11_par as jpar                        # noqa: E402
from value_leakage.judge import NUMBER_JUDGE_PROMPT, parse_tagged_estimate  # noqa: E402

MODEL = "Qwen/Qwen2.5-14B-Instruct"
OUT = ROOT / "analysis" / "out"
HARVEST = ROOT / "runs" / "w15_harvest" / "form_B" / "above_good.json"
TRANS = ROOT / "runs" / "w15_transplant"
DIR_CACHE = OUT / "w15_direction_cache.json"
NUM_CACHE = OUT / "w15_extractions.json"
USAGE_OUT = OUT / "w15_api_usage.json"

CPT_NUMBER, OUT_TOK_NUMBER = 2.84, 20.0             # D-040
CPT_DIRECTION, OUT_TOK_DIRECTION = 3.15, 56.0       # D-040
PRICE_IN, PRICE_OUT = 3.0, 15.0
CEILING_API = 6.0            # PR-011 item 8: the API share of R-017's $10 packet ceiling


def harvest_rows():
    d = json.loads(HARVEST.read_text())
    nom = json.loads((OUT / "w15_nominated.json").read_text())
    want = set(nom["nominated"]["1"]) | set(nom["nominated"]["-1"])
    p = d["prompt_text"]
    return [("%s|B|above_good|%d" % (MODEL, r["i"]), p, r["visible_answer"] or "", r["i"])
            for r in d["rows"] if r["i"] in want]


def cont_rows():
    out = []
    for path in sorted(TRANS.glob("*.json")):
        d = json.loads(path.read_text())
        for r in d["rows"]:
            key = "%s|B|%s_%s|%d" % (MODEL, r["direction"], r["arm"], r["pair_index"])
            out.append((key, d["templated_prompt"] and
                        json.loads(HARVEST.read_text())["prompt_text"],
                        r["visible_answer"] or "", r["pair_index"]))
    return out


def _cont_rows_fast(deep=False):
    p = json.loads(HARVEST.read_text())["prompt_text"]
    out = []
    root = (TRANS.parent / "w15_transplant_deep") if deep else TRANS
    tag = "deep_" if deep else ""
    for path in sorted(root.glob("*.json")):
        d = json.loads(path.read_text())
        for r in d["rows"]:
            out.append(("%s|B|%s%s_%s|%d" % (MODEL, tag, r["direction"], r["arm"],
                                             r["pair_index"]), p,
                        r["visible_answer"] or "", r["pair_index"]))
    return out


def estimate(rs, with_number):
    d_chars = sum(len(dj.DIRECTION_JUDGE_PROMPT.format(prompt=p, response=v))
                  for _, p, v, _ in rs)
    dirc = (d_chars / CPT_DIRECTION / 1e6 * PRICE_IN
            + OUT_TOK_DIRECTION * len(rs) / 1e6 * PRICE_OUT)
    num = 0.0
    if with_number:
        uniq = sorted({v for _, _, v, _ in rs if v.strip()})
        j_chars = sum(len(NUMBER_JUDGE_PROMPT.format(llm_text=t)) for t in uniq)
        num = (j_chars / CPT_NUMBER / 1e6 * PRICE_IN
               + OUT_TOK_NUMBER * len(uniq) / 1e6 * PRICE_OUT)
    est = {"n_calls_direction": len(rs), "constants": "D-040",
           "direction_judge_est_usd": round(dirc, 4),
           "number_judge_est_usd": round(num, 4),
           "total_est_usd": round(dirc + num, 4),
           "api_ceiling_usd": CEILING_API,
           "under_ceiling": bool(dirc + num <= CEILING_API)}
    print(json.dumps(est, indent=2))
    return est


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["harvest", "cont"], required=True)
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--deep", action="store_true", help="JC-4 diagnostic continuations")
    a = ap.parse_args()

    rs = harvest_rows() if a.phase == "harvest" else _cont_rows_fast(a.deep)
    with_number = a.phase == "cont"
    est = estimate(rs, with_number)
    if not a.run:
        return 0
    if not est["under_ceiling"]:
        print("PAUSING: projected $%.2f exceeds the $%.2f API share of R-017's ceiling."
              % (est["total_est_usd"], CEILING_API))
        return 2

    u_num = {"in": 0, "out": 0, "calls": 0}
    u_dir = {"in": 0, "out": 0, "calls": 0}

    if with_number:
        nc = json.loads(NUM_CACHE.read_text()) if NUM_CACHE.exists() else {}
        mc = nc.setdefault(MODEL, {})
        todo = sorted({v for _, _, v, _ in rs if v.strip()} - set(mc))
        print("number judge: %d unique answers to call (%d cached)" % (len(todo), len(mc)))
        mc.update(jpar._pool(todo, lambda t: parse_tagged_estimate(
            jpar._call(NUMBER_JUDGE_PROMPT.format(llm_text=t), (200,), u_num, False)),
            a.procs, "num"))
        NUM_CACHE.write_text(json.dumps(nc, indent=2))

    dc = json.loads(DIR_CACHE.read_text()) if DIR_CACHE.exists() else {}
    byk = {k: (p, v, i) for k, p, v, i in rs}
    todo2 = [k for k in byk if dc.get(k, {}).get("direction") is None]
    print("direction judge: %d to call (%d cached)" % (len(todo2), len(dc)))

    def one(k):
        p, v, i = byk[k]
        raw = jpar._call(dj.DIRECTION_JUDGE_PROMPT.format(prompt=p, response=v),
                         (600, 2000, 4000, 4000), u_dir, True)
        m, d = dj.parse_verdict(raw)
        return {"key": k, "i": i, "mentions_bet": m, "direction": d, "raw": raw}

    dc.update(jpar._pool(todo2, one, a.procs, "dir"))
    DIR_CACHE.write_text(json.dumps(dc, indent=2))

    c_n = u_num["in"] / 1e6 * PRICE_IN + u_num["out"] / 1e6 * PRICE_OUT
    c_d = u_dir["in"] / 1e6 * PRICE_IN + u_dir["out"] / 1e6 * PRICE_OUT
    prev = json.loads(USAGE_OUT.read_text()) if USAGE_OUT.exists() else {}
    prev[a.phase + ("_deep" if a.deep else "")] = {"estimate": est, "procs": a.procs,
                     "number_judge": dict(u_num, usd=round(c_n, 4)),
                     "direction_judge": dict(u_dir, usd=round(c_d, 4)),
                     "actual_usd": round(c_n + c_d, 4),
                     "projection_error_pct": round(100 * (est["total_est_usd"] - (c_n + c_d))
                                                   / (c_n + c_d), 1) if (c_n + c_d) else None}
    prev["cumulative_actual_usd"] = round(
        sum(v["actual_usd"] for k, v in prev.items() if isinstance(v, dict)
            and "actual_usd" in v), 4)
    USAGE_OUT.write_text(json.dumps(prev, indent=2))
    print("\n[%s] number $%.4f (%d calls) | direction $%.4f (%d calls, in/out %d/%d)"
          % (a.phase, c_n, u_num["calls"], c_d, u_dir["calls"], u_dir["in"], u_dir["out"]))
    print("ACTUAL $%.4f vs projection $%.4f | W15 cumulative API $%.4f"
          % (c_n + c_d, est["total_est_usd"], prev["cumulative_actual_usd"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
