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

## Where things stand (end of W1)

W0/W0b accepted (**R-003**, **V-001**). **W1 complete.** **PR-001 is the pre-registration of
record**, frozen at commit `0152943` (**F-014**) — items 8/9 in `src/extract_regex.py`, item 3
in `src/gen_neutral.py`. Any change to either file is a deviation needing a `D-` entry.

**Neutral calibration done, four models, 50 rollouts each, zero truncations** (**P-001**):
τ (judge) = Qwen3-8B **31,250,000** · R1-Qwen-7B **2,400,000** · R1-Llama-8B **2,500,000** ·
Qwen2.5-14B **15,300,000**. `google/gemma-2-9b-it` is **gated and inaccessible**; not substituted.

**Two things need a researcher ruling before W2 runs:**
1. **D-011** — the LAST-literal extractor disagrees with the judge on **20%/36%** of R1-distill
   answers (they write answer-first, then operands). Left unfixed on purpose; τ of record is the
   judge's and is unaffected.
2. **P-002** — G0's "median ≥2 parseable intermediates" must be pinned to the **raw** or the
   **filtered** variant *before* W2. `Qwen2.5-14B-Instruct` sits at 2 raw / **1 filtered**, so
   the choice decides whether it can pass at all.

**Pod `gwhn0ex0eeyntn` is STOPPED, keep it.** RunPod stop **wipes the container filesystem**
(**D-009**) — only `/workspace` survives. The stack now lives on the volume at
`/workspace/venv` (17 GB, 21 min to build) and the deploy key at `/workspace/.ssh/id_deploy`
(repo key id `161661175`; the old `161657105` is revoked).
**Every GPU packet starts with `source /workspace/bootstrap.sh`.**
Volume at close: 60 GB of 100 GB used.

**Spend: $3.61 GPU of $60, plus $0.45 Anthropic API.** Owner-clock minutes remain **owed for
W0, W0b and W1** — asked three times.

Tooling in `src/`: `pod.py` · `pod_survey.py` · `runpod_client.py` · `extract_runpod_key.py` ·
`gen_neutral.py` · `extract_regex.py` · `tau.py` · `trace_sample.py` · both smoke scripts.
Laptop-side judge/analysis runs in `.venv-w1/` (fire, anthropic, tenacity, numpy, tqdm, dotenv).
