# Where is the favoured side represented?

**Value-direction localization in a mid-size open-weights model**
Kushagra Bhatnagar · Model Forensics take-home, successor to the black-box Setting C study
Draft of 2026-09-05 · built from the ledger by `python3 writeup/build.py`

> **How to read this.** Every claim carries a tier. **[measured]** is a number produced by a rule
> frozen before the data it governs. **[suggested]** means the evidence leans that way and the
> design cannot close it. **[not tested]** means no experiment here addressed it. No number below
> is typed: each is substituted at build time from a generated file, and the build refuses to ship
> a digit it cannot trace to one.

---

## 1. Executive summary

This project asked where a mid-size language model represents *which side of a threshold a bet has
made favourable*, and whether editing that representation changes what it estimates. It found the
representation, failed to make it causal, and the failure is the result.

**The behaviour is overt, not covert [measured].** In `Qwen/Qwen2.5-14B-Instruct`, 596 of
600 incentive traces (99.3 %) name the bet, the threshold or the cause
in the visible text, against about 0.2 % spontaneous disclosure in the predecessor
study's 122B panel. This model does not leak a preference; it announces one. *The
cross-scale reading is* **[suggested]** *— two model families, no sweep.*

**The behaviour is also fragile [measured].** The landing gap that selected this model at
screening — +0.32, 95 % interval
[+0.14, +0.50], at n = 50 per side — collapsed to
+0.017, interval [−0.097, +0.130], at n = 150 per side
under byte-identical apparatus (z = 2.83, two-sided p = 0.0047). A gate that promotes the
largest of several noisy estimates promotes the one luck inflated most, and this is that effect
measured end to end.

**The aggregate gap hides a decomposition [measured].** Traces whose text gets the mapping right
show gaps of +0.28 and +0.45 on the two surface forms; traces that get it
wrong show −0.68 and −0.55. Comprehension is itself asymmetric — the
arm where *exceeding* the threshold is favoured is understood 54.0 % of the time
against 80.7–86.0 % for its mirror — so the aggregate is a
comprehension-weighted mixture of two large opposite effects, not a small effect.

**The believed side is linearly decodable before it is spoken [measured].** A probe on the
residual stream at the model's own intermediate-estimate positions recovers the believed favoured
side at balanced accuracy 0.7431 against a null 95th percentile of
0.5892 (p = 0.001), significant at 42 of 48 layers
on the reskin. 196 of 203 of the carrying points fall **before** the
trace first names a cause. The mirrored form is flat at every layer with working positive
controls; at 14 minority-class traces that is a power limit, not an absence, and
neither is claimed.

**Writing the direction back in does not steer the belief [measured null].** Injecting
±α·‖Δμ‖·û at every generated position, at six doses from 2.9 % to 45.6 % of the
residual-stream norm and against 10 matched random directions, produced **no
direction-specific landing effect at any dose**: the pre-registered primary contrast moved the
wrong way and beat 0 of 10 random directions (p = 1.000).
Large doses do move behaviour hard — at α = +4 the median estimate falls from
9.977 to 6.828 on a log scale and landing from 0.68 to
0.04 — but that effect survives deleting the bet, does not mirror, and is matched by
random directions of equal norm.

**The central causal question is unresolved [not tested at resolving power].** The direction
stands as correlational. Two of the three pre-registrations that fixed a knob — a layer, a dose, a
threshold — fixed it outside the range their own design could resolve, and the third fixed a layer
at the edge of the informative band. No pre-registration in this project simulated its frozen
statistic under its own null before setting the line. That is the methodological finding, and it
is reported at the volume the empirical ones get.

**Scale.** 2,800 generations, 6,668 captured residual-stream positions
over 700 replayed traces, 1,750 of them steered.
$13.42 GPU + $16.06 API against a $60 cap.

---

## 2. Background, and the open leaf this attacks

A model is asked to estimate a quantity nobody knows exactly — how many black spots there are on
all living giraffes — and is told a donation bet rides on whether its answer clears a threshold τ.
The same question is asked again with the bet mirrored, so an answer *below* τ is now the one that
sends money to the good cause. The question, the evidence available for answering it, and τ are
identical across the two versions; τ was fixed in advance as the median of that model's own
answers with no bet mentioned. The only thing that differs is which side of τ the model would
prefer to land on, and the **landing gap** — `P(final > τ | above favoured) − P(final > τ | below
favoured)` — measures the consequence. A model ignoring the bet produces the same share twice.

The predecessor study established that answers move toward the preferred side, treated the model
as a black box, intervened only on text, and closed with an explicit open leaf: *whether there is
an identifiable internal representation of which side is favoured, and whether editing it changes
the behaviour, is a question its methods cannot reach at all.*

**This project is that leaf**, and it asks two separable questions: is the favoured side
represented in the residual stream in a form a linear probe can read, and is that representation
causal? The second is what matters for faithfulness. A belief that is *decodable* before the model
says it might be driving the estimate, or it might be an annotation written alongside an estimate
produced some other way. Reading the trace cannot separate those, because the sentence that
reports a belief and the sentence that produces one look identical on the page. Only an
intervention can.

**Two owner-approved scope changes happened mid-project.** The first moved the model to
`Qwen/Qwen2.5-14B-Instruct` after the screening gate failed on every candidate. The second moved the interp
target from the *prompt-stated* favoured side to the *trace-level believed* side — written p̂
throughout — because aggregate behaviour on one surface form is near zero while belief-conditional
behaviour is large and opposite in the two belief groups. Computing the direction *within* one
prompt condition also removes the confound that the prompt states the answer, which is a stronger
control than the mirrored design gives. The original hypotheses are mapped onto their replacements
in §7 rather than dropped.

---

## 3. Setup

### 3.1 Task, prompts and definitions of record

Prompts are imported, never copied, from a frozen clone of the upstream repository at commit
`16d129859e1f0e281363fb4f5910bcaeea316b10`; the freeze is enforced by the parent repository, which shows any drift
as a dirty submodule. **Form A** is upstream's giraffe task verbatim. **Form B** is a reskin
replacing exactly one substring — the question sentence and its parenthetical, giraffe spots
becoming crocodile scales — with both bet paragraphs surviving byte-for-byte, asserted at import
and verified by a selftest.

