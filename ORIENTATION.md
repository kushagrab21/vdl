# ORIENTATION.md — read this first

A fresh runner must be able to re-orient from **this file + the tail of `RESULTS.md`** alone.

## The project

Value-direction localization in Value Leakage. The setting: a model Fermi-estimates an
unknowable quantity (black spots on all living giraffes); a stated donation bet makes one side
of a threshold τ "favoured"; prior black-box work (predecessor project, `../RESULTS.md`)
established that estimates systematically land on the favoured side.

**This project asks where the favoured side is represented in the residual stream of a small
open-weights model, and whether editing that representation changes the behaviour.** Arc:
screen small models for the phenotype → collect a frozen behavioural dataset → replay traces
with activation hooks → compute a candidate value direction `v_p` → three rungs of
intervention.

## Roles

- **RESEARCHER** — designs experiments, audits reports, promotes `P-` → `E-`. No code execution.
- **RUNNER** (you) — executes one work order at a time on real hardware; reports back.
  Each order is self-contained because runner context may vanish between packets.
- **OWNER / COURIER** — relays messages between researcher and runner; **approves all spend.**

## Hard limits

- **$60 total GPU spend.** Owner approves any raise. **Stop and surface before crossing $45
  cumulative.**
- **16 h owner clock.**
- Write-up submitted **Friday 2026-09-05**.

## Ledger rules (`RESULTS.md`)

Append-only. Entries numbered per kind, **never edited** — a wrong entry is corrected by a later
entry that names it. Every number in an `E-` entry states: **metric definition, filter set, n,
source file(s), and the exact command that regenerates it.**

| kind | meaning |
|---|---|
| `F-` | freeze / setup fact (commit hashes, versions, hardware) |
| `PR-` | pre-registration — rules frozen **before** the data they govern is read; cites the packet it binds |
| `E-` | established result (audited; the write-up is built only from `E-` and `V-`) |
| `P-` | provisional result, awaiting audit; promoted to `E-` by a `V-` |
| `V-` | audit / verification note — what was recounted, matched or not |
| `D-` | deviation, surprise, or extractor disagreement |
| `R-` | researcher ruling — transcribed **verbatim** when the courier delivers it |
| `G-` | gate outcome (G0, G1, …) — pass/fail with the evidence cited |
| `T-` | time: owner-clock minutes (courier supplies), runner wall time, GPU hours |
| `S-` | spend: instance type, $/hr, hours this packet, cumulative $ against the $60 cap |

## Standing constraints (every packet)

1. `upstream/` is **frozen**; all new code in new files under `src/`. Verify with
   `git -C upstream status --porcelain` → must print nothing.
2. Every reported number must be regenerable by a **named command over committed files**. No
   number enters the ledger from memory or from a scrolled-away terminal.
3. **Secrets** (HF tokens, RunPod/API keys) live in environment variables or untracked `.env`
   files — never in commands pasted into reports, never in the ledger, never committed.
4. **Report every judgment call.** When an instruction is ambiguous: choose, record the choice,
   and flag it — never silently interpret.
5. The ledger is **append-only**; corrections are new entries.
6. Per-packet `T-` and `S-` entries are **mandatory**. If cumulative spend would cross **$45**,
   stop and surface before continuing.
7. If a result is surprising: **first** hypothesis is a bug in new code, **second** is a flaw in
   the instruction, **third** is a discovery. Report which you checked.
8. **Do not start the next packet's work early.** Stop at the end of the order and report.

## Layout

```
vdl/
  RESULTS.md       the ledger — append-only
  ORIENTATION.md   this file
  upstream/        frozen clone @ 16d1298… — NEVER modified
  src/             all new code, this project only
  runs/            raw generation data (gitignored; inventoried in MANIFEST.md)
  analysis/out/    generated CSVs/JSONs that feed the write-up (committed)
```

## Packet map

Packet map (details arrive one order at a time):
```
W0  ledger, upstream freeze, environment (done; GPU half re-issued as W0b)
W0b pod provisioning, GPU verification, stack install, smoke tests (this packet)
W1  pre-registration (screening rule, parse rule, tie convention, extractors, gate G0)
    + neutral calibration: ~50 no-bet rollouts/model to set each model's τ
W2  mirrored screening across small models; gate G0 selects the model or stops the project
W3  behavioural baseline on the chosen model: the frozen dataset (~150/side × 2 surface forms)
W4  activation replay of W3 traces with hooks; positional acceptance check is load-bearing
W5  value direction v_p (per-layer difference-in-means) + probes + shuffled-label nulls
W6  invariance tests: cross-surface and cross-mirror transfer; control probes must NOT transfer
W7  intervention I: ablate/subtract v_p during generation; landing gap vs random-direction null
W8  intervention II: inject ±α·v_p on neutral prompts; dose-response (priority rung if time binds)
W9  intervention III: mirrored macrostate patch; single- vs all-points (H1/H2/H3 fork)
W10 skepticism pass, build script, write-up assembly from E-/V- entries only
```
Delivered by the W0b order; topology by ruling **R-004**.

## Where things stand (end of W7)

W0–W5 accepted (**R-003**, **V-001**, **V-002**, **V-003**, **V-006**, **V-009**, **V-011**).
**PR-001** remains the pre-registration of record; **PR-002**–**PR-005** bind. **R-008** pivoted
the model to `Qwen2.5-14B-Instruct`; **R-009 (owner-approved)** re-targeted the interp work to
the trace-level believed favoured side `p̂`; **R-010** set the transfer policy.

