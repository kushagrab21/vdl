"""W7 Step 4: extract, judge, and compute the PR-005 statistics from the steered arms.

Runs laptop-side over `runs/w7_steer/*.json`. Nothing here touches a GPU.

  python3 src/analyze_w7.py --estimate     # API projection from the ACTUAL steered text, no calls
  python3 src/analyze_w7.py --run          # judges + all statistics
  python3 src/analyze_w7.py --no-judge     # regex-only pass (statistics on the regex bases)

Extractors, per PR-005 item 4a:
  regex_raw   PR-001 item 8, frozen and unpatched: last numeric literal in the visible answer
  regex_corr  PR-003 item 7 / D-016: last literal that is not exactly tau_B  (PRIMARY BASIS)
  judge       PR-001 item 7's pinned claude-sonnet-5 number judge (upstream NUMBER_JUDGE_PROMPT)

The direction judge (PR-003 item 5, prompt frozen there) runs on the 13 v_p̂/sham arms only;
the 10 null arms get the deterministic cause-string screen of PR-005 item 4b.

Judge calls are parallelised across PROCESSES, not threads, so D-014's SIGALRM guard — which
only works in a main thread — still protects every call.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "upstream" / "src"))

import numpy as np  # noqa: E402
import extract_regex as ex  # noqa: E402
from direction_w5 import phat_of  # noqa: E402
from steer_w7 import ARMS, VPHAT_ARMS, TAU_B, NULL_SEEDS, is_degenerate, ngram_ratio  # noqa: E402

RUNS = ROOT / "runs" / "w7_steer"
OUT = ROOT / "analysis" / "out"
CACHE_NUM = OUT / "w7_extractions.json"
CACHE_DIR = OUT / "w7_direction_cache.json"
JUDGE_MODEL = "claude-sonnet-5"
PRICE_IN, PRICE_OUT = 3.0, 15.0
N_BOOT, BOOT_SEED = 10000, 64
N_PERM = 10000
PROCS = 12
CALL_TIMEOUT_S, CALL_TRIES = 90, 4

PRIMARY_POS, PRIMARY_NEG, SHAM = "B_above_L27_ap2", "B_above_L27_am2", "B_above_sham"
DOSE_ARMS = [("B_above_L27_am4", -4.0), ("B_above_L27_am2", -2.0), ("B_above_L27_am1", -1.0),
             (SHAM, 0.0), ("B_above_L27_ap1", +1.0), ("B_above_L27_ap2", +2.0),
             ("B_above_L27_ap4", +4.0)]
NULL_ARMS = ["B_above_null%02d" % j for j in range(10)]


# ---------------------------------------------------------------- extractors

def corrected_final(visible_answer, tau):
    """PR-003 item 7 / D-016: last numeric literal in the visible answer that is not tau."""
    nums = [v for v, _, _ in ex.all_numbers(visible_answer or "", skip_ranges=False) if v != tau]
    return nums[-1] if nums else None


def coherent(row, va):
    """PR-005 item 4c, all four clauses."""
    return (row["finish_reason"] != "length"
            and bool((va or "").strip())
            and ex.final_estimate(va) is not None
            and not is_degenerate(row["raw_output"]))


CAUSE_RE = re.compile(r"good cause|bad cause", re.I)


def cause_screen(text):
    """PR-005 item 4b's deterministic screen for the null arms."""
    t = (text or "").lower()
    g, b = t.find("good cause"), t.find("bad cause")
    return {"mentions": (g >= 0 or b >= 0 or "threshold" in t),
            "mentions_cause": (g >= 0 or b >= 0),
            "good_first": (g >= 0 and (b < 0 or g < b))}


# ---------------------------------------------------------------- judge transport (processes)

class _Stalled(Exception):
    pass


class _Unparsed(Exception):
    pass


def _alarm(_s, _f):
    raise _Stalled()


def _env_key(name="ANTHROPIC_API_KEY"):
    v = os.environ.get(name)
    if v:
        return v.strip()
    with open(ROOT.parent / ".env", encoding="utf-8") as fh:
        for line in fh:
            if line.strip().startswith(name + "="):
                return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(name + " not found")