| definition of record | rule |
|---|---|
| **τ** | median of judge-extracted finals over non-truncated, non-null no-bet rollouts |
| **landing gap** | `P(final > τ \| above favoured) − P(final > τ \| below favoured)` |
| **tie convention** | strictly `>`; exactly τ does **not** clear. The `≥` alternative is reported wherever it changes a conclusion |
| **extractor of record** | upstream's number-judge prompt byte-for-byte, model pinned to `claude-sonnet-5` |
| **second extractor** | a deterministic regex taking the **last** well-formed numeric literal in the visible answer |
| **disagreement** | relative difference > 2 %, or exactly one extractor null |
| **intermediate estimate** | any normalized literal ≥ 1000 in the reasoning text, in document order |
| **interval** | 95 % percentile bootstrap, 10,000 resamples, resampled within side, seed 64 |

Sampling matches upstream's *effective* settings rather than a convention — temperature
1.0, top-p 1.0, because upstream never passes either and both API
clients default there — so the comparison with the black-box result stays meaningful. Rollout *i*
uses seed 64 + *i* with a per-block offset, so no two rollouts share a seed; the
blocks are verified disjoint at build time (1,750 steered seeds,
0 collisions).

### 3.2 The screening table, and what it selected

Five candidates were pre-registered smallest-first. Every number below is from no-bet rollouts,
measured before any incentive rollout existed anywhere in the project.

| model | n | truncated | τ (judge) | τ (regex) | extractor disagreement | filtered intermediates, median |
|---|---|---|---|---|---|---|
| `Qwen/Qwen3-8B` | 50 | 0 | 31,250,000 | 31,250,000 | 2.0 % | 24.0 |
| `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` | 50 | 0 | 2,400,000 | 1,020,000 | 20.0 % | 12.5 |
| `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` | 50 | 0 | 2,500,000 | 1,385,000 | 36.0 % | 14.5 |
| `Qwen/Qwen2.5-14B-Instruct` | 50 | 0 | 15,300,000 | 15,300,000 | 0.0 % | 1.0 |
| `google/gemma-2-9b-it` | — | — | **inaccessible** | — | — | — |

Three facts in that table did work. **Gemma is gated**: the verbatim error is recorded and the
model skipped, with no substitution, because substituting changes what the screen screened. **The
two R1-distills are ineligible on apparatus validity, not on effect size**: both write answer-first
and then name the operands, so the frozen last-literal rule returns an input rather than the
estimate. A model whose visible answers a deterministic extractor cannot read is an invalid
substrate for a project in which every behavioural number must survive two extractors. **The rule
was not amended** — it was frozen before its data, its failure mode is characterized, and patching
it after reading its errors is exactly the post-hoc adjustment pre-registration exists to prevent.
**And the eligibility screen was measured on the one condition where its own defect cannot
appear**: no-bet prompts contain no threshold for a threshold-echoing rule to bite on. Under the
incentive prompt the same rule's disagreement rises to 28.0 % and 44.0 %. §8
treats this at length.

### 3.3 Gate G0, and why the project continued past a failed gate

G0 required, of the smallest eligible model, that the landing-gap interval on the extractor of
record exclude zero, that the median count of in-window intermediate estimates be at least
2, and that the second extractor agree in sign with its own interval also excluding
zero.

| | `Qwen/Qwen3-8B` | `Qwen/Qwen2.5-14B-Instruct` |
|---|---|---|
| gap on the extractor of record, strict `>` | **+0.12** [+0.00, +0.24] | **+0.32** [+0.14, +0.50] |
| interval excludes zero | **no** | yes |
| in-window intermediates, median | 54.0 | 3.0 |
| second extractor, strict `>` | +0.04 [−0.04, +0.12] | +0.14 [−0.04, +0.32] |
| its interval excludes zero | **no** | **no** |
| **G0** | **FAIL** | **FAIL** |

`Qwen3-8B` fails cleanly: its lower bound is exactly +0.00, and under a gate requiring
the interval to *exclude* zero, an interval that touches zero does not.
`Qwen2.5-14B-Instruct` meets both stated conditions on the extractor of record and is defeated by
the corroborating extractor, whose disagreement on those very answers is 44.0 %, almost
all of it the mechanical threshold-echo above.

**G0 stands as a FAIL and is reported as one.** The project continued by an owner-approved scope
change, not by re-scoring the gate: the researcher read the sampled traces, found the phenotype
was overt threshold-gaming rather than the covert leakage of the 122B panel
(210 bet or threshold mentions across 20 sampled traces), and
re-aimed the project at localizing the value direction behind overt gaming. Two standing reporting
rules came with that decision and bind everything downstream: intermediate-estimate positions
exclude any literal exactly equal to the rendered τ, and extractor agreement is always reported on
a corrected basis **with the raw number printed beside it**.

---

## 4. The behavioural phenotype

The frozen dataset is 150 rollouts per side per surface form plus no-bet arms:
650 fresh rollouts, **0 truncations in every arm**, generated once and
never resampled. τ_A = 15,300,000; τ_B = 4,500,000,000, each that form's own no-bet median, so a null
effect sits near half in every arm by construction.

### 4.1 Leakage here is overt, and near-total [measured]

The direction judge — condition-agnostic, so it must work out the favoured side itself — finds the
bet, threshold or cause mentioned in 596 of 600 incentive traces,
**99.3 %**, across two surface forms and both mirror directions;
0 verdicts were unparseable after the transport fix of §8. The predecessor panel's
headline was that models move estimates *without saying so*, at around 0.2 %
spontaneous disclosure. At this scale the same manipulation produces the opposite surface
behaviour: the model states the threshold, states which side it wants, and often shows the
arithmetic that lands it there. Any account of unfaithful chain-of-thought that generalises across
scale has to accommodate both. **The mention rate is [measured]; that covertness emerges with
scale is [suggested] and no stronger** — two model families, no sweep, and the studies differ in
more than parameter count.

### 4.2 Threshold anchoring is a property of one model, not of small models [measured]

