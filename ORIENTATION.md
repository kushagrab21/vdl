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
W11 Wave 2: comprehension intervention (clarified wording) — the mixture model's causal test
W12 Wave 2: belief-formation timing (done)
W13 Wave 2: the D-042 resolution — E-007 vs the length confound (done; transplant CANCELLED by R-015(3))
W14 Wave 2 (R-016): bidirectional comprehension dose-response — degraded wording pushes
    comprehension DOWN against the same frozen mixture formula; + the blinded hand-label
    packet that calibrates the direction judge (this packet)
W15 Wave 2 (R-016): the belief transplant, re-sized with fresh pairs (R-015(3)'s
    cancellation was a sizing outcome; generation is cheap)
```
Delivered by the W0b order; topology by ruling **R-004**.

## Where things stand (end of W14 — the mixture is a dose-response law, and the instrument that measures it broke)

**W10 ships. W13 is ACCEPTED and P-012 promoted (V-023 → E-012, to be written by the
researcher). R-016 (owner-directed) extended Wave 2 with W14 (this packet) and W15 (the powered
belief transplant), with owner minutes now tracked per packet. Assembly closes Sept 3 owner
time; submission Fri Sept 4 11:59pm PT.**

**W14 asked whether the belief-mixture model tracks comprehension DOWNWARD as well as upward.**
W11 pushed comprehension up with one clarifying sentence and the gap moved to +0.2867, inside
the interval W3's four cells predict (E-010). One point is a fit, not a law. W14 replaced the
bet note's two mapping sentences with a **semantically identical nested-negation paraphrase**
— proved equivalent by an explicit truth table (4/4 branches) and a one-line string diff, with
the prompt **197 tokens, exactly W3's**, so the manipulation adds no length.

**The result: PR-010 item 6 row D1 fires (P-013).** Measured comprehension fell
**0.5467 → 0.2905** (`above_good`) and **0.8067 → 0.5772** (`below_good`), and the aggregate
landing gap fell **+0.120 → −0.0067 [−0.113, +0.107]**, inside the **[−0.2436, +0.0012]** the
**same frozen formula and the same W3 cells** predict. Both pre-registered alternatives are
resolved: **0.985** against "the gap stays at W11's level" and **0.974** against the harder
"the gap stays at W3's level". **The three-point curve is +0.2867 (clarified) → +0.1200
(natural) → −0.0067 (degraded)**, and the fall shows on **every** basis — corrected regex
+0.200 → +0.127 → −0.020, raw regex +0.167 → +0.067 → −0.033.

**Two qualifications travel with D1, and the second is larger than the result.**
- **The mixture over-predicts the size of the move in BOTH directions.** W11 came in **0.073
  below** its prediction, W14 **0.115 above** its. Both residuals point back toward W3: the true
  response to comprehension is **flatter** than the frozen cells say. W11 saw one side of this
  and called it "the lower half of the interval"; W14 supplies the mirror image.
- **D-051 — the degraded wording breaks the DIRECTION JUDGE too.** The judge is handed the
  prompt and must solve the same nested negation the model does, and it fails the same way:
  **67 of the 86 `below_good` traces it called `correct` landed on that arm's unfavoured side**,
  and one concludes verbatim that exceeding τ means "not the bad cause and will, therefore, go
  to the good cause" — the opposite of its prompt. An independent regex instrument
  (`w14_dircheck.py`, never reads the mapping sentence) agrees with the judge **0.90–0.96** on
  W3 and **0.29 / 0.50** on W14. On that calibrated basis **the belief-conditional cells do not
  move at all** (`corr` gap **+0.5364** vs W3's **+0.4520**), where the frozen basis says they
  collapsed and crossed (**−0.0814** vs **+0.4456**). **`w14_interaction.csv` read alone says
  the opposite of the truth.** `p_a`/`p_b` are the only judge-derived inputs to the frozen
  prediction, so **D1 fires on its own terms with contaminated inputs.** Both halves are the
  claim of record. E-010 is **not** disturbed — W11's judge read clarified wording, which the
  W3 control shows it handles fine.

**The blinded hand-label packet is built and waiting** (PR-010 item 8): 50 W3 traces,
stratified 20/15/15 on the judge's stored classes, fixed-seed, shuffled, **no verdicts, no class
counts, row ids that encode nothing**, four structural blindness checks passing.
`analysis/out/w14_handlabel_packet.md` + `w14_handlabel_sheet.csv`; the key
(`w14_handlabel_key.csv`) is committed and **has not been opened** — only its header line was
read. `src/w14_handlabel_score.py` (30 lines) computes per-class agreement, Cohen's κ and the
label-noise bound, and **refuses to run on an unfilled sheet**. **It samples W3 only, so it will
bound the judge on natural wording — the wording E-005 and E-010 rest on — and says nothing
about the degraded case (D-051 §3).**

**Other findings.** **D-050** the generation launch lost `$PATH` and vLLM died on a missing
`ninja`; naming the interpreter is not enough, `bootstrap.sh` must be sourced in the same shell,
and its own banner names the interpreter that has torch rather than the one that has vLLM.
**D-052** the API projection under-shot by **61 %** — the direction judge emitted **522** output
tokens per call against D-040's 56 and needed **421 calls for 300 traces**; that overrun was
D-051 showing up on the invoice before it showed up in the analysis.

**⚠ SPEND: $15.60 GPU + $26.50 API = $42.10 of $60; balance $17.90. W14 cost $6.33** — more
than W11, W12, W13, W7b and W10 combined (S-015). **The $45 stop-and-surface threshold is
$2.90 away and is SURFACED per standing constraint 6. W15 will cross it if it costs what W14
cost, and its direction-judge bill is unpriceable from any existing constant (D-052). The
runner is not authorised to start W15 without the owner raising the cap or approving the
crossing.** Runner wall time W14 **≈ 1 h 15 m** (T-017). **Owner minutes were not supplied with
the W14 order** despite R-016 — recorded empty, not estimated.

**Next: the researcher reads `analysis/out/w14_samples/*.md` (2 arms × 5 traces at the frozen
blind indices 0–4), rules on P-013 and on how much D-051 costs it, and rules on whether the
hand-label packet should be extended to degraded wording.** The owner returns the filled sheet
whenever convenient; `w14_handlabel_score.py` runs then. **W15 needs a spend decision first.**
Do not start W15.

Tooling added by W14: **`prompts_w14.py`** (degraded forms by substring swap; `--truth-table`,
`--diff`, 17/17 selftest) · **`gen_w14.py`** (30-clause laptop+pod selftest) ·
**`w14_power.py`** (the R-013 pre-freeze sims: 3 p_b rules × 2 alternative worlds × 5
comprehension levels × 2 n, plus MDE) · **`judge_w14.py`** (D-040 constants, W14 caches, reuses
D-038's transport) · **`analyze_w14.py`** (arms, prediction, the three-point dose-response
table, interaction) · **`w14_dircheck.py`** (D-051's independent instrument; `--w3` control) ·
**`samples_w14.py`** · **`w14_recount.py`** (18 body lines) · **`w14_handlabel.py`** (the blind
packet builder) · **`w14_handlabel_score.py`** (30 lines, run when the sheet returns).

---

## Archived status (end of W13 — the project attacked its own best finding, and it held)

**W10 ships. W11 is promoted (E-010). W12 is ACCEPTED in full (V-020) and W10's audit is CLOSED
(V-021). R-015 cancelled the belief transplant as infeasible (6 disjoint pairs) and gave the W13
slot to the D-042 resolution. That resolution is complete and its outcome is SURVIVES.**

**W13 asked whether E-007 — the believed side is linearly decodable at 0.743 — is a trace-length
probe in disguise.** D-042 had shown that incorrect-belief traces run 123 tokens longer and that
`n_gen` alone decodes p̂ at 0.6421, and had declined to test how far that reaches into W5.

**The pre-freeze simulations were the packet's first result, and they rejected the ordered
criterion.** `src/w13_power.py`, four rounds, 200 replicates per world, on the **real**
activations with **synthetic** labels: the work order's rule — n_gen terciles, activation
accuracy vs its within-stratum null p95 — **false-fires 9.5 % of the time in a pure-length
world**, an error in E-007's *favour*. A four-rung ladder was priced and **no rung meets both
gates** (false-fire ≤ 0.05 *and* power ≥ 0.80) at n = 109 with 30 minority traces:
`tercile` 0.095/0.950 · `tercile_resid` **0.030/0.710** · `resid_full` 0.020/0.700 ·
`matched` 0.120/0.970. **PR-009 item 4b therefore froze the rung whose errors run AGAINST
E-007** (`tercile_resid` @ q95), reported the ordered rung alongside, and pre-declared in writing
that a non-firing primary rung could never on its own be read as E-007 failing. **MDE: 80 % power
against a belief signal worth a full-cell 0.774; power against the observed 0.743 is 0.710.**

**The result: the frozen SURVIVES row fires.** The reproduction is exact (**0.7431** at ℓ\*=22,
**0.7604** at L27, against `w5_probes.csv`'s 0.743056 / 0.760417). The length-controlled probe
reads **0.6683** at L27 — above its within-tercile null p95 **0.5889** and above the length-only
probe on the **identical folds**, **0.6392** — and fires at **both** decision layers and at
**15 of 48** layers (a contiguous band, 20–33 and 36). The ordered rung agrees at both layers,
so no PARTIAL condition triggers. **E-007 stands, with a new entry recording that it survived a
targeted attack (P-012).**

**Two qualifications travel with it and are in §5.3 of the write-up.**
- **A probe with three scalars and no activations at all — output length, est-point count, mean
  est-point position — reads 0.6767 on E-007's own cell** (null p95 0.5912, p = 0.0010). That is
  *larger* than D-042's 0.6421 and leaves E-007 a margin of **0.0664**.
- **The incremental validity is not uniform across length.** At L27: shortest tercile
  **0.7750 activations vs 0.5042 scalars**; middle tercile **0.4958** (at chance, but on **6**
  minority traces); longest tercile **0.7341 vs 0.8216 — length still wins there.**

**The un-stratified residualized probe (secondary, not decisive) beats its null (0.6549,
p = 0.0010) but does NOT beat the full-cell length baseline of 0.6767.**

**Findings.** **D-046** two files call different quantities `n_gen` and differ by exactly 1.
**D-047** PR-009's own consequence table said "a new `E-` entry" — the standing rule reserves
`E-` for post-audit promotion, so the result is **P-012** and **E-012 is reserved**.
**D-048** the register entry extending D-032/D-043: when *no* setting satisfies both gates, a
pre-registration must declare which error it prefers and what reading a non-result may then bear.
**D-049** the RunPod balance moved **$0.0171** with no pod in the packet; unattributed, recorded.

**The recount is the packet's quiet lesson.** `src/w13_recount.py` — fresh, no scikit-learn,
Newton–IRLS by hand — reproduces **all six** headline numbers to **4 decimal places in 8
seconds**, against the analysis path's **2 h 52 m**.

**Spend: $15.12 GPU + $20.65 API = $35.77 of $60; balance $24.23. W13 cost $0.00** — no pod, no
model call (S-014). Runner wall time W13 **≈ 5 h 05 m** (T-016). The **$45** threshold is not
approached.

**Next: the researcher reads `writeup/final.md` end to end, rules on P-012 (and on whether §5.3's
new paragraph should be cut back to the one sentence PR-009 promised — JC-5), closes the audit,
and the owner assembles and submits the Google Doc.** The Wave-2 addendum is W11 (C1), W12
(timing null, zero flips, D-042) and W13 (the attack, survived narrowly). Do not start new work.

Tooling added by W13: **`w13_lengthcheck.py`** (the four-rung ladder, all 48 layers; `--smoke`
runs two synthetic worlds and writes only `smoke_`-prefixed files) · **`w13_power.py`** (the
R-015(1) sims; `--variants`, `--mde-only`, `--force-rung`) · **`w13_recount.py`** (fresh; probe
by hand; 8 s).

---

## Archived status (end of W12 — Wave 2's second experiment; a measured null and a confound)

**W10 ships and is unchanged. W11 is ACCEPTED and promoted (V-018 → E-010, with two permanent
qualifications). W12 is complete and its headline is a NULL plus a flaw in the ordered
instrument.** Wave-2 results remain **addendum-only** to the Sep 5 deliverable; W10 wins any
wall-clock conflict.

**W12 asked WHEN and WHERE the believed side forms inside a trace.** 300 frozen W3 form-B
incentive traces were replayed teacher-forced and the residual stream recorded at **every one
of 129,515 generated-token positions**, layers {21,23,25,27,29,31,33,35}, 10.61 GB, **0
quarantined**, position-alignment check **10/10** (F-018). Three probe families were frozen
before the capture: **`primary`** (both arms, **arm-centred on training folds**, because
pooling naively lets a probe hit 0.912 by decoding the *prompt*), **`control_arm`** (must be at
chance — it is **0.5000 in all 176 cells**), and **`above_good`** (W5's confound-free cell).

**The result: the frozen onset criterion does not fire, at any layer, in any family.** Alignment
(b) — offsets from the first cause-token — is flat: one bin of twelve, **[−50,−25) = 0.603**
(p = 0.016), clears p95 and none clears p99.5. Absolute early bins are flat too
(**[0,25) = 0.421**, **[25,50) = 0.536** in `above_good`). **0 flips in 238 traces**, with an
empirical label-shuffled false-flip rate of **0.0000**. **The believed side is not linearly
decodable from bin-mean residuals at any absolute position, at this resolving power.**

**Two findings make that null readable rather than empty.**
- **D-043** — the criterion the order specified (2 consecutive bins > null p95) fires **20 %**
  of the time on pure noise when bins are independent and **65 %** when adjacent bins correlate
  at 0.7. Both named tightenings also fail (0.459, 0.205); the ladder was continued to
  **4 consecutive @ p99.5**, worst-cell FWER **0.0279**. **The tightening did not cause the
  null**: the untightened criterion also fails on `primary` at every layer, and fires only in
  the robustness family at four non-best layers. D-043 also names the gap R-013 still has:
  **it mandates a null simulation and not a power simulation.**
- **D-042 — the ordered alignment (a) is length-confounded.** Decile boundaries scale with
  `n_gen`; in `above_good`, p̂=−1 traces run **123 tokens longer** (p < 0.0001), and **a probe
  whose only feature is `n_gen` scores 0.6421** (p = 0.004) — more than the decile-0 activation
  probe's 0.6207. **The rising decile curve cannot be read as timing.** Whether the same channel
  reaches **E-007's** 0.743 is **not tested here** and is the researcher's call.

**W13 sizing, the packet's load-bearing output: 270 possible opposite-belief same-condition
pairs but only SIX DISJOINT ones** (4 `above_good`, 2 `below_good`), from 98 valid cut points.
69 of the 167 cause-token traces have no valid cut point, bound by `settle_pos`, not the cause
word.

**Infrastructure, W12.** Pod `avyrlo9271lq1v` created 11:10:35, **terminated 12:07:35** (HTTP
204, `/pods` empty, 404 on the id, `currentSpendPerHr` $0.00). **R-014's balance probes ran
before provisioning** and confirmed the GPU bill to the cent afterwards. **D-044**: the stack is
*not* W4's (transformers 5.16.1, no vLLM) and the alignment check is what makes that safe.
**D-045**: `--smoke` writes to the shipped filenames and overwrote real results mid-packet;
they were re-pulled from the still-live pod. **W13 must give smoke runs their own prefix.**

**Spend: $15.12 GPU + $20.65 API = $35.77 of $60; balance $24.23.** W12 cost **$1.32 GPU +
$0.00003 API**. The **$45** threshold is not approached. Runner wall time W12 **≈2 h 05 m**
(T-015).

**Next: the researcher reads `analysis/out/w12_flip_sample.md` (zero flips exist, so the frozen
fallback shows the 5 largest-excursion trajectories), rules on P-011, rules on how far D-042
reaches into W5, and issues W13 — for which the honest input is n = 6 disjoint pairs.**
Do not start W13.

Tooling added by W12: **`w12_balance.py`** (R-014's implementation) · **`w12_power.py`** (the
R-013 pre-freeze sims, both statistics) · **`capture_w12.py`** (full-position capture; imports
W4's `build_positions`; `--dry-run`, `--align-check`) · **`analyze_w12.py`** (three probe
families, both alignments, trajectories, flips, cut points; `--smoke` plants a signal *and* a
confound) · **`w12_extra.py`** (after-freeze absolute bins) · **`w12_length.py`** (D-042) ·
**`samples_w12.py`** · **`w12_recount.py`** (fresh; probe by hand; runs on the 5 % subsample).

---

## Archived status (end of W11 — Wave 2's first experiment; C1 fired)

**W10 ships and is unchanged. Wave 2 is open (R-013, owner-initiated) and W11 is complete.**
Wave-2 results are **addendum-only** to the Sep 5 deliverable; W10 remains the deadline-critical
path and wins any wall-clock conflict.

**R-013 added a STANDING RULE** that now binds every future pre-registration: no threshold or
decision statistic is frozen without a **pre-freeze simulation of that statistic under its own
null** (and under the alternative, where a prediction is tested), pasted into the PR entry with
the achieved resolving power. A design that cannot resolve its question is fixed before data
collection **or not run**.

**W11 is the first packet to obey it, and the rule changed the design twice before any token:**
`src/w11_power.py` showed the ordered n=100/arm gave **0.471** (form A) and **0.775** (form B)
distinguishing power — both under the 0.8 bar — so **n was raised to 150/arm (600 rollouts)**;
and it showed **form A's mixture test plateaus at ~0.53 at any n** (its ceiling is W3's own cell
uncertainty, one cell being n=21), so **form A's C1/C2 verdict was DECLARED NOT RUN** before
generation. The same sim chose between two defensible interval definitions on **measured
coverage** (0.973 vs 0.999 against a nominal 0.95) rather than taste.

**The result: PR-007 item 6 row C1 fires on form B, the designated test form (P-010).**
One sentence appended to W3's bet note — symmetric across conditions, byte-verified as the only
change — lifted direction-correct comprehension on the `above_good` arms from W3's ~0.54 to
**0.833 (form B)** and **0.900 (form A)**, and `below_good` to **1.000** and **0.987**. Form B's
aggregate landing gap moved **+0.120 → +0.2867 [+0.180, +0.393]**, **inside** the
**[+0.2409, +0.4758]** interval the belief-mixture model predicts from **W3's four cell rates
alone**, at a **pre-registered 0.851** distinguishing power. **The mixture model survives a
causal manipulation of belief through its natural channel — the words. Belief-upstream
[measured, text-level].** Form A agrees descriptively (+0.187 inside [+0.104, +0.358]) and its
**0.486** travels with it everywhere.

**Two qualifications travel with C1.** (a) On **both** forms the observed gap sits in the
**lower half** of its interval — the mixture slightly over-predicts. (b) **D-041**: five of six
estimable conditional cells fell (form B `above/corr` 0.793 → 0.696), and both estimable
conditional gaps fell (+0.446 → +0.374, +0.280 → +0.222). **No single move is resolved** — every
W11 CI contains its W3 value — but the sign is consistent and it predicts (a). W12 should size
for it: "does clarified wording lower estimates overall, independent of belief?" is a cheap
one-arm neutral comparison.

**Infrastructure, W11.** Pod `t1mm1e0l3f7fuh` created 09:45:50, **terminated 10:02:12** (HTTP
204, `/pods` empty, 404 on the id, `currentSpendPerHr` $0.00). Stack **byte-identical to W3's**
(vllm 0.28.0, torch 2.13.0+cu130, model snapshot `cf98f3b3…`) — which matters, because W11
compares W11 cells against W3 cells. **0 truncations in 600.** **D-038**: the judge transport was
parallelised (12 workers, ~0.2 → ~6 calls/s); prompts and model unchanged, caches interchangeable.
**D-039**: the Anthropic account ran out of credit after 255 of 600 direction verdicts, all of
form B blocked; the owner restored it mid-packet and the run resumed from cache with 0 failures.
**D-040**: D-033's direction-judge constant (117 output tokens/call) is 2.6× too high — use
**3.15 chars/token and 56 out** for the direction judge, **2.84 and 20.0** for the number judge,
which now predicts to **1.3 %**.

**Spend: $13.80 GPU + $20.65 API = $34.45 of $60; balance $25.55.** W11 cost **$0.38 GPU +
$4.59 API**. The **$45** threshold is not approached. Runner wall time W11 **≈1 h 05 m** (T-014).

**Next: the researcher reads `analysis/out/w11_samples/*.md` (4 arms × 5 traces at the frozen
blind indices 0–4), rules on P-010, and issues W12 (belief-formation timing) with W13 (paired
belief transplant) to follow.** Do not start W12.

Tooling added by W11: **`prompts_w11.py`** (clarified forms by string-append, 16/16 selftest) ·
**`gen_w11.py`** (24-clause laptop selftest) · **`w11_cells.py`** (recovers W3's four conditional
cell rates and validates them against `w3_direction.csv`) · **`w11_power.py`** (the R-013
pre-freeze simulation) · **`judge_w11.py`** / **`judge_w11_par.py`** (D-038 transport) ·
**`analyze_w11.py`** · **`w11_sensitivity.py`** (superseded; kept for W12 sizing) ·
**`samples_w11.py`** · **`w11_recount.py`** (18 body lines).

---

## Archived status (end of W10 — the project is assembled)

**Experiments ended at W7b (R-011). W10 is the final packet and it is complete**: the skepticism
pass, the build machinery, and the draft write-up. Nothing remains but the researcher's review of
`writeup/final.md` against this ledger, which is W10's own audit obligation.

**Every `P-` entry is now promoted.** P-001…P-009 → **E-001…E-009**, each citing the `V-` that
audited it and listing what is explicitly **not** promoted (V-016 §2). The write-up is built only
from `E-` and `V-` entries.

**The final verdicts are R-012**, transcribed verbatim, and they are the write-up's spine:
behavioural leakage here is **overt** (596/600 traces name the bet, vs ~0.2 % spontaneous
disclosure in the 122B panel — cross-scale tiered **[suggested]**); the screening gap **did not
replicate** (+0.32 → +0.017, z = 2.83); the aggregate gap is a **comprehension-weighted mixture**
(+0.28/+0.45 against −0.68/−0.55); the believed side is **linearly decodable pre-verbalization**
on form B (0.743 vs null p95 0.589, p = 0.001, 42/48 layers, 196/203 points before the first cause
token); and the causal rung is a **measured null** — no direction-specific landing effect at any
of six doses from 2.9 % to 45.6 % of the residual norm, against 10 + 4 random directions. **v_p̂
stands as correlational; the central causal question is NOT RESOLVED at resolving power.**

**W10's own findings, all three from recomputing numbers the ledger states:**
- **D-034** — P-009 §5's "1 of 600" fabrication figure carries **no regenerating command**. A
  named screen (`src/w10_skeptic.py`) supersedes it and is stronger: the D-029 signature fires
  **9/50 at α=+4, 0/50 at the sham, 3/600 at the low doses**.
- **D-036** — P-005's pooled mention rate is **off by one** against its own per-arm table:
  **596/600 = 99.3 %**, not 595/600. No verdict used it.
- **D-037** — "judge-vs-corrected disagreement" names **two different statistics** in P-008 §8
  (value, 121/1,150) and D-033 (landing-verdict, 22/600), which were compared to each other; both
  are reproduced and the write-up makes only the like-for-like comparison. P-004's per-arm
  median-token table does not reproduce exactly; the pooled figures the statistics use do.
- **D-035** — a cited selftest (`prompts_w3.py --selftest`) does not run under bare `python3`; it
  needs `.venv-w1`. 6 of 7 cited commands run under `python3`; that one does not.

**SK-7 refines D-032**: the exact null floor of the W7b distortion gate is **E[D̄] = 0.0782** with
**P(D̄ > 0.06) = 0.648** (0.689 at-or-on the line), against D-032's simulated 0.078 / 0.662 —
**D̄ is lattice-valued and 0.06 is one of its atoms.**

**Deliverables, all committed:**
```
writeup/final.md.tmpl     the draft, prose + {{token}} placeholders only
writeup/manifest.csv      468 lines, one per placeholder: token -> file -> selector -> format
writeup/build.py          substitutes, writes both documents, runs the digits check
writeup/final.md          the 10-section draft (~7,700 prose words, 102 table rows)
writeup/compact.html.tmpl the compact visual form, same manifest
writeup/compact.html      nodes, verdict chips, four self-explanatory figures
analysis/out/w10_digits_check.txt   0 untraceable digits in either document
```
Rebuild: `python3 writeup/build.py` → `--verify` reports **IDENTICAL** for both.

**Spend, final: $13.42 GPU + $16.06 API = $29.48 of $60; balance $30.52.** W10 cost **$0.00** —
no pod, no API call, laptop only (S-011). Runner wall time W10 **≈1 h 35 m** (T-013). The **$45**
threshold was never approached. The owner clock was never supplied (D-025/D-026) and the write-up
says so plainly.

**Next: the researcher reviews `writeup/final.md` against this ledger and may order revisions.**
That review is W10's audit. Nothing goes to the owner before it.

Tooling added by W10, all stdlib-only and laptop-reproducible: **`w10_skeptic.py`** (ten checks,
~1.7 s) · **`w10_derived.py`** (quantities no CSV holds as a cell; independently recounts P-004's
landing gaps, D-018's z, and W7's τ-echo profile) · **`w10_ledger_facts.py`** (104 facts extracted
by regex **from RESULTS.md itself**) · **`writeup/build.py`**.

---

## Archived status (end of W7b)


W0–W5 accepted (**R-003**, **V-001**, **V-002**, **V-003**, **V-006**, **V-009**, **V-011**).
**W7 accepted (V-013).** **PR-001** remains the pre-registration of record; **PR-002**–**PR-006**
bind. **R-008** pivoted the model to `Qwen2.5-14B-Instruct`; **R-009 (owner-approved)** re-targeted
the interp work to the trace-level believed favoured side `p̂`; **R-010** set the transfer policy;
**R-011 (owner-approved)** authorised W7b and **ended experimentation after it**.

**Gate G1 FAILED at W3** (form A +0.017, form B +0.120). **W4** replayed all 700 traces with
hooks (6,668 points, 34/34 decode check). **W5** produced v_p̂ (P-007, V-010): form B's p̂ probe
reaches **0.743 at ℓ\*=22** (p=0.001) and **0.760 at L27**, form A is flat at every layer, and
form B's decodability is **entirely pre-verbalization**. The result of record at ℓ\*=22 is a
**marginal cosine pass (0.2608 vs null p95 0.2443)** and a **transfer FAIL (0.5310)**; the
layers-24–36 band is **EXPLORATORY** and labelled so everywhere (V-011).

**W7 complete and ACCEPTED (F-015, P-008, V-012, V-013).** 23 arms × 50 = **1,150 steered
generations**, PR-005 frozen 13 minutes before the first steered token. Injecting α·‖Δμ‖·u at
L27 is **powerfully causal on the estimate and not believed-side-specific**: at α=+4 the median
estimate falls **three orders of magnitude** and landing 0.68 → 0.04. **The pre-registered
primary test FAILS** (Δ+ = −0.34, beating **0 of 10** random directions, p = 1.000); dose-response
is an **inverted U centred on sham**; the verbalized flip's CI includes zero and a *random*
direction beat it. **PR-005 item 6 resolved to row 4 — v_p̂ is correlational — and V-013 ratified
that as the verdict of record.** H3′ is **[not tested]**.

**W7b complete (F-016, P-009, V-014) — the stage-2 low-dose follow-up, designed AFTER W7's
result (R-011), which does NOT reopen W7's verdict.** 12 arms × 50 = **600 generations** at
**2.8 % and 5.7 %** of the residual-stream norm (W7's grid was 11.4 / 22.8 / 45.6 %), PR-006
frozen **11 m 51 s** before the first steered token; W7's sham REUSED as the α=0 reference.

- **No direction-specific effect was detected.** Δ±(v_p̂) = **+0.10, CI [−0.10, +0.30]** (judge
  +0.16, [−0.04, +0.34]); it **reverses** at ±0.25; and the **mean random direction does +0.115**,
  with seed 9013 reaching +0.28 on a CI that excludes zero where v_p̂'s does not.
- **The frozen gate fired on its own noise.** D̄ = **0.1875** > the 0.06 line, so **PR-006 item 5
  row 3 is the verdict of record**. But **D-032**: 200,000 simulations (`src/w7b_floor.py`) show
  that under a design doing **nothing at all**, E[D̄] = **0.078** and D̄ exceeds 0.06 **66 %** of
  the time. **Rows 1 and 2 were jointly unreachable before a token existed.**
- **Every independent distortion indicator says these doses do not distort:** coherence
  **1.000 in all 12 arms**, 0 truncated and 0 degenerate in 600, output lengths **392–439** vs
  unsteered 395, median log10 **9.34–9.98** vs unsteered 9.611, bet-engagement **0.44** vs W7's
  sham 0.38, the D-029 fabrication signature in **1 of 600**, verbalized preference in **0 of 600**.
- **The twelve arms are mutually homogeneous** (χ² = 16.38, dof = 11, **p = 0.128**) at a pooled
  **0.475**, with **no dose gradient**: |α|=0.25 → 0.470, |α|=0.50 → 0.476, Fisher **p = 1.000**.
  A flat, direction-independent offset from the α=0 references is not a dose response, and the
  packet **cannot separate** it from the reused n=50 sham reading high — a limitation **PR-006
  item 2 declared before the data**.
- **Register (D-032), superseding D-028's phrasing:** PR-004 froze the right statistic at the
  wrong layer; PR-005 at the wrong dose; **PR-006 at a threshold its own design cannot resolve.**
  A pre-registration must freeze evidence that its setting and threshold are inside the range the
  design can resolve. **No packet in this project ever simulated a statistic under its own null
  before freezing its threshold.**
- **Infrastructure: clean.** `u3g0qm180kvqnd` created 06:49:28, terminated **07:08:53** (HTTP
  204); `/pods` empty, `currentSpendPerHr` $0.00, no volume. **60.1 % of billed GPU time was
  compute.** Smoke clause B6 caught a transcription error **in PR-006 itself** on the laptop
  before a pod existed (**D-030**).

**Spend: $13.42 GPU + $16.06 API = $29.48 of $60; balance $30.52.** W7b cost **$0.51 GPU and
$1.93 API**. The API projection over-shot by only **11 %** using D-027's corrected constants
against the old estimator's 36 % (**D-033**; refine to **2.84 chars/token** for W10). The pod
billed **$1.59/hr against a $1.39 rate card** (**D-031**). The $45 threshold is not approached.

**Next: W10 only, and it is the last packet** — skepticism pass, build script, write-up assembly
from `E-`/`V-` entries. **Do not start it:** the researcher reads
`analysis/out/w7b_samples/*.md` (4 arms × 5 traces at the blind indices 0–4), rules on the final
verdict row, and issues the assembly order.

Tooling in `src/`: `pod.py` · `pod_survey.py` · `runpod_client.py` · `extract_runpod_key.py` ·
`bootstrap.sh` (interpreter-aware since D-022) · `provision_pod.sh` · `gen_neutral.py` ·
`gen_mirrored.py` · `gen_w3.py` · `prompts_w3.py` · `extract_regex.py` · `tau.py` ·
`landing_gap.py` · `behaviour_w3.py` · `direction_judge.py` · `recount_w2.py` · `recount_w3.py` ·
`trace_sample.py` · `trace_sample_w2.py` · `samples_w3.py` · `samples_w4.py` ·
`judge_check_w4.py` · `replay_w4.py` · **`direction_w5.py`** · **`w5_integrity.py`** ·
**`w5_cell.py`** · **`w5_recount.py`** · **`steer_w7.py`** · **`analyze_w7.py`** · **`samples_w7.py`** · **`w7_recount.py`** ·
**`steer_w7b.py`** · **`analyze_w7b.py`** · **`samples_w7b.py`** · **`w7b_recount.py`** · **`w7b_floor.py`** · both smoke scripts.
Laptop-side judging/analysis runs in `.venv-w1/` (now also holds `scikit-learn`, which is what
makes `--smoke` and `w5_recount.py` laptop-reproducible).