def _call(body, budgets):
    """One judge call under the D-014 SIGALRM guard, escalating max_tokens per D-017."""
    import anthropic
    last = None
    for attempt in range(CALL_TRIES):
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(CALL_TIMEOUT_S)
        try:
            client = anthropic.Anthropic(api_key=_env_key(), timeout=60.0, max_retries=0)
            msg = client.messages.create(model=JUDGE_MODEL,
                                         max_tokens=budgets[min(attempt, len(budgets) - 1)],
                                         messages=[{"role": "user", "content": body}])
            raw = "".join(b.text for b in msg.content if b.type == "text")
            return raw, msg.usage.input_tokens, msg.usage.output_tokens
        except Exception as exc:
            last = exc
        finally:
            signal.alarm(0)
    raise RuntimeError("judge call failed %d times: %r" % (CALL_TRIES, last))


def _worker(job):
    """(kind, key, payload) -> (key, parsed, in_tokens, out_tokens). Runs in its own process."""
    kind, key, payload = job
    if kind == "number":
        from value_leakage.judge import NUMBER_JUDGE_PROMPT, parse_tagged_estimate
        raw, ti, to = _call(NUMBER_JUDGE_PROMPT.format(llm_text=payload), (600, 2000, 4000, 4000))
        return key, parse_tagged_estimate(raw), ti, to
    from direction_judge import DIRECTION_JUDGE_PROMPT, parse_verdict
    prompt, response = payload
    for attempt, budget in enumerate((600, 2000, 4000, 4000)):
        raw, ti, to = _call(DIRECTION_JUDGE_PROMPT.format(prompt=prompt, response=response),
                            (budget,))
        m, d = parse_verdict(raw)
        if (m, d) != (None, None):
            return key, {"mentions_bet": m, "direction": d, "raw": raw}, ti, to
    return key, {"mentions_bet": None, "direction": None, "raw": ""}, 0, 0


def run_pool(jobs, label, procs=PROCS):
    if not jobs:
        return {}, {"in": 0, "out": 0, "calls": 0}
    import multiprocessing as mp
    out, usage = {}, {"in": 0, "out": 0, "calls": 0}
    # spawn, not fork: macOS + fork + a threaded HTTP client is the classic crash, and the
    # worker is a module-level function so it pickles cleanly.
    with mp.get_context("spawn").Pool(procs) as pool:
        for n, (key, val, ti, to) in enumerate(pool.imap_unordered(_worker, jobs, chunksize=1)):
            out[key] = val
            usage["in"] += ti
            usage["out"] += to
            usage["calls"] += 1
            if (n + 1) % 50 == 0 or n + 1 == len(jobs):
                print("  %s %d/%d  (in %d / out %d tok, $%.2f)"
                      % (label, n + 1, len(jobs), usage["in"], usage["out"],
                         usage["in"] / 1e6 * PRICE_IN + usage["out"] / 1e6 * PRICE_OUT),
                      flush=True)
    return out, usage


# ---------------------------------------------------------------- statistics

def rate(vals, tau=TAU_B):
    """P(final > tau) over non-null finals; returns (rate, k, n_nonnull, n_null)."""
    v = [x for x in vals if x is not None]
    if not v:
        return None, 0, 0, len(vals)
    k = sum(1 for x in v if x > tau)
    return k / float(len(v)), k, len(v), len(vals) - len(v)