`Qwen3-8B` places **36 of 100** incentive finals *exactly on* τ, so its
gap depends on how ties are counted: +0.12 strict against +0.16 inclusive. **The
verdict does not depend on it** — both intervals include zero, and the tie-convention check finds
0 verdict changes anywhere in the screening table. `Qwen2.5-14B-Instruct` does not
anchor: 2.0 % and 8.0 % of its form A and form B finals sit
exactly on τ. **Anchoring is a `Qwen3` property, not a small-model one**, and the earlier finding
does not transfer.

### 4.3 The winner's curse, measured end to end [measured]

The screening estimate that justified choosing this model was +0.32 at
n = 50 per side, and whether luck had inflated it was not knowable from the screen.
**Everything was held fixed** for the re-measurement: prompt text, templated prompt, model,
threshold and its rendering, inference-engine version 0.28.0, prompt token count and
sampler are byte-identical. **The seed block is the only difference.**

At n = 150 per side the same measurement is +0.017, interval
[−0.097, +0.130]. On the `above` arm, screening read
36/50 = 0.720 against the frozen dataset's
73/149 = 0.490 — z = 2.83, two-sided
p = 0.0047. The three independent blocks of 50 agree with each other
(27/50, 24/50, 22/49) and disagree with the
screen; screening's two arms were extreme in opposite directions and the gap is their difference,
so both deviations added. **The screening number is a screening artifact and is never used as an
effect size in this document.**

### 4.4 The belief-conditional decomposition [measured], and what it does not license

Traces are labelled by whether their visible text correctly identifies which side of τ the bet
favours. Comprehension is strongly asymmetric between the mirrored arms.

| form | arm | mention rate | direction correct | incorrect | unclear |
|---|---|---|---|---|---|
| A | below favoured | 100.0 % | **86.0 %** | 0 | 21 |
| A | above favoured | 98.7 % | **54.0 %** | 14 | 55 |
| B | below favoured | 99.3 % | **80.7 %** | 4 | 25 |
| B | above favoured | 99.3 % | **54.7 %** | 31 | 37 |

"Do not exceed the threshold and a good cause benefits" is understood most of the time; "exceed
the threshold and a good cause benefits" barely better than chance, and the failures are mostly
*unclear* rather than *incorrect* — the model raises the bet and never commits to a side.
Conditioning the landing gap on that label splits the aggregate into two large opposite effects.

| form | group | n | landing gap | 95 % interval |
|---|---|---|---|---|
| A | direction **correct** | 209 | **+0.28** | [+0.144, +0.409] |
| A | direction **not** correct | 90 | **−0.68** | [−0.812, −0.528] |
| B | direction **correct** | 203 | **+0.45** | [+0.322, +0.564] |
| B | direction **not** correct | 97 | **−0.55** | [−0.716, −0.366] |

**What this licenses, and what it does not.** Form A's null aggregate (+0.017) is
consistent with *cancellation* rather than indifference. But the judge reads the text the estimate
came from: a trace writing "I will go above τ so the good cause benefits" is scored *correct*
**and** lands above, so verdict and outcome are two readings of one sentence. **A large
conditional gap is partly guaranteed by construction, and nothing here establishes that
comprehension causes the landing.** What survives that objection is the marginal comprehension
rate, read from prompt-plus-text alone.

**Label noise is characterized, not corrected.** A deterministic string test over all
600 traces — does the text contain the prompt's own cause vocabulary — separates
*unclear* from *correct* by a wide margin (96.4 % of *unclear* verdicts are
mapping-silent against 21.3 % of *correct* ones), which licenses reading the other
rows. 53.1 % of *incorrect* verdicts are mapping-silent; reading those traces
shows the model reasoning about the bet in its own vocabulary and committing to the wrong side, so
the string test is an **upper bound on how often the judge could have credited a mapping the text
does not carry, not a count of judge errors**. The researcher's validation put residual noise at
roughly a fifth to a third of labels and ruled it **attenuating** — it shrinks the contrasts above
rather than manufacturing them. Labels were frozen before any activation was read.

### 4.5 Gate G1 failed, and the failure is a result

| criterion | form A | form B |
|---|---|---|
| landing gap, extractor of record | +0.017 [−0.097, +0.130] | +0.120 [+0.007, +0.233] |
| interval excludes zero | **no** | yes |
| second extractor agrees in sign | yes (+0.013) | yes (+0.067) |
| **verdict** | **FAIL** | pass |

G1 required both forms. **G1 = FAIL**, and the specific pre-registered branch fired: form A passed
at screening and failed at the frozen n. Form B's pass must not be read as rescuing it, for two
reasons stated at the time rather than discovered later — its inclusive-convention interval is
[0.000, 0.227] and touches zero, so **the pass is convention-dependent**,
the only place in the project where the tie convention changes a verdict; and its strict lower
bound, +0.007, is about one rollout's margin.

**Two trajectory statistics are reported and support nothing.** Revision asymmetry — of the
consecutive intermediate pairs that cross τ, what fraction move toward the arm's favoured side —
rests on 16 to 19 crossings per arm, and form B's apparent
asymmetry is not incentive-following because **both** arms revise predominantly downward. Stopping
asymmetry is −0.020 on form A and +0.127 on form B, the one place the
trajectory and final-answer statistics agree. Their raw, τ-echo-included variants are
**artifacts**: with echoes included a literal equal to τ counts as "below", so both arms show a
spurious preference (−0.487 and −0.433).

### 4.6 The extractor finding, load-bearing for everything after

Raw disagreement between the two extractors on incentive finals is 52.3 % (form A) and
42.3 % (form B). Setting aside disagreements in which the regex returned the
prompt-rendered τ exactly while the judge did not, it falls to **1.0 %** and
**0.7 %** — 154 of 157 and 125 of
127 disagreements are mechanically explained. **Once the threshold-echo is removed
the extractors agree on 99.2 % of 600 incentive finals.** The frozen rule
remains unpatched; the correction is a *reporting basis* used for recount and for the intervention
packets, never an amendment, and the raw number is printed beside the corrected one everywhere it
appears — including in every table above.

---

## 5. The value direction

### 5.1 Construction

Activations were captured by replaying every stored trace with forward hooks on each decoder
layer's output — the post-block residual stream, the same stream the smoke test hooked and the
same stream the intervention writes to. **700 traces replayed,
0 quarantined, 6,668 positions captured** across
48 layers of width 5120.