**Gate G1 FAILED at W3** (form A +0.017, form B +0.120). **W4** replayed all 700 traces with
hooks (6,668 points, 34/34 decode check). **W5** produced v_p̂ (P-007, V-010): form B's p̂ probe
reaches **0.743 at ℓ\*=22** (p=0.001) and **0.760 at L27**, form A is flat at every layer, and
form B's decodability is **entirely pre-verbalization**. The result of record at ℓ\*=22 is a
**marginal cosine pass (0.2608 vs null p95 0.2443)** and a **transfer FAIL (0.5310)**; the
layers-24–36 band is **EXPLORATORY** and labelled so everywhere (V-011).

**W7 complete (F-015, P-008, V-012).** The project's one causal rung. 23 arms × 50 = **1,150
steered generations** on a fresh A100, PR-005 frozen **13 minutes** before the first steered
token. Injection is α·‖Δμ‖·u added to L27's (or L30's) output at every decode position;
‖Δμ‖ = 12.726 at L27, and α=2 is 22.8 % of the residual-stream norm.

- **The intervention is powerfully causal and not believed-side-specific.** At α=+4 the median
  estimate falls **three orders of magnitude** (9.5×10⁹ → 6.7×10⁶) and landing falls 0.68 → 0.04,
  with **fluent, on-task, arithmetic-showing text** — coherence is **1.000 in 22 of 23 arms**,
  zero degenerate generations in 1,150, so the |α|-halving retry was never triggered.
- **The pre-registered primary test FAILS.** PR-005 froze +α as the believed-**above** pole, so
  +α should have *raised* P(final > τ_B). Δ+ = **−0.34**, beating **0 of 10** matched random
  directions (one-sided p = 1.000); Δ± = −0.14, beats 7/10. Dose-response is an **inverted U
  centred on sham**, monotone in |α| and **not** in α (Spearman ρ = −0.131, p = 0.016 — significant
  and negative).
- **The verbalized flip does not survive.** +0.213 in the predicted direction but CI
  **[−0.041, +0.466]** includes zero; it is carried entirely by the −α arm; the mirrored
  `below_good` arm does not move (0.049 vs 0.068); and a **random** direction (seed 9005) reaches
  P(p̂=+1) = **0.878** against v_p̂'s 0.700 and sham's 0.692.
- **The neutral rung is the sharpest result.** With the bet removed there is nothing to
  rationalize, and ±2 still moves the median estimate by **0.54 log10** and landing by **0.28**
  (CI [−0.46, −0.10]).
- **PR-005 item 6 therefore resolves to its fourth row: v_p̂ is correlational, reported at full
  volume as the null result.** H3′ is **[not tested]**. The leading alternative — that the
  pre-registered α grid sits entirely in a regime where generic distortion dominates (the ten
  nulls suppress landing by 0.158 on average) — is stated in P-008(7) and is **not separable**
  by this design, because no α small enough was pre-registered.
- **Register entry (D-028):** *PR-004 froze the right statistic at the wrong layer; PR-005 froze
  the right statistic at the wrong dose.*
- **Infrastructure: clean.** `heenrekmx8f4da` created 05:51:31, terminated **06:23:00** (HTTP
  204); `/pods` empty, `currentSpendPerHr` $0.00, no volume. **72.7 % of billed GPU time was
  compute** (best in the project), because V-011's laptop-smoke-before-provisioning rule was
  executed: 7/7 smoke plus an end-to-end 0.5B rehearsal before a pod existed.

**Spend: $12.91 GPU + $14.13 API = $27.04 of $60.** W7 cost **$0.73 GPU and $7.78 API** — and
the API projection under-shot by **53 %** (**D-027**: 4 chars/token is really ~3.2, and
sonnet-5's thinking block makes the direction judge cost ~117 output tokens per call, not 20).
**The API is now the dominant spend line.** The $45 threshold is not approached.

**Next: W10 only** — skepticism pass, build script, write-up assembly from `E-`/`V-` entries.
**Do not start it:** the researcher reads `analysis/out/w7_samples/*.md` (13 arms × 10 traces at
the blind indices 0–9) before any W7 number is promoted to `E-`.

Tooling in `src/`: `pod.py` · `pod_survey.py` · `runpod_client.py` · `extract_runpod_key.py` ·
`bootstrap.sh` (interpreter-aware since D-022) · `provision_pod.sh` · `gen_neutral.py` ·
`gen_mirrored.py` · `gen_w3.py` · `prompts_w3.py` · `extract_regex.py` · `tau.py` ·
`landing_gap.py` · `behaviour_w3.py` · `direction_judge.py` · `recount_w2.py` · `recount_w3.py` ·
`trace_sample.py` · `trace_sample_w2.py` · `samples_w3.py` · `samples_w4.py` ·
`judge_check_w4.py` · `replay_w4.py` · **`direction_w5.py`** · **`w5_integrity.py`** ·
**`w5_cell.py`** · **`w5_recount.py`** · **`steer_w7.py`** · **`analyze_w7.py`** · **`samples_w7.py`** · **`w7_recount.py`** · both smoke scripts.
Laptop-side judging/analysis runs in `.venv-w1/` (now also holds `scikit-learn`, which is what
makes `--smoke` and `w5_recount.py` laptop-reproducible).
