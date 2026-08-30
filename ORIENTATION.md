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

## Where things stand (end of W4)

W0–W3 accepted (**R-003**, **V-001**, **V-002**, **V-003**, **V-006**). **PR-001** remains the
pre-registration of record; **PR-002** and **PR-003** bind. **R-008** pivoted the model to
`Qwen2.5-14B-Instruct`; **R-009 (pivot 2, owner-approved)** re-targets the interp work from the
prompt-stated favoured side `p` to the **trace-level believed favoured side `p̂`**, computed
**within** a condition, with an intervention rung asking whether the verbalized belief is
causally upstream of the estimate.

**Gate G1 FAILED at W3** (form A +0.017, CI [−0.097, 0.130]; form B +0.120, CI [0.007, 0.233];
D-018 winner's curse). The live finding is the **belief-conditional decomposition** (P-005):
direction-correct traces gap +0.28 (A) / +0.45 (B), direction-incorrect −0.68 / −0.55, with
`above_good` comprehension only ~54 %.

**W4 complete.** Two deliverables and one blocker.

1. **Judge validation (V-007, no GPU, no API).** The mechanical cause-mapping cross-check over
   all 600 judged traces: `unclear` is 96.4 % mapping-silent (the check behaves), `correct` is
   21.3 % (V-006's lenient case — it **dilutes** the conditional split, it cannot manufacture
   it), `incorrect` is **53.1 %**, and 67.7 % on form B `above_good`. Reading the printed
   `incorrect` traces shows the model mapping the sides in its own vocabulary rather than the
   prompt's, so the string test is an **upper bound on possible judge leniency, not a count of
   errors**. `analysis/out/w4_direction_sample2.md` holds the 4-cell sample the researcher must
   read before W5. Form A `below_good` has **zero** `incorrect` verdicts; form B `below_good`
   has only 4.
2. **Activation replay (P-006, V-008).** 700/700 traces replayed, **0 quarantined**, **6,668
   points** at 48 layers × 5,120 dims, bf16 forward / fp16 storage. The load-bearing acceptance
   check passed **34/34** — stored token-id spans decode to the parsed literals, commas
   included. Token reconstruction is verified four ways per trace against vLLM's own token
   counts, and the whole position index was built twice (laptop and pod) with **identical
   results for all 6,668 points**. The `est` counts reproduce P-004's trajectory-point counts
   exactly (254/255/276/273).
3. **BLOCKER (D-020): the RunPod account balance is negative (−$0.12) and RunPod stopped the
   pod mid-rsync.** 3 of 6 activation files reached the laptop complete (**1,824 of 6,668
   points**); three are truncated prefixes. **No further GPU work is possible until the owner
   funds the account.** Nothing in the ledger is lost — every W4 number is regenerable on a
   laptop by `python3 src/replay_w4.py --dry-run` — but W5 needs the three missing arms, which
   cost ~$0.12 of A100 time to recompute and ~12 minutes to move.

**The transfer, not the compute, is the cost.** 700 forward passes took 94.8 s of the 33 billed
minutes; the 3.28 GB egress took ~15 min and did not finish. **D-020's recommendation, for the
researcher to rule on before W5: run the difference-in-means on the pod and move the direction
vectors (983 KB) plus a fixed 5 % raw subsample, not the tensors.**

**Pods: four stopped, four unstartable (D-021).** `io6c1fhnarzoj9` holds the only copy of the
three incomplete activation files. `axvdenxbcepd10` and `bkl3m9ieis977o` are proven dead and
hold nothing needed; idle volume storage bills **~$2.00/day against a negative balance**, and
terminating those two is recommended but **not executed** — it is irreversible and the
researcher's call, per the V-003 precedent.

**Spend: $11.34 GPU + $6.35 API = $17.69 of $60.** W4 cost **$0.77 GPU and $0.00 API**.
Owner-clock minutes remain **owed for W0–W4** — asked six times.

Tooling in `src/`: `pod.py` · `pod_survey.py` · `runpod_client.py` · `extract_runpod_key.py` ·
`bootstrap.sh` · `provision_pod.sh` · `gen_neutral.py` · `gen_mirrored.py` · `gen_w3.py` ·
`prompts_w3.py` · `extract_regex.py` · `tau.py` · `landing_gap.py` · `behaviour_w3.py` ·
`direction_judge.py` · `recount_w2.py` · `recount_w3.py` · `trace_sample.py` ·
`trace_sample_w2.py` · `samples_w3.py` · **`samples_w4.py`** · **`judge_check_w4.py`** ·
**`replay_w4.py`** · both smoke scripts.
Laptop-side judging/analysis runs in `.venv-w1/` (now also holds `transformers` + `safetensors`,
which is what makes `--dry-run` and `--decode-check` laptop-reproducible).