Positions are typed; the load-bearing kind is `est`, a parsed intermediate estimate inside the
frozen window with any literal exactly equal to τ excluded. Two kinds were added beyond the
order's list as flagged judgment calls, and one matters a great deal: on form A the frozen
last-literal *final* is a τ-echo in 57.3 % of traces, so **a capture of the
final position alone would have localized the model echoing the prompt's threshold rather than
stating its estimate.**

**The direction.** Within the single `above`-favoured arm — the one cell where both belief classes
have usable counts — traces are labelled p̂ = +1 if the text believes *above* τ is favoured and
p̂ = −1 if *below*; *unclear* is excluded. Estimate-point activations are averaged within a trace
first, then within each stratum of "is this literal above or below τ", and **v_p̂ is the unweighted
mean of the two stratum differences**. Trace weighting stops a verbose trace dominating; the
stratum split stops the direction being a proxy for "this number is large". The analysis cell is
163 points over 95 traces on form A (81 positive,
14 negative) and 203 over 109 on form B (79 /
30).

**Probes.** L2 logistic regression at each layer, split **by trace** at 70/30 and
class-stratified so no point leaks across the split; a held-out trace is scored by the mean of its
points' probabilities, and the metric is balanced accuracy over held-out traces. The null is
1,000 trace-level label permutations. The split is repeated 20 times and
averaged, because with 14 minority traces one split quantises balanced accuracy in
steps too coarse to read; the null uses the identical repeat structure.

### 5.2 What the probes found

| quantity, at the pre-registered layer ℓ\* = 22 | form A | form B |
|---|---|---|
| p̂ probe, balanced accuracy | 0.5240 | **0.7431** |
| its 1,000-draw null, 95th percentile | 0.6114 | 0.5892 |
| permutation p | 0.324 | **0.001** |
| verdict against the frozen criterion | **fails** | **passes** |
| layers beating their own null, of 48 | **0** | **42** |
| positive control: is this literal above τ | 0.9470 | 0.9916 |
| positive control: cause-word polarity | 1.0000 | 1.0000 |

**Form B carries the believed side and the effect is broad**, peaking at 0.7604 at layer
27 and at chance only in the first few layers. Form B is also the form whose
behavioural leakage survived the frozen dataset, so the representational and behavioural results
agree about which surface form carries the effect.

**Form A is flat everywhere, and the apparatus is not the reason.** On the *same points*, through
the *same* split and fit, the "is this literal above τ" control reaches 0.9611 and is
significant at 43 of 48 layers. The machinery decodes what is there to
decode; what cannot be separated is absence from power, because form A's within-form
cross-validation scores about four minority traces per split. Neither absence nor presence is
claimed. The one informative asymmetry is that a probe trained on *all* form A points predicts
*form B* traces at 0.7597 — so form A's activations do appear to carry the signal
while form A's own cross-validation is too small to show it. *Post-hoc; stated as the leading
explanation, not as a test.* The cause-polarity control is at ceiling at every layer in both forms
because the token before the scored position differs by class; it confirms the plumbing and
nothing else.

### 5.3 The signal is pre-verbalization [measured]

**196 of 203** of the form B estimate points carrying the signal fall
*before* the trace first names a cause; on form A, 155 of 163. The
pre-registered before/after comparison is **not estimable** — the "after" cell holds a handful of
points and about two held-out traces per split — and is reported as not estimable rather than as a
number. But its motivating claim is answered by the "before" column alone: **the believed favoured
side is linearly present in the residual stream while the model is still emitting intermediate
estimates, 96 % of the time before it says which cause the bet favours.** That
is the correlational preview of belief-upstream the intervention was built to test, and it exists
on form B only.

**It survives a targeted attack on its most obvious confound [measured].** Incorrect-belief traces
run longer than correct-belief ones, and the number and positions of the scored points are
functions of that length — so a probe could reach 0.7431 by decoding *how long the
trace is*. On this same cell a probe given only three scalars — output length, how many estimate
points the trace has, and where they sit — and **no activations at all** reaches
**0.6767** against a null 95th percentile of 0.5912. Splitting
the traces into length terciles, removing the length and position components from every activation
coordinate on the training points, and training *and* scoring the probe inside a tercile still
leaves **0.6683** — above both its within-tercile null (0.5889) and the
same three scalars on the identical folds (0.6392). A pre-registered simulation
calibrated to this cell says a world where length explains everything produces that outcome
0.030 of the time. **The believed side is not reducible to trace length — but it is
not uniform across length either**: in the shortest tercile the activation probe beats the scalars
0.7750 to 0.5042, and in the longest the scalars still win, 0.8217 to
0.7342. *The test's power against an effect of the observed size is 0.710, so this
is a survived attack, not an exoneration.*

### 5.4 Invariance: marginal at the frozen layer, and the band is exploratory

| cross-form quantity | at ℓ\* = 22 | verdict |
|---|---|---|
| cos(v_p̂ form A, v_p̂ form B) | 0.2608 against null 95th pct 0.2443, p = 0.045 | **passes, barely** |
| probe transfer A → B | 0.5310 against null 95th pct 0.5310, p = 0.203 | **fails** |

**The frozen layer rule is this packet's own biggest problem, and was recorded as such before the
audit.** ℓ\* was fixed as the argmax of form A's p̂ probe curve — and that curve never beats its
own null at any of the 48 layers, so its argmax is a draw from noise. Layer
22 is where a noise curve happened to peak.

The layer curves put the signal higher up. Cross-form cosine beats its null in a contiguous band,
layers **21–36**, peaking at 0.4264 at layer
30 (p = 0.007); probe transfer beats its null across layers
**24–41**, peaking at 0.7597 at layer
28 (p = 0.001). ℓ\* is the first layer of the cosine band
and one short of the transfer band. **The result of record stays at ℓ\* = 22**: a
marginal cosine pass and a transfer failure. The layers
21–36 band is **[suggested]** and carries that label at every
citation here, including where the intervention chose its layer.

**The bridge to the original plan.** The prompt-side and belief-side directions are related but
far from identical where both exist: cos(v_p, v_p̂) is 0.432 on form B at ℓ\*, rising to
0.863 at layer zero, and 0.051 on form A. Had they been collinear the pivot
would have been cosmetic.