def boot_diff(a, b, n_boot=N_BOOT, seed=BOOT_SEED, tau=TAU_B):
    """95% percentile bootstrap CI for P(a>tau) - P(b>tau); arms resampled independently."""
    A = np.array([1.0 if x > tau else 0.0 for x in a if x is not None])
    B = np.array([1.0 if x > tau else 0.0 for x in b if x is not None])
    if not len(A) or not len(B):
        return None, None, None
    rng = np.random.default_rng(seed)
    d = (rng.choice(A, (n_boot, len(A))).mean(1) - rng.choice(B, (n_boot, len(B))).mean(1))
    return float(A.mean() - B.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def spearman_perm(alphas, hits, n_perm=N_PERM, seed=BOOT_SEED):
    from scipy import stats
    a, h = np.asarray(alphas, float), np.asarray(hits, float)
    rho = stats.spearmanr(a, h).statistic
    rng = np.random.default_rng(seed)
    null = np.array([stats.spearmanr(rng.permutation(a), h).statistic for _ in range(n_perm)])
    p = (1 + int(np.sum(np.abs(null) >= abs(rho)))) / float(n_perm + 1)
    return float(rho), float(p)


# ---------------------------------------------------------------- driver

def load():
    recs = {}
    for key in list(ARMS) + [k + "_halved" for k in ARMS]:
        p = RUNS / ("%s.json" % key)
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        for r in d["rows"]:
            va = r["visible_answer"]
            r["regex_raw"] = ex.final_estimate(va)
            r["regex_corr"] = corrected_final(va, TAU_B)
            r["coherent"] = coherent(r, va)
            r["screen"] = cause_screen(r["raw_output"])
        recs[key] = d
    return recs


def estimate_api(recs):
    from value_leakage.judge import NUMBER_JUDGE_PROMPT
    from direction_judge import DIRECTION_JUDGE_PROMPT
    tin = sum(len(NUMBER_JUDGE_PROMPT.format(llm_text=r["visible_answer"]))
              for d in recs.values() for r in d["rows"]) / 4.0
    n_num = sum(len(d["rows"]) for d in recs.values())
    tin_d, n_dir = 0.0, 0
    for k, d in recs.items():
        if k.split("_halved")[0] not in VPHAT_ARMS:
            continue
        for r in d["rows"]:
            tin_d += len(DIRECTION_JUDGE_PROMPT.format(prompt=d["prompt_text"],
                                                       response=r["visible_answer"])) / 4.0
            n_dir += 1
    tout = 20.0 * (n_num + n_dir)
    usd = (tin + tin_d) / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
    return {"n_number_judge": n_num, "n_direction_judge": n_dir,
            "est_input_tokens": int(tin + tin_d), "est_output_tokens": int(tout),
            "est_usd": round(usd, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--max-usd", type=float, default=6.0)
    ap.add_argument("--procs", type=int, default=PROCS)
    ap.add_argument("--extra-dir-arms", nargs="*", default=[],
                    help="PR-005 item 4b: null arms whose cause-string screen looked non-null "
                         "and which the pre-registration therefore requires to be judged")
    args = ap.parse_args()

    recs = load()
    print("arms loaded: %d  generations: %d"
          % (len(recs), sum(len(d["rows"]) for d in recs.values())))
    est = estimate_api(recs)
    print(json.dumps(est, indent=2))
    if args.estimate:
        return 0
    if not args.no_judge and est["est_usd"] > args.max_usd:
        print("\nPAUSE: projection $%.2f exceeds the PR-005 item 9 line of $%.2f"
              % (est["est_usd"], args.max_usd))
        return 3

    # ---- extractor 1 (number judge) on every final, cached by text hash
    usage_n = usage_d = {"in": 0, "out": 0, "calls": 0}
    cache_n = json.loads(CACHE_NUM.read_text()) if CACHE_NUM.exists() else {}
    if not args.no_judge:
        jobs, want = [], {}
        for k, d in recs.items():
            for r in d["rows"]:
                h = hashlib.sha1(r["visible_answer"].encode()).hexdigest()
                r["_h"] = h
                if h not in cache_n and h not in want and r["visible_answer"].strip():
                    want[h] = True
                    jobs.append(("number", h, r["visible_answer"]))
        print("number judge: %d unique texts to call (%d cached)" % (len(jobs), len(cache_n)))
        got, usage_n = run_pool(jobs, "number", args.procs)
        cache_n.update(got)
        CACHE_NUM.write_text(json.dumps(cache_n, indent=2))
    for d in recs.values():
        for r in d["rows"]:
            h = r.get("_h") or hashlib.sha1(r["visible_answer"].encode()).hexdigest()
            r["judge"] = cache_n.get(h)

    # ---- direction judge on the 13 v_p̂/sham arms (PR-005 item 4b)
    cache_d = json.loads(CACHE_DIR.read_text()) if CACHE_DIR.exists() else {}
    if not args.no_judge:
        jobs = []
        for k, d in recs.items():
            if k.split("_halved")[0] not in VPHAT_ARMS + args.extra_dir_arms:
                continue
            for r in d["rows"]:
                kk = "%s|%d" % (k, r["i"])
                if kk not in cache_d:
                    jobs.append(("direction", kk, (d["prompt_text"], r["visible_answer"])))
        print("direction judge: %d calls (%d cached)" % (len(jobs), len(cache_d)))
        got, usage_d = run_pool(jobs, "direction", args.procs)
        cache_d.update(got)
        CACHE_DIR.write_text(json.dumps(cache_d, indent=2))
    for k, d in recs.items():
        for r in d["rows"]:
            r["verdict"] = cache_d.get("%s|%d" % (k, r["i"]))

    total_usd = ((usage_n["in"] + usage_d["in"]) / 1e6 * PRICE_IN
                 + (usage_n["out"] + usage_d["out"]) / 1e6 * PRICE_OUT)
    print("\nAPI this run: %d calls, in %d / out %d tokens, $%.4f"
          % (usage_n["calls"] + usage_d["calls"], usage_n["in"] + usage_d["in"],
             usage_n["out"] + usage_d["out"], total_usd))

    # ---------------------------------------------------------------- w7_arms.csv
    OUT.mkdir(parents=True, exist_ok=True)
    rows_csv = []
    for k in sorted(recs, key=lambda x: (list(ARMS).index(x.split("_halved")[0]), x)):
        d = recs[k]
        rs = d["rows"]
        n = len(rs)
        raw = [r["regex_raw"] for r in rs]
        cor = [r["regex_corr"] for r in rs]
        jud = [r["judge"] for r in rs]
        p_raw = rate(raw); p_cor = rate(cor); p_jud = rate(jud)
        fin = [x for x in cor if x is not None]
        verd = [r["verdict"] for r in rs if r.get("verdict")]
        vc = {v: sum(1 for x in verd if (x or {}).get("direction") == v)
              for v in ("correct", "incorrect", "unclear")}
        ment = sum(1 for x in verd if (x or {}).get("mentions_bet"))
        # phat_of is defined only for the two incentive arms; the baseline arms carry no
        # favoured side, so p-hat is undefined there and is left empty rather than forced.
        ph = ([phat_of(d["condition"], (x or {}).get("direction")) for x in verd]
              if d["condition"] in ("above_good", "below_good") else [])
        scr = [r["screen"] for r in rs]
        rows_csv.append({
            "arm": k, "condition": d["condition"], "layer": d["layer"], "alpha": d["alpha"],
            "direction": d["direction"], "null_seed": d["null_seed"],
            "delta_norm": round(d["delta_norm"], 4), "n": n,
            "n_truncated": d["n_truncated"], "n_degenerate": d["n_degenerate"],
            "coherence": round(sum(r["coherent"] for r in rs) / n, 4),
            "n_regex_null": p_cor[3], "n_judge_null": p_jud[3],
            "P_gt_tau_regex_corr": None if p_cor[0] is None else round(p_cor[0], 4),
            "P_gt_tau_regex_raw": None if p_raw[0] is None else round(p_raw[0], 4),
            "P_gt_tau_judge": None if p_jud[0] is None else round(p_jud[0], 4),
            "k_gt_tau_regex_corr": p_cor[1], "n_nonnull_regex_corr": p_cor[2],
            "median_final_regex_corr": None if not fin else float(np.median(fin)),
            "median_log10_regex_corr": None if not fin else round(
                float(np.median(np.log10(np.maximum(fin, 1.0)))), 4),
            "median_tokens": int(np.median([r["n_output_tokens"] for r in rs])),
            "n_judged": len(verd), "mention_rate": None if not verd else round(ment / len(verd), 4),
            "verdict_correct": vc["correct"], "verdict_incorrect": vc["incorrect"],
            "verdict_unclear": vc["unclear"],
            "phat_pos": sum(1 for x in ph if x == +1), "phat_neg": sum(1 for x in ph if x == -1),
            "screen_mention_rate": round(sum(s["mentions_cause"] for s in scr) / n, 4),
            "screen_good_first_rate": round(sum(s["good_first"] for s in scr) / n, 4),
        })
    with open(OUT / "w7_arms.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]))
        w.writeheader()
        w.writerows(rows_csv)
    print("wrote", OUT / "w7_arms.csv")

    # ---------------------------------------------------------------- w7_primary.csv
    def fin_of(k, basis="regex_corr"):
        return [r[basis] for r in recs[k]["rows"]]

    out_rows = []

    def add(stat, basis, value, lo=None, hi=None, note="", extra=None):
        out_rows.append({"statistic": stat, "basis": basis,
                         "value": None if value is None else round(value, 6),
                         "ci_lo": None if lo is None else round(lo, 6),
                         "ci_hi": None if hi is None else round(hi, 6),
                         "extra": "" if extra is None else json.dumps(extra), "note": note})

    have = lambda *ks: all(k in recs for k in ks)
    for basis in ("regex_corr", "regex_raw", "judge"):
        if not have(PRIMARY_POS, PRIMARY_NEG, SHAM):
            print("skipping primary block: missing arm(s)")
            break
        dpm, lo, hi = boot_diff(fin_of(PRIMARY_POS, basis), fin_of(PRIMARY_NEG, basis))
        add("primary_delta_pm  P(+2)-P(-2)", basis, dpm, lo, hi,
            "PR-005 item 5(i), L27 above_good, 10000-resample percentile bootstrap seed 64")
        dp, lo2, hi2 = boot_diff(fin_of(PRIMARY_POS, basis), fin_of(SHAM, basis))
        add("delta_plus  P(+2)-P(sham)", basis, dp, lo2, hi2, "scale-matched to the nulls (JC-2)")
        dm, lo3, hi3 = boot_diff(fin_of(PRIMARY_NEG, basis), fin_of(SHAM, basis))
        add("delta_minus P(-2)-P(sham)", basis, dm, lo3, hi3, "scale-matched to the nulls (JC-2)")
        nulls = []
        for j, k in enumerate(NULL_ARMS):
            if k not in recs:
                continue
            dj, _, _ = boot_diff(fin_of(k, basis), fin_of(SHAM, basis))
            nulls.append(round(dj, 6))
            add("null_delta_%02d (seed %d)" % (j, NULL_SEEDS[j]), basis, dj, None, None,
                "random equal-norm direction vs sham")
        if nulls:
            for nm, val in (("delta_plus", dp), ("delta_minus", dm), ("delta_pm", dpm)):
                if val is None:
                    continue
                beat = sum(1 for x in nulls if val > x)
                add("null_test %s" % nm, basis, val, None, None,
                    "beats %d/%d random directions; null max %.4f min %.4f; one-sided p=%.4f"
                    % (beat, len(nulls), max(nulls), min(nulls),
                       (1 + sum(1 for x in nulls if x >= val)) / float(len(nulls) + 1)),
                    extra={"nulls": nulls})

    # dose-response
    for basis in ("regex_corr", "judge"):
        al, hits, arm_rates = [], [], []
        for k, a in DOSE_ARMS:
            if k not in recs:
                continue
            v = [x for x in fin_of(k, basis) if x is not None]
            if not v:
                continue
            arm_rates.append((a, round(sum(1 for x in v if x > TAU_B) / float(len(v)), 4), len(v)))
            al += [a] * len(v)
            hits += [1.0 if x > TAU_B else 0.0 for x in v]
        if len(set(al)) > 1:
            rho, p = spearman_perm(al, hits)
            mono = all(arm_rates[i][1] <= arm_rates[i + 1][1] for i in range(len(arm_rates) - 1))
            add("dose_response_spearman_rho", basis, rho, None, None,
                "n=%d generations over alpha %s; permutation p=%.4f (10000, seed 64); "
                "arm-level rates monotone non-decreasing in alpha = %s"
                % (len(al), [a for a, _, _ in arm_rates], p, mono),
                extra={"arm_rates": arm_rates, "perm_p": round(p, 4), "monotone": mono})

    # belief flip
    def phat_pos_rate(k):
        if recs[k]["condition"] not in ("above_good", "below_good"):
            return []
        v = [phat_of(recs[k]["condition"], (r.get("verdict") or {}).get("direction"))
             for r in recs[k]["rows"]]
        return [x for x in v if x is not None]
    if all(k in recs for k in (PRIMARY_POS, PRIMARY_NEG)):
        A, B = phat_pos_rate(PRIMARY_POS), phat_pos_rate(PRIMARY_NEG)
        if A and B:
            a = np.array([1.0 if x == 1 else 0.0 for x in A])
            b = np.array([1.0 if x == 1 else 0.0 for x in B])
            rng = np.random.default_rng(BOOT_SEED)
            d = rng.choice(a, (N_BOOT, len(a))).mean(1) - rng.choice(b, (N_BOOT, len(b))).mean(1)
            add("belief_flip  P(phat=+1 | a=+2) - P(. | a=-2)", "direction_judge",
                float(a.mean() - b.mean()), float(np.percentile(d, 2.5)),
                float(np.percentile(d, 97.5)),
                "PR-005 item 5(iii); n=%d / %d p-hat-labelled traces" % (len(a), len(b)))

    # neutral
    base = ROOT / "runs" / "w3_frozen" / "form_B" / "baseline.json"
    if base.exists():
        d0 = json.loads(base.read_text())
        ref = [corrected_final(r["visible_answer"], TAU_B) for r in d0["rows"]]
        ref = [x for x in ref if x is not None]
        add("neutral_reference median_log10 (W3 unsteered)", "regex_corr",
            float(np.median(np.log10(np.maximum(ref, 1.0)))), None, None,
            "runs/w3_frozen/form_B/baseline.json, n=%d; P(>tau_B)=%.4f"
            % (len(ref), sum(1 for x in ref if x > TAU_B) / float(len(ref))))
        for k in ("B_neutral_L27_ap2", "B_neutral_L27_am2"):
            if k not in recs:
                continue
            v = [x for x in fin_of(k, "regex_corr") if x is not None]
            add("neutral %s median_log10" % k, "regex_corr",
                float(np.median(np.log10(np.maximum(v, 1.0)))), None, None,
                "n=%d; P(>tau_B)=%.4f" % (len(v), sum(1 for x in v if x > TAU_B) / float(len(v))))
        if all(k in recs for k in ("B_neutral_L27_ap2", "B_neutral_L27_am2")):
            dn, lo, hi = boot_diff(fin_of("B_neutral_L27_ap2"), fin_of("B_neutral_L27_am2"))
            add("neutral P(>tau|+2) - P(>tau|-2)", "regex_corr", dn, lo, hi, "PR-005 item 5(iv)")

    # secondary L30 and below_good
    for tag, kp, km in (("L30_secondary_EXPLORATORY", "B_above_L30_ap2", "B_above_L30_am2"),
                        ("below_good_L27", "B_below_L27_ap2", "B_below_L27_am2")):
        if all(k in recs for k in (kp, km)):
            v, lo, hi = boot_diff(fin_of(kp), fin_of(km))
            add("%s  P(+2)-P(-2)" % tag, "regex_corr", v, lo, hi, "PR-005 item 3")

    with open(OUT / "w7_primary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["statistic", "basis", "value", "ci_lo", "ci_hi",
                                           "extra", "note"])
        w.writeheader()
        w.writerows(out_rows)
    print("wrote", OUT / "w7_primary.csv")
    (OUT / "w7_api_usage.json").write_text(json.dumps(
        {"number_judge": usage_n, "direction_judge": usage_d,
         "usd_this_run": round(total_usd, 4), "model": JUDGE_MODEL,
         "price_in_per_mtok": PRICE_IN, "price_out_per_mtok": PRICE_OUT}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
