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

## Where things stand (end of W5)

W0–W4 accepted (**R-003**, **V-001**, **V-002**, **V-003**, **V-006**, **V-009**).
**PR-001** remains the pre-registration of record; **PR-002**, **PR-003** and **PR-004** bind.
**R-008** pivoted the model to `Qwen2.5-14B-Instruct`; **R-009 (owner-approved)** re-targeted
the interp work from the prompt-stated favoured side `p` to the **trace-level believed
favoured side `p̂`**. **R-010** set the transfer policy: activation analysis runs pod-side, the
laptop receives summaries, scalars, direction tensors and a subsample — never the full tensors.

**Gate G1 FAILED at W3** (form A +0.017, form B +0.120). The live finding is the
belief-conditional decomposition (P-005). **W4** replayed all 700 traces with hooks
(6,668 points, 48 layers × 5,120, 34/34 decode check, P-006/V-008).

**W5 complete (P-007, V-010).** v_p̂, the layer profile, probes with 1000-draw nulls, and
cross-form invariance, all computed pod-side against PR-004 frozen beforehand (commit
`956052c`, 91 s before the analysis started).

- **Form B carries the believed direction; form A does not.** p̂ probe balanced accuracy at
  the pre-registered ℓ\* = 22: **B 0.743 (p = 0.001)**, **A 0.524 (p = 0.324)**. Form A is
  below its null at **0 of 48 layers**; form B is above at **42 of 48**, peaking 0.760 at
  layer 27. The d_t positive control reaches 0.96/0.99 on the same points and pipeline, so the
  apparatus is not the reason.
- **ℓ\* = 22 is a noise argmax.** PR-004 fixed ℓ\* as the argmax of the form-A curve, and
  that curve is never significant. The signal band is **layers ~24–36**: cross-form cosine
  beats its null at layers 21–36 (peak **0.426** at layer 30), transfer A→B at layers 24–41
  (peak **0.760** at layer 28). At ℓ\* the cosine **passes** (0.261 vs null p95 0.244,
  p = 0.045) and transfer **fails** (0.531, p = 0.203).
- **Decodability is pre-verbalization.** 155/163 (A) and 196/203 (B) est points precede the
  trace's first `good cause`/`bad cause` token, so the "after" cell (~2 traces) is not
  estimable and form B's 0.743 is entirely a before-the-belief-is-stated number.
- **cos(v_p, v_p̂)** at ℓ\*: B **0.432**, A **0.051** — related, not collinear, which is what
  makes R-009's pivot non-cosmetic.
- **Infrastructure: closed out.** `io6c1fhnarzoj9` **resumed on the first attempt** once the
  account was funded (D-023 — the first resume in the project; D-021's "four of four" conflated
  capacity refusals with a billing refusal), so no recompute was needed. All six activation
  files were verified pod-side (rows == index, 30/30 decode, V-010) and **all three pods are
  now terminated**: account balance $24.05, `currentSpendPerHr` **$0.00**, no volume anywhere.
- **The 3.28 GB of W4 tensors no longer exist.** What survives is
  `runs/w5_subsample/` (588 MB, gitignored, MANIFESTed): the pre-registered 10 % subsample and
  — added as JC-4 after the analysis was frozen — the **analysis cell** (528 est points of both
  `above_good` arms), because the 10 % rule lands only 17 cell points per form and cannot
  support PR-004's recount (**D-024**). `python3 src/w5_recount.py` rebuilds v_p̂(ℓ\*) from the
  cell at **cosine 1.000000**.

**Spend: $12.18 GPU + $6.35 API = $18.53 of $60.** W5 cost **$0.84 GPU and $0.00 API**.
Owner-clock minutes were never supplied, across seven asks; per **R-010(5)** the asks have
**stopped** and **D-025** records that time accounting rests on runner wall time alone.

**Next: the researcher reads the layer profile and rules on the intervention design** (which is
where H1/H2/H3-as-p̂ are decided). W7–W9 need a fresh pod and will have to regenerate the W4
tensors (`python src/replay_w4.py`, 94.8 s of forward passes, ~$0.12) or hook during generation
directly.

Tooling in `src/`: `pod.py` · `pod_survey.py` · `runpod_client.py` · `extract_runpod_key.py` ·
`bootstrap.sh` (interpreter-aware since D-022) · `provision_pod.sh` · `gen_neutral.py` ·
`gen_mirrored.py` · `gen_w3.py` · `prompts_w3.py` · `extract_regex.py` · `tau.py` ·
`landing_gap.py` · `behaviour_w3.py` · `direction_judge.py` · `recount_w2.py` · `recount_w3.py` ·
`trace_sample.py` · `trace_sample_w2.py` · `samples_w3.py` · `samples_w4.py` ·
`judge_check_w4.py` · `replay_w4.py` · **`direction_w5.py`** · **`w5_integrity.py`** ·
**`w5_cell.py`** · **`w5_recount.py`** · both smoke scripts.
Laptop-side judging/analysis runs in `.venv-w1/` (now also holds `scikit-learn`, which is what
makes `--smoke` and `w5_recount.py` laptop-reproducible).