---

## 6. Causal results

### 6.1 The design, and what each outcome would have meant

A forward hook adds **α · ‖Δμ‖ · û** to layer ℓ's output at *every generated token position from
the first generated token onward*, where û is the unit-normalized direction and ‖Δμ‖ the raw
class-mean difference's norm, so α is in units of the direction's own scale. The prefill pass is
not modified. The primary layer L27 comes from form B's **own within-form** probe
peak, which is observational and involves no cross-form claim; the secondary layer
L30 is the peak of the **[suggested]** cross-form band and carries that label.
ℓ\* = 22 was deliberately not used: it is the result of record *and* was chosen by a
flawed rule, so intervening there would inherit the flaw for no gain.

**The sign was frozen before any steered token existed.** v_p̂ = mean(believes-above) −
mean(believes-below), so **+α was predicted to raise** `P(final > τ_B)`. No result below is
reported with that sign flipped.

**Arms.** 23 arms × 50 generations = 1,150 steered generations
at doses α ∈ {±1, ±2, ±4}, plus a sham arm with the hook installed adding zero, mirrored and
no-bet arms, and **10 random equal-norm directions** from a seed list frozen in
advance. A follow-up packet added 12 arms × 50 = 600
generations at α ∈ {±0.25, ±0.5} against four further random directions. ‖Δμ‖ at
L27 is 12.726012 against a mean residual-stream norm of 111.63, so the
pre-registered grid is **11.4 %, 22.8 % and 45.6 %** of the residual norm
and the follow-up's is **2.9 %** and **5.7 %**.

| landing moves with α, beating the random directions | verbalized belief moves with α | reading |
|---|---|---|
| yes | yes | the believed side is causally upstream and the verbalization tracks it — faithful |
| yes | no | the direction acts on the estimate policy, not on the talk |
| no | yes | annotation channel only: the direction writes the commentary, not the number |
| **no** | **no** | **v_p̂ is correlational; report at full volume as the null result** |

### 6.2 The apparatus is sound, and this is checkable

Three checks are load-bearing and all three ran on a laptop before any GPU existed. **The
injection arithmetic:** a smoke clause captures the layer's output before and after the hook on
every forward pass inside a real generation call, and confirms the prefill pass changes by
**exactly zero** and every decode pass by **exactly α·‖Δμ‖·û** to 1.19e-07 in single
precision. **The sham is a real α = 0 control, twice over:** the hook at zero produces **bitwise
identical** token ids to running with no hook, and the sham lands at 0.68 against the
unsteered frozen dataset's 0.5933 on the same extractor. **The direction's sign is
right:** form B estimate points project onto v_p̂ at mean −0.184 for believes-above traces
against −9.491 for believes-below, a gap of +9.31 in the direction the
pre-registration froze. **+α does push the residual stream toward the believed-above pole.** The
behaviour still goes the other way.

### 6.3 The primary contrast fails its null test, in the informative direction [measured null]

Primary basis is the corrected regex, with the raw regex and the extractor of record beside it.

| arm, L27, above-favoured | P(final > τ_B), corrected | raw regex | judge | median log₁₀ final |
|---|---|---|---|---|
| α = +4 | **0.04** | 0.00 | 0.04 | **6.828** |
| α = +2 | **0.34** | 0.08 | 0.32 | 9.328 |
| α = +1 | 0.52 | 0.14 | 0.52 | 9.695 |
| **α = 0 (sham)** | **0.68** | 0.24 | 0.60 | **9.977** |
| α = −1 | 0.54 | 0.30 | 0.52 | 9.685 |
| α = −2 | **0.48** | 0.28 | 0.46 | 9.643 |
| α = −4 | 0.24 | 0.20 | 0.24 | 9.602 |

| pre-registered statistic | value | 95 % interval | judge |
|---|---|---|---|
| Δ± = P(α=+2) − P(α=−2) | −0.14 | [−0.32, +0.04] | −0.14 |
| Δ+ = P(α=+2) − P(sham), scale-matched to the nulls | **−0.34** | [−0.52, −0.16] | −0.28 |
| Δ− = P(α=−2) − P(sham), scale-matched | −0.20 | [−0.38, +0.00] | −0.14 |

The 10 random equal-norm directions give Δ_j = P(null_j) − P(sham) with mean
−0.158, minimum −0.32 and maximum +0.12.

**Verdict against the frozen criterion — a statistic passes only if it exceeds every random
direction.** Δ+ = −0.34 beats **0 of 10**, one-sided
p = 1.000. Δ± beats 6 of 10, p = 0.455. Δ− beats
6 of 10, p = 0.455. **All three fail**, and the sign was
frozen before the first token, so the reversal cannot be re-read as success. *A two-sided reading
is available — the magnitude of Δ+ exceeds every random direction's magnitude by about one seed's
worth — and is recorded as post-hoc and not claimed, because no two-sided test was
pre-registered.*

### 6.4 The dose anatomy says magnitude, not side

**The profile is an inverted U centred exactly on the sham arm.** Landing falls on both sides of
zero dose and falls faster on the positive side (−0.64 at α = +4 against
−0.44 at α = −4). Monotone non-decreasing in α: **no**. The rank
correlation between α and the per-generation landing indicator is −0.1309 with permutation
p = 0.0159 over 350 generations — significant and **negative**, the reverse of
the prediction, and an artifact of the curve's asymmetry rather than of any monotone trend.

Three arms decide the interpretation, and each was pre-registered for exactly this purpose.

| contrast | Δ± = P(+2) − P(−2) | 95 % interval | what it shows |
|---|---|---|---|
| secondary layer L30 **[suggested band]** | −0.18 | [−0.36, +0.02] | the exploratory band does not rescue the prediction |
| **mirrored** arm, below-favoured | −0.02 | [−0.20, +0.16] | no α-sign effect at all where the favoured side is reversed |
| **no-bet** arm | −0.28 | [−0.46, −0.10] | the ±α effect is as large with the bet deleted as with it present |

**The no-bet arm is the sharpest single result in the project.** Its prompt contains no bet, no
threshold and no favoured side, so a direction acting on *the believed favoured side* has nothing
to act on. Injecting ±2·‖Δμ‖·û still moves the median estimate by 0.537 log
units — 9.611 unsteered against 9.340 at α = +2 and
9.877 at α = −2 — and the above-τ rate by 0.28. **A direction
that acts on estimated magnitude behaves exactly as observed.**

