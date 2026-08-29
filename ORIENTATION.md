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

## Where things stand (end of W2)

W0/W0b/W1 accepted (**R-003**, **V-001**, **V-002**). **PR-001 remains the pre-registration of
record**, frozen at commit `0152943` (**F-014**); **PR-002** adds R-007(1),(2),(4) plus the
incentive seed scheme and the landing-gap definition, all frozen before any incentive rollout
existed.

**W2 complete. GATE G0 FAILED ON BOTH ELIGIBLE MODELS — the project is at a hard stop pending
an owner/researcher ruling (G-001).** 200 incentive rollouts, zero truncations:

| model | judge gap (strict `>`) | 95 % CI | filtered inter. median | G0 |
|---|---|---|---|---|
| `Qwen/Qwen3-8B` | +0.12 | **[0.00, 0.24]** | 54.0 | **FAIL** — CI touches zero |
| `Qwen/Qwen2.5-14B-Instruct` | **+0.32** | **[0.14, 0.50]** | 3.0 | **FAIL** — extractor disagreement |

Qwen2.5-14B meets **both** stated G0 conditions and is failed only by the corroborating regex
extractor, whose CI is [−0.04, 0.32]. **D-016** is why: the incentive prompt contains τ, both
models answer-first-then-justify, and PR-001 item 8's LAST-literal rule reads the echoed
threshold instead of the answer — **28 %/44 % disagreement on incentive vs 2 %/0 % on neutral**.
The extractor was **not** amended. The tie convention changes no verdict.

**Four options are on the researcher's desk (G-001): accept Qwen2.5; amend item 8 and re-run
both extractors over all W1+W2 data; raise n to ~150/side (~$0.60, the runner's recommendation);
or invoke the fallback ladder (never transcribed here).** The trace sample the order requires
before W3 is `analysis/out/w2_trace_sample.md` — 10 traces per model at fixed indices
0/10/20/30/40 per condition, no substitutions needed.

**Pods: BOTH STOPPED (`EXITED`).** `axvdenxbcepd10` (A100-SXM4-80GB, $1.39/hr) holds the current
stack — `/workspace/venv` + 43 GB model cache, 52 GB of 100 GB. **`gwhn0ex0eeyntn` could not be
restarted at all (D-012: "not enough free GPUs on the host machine", 20 attempts) — its 60 GB
volume is unreachable and still billing ~$0.33/day; terminating it needs a ruling.** Because a
stop can be one-way, `src/bootstrap.sh` and `src/provision_pod.sh` are now **committed**, and a
fresh pod rebuilds the whole stack in ~19 min with one command.

**Spend: $10.25 GPU of $60, plus $0.99 Anthropic API.** Of W2's $6.64, only ~$1.11 bought the
experiment — $0.78 was a dead container (D-013) and ~$4.75 an idle pod (D-015). From W3 the pod
is stopped the moment the last GPU command returns. Owner-clock minutes remain **owed for W0,
W0b, W1 and W2** — asked four times.

Tooling in `src/`: `pod.py` (now with `start`) · `pod_survey.py` · `runpod_client.py` ·
`extract_runpod_key.py` · `bootstrap.sh` · `provision_pod.sh` · `gen_neutral.py` ·
`gen_mirrored.py` · `extract_regex.py` · `tau.py` · `landing_gap.py` · `recount_w2.py` ·
`trace_sample.py` · `trace_sample_w2.py` · both smoke scripts.
Laptop-side judge/analysis runs in `.venv-w1/` (fire, anthropic, openai, tenacity, numpy, tqdm,
dotenv).
