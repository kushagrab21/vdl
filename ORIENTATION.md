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

## Where things stand (end of W3)

W0–W2 accepted (**R-003**, **V-001**, **V-002**, **V-003 audit**). **PR-001** remains the
pre-registration of record; **PR-002** (W2) and **PR-003** (W3 frozen dataset, reskin, direction
judge, gate G1) bind. **R-008** pivoted the project to `Qwen2.5-14B-Instruct` by owner-approved
scope change, localizing the value direction behind **overt** gaming.

**W3 complete. GATE G1 FAILED — hard stop, PR-003 item 6's named branch (G-002).** 650 fresh
rollouts, **zero truncations**, frozen per PR-003 item 8.

| form | τ | judge landing gap (strict `>`) | 95 % CI | G1 |
|---|---|---|---|---|
| A (giraffe) | 15,300,000 | **+0.017** | [−0.097, 0.130] | **FAIL** |
| B (crocodile reskin) | **4,500,000,000** | **+0.120** | [0.007, 0.233] | PASS (fragile) |

**D-018 is the reason and the methodological finding of the packet: W2's screening estimate did
not replicate.** Form A was +0.32 (CI [0.14, 0.50]) at n=50 and is +0.017 at n=150 — apparatus
byte-identical, seed block the only difference, W3's three blocks of 50 mutually consistent
(z=2.83, p=0.005 vs W2). A winner's-curse effect: G0 promoted the model whose gap looked biggest.
Form B's pass is convention-dependent (`≥` CI touches zero) and one rollout from its lower bound.

**Two results do stand strongly.** (1) **The overt phenotype**: the model mentions the bet in
**99.2 % of 600 incentive traces** (vs ~0.2 % spontaneous disclosure in the 122B panel) — the
overt-vs-covert contrast R-008 promoted survives at n=600 on two surfaces. (2) **D-016 is
confirmed**: raw extractor disagreement 52.3 %/42.3 % collapses to **1.0 %/0.7 %** on the
corrected basis, and the corrected-basis recount reproduces form B's judge gap to within one
rollout (+0.1267 vs +0.120).

**Held back deliberately:** P-005's comprehension-conditioned gaps (±0.3–0.5, and an `above_good`
comprehension rate of only ~54 %) would say form A's null is *cancellation*, not indifference —
but the direction judge reads the same text the estimate came from, so the causal reading is
**circular until validated**. `analysis/out/w3_direction_sample.md` exists for exactly that.
**Validating it is the highest-value next action and costs no GPU.** A third surface form would
break the A-vs-B tie for ~1 min of A100 time (~$0.12 + ~$1 judging) — the runner's recommendation.

**Pods: `bkl3m9ieis977o` STOPPED** (A100-SXM4, $1.39/hr, venv + 28 GB cache).
`gwhn0ex0eeyntn` **terminated** per V-003. **`axvdenxbcepd10` failed 18 restart attempts
(D-019) — two of two stopped pods in this project never resumed**, so a stopped pod is not a
reliable way to preserve a stack; `src/provision_pod.sh` rebuilt everything on a fresh pod in
~10 min, and it is committed precisely because the previous copy died with its volume.

**Spend: $10.57 GPU + $6.35 API = $16.92 of $60.** W3 cost **$0.32 of GPU** — the V-003 idle rule
held: 13.6 min billed against ~65 min of laptop work. Owner-clock minutes remain **owed for
W0–W3** — asked five times.

Tooling in `src/`: `pod.py` · `pod_survey.py` · `runpod_client.py` · `extract_runpod_key.py` ·
`bootstrap.sh` · `provision_pod.sh` · `gen_neutral.py` · `gen_mirrored.py` · `gen_w3.py` ·
`prompts_w3.py` · `extract_regex.py` · `tau.py` · `landing_gap.py` · `behaviour_w3.py` ·
`direction_judge.py` · `recount_w2.py` · `recount_w3.py` · `trace_sample.py` ·
`trace_sample_w2.py` · `samples_w3.py` · both smoke scripts.
Laptop-side judging/analysis runs in `.venv-w1/`.