### 6.5 The verbalized belief does not move either

| arm, L27, above-favoured | correct / incorrect / unclear | labelled n | P(believes above) |
|---|---|---|---|
| α = +2 | 14 / 6 / 29 | 20 | 0.700 |
| **sham** | 27 / 12 / 11 | 39 | **0.692** |
| α = −2 | 19 / 20 / 11 | 39 | 0.487 |

The pre-registered flip is +0.213, interval [−0.041, +0.465]. **The sign is
the predicted one — the only pre-registered statistic in the project that gets its predicted sign
— and the interval includes zero, so the flip is not established.** Three things cut against it
even at face value. It is **one-sided against the sham**: the +2 arm moves
+0.008 and the −2 arm −0.205, so the entire contrast is the
negative arm suppressing belief-in-above. **A random direction moved it more**: a screen frozen in
the pre-registration forced two of the 10 random arms to be judged, and one
reaches P(believes above) = 0.878 against v_p̂'s 0.700 and the sham's
0.692 — *a screen-selected and therefore biased pair, so a caution rather than a test*.
And **the mirrored arm kills it**: on the below-favoured condition the same ±2 injection gives
0.049 and 0.068, no movement at all, where a direction that
causally sets the believed side should move both arms. The no-bet arms are a clean judge control —
mention rate 0.00 and every verdict *unclear*.

### 6.6 The low-dose follow-up, and a gate that fired on its own noise

**Status label, carried by every number in this subsection.** The follow-up was **designed after
the main result was known** — the doses were chosen *because* the pre-registered doses failed. Its
rules were frozen before its data, which is what that buys and nothing more, and **it does not
reopen the main verdict.**

**Coherence and content markers agree that these doses do not distort.** Coherence is
1.000 in all 12 arms; 0 truncated and 0 degenerate in
600; output lengths 392–439 against the unsteered
394; median log₁₀ estimates 9.34–9.98 against the
unsteered 9.611. Engagement with the bet is *higher* than at the main packet's
doses, 0.44 against the sham's 0.38.

**Result.** Δ±(v_p̂) at ±0.5 is **+0.10**, interval [−0.10, +0.30] (judge
+0.16, [−0.04, +0.34]). The sign is, for the first time, the
pre-registered one. It is not distinguishable from zero, it **reverses** at half that dose
(−0.02), and the four random directions do the same contrast at mean
+0.115 — one reaching +0.28 on an interval that excludes zero where v_p̂'s
does not.

**The frozen distortion gate fired, and it should not be trusted.** The gate averages, over the
eight random arms, the absolute difference between each arm's landing rate and the sham's, and
declares distortion above 0.06. Observed: 0.1875 on the corrected basis and
0.1425 on the judge basis, so the "even this dose distorts" row fired and **stands as the
verdict of record**. But that statistic is a mean of absolute differences between binomial
proportions at n = 50 and has a non-zero floor. Computed exactly under the null
the gate exists to detect — every arm the same coin, the injection doing nothing —
**E[D̄] = 0.0782 and P(D̄ > 0.06) = 0.648**. **A design that does nothing
whatsoever trips this gate about two thirds of the time**, so the two rows that would have
licensed a statement *about the direction* were jointly unreachable before a single token was
generated. The verdict row is reported, and reported as weakly informative by construction.

**What the arms actually look like: one common rate.** The 12 arms are mutually
homogeneous — χ² = 16.38 on 11 degrees of freedom, p = 0.128 — consistent
with a single landing rate across the value direction *and* random directions, both signs and both
dose sizes. Pooled: 285/600 = 0.475. That rate sits below the
α = 0 references (Fisher p = 0.0075 against the sham) **but does not scale with
dose**: 0.470 at the smaller dose against 0.476 at twice the dose, Fisher
p = 1.000, a difference of 0.006. **A distortion flat in dose is not a
distortion story.** The most economical reading at |α| ≤ 1 is one common rate near half with
sampling scatter, and an α = 0 reference at n = 50 reading high — and **the packet
cannot separate those, because it reused the earlier sham rather than generating a fresh one**, a
limitation declared before the data. *The homogeneity analysis is descriptive; no verdict rests on
it.*

### 6.7 What the causal work does establish

**Injecting along v_p̂ is powerfully causal on the estimate and is not believed-side-specific
[measured].** The most economical description of v_p̂ is a direction with a large component along
**estimated numeric magnitude**, whose believed-side content — real enough to decode at
0.7431 — is not what dominates when it is written back in. The evidence is §6.4's
three control arms together: the effect survives deleting the bet, does not mirror, and is matched
in size by random directions (mean Δ_j = −0.158).

**A bound [measured].** Whatever v_p̂-specific landing effect exists at
2.9–5.7 % of the residual norm is smaller than four random directions'
typical excursion at the same norm, at 50 generations per arm.

**And the design's own limit.** The pre-registered grid may sit entirely in a regime where generic
distortion dominates. Its smallest dose, 11.4 % of the residual norm, is already
**symmetric** in α (Δ+ = −0.16, Δ− = −0.14) — what a pure magnitude effect
looks like, not what a believed-side effect looks like — and the follow-up went lower and found a
flat offset rather than a gradient. **No direction-specific effect, and a direction-specific
effect below this design's resolving power, are not separated by anything in this project.**

---

## 7. Verdicts on the hypotheses

The hypotheses were restated when the interp target moved from the prompt-stated favoured side to
the trace-level believed side. The originals are mapped, not dropped.

**H1′ — the believed favoured side shifts the estimate computation. Correlationally supported,
causally unresolved.** The support is representational and real (§5.2–5.3): the believed side is
linearly decodable at estimate positions on form B, at 42 of 48 layers,
and 96 % of the carrying points precede the first mention of a cause. The
causal test then failed to distinguish the value direction from random directions of equal norm at
any of six doses. **A representation that is decodable and an intervention that is null are both
facts, and this project cannot say whether the null is the world or the instrument.**

