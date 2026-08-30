"""W11 judging, parallel transport. PROMPTS AND MODEL UNCHANGED.

D-038: at 600 generations x 2 judges the serial transport in landing_gap.py /
direction_judge.py runs at ~0.2 calls/s -> ~2 h of wall clock for one packet's judging.
This driver dispatches the SAME prompt strings to the SAME pinned model through a thread
pool. What changes is transport only:

  * D-013's SIGALRM stall guard is main-thread-only, so it is replaced by a per-future
    timeout of the same length (90 s) plus the SDK's own 60 s timeout; a stalled worker
    costs one slot instead of the run.
  * the number judge's prompt is `value_leakage.judge.NUMBER_JUDGE_PROMPT`, imported;
    the direction judge's is `direction_judge.DIRECTION_JUDGE_PROMPT`, imported, with
    PR-003 item 5's per-attempt max_tokens escalation (600/2000/4000/4000) preserved.
  * caches are the same files, keyed the same way, so a serial run and this one are
    interchangeable and resumable from each other.

  python3 src/judge_w11_par.py --run --procs 12
"""

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import direction_judge as dj                              # noqa: E402
from judge_w11 import (RUN_ROOT, NUM_CACHE, DIR_CACHE, USAGE_OUT, MODEL,  # noqa: E402
                       PRICE_IN, PRICE_OUT, PAUSE_USD, estimate, rows)
from value_leakage.judge import NUMBER_JUDGE_PROMPT, parse_tagged_estimate  # noqa: E402

CALL_TRIES = 4
TIMEOUT_S = 90
_lock = threading.Lock()


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=dj.load_env_key("ANTHROPIC_API_KEY"),
                               timeout=60.0, max_retries=0)


def _call(body, budgets, usage, need_tags):
    """One judged call with retry + budget escalation. Thread-safe accounting."""
    last = None
    for attempt in range(CALL_TRIES):
        try:
            msg = _client().messages.create(
                model=dj.JUDGE_MODEL, max_tokens=budgets[min(attempt, len(budgets) - 1)],
                messages=[{"role": "user", "content": body}])
            raw = "".join(b.text for b in msg.content if b.type == "text")
            with _lock:
                usage["in"] += msg.usage.input_tokens
                usage["out"] += msg.usage.output_tokens
                usage["calls"] += 1
            if need_tags and dj.parse_verdict(raw) == (None, None):
                raise RuntimeError("empty or tagless reply")
            return raw
        except Exception as exc:
            last = exc
    raise RuntimeError("judge call failed %d times: %r" % (CALL_TRIES, last))


def _pool(items, fn, procs, label):
    out, done = {}, 0
    with ThreadPoolExecutor(max_workers=procs) as exe:
        futs = {exe.submit(fn, k): k for k in items}
        for f in as_completed(futs):
            k = futs[f]
            try:
                out[k] = f.result(timeout=TIMEOUT_S * CALL_TRIES)
            except Exception as exc:
                print("  %s FAILED %r: %r" % (label, k if len(str(k)) < 60 else "…", exc))
            done += 1
            if done % 50 == 0:
                print("  %s %d/%d" % (label, done, len(items)), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--procs", type=int, default=12)
    a = ap.parse_args()
    est = estimate()
    if not a.run:
        return 0
    if not est["under_pause_line"]:
        print("PAUSING: projected $%.2f exceeds $%.2f." % (est["total_est_usd"], PAUSE_USD))
        return 2

    rs = rows()
    u_num = {"in": 0, "out": 0, "calls": 0}
    u_dir = {"in": 0, "out": 0, "calls": 0}

    # ---- extractor 1, the number judge (cache keyed by exact answer text) ----
    nc = json.loads(NUM_CACHE.read_text()) if NUM_CACHE.exists() else {}
    mc = nc.setdefault(MODEL, {})
    todo = sorted({(v or "") for _, _, _, _, v, _ in rs if (v or "").strip()} - set(mc))
    print("number judge: %d unique answers to call (%d cached)" % (len(todo), len(mc)))
    got = _pool(todo, lambda t: parse_tagged_estimate(
        _call(NUMBER_JUDGE_PROMPT.format(llm_text=t), (200,), u_num, False)),
        a.procs, "num")
    mc.update(got)
    NUM_CACHE.write_text(json.dumps(nc, indent=2))

    # ---- the FROZEN direction judge (cache keyed by model|form|cond|i) -------
    dc = json.loads(DIR_CACHE.read_text()) if DIR_CACHE.exists() else {}
    byk = {k: (f, c, p, v, r) for k, f, c, p, v, r in rs}
    todo2 = [k for k in byk if dc.get(k, {}).get("direction") is None]
    print("direction judge: %d to call (%d cached)" % (len(todo2), len(dc)))

    def one_dir(k):
        f, c, p, v, r = byk[k]
        raw = _call(dj.DIRECTION_JUDGE_PROMPT.format(prompt=p, response=v),
                    (600, 2000, 4000, 4000), u_dir, True)
        m, d = dj.parse_verdict(raw)
        return {"form": f, "condition": c, "i": r["i"], "mentions_bet": m,
                "direction": d, "raw": raw}

    dc.update(_pool(todo2, one_dir, a.procs, "dir"))
    DIR_CACHE.write_text(json.dumps(dc, indent=2))

    c_n = u_num["in"] / 1e6 * PRICE_IN + u_num["out"] / 1e6 * PRICE_OUT
    c_d = u_dir["in"] / 1e6 * PRICE_IN + u_dir["out"] / 1e6 * PRICE_OUT
    prev = json.loads(USAGE_OUT.read_text()) if USAGE_OUT.exists() else {}
    USAGE_OUT.write_text(json.dumps(
        {"estimate": est, "transport": "parallel (D-038); prompts and model unchanged",
         "procs": a.procs,
         "number_judge": dict(u_num, usd=round(c_n, 4)),
         "direction_judge": dict(u_dir, usd=round(c_d, 4)),
         "actual_total_usd": round(c_n + c_d, 4),
         "projection_error_pct": round(100 * (est["total_est_usd"] - (c_n + c_d))
                                       / (c_n + c_d), 1) if (c_n + c_d) else None,
         "prior_partial_serial_run": prev.get("actual_total_usd")}, indent=2))
    print("\nnumber   $%.4f (%d calls, in/out %d/%d)" % (c_n, u_num["calls"], u_num["in"], u_num["out"]))
    print("direction $%.4f (%d calls, in/out %d/%d)" % (c_d, u_dir["calls"], u_dir["in"], u_dir["out"]))
    print("ACTUAL total $%.4f vs projection $%.3f" % (c_n + c_d, est["total_est_usd"]))
    print("cached-but-uncounted: the ~30 number-judge calls from the aborted serial run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