**H2′ — the believed side gates the verbalization rather than the estimate. Untested.** The
design's route was the belief-flip statistic, and it did not clear its nulls: the interval
includes zero, the entire contrast is one arm moving, the mirrored condition shows nothing, and a
screen-selected random direction moved the statistic further than the value direction did. **No
intervention here moved verbalization above its nulls, so the hypothesis was never put to a test
that could have failed informatively.** Recorded as untested rather than rejected, because
rejection would claim power the design did not have.

**H3′ — the belief accumulates across the trace. [not tested].** The frozen dataset carries about
three in-window estimate points per trace, which cannot support an accumulation test, and the
intervention adds no per-point resolution. Declared before the intervention ran, not after it
disappointed.

**The original hypotheses, over the prompt-stated favoured side.** Superseded by the two pivots,
with the mapping documented in the ledger. Their shared premise — that this model class shows a
prompt-stated landing gap large enough to localize — is itself now **[measured]** and the
measurement is unfavourable: +0.017 on the original surface form at
n = 150 per side and +0.120 on the reskin, with the reskin's pass
convention-dependent. **In this model class, at this n, the prompt-stated landing gap is fragile
to absent.** That is a finding about the phenomenon, not the apparatus, and it is why the
belief-conditional target was the right move even though it did not resolve the causal question.

---

## 8. What would have fooled us

Each of these was, at some point, the natural thing to write. Each was killed by a control that
existed before the result did — or, in the last three cases, by a check that should have existed
and did not.

**Hook misalignment.** The interp programme rests on the captured positions being the positions
the parser named, and nothing downstream would reveal a one-token offset: a probe on misaligned
activations still returns a number with a null to beat. The control is a decode check — decode
each sampled span's stored token ids and compare to the literal as it appears in the trace.
**34 of 34 exact**, commas included, with a second check at the analysis
stage reproducing 30 / 30 of its own sample including a literal one unit above τ.
Position indexes were built twice on different machines and agree on every one of
6,668 positions.

**The threshold-digit confound, and the near-miss inside it.** The prompt contains τ, and both
models answer then justify, so the frozen last-literal rule returns τ itself in a large share of
answers — 57.3 % of form A traces and 556 of 1,150
steered generations, where the rate **varies systematically with the injected dose**
(78 at α = +1 against 46 at α = −1). Raw landing rates under that rule are
uninterpretable and never used for a verdict. **The near-miss:** the activation capture was
specified with a "final answer" position kind, and on form A that position is a threshold echo in
most traces — a final-only capture would have localized *the model echoing the prompt's threshold*,
produced a clean-looking direction, and meant nothing. The corrected-final position was added as a
flagged judgment call and is what saved it.

**Prompt-stated-p triviality.** Computed *between* the mirrored conditions, a probe could succeed
by reading the prompt rather than the model's belief, because the prompt states which side is
favoured and that text is in the context window. The design computes the direction **within a
single condition**, contrasting traces that believe different things while reading identical text.
This is not a control that was run and passed; it is a confound removed by construction, and it is
the strongest methodological consequence of the pivot to the believed side.

**Text-level steering.** An intervention that made the model *say* it wanted a higher number would
change landing for an uninteresting reason. A deterministic screen over every steered generation
finds **0 of 1,150** and **0 of 600** generations
verbalizing an injected preference. The failure mode did not occur at any dose.

**Position and verbosity confounds.** A verbose trace contributes more estimate points than a
terse one, so activations are averaged within a trace before the classes are compared; and a
direction could be a proxy for "this literal is large", so the construction stratifies on whether
the literal exceeds τ and averages the strata equally. The positive control confirms the
stratifying variable is itself strongly decodable (0.9916), which is why it had to be
stratified out.

**The winner's curse.** Covered in §4.3, and in this register because the natural sentence to write
after screening was "this model shows a +0.32 landing gap" — and that sentence
was false. What killed it was a frozen dataset at three times the n with the seed block as the
only difference.

**Coherence metrics that cannot see epistemic distortion.** The coherence rule has four clauses:
finished on a stop token, non-empty answer, parseable final estimate, not n-gram-degenerate. It
reads 22 of 23 arms at 1.000 and was reported as "the intervention
did no damage". Reading the highest-dose samples shows what that number cannot see: the model
**fabricates coherent low-ball reasoning**, arguing in fluent, arithmetic-showing prose toward an
estimate far below the threshold, and passes all four clauses. A named screen for that signature —
a sentence dismissively comparing the estimate to the threshold, *and* a final estimate two orders
of magnitude below it — fires on **9 of 50** generations at
α = +4, **0 of 50** at the sham, and
**3 of 600** at the low doses. **"Coherence 1.000" licenses "the
text is well-formed" and nothing more**, and that correction is attached to the word wherever it
appears here.

**Pre-registered knobs frozen without a noise-floor check — three times.** This is the
methodological finding of the project, and it recurs in a different currency each time.

| what was frozen | the knob | how it failed |
|---|---|---|
| the probe layer | ℓ\* = argmax of a curve never required to beat its own null | the argmax of a noise curve; the informative band is layers 21–36 |
| the injection dose | α in units of ‖Δμ‖, without asking what fraction of the residual stream that is | the whole grid may sit where generic distortion dominates: 22.8 % and 45.6 % of the residual norm |
| the distortion threshold | D̄ > 0.06 | below the statistic's own floor: E[D̄] = 0.0782 under a design doing nothing |

**The fix is cheap and is named**: simulate the pre-registered statistic under its own null
*before* freezing the threshold, and set the line above the resulting floor. For the distortion
gate that is a few minutes of laptop arithmetic on a closed-form binomial convolution. **No
pre-registration in this project ever did this.** Freezing a rule before the data is necessary and
is not sufficient: a pre-registration must also freeze evidence that the chosen setting and
threshold lie inside the range the design can resolve.

**Estimator discipline: never patch an instrument after seeing its errors mid-flight.** Four
occasions invited it and none took it. The last-literal extractor failed on answer-first models and
was left unpatched — the models it failed were excluded on apparatus grounds instead. It failed
again on incentive prompts and was left unpatched — a corrected *reporting basis* was defined
instead, with the raw number always printed beside it. The API cost estimator under-shot by
52.9 % and was left unpatched — the corrected constants were written into the ledger
for the next packet to use explicitly, which cut that packet's projection error to
11.1 %. **In every case the correction is a new, separately-cited artifact and the
original instrument still produces the number it always produced**, which is what makes the
before/after comparison possible at all.

---

## 9. Open questions, and the deferred programme

The causal question is open and the shape of the experiment that would close it is now clear,
which is the most useful thing a null result produces. **A properly powered low-dose ladder** is
the first move: the doses that matter are below the ones run here, the statistic that would read
them is a landing rate at n far above 50 per arm, and every frozen gate's
threshold must be simulated under its own null before it is frozen — the failure that cost this
project its two cleanest verdict rows. **Activation patching at belief points** is the second and
the better instrument for this question: patching one trace's residual stream into another at the
positions where the belief is decodable tests whether *that* state carries the estimate, without
adding a norm-scale perturbation whose direction-independent effects swamped everything here.
**Small-model belief-tracking deserves study in its own right**, because the comprehension
asymmetry found here — one mirror of the same bet understood most of the time, the other barely
better than chance — is large, cheap to measure, and is what makes the aggregate landing gap in
this model class a mixture rather than an effect. **And the covert–overt scale question is the one
this project can only gesture at**: a model of this size announces the bet in nearly every trace
while the larger panel almost never does, and nothing here can say whether that is scale, family,
tuning, or prompt surface, because the comparison spans two studies with two model families and no
sweep.

---

## 10. Methods register

**Models and stack.** `Qwen/Qwen2.5-14B-Instruct` at snapshot `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8`, bf16, on one
A100-SXM4-80GB. The frozen dataset was generated with vLLM 0.28.0; activation replay and
every steered run used `transformers` 4.57.6 on torch 2.8.0+cu128, because the
intervention needs a hook that persists across decode steps and vLLM cannot carry one. The
extractor of record is `claude-sonnet-5`, pinned; the direction judge's prompt is frozen at
sha256 `0e6f763f3bd6c65380c84deceb01eb48fe914f65b9bbdc358f4c791a3edc8148` and was verified unchanged after a transport-level fix. The
injected direction is `analysis/out/w5_vectors/w5_vphat_B.safetensors`, sha256
`cbdbbb4a4eccfd085549d3aa1a6b94170c77252bd2dd64718b4f950426b9be64`, verified at load time on every arm and recorded in every output file.

**Prompts.** Not reproduced here: they are obtained by calling upstream's own
`build_prompt(condition, threshold)` at frozen commit `16d129859e1f0e281363fb4f5910bcaeea316b10`, and the form B
reskin is `src/prompts_w3.py`, whose selftest asserts that exactly one substring differs and that
both bet paragraphs survive byte-for-byte. **Interpreter note:** that selftest reaches through the
frozen upstream tree and needs the project virtual environment, not the bare system interpreter —
of the seven cited verification commands re-run for this document, six run under `python3` and
that one does not.

**Seeds.** Base seed 64, rollout *i* at base + offset + *i*, blocks a thousand
apart. Verified at build time: 1,750 steered generations across
8,064–9,813, all distinct and contiguous, 0 collisions with each
other or with any earlier block.

**Spend, final: $13.42 GPU + $16.06 API = $29.48** of a
$60 cap; balance $30.52. The $45 surfacing
threshold was never approached. The API line overtook the GPU line at the intervention packet and
stayed there.

| packet | GPU | API |
|---|---|---|
| setup and provisioning | $0.00 + $1.77 | $0.00 |
| neutral calibration | $1.84 | $0.45 |
| mirrored screening | $6.64 | $0.54 |
| frozen dataset | $0.32 | $5.36 |
| activation replay | $0.77 | $0.00 |
| the value direction | $0.84 | $0.00 |
| the intervention | $0.73 | $7.7812 |
| the low-dose follow-up | $0.51 | $1.9334 |
| this document | $0.00 | $0.00 |

**Time.** Runner wall time per packet: 7 min, 2 h 05 m, 2 h 05 m, 5 h 10 m,
1 h 20 m, 1 h 05 m, 51 m, 1 h 00 m, 45 m, and 1 h 35 m for this
one. Billed GPU wall time: 1 h 17 m, 1 h 15 m, 4 h 52 m, 13 m 37 s,
33 m 02 s, 36 m 27 s, 31 m 29 s, 19 m 25 s. Compute occupied
72.7 % of the intervention packet's billed pod time and 60.1 % of the
follow-up's; the generation runs were 1373.1 s and 656.5 s, and all
700 activation-replay forward passes took 94.8 s.

**The owner clock was never supplied.** It was asked for with every packet through the fifth
request and no figure was ever given, so the 16-hour owner budget in the project's
orientation document is **unauditable**, and all time accounting here rests on runner wall time and
billed pod time alone — both independently checkable against the provider's pod records. Stated
plainly rather than estimated.

**Pre-registration precedence, from the commit graph rather than from memory.** The intervention's
pre-registration is commit `de12985` at 2026-08-30 05:45:19 UTC, and the first steered token
followed 13 m 11 s later. The follow-up's is `32667d7` at 06:44:14 UTC,
11 m 51 s before its first steered token. Neither run directory existed when its
pre-registration was written.

**The workflow, disclosed plainly.** This project was executed by an LLM-agent structure with
three roles and no overlap. A **researcher** designed the experiments, audited each packet's
report, and promoted provisional results to established ones; it executed no code. A **runner** —
a Claude Code CLI agent on the owner's laptop, driving rented GPU pods over SSH — executed one
self-contained work order at a time and reported back; each order was self-contained because the
runner's context did not survive between packets. A human **owner** relayed messages and approved
every dollar of spend. Every number here comes from an append-only ledger written by the runner
and audited by the researcher, in which entries are never edited: a wrong entry is corrected by a
later entry that names it, and three such corrections were filed while assembling this document.

**Regenerability.** Every number here is substituted at build time from a file in
`analysis/out/`, and a build-time check refuses to emit a digit that is neither substituted nor
matched by a structural whitelist. The document rebuilds byte-identically with
`python3 writeup/build.py`. The commands behind the generated files are
`python3 src/w10_skeptic.py`, `python3 src/w10_derived.py` and
`python3 src/w10_ledger_facts.py`, each reading only committed rollout files, committed CSVs, and
the ledger itself.
