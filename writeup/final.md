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
representation, failed to make it causal at the activation level in three independent attempts,
and then showed — by intervening on the text instead — that the belief really is driving the
behaviour. **The gap between those two answers is the result.**

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

**But the belief does drive the behaviour — through the text [measured].** Wave 2 attacked the
same question from the side an activation edit cannot reach. Rewriting the bet note so the model
understands it *better* raised comprehension to 0.8333 and moved the landing gap to
+0.2867 [+0.180, +0.393] — inside the +0.3600 [+0.241,
+0.476] that §4.4's frozen cells predict in advance, which is row C1 at a distinguishing
power of 0.851. Rewriting it as a **length-identical** nested negation so the model
understands it *worse* dropped comprehension to 0.2905 and collapsed the gap to −0.0067
[−0.113, +0.107], again inside prediction. **The three points —
+0.2867 clarified, +0.1200 natural, −0.0067 degraded — are a
dose-response law [measured]**, with two qualifications that travel with them: the mixture
over-predicts the size of the move in both directions (−0.0734 and +0.1151),
and the degraded point's *comprehension* coordinate is **[suggested]**, because the judge that
measures comprehension fails on exactly the wording that breaks the model and **human calibration
of the direction judge on degraded wording was pending at submission**.

**The last experiment carried the belief back to the activations, and it did not survive the trip
[measured null].** Swapping the belief component between traces of the same prompt that formed
opposite beliefs moved landing by **Δ_swap = +0.0000 [+0.0000, +0.0000]**
in both directions, at 40 disjoint pairs each. **Its own qualification is larger than
the result**: the pre-registered cut left only 6 of 40 landings
still movable, so achieved power was 0.00–0.87 against the
0.97–1.00 declared — and a post-hoc diagnostic at full
surface, where 26 of 40 pairs genuinely change their final number,
still shows nothing **[suggested]**. **The model's belief about the favoured side drives its
estimate through the text channel, demonstrably; no one-dimensional activation-space handle on
that belief was found at any operation or power this project could reach.**

**The activation-level question is unresolved [not tested at resolving power].** The direction
stands as correlational. **Four pre-registrations in this project fixed a knob outside the range
their own design could resolve** — a probe layer chosen as the argmax of a curve never required to
beat its own null, an injection dose grid that may sit entirely where generic distortion
dominates, a distortion threshold set below its own statistic's floor, and a transplant whose
declared power rested on a locked-fraction parameter measured on the wrong object. The first three
share one cause: **no pre-registration before Wave 2 simulated its frozen statistic under its own
null before setting the line.** The fourth is the more interesting one, because by then the rule
existed and was being followed: the simulation was methodologically correct at every step and
calibrated on the traces the experiment started from rather than the continuations its statistic
would be computed on, and it over-stated power from 0.997 to 0.000
at the worst cell. **Freezing a rule before the data is necessary and is not sufficient, and
simulating the statistic is not sufficient either: the simulation has to run on the object the
statistic will actually be computed from.** That is the methodological finding, and it is reported
at the volume the empirical ones get.

**Scale.** 5,180 generations — 2,380 of them in Wave 2 —
6,668 captured residual-stream positions over 700 replayed traces, and
2,110 generations carrying an activation intervention (1,750 steered
along the direction, 360 with the belief component replaced).
$19.30 GPU + $30.87 API = $50.17 against a
$60 cap, across 16 work orders.

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
in §8 rather than dropped.

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
incentive prompt the same rule's disagreement rises to 28.0 % and 44.0 %. §9
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
0 verdicts were unparseable after the transport fix of §9. The predecessor panel's
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

## 7. Wave 2 — the text channel is causal, the activation channel is not

Sections §3–6 are the project as first scoped: build the direction, steer along it, report the
null. **Wave 2 is five packets the owner authorised after that null**, and it exists to attack
the question the null left open — *is the null the world, or the instrument?* — from the side the
first six sections could not reach. Two packets intervene on the **text** that carries the belief.
Two attack the **decodability** result that everything upstream rests on. The last returns to
activations one final time with a different operation and a pre-registered power calculation.
**The verdict is split and both halves are of record.** Negative results below are reported at the
same length as positive ones, because in this project they are the same size.

### 7.1 The belief-mixture is causally load-bearing at the text level — upward [measured]

§4.4 decomposes the landing gap into a comprehension-weighted mixture of two large opposite
belief-conditional effects. A decomposition that fits four cells is a description, not a
mechanism. **W11 tested it causally**: one clarifying sentence was added to the bet note on form
B — nothing else changed, and the prompt grows from 197 to 254 tokens
— and the **frozen W3 cells were then asked to predict the new landing gap in advance** from the
new comprehension rates alone.

Comprehension rose as intended, from 0.5467 to **0.8333** on the `above_good` arm and
from 0.8067 to **1.0000** on `below_good`. Landing followed: 0.6067 against
0.3200, an aggregate gap of **+0.2867** [+0.180, +0.393] at
n = 150 per arm, against the frozen formula's prediction of +0.3600
[+0.241, +0.476]. **The observed gap lands inside the predicted interval and row
C1 fires at a distinguishing power of 0.851** — the mixture, not a rival flat model, is
what the manipulation moved.

**The form-A arm is reported and is not a test.** Its gap is +0.1867 against a prediction of
+0.2323 — descriptively inside — but its distinguishing power is **0.486**, which
the pre-registration itself had ruled below the line at which the arm may be read as evidence. It
is printed because it was run, not because it decides anything. **Nor did the belief-conditional
cells move the way a naive reading would want**: the `corr` conditional gap is +0.3739
here against +0.4456 on the same W3 cells, every cell drifted slightly down, and **no
single cell's move is resolved at this n**. The claim is about the mixture's aggregate
prediction, and it is that claim alone that fired.

### 7.2 Belief formation has no readable onset, and the curve that looked like one was length [measured null]

**W12 asked when in the trace the believed side becomes decodable.** It replayed the frozen
dataset with hooks and swept a probe across three alignments: offset from the first cause token,
absolute token index, and trace fraction. 238 traces carry a usable belief label
and 167 of them contain a cause token to anchor on.

**The frozen onset criterion — 4 consecutive bins above the null's
0.995 percentile — does not fire, at any layer, in any family.** The layer sweep is
equally flat: the frozen best layer is L29 and the eight swept layers span
0.5537–0.5570, a range far too narrow for the argmax to mean anything —
**the same failure mode §5.1's ℓ\* has, found a second time by a rule that had to name it in
advance.** Belief *flips* were the other pre-registered outcome and there are **0 of
238** under the ordered rule and **0** under the strict one,
with a label-shuffled empirical false-flip rate of 0.0000: the statistic is not
insensitive, there is simply nothing in the data for it to catch.

**One alignment did rise, and it is a length artefact [measured].** The trace-fraction curve
climbs monotonically and clears its null — and a probe with **one feature, the trace's output
length, and no activations at all**, reads 0.6421 on the same traces, folds and null.
Decile boundaries scale with generated length, and generated length is associated with the
believed side: traces that get the mapping wrong run **123 tokens longer** on
average (526.2 against 402.9). **The trace-fraction result is
therefore not a timing result**, and the two length-invariant alignments, which are the ones that
can be read, are both flat. This is **D-042**, promoted to a standing instrument finding: *any
statistic binned on trace fraction in this dataset is confounded with the outcome it is
predicting.*

**The packet's other product was a census that re-sized a later experiment.** Of the traces with
a cause token, 98 carry a valid cut point; 270 opposite-belief
same-condition pairs exist but only **6** of them are disjoint. That number
is why the belief transplant was cancelled once (§7.5) before being re-sized and run.

### 7.3 The decodability result survives a targeted length attack [measured]

D-042 raises an obvious question about §5.2: if length predicts the believed side, is the probe
in §5.2 a length probe wearing activations? **W13 attacked E-007 with its own confound** and the
result is integrated where it belongs, in **§5.4** — the frozen within-tercile rung, the
length-only baseline on identical folds, the shortest- and longest-tercile split, and the
simulation showing a pure-length world produces that outcome 0.030 of the time.
**The finding survives and is narrower than the number it defends**: the believed side is not
reducible to trace length, and it is also not uniform across length. Nothing in Wave 2 changes
that reading; it is restated here only so the addendum's inventory is complete.

### 7.4 The mixture tracks downward too — and the instrument that measures it breaks on the same words [measured, with a suggested coordinate]

One point is a fit. **W14 pushed comprehension the other way**: the bet note's two mapping
sentences were replaced with a semantically identical **nested-negation paraphrase**, proved
equivalent by an explicit truth table over all four branches. The degraded prompt is
197 tokens — **exactly W3's 197** — so unlike W11 the manipulation adds
no length at all, which is the control D-042 makes mandatory.

Comprehension fell as intended, 0.5467 → **0.2905** and 0.8067 →
**0.5772**, and the aggregate landing gap fell with it. Landing is 0.6067 on
`above_good` against 0.6133 on `below_good` at n = 150 per arm — a gap of
**−0.0067** [−0.113, +0.107] against the same frozen formula's −0.1217
[−0.244, +0.001]. **Row D1 fires**, and both pre-registered alternatives are resolved — power
0.985 against "the gap stays where W11 left it" and 0.974 against the harder
"the gap stays at W3's level". **The three-point curve is +0.2867 (clarified) →
+0.1200 (natural) → −0.0067 (degraded)**, monotone in comprehension, and it falls
on every extraction basis.

**The mixture over-predicts the size of the move in both directions.** W11 came in
−0.0734 against its prediction and W14 +0.1151 against its — opposite signs,
same message. **The true response to comprehension is flatter than the frozen W3 cells say**, and
W11 alone could not see that: it read its own residual as "the lower half of the interval". Two
points make it a property of the model rather than of one arm. *The dose-response law is*
**[measured]**; *the flatness correction is* **[suggested]** *— two residuals are not a curve.*

**D-051 — the degraded wording breaks the direction judge, not only the model.** The frozen judge
is handed the prompt and must solve the same nested negation the model does, and it fails the same
way: **67 of the 86** `below_good` traces it called `correct`
landed on that arm's unfavoured side, and one concludes verbatim that clearing τ means the
donation will *not* go to the bad cause and will therefore go to the good one — the opposite of
its own prompt. An independent regex instrument that never reads the mapping sentence agrees with
the judge 0.9032/0.9605 on natural wording and
**0.2895/0.5000** on degraded. On the calibrated basis the
belief-conditional cells **do not move at all** (0.5364 against W3's
0.4520), where the frozen basis says they collapsed and crossed (−0.0814
against +0.4456); on W3 the two instruments reproduce each other to
0.4520 versus 0.4456, which is what earns the diagnostic the right to
be believed about the *direction* of the discrepancy. **Read alone, the frozen interaction table
says the opposite of the truth.**

**Both halves are the claim of record, and they carry different tiers.** The landing collapse is
**[measured]** — landing rates are judge-independent and recount-confirmed on every basis. **The
degraded point's comprehension coordinate is [suggested]**, because the only instrument that
produced it is the one D-051 shows failing on exactly these words, and **because human
calibration of the direction judge on degraded wording was pending at submission**: a blinded
70-row hand-label sheet was built, sealed and sent, and 0 rows had been
returned when this document was frozen. The judge's own failure is promoted in its own right —
**an LLM-judge validity result**: the judge fails exactly where the model fails, so a judge and a
subject that share a weakness cannot be used to measure that weakness. Its early warning was on
the invoice, not in the analysis: the same traces made the judge emit an order of magnitude more
output tokens than any prior packet's constant predicted. §4.4's decomposition and §7.1's upward
test are **not** disturbed — both read natural or clarified wording, where the judge is calibrated.

### 7.5 The belief transplant: a measured null, and a design that could not have found anything [measured null]

**W15 was the project's last experiment**, and it asked the cleanest activation-level question
available: take two traces of the *same prompt* that formed *opposite* beliefs, and swap the
belief component of one into the other. Unlike §6's additive steering, this operation adds no
norm-scale perturbation of its own — it replaces one class's mean profile with the other's — so
the direction-independent effects that swamped §6.4 do not apply.

**The harvest.** 1,000 fresh rollouts of the natural-wording prompt — the same
197 tokens as §4's frozen dataset — were screened by the regex instrument for free, 435 carried a usable belief label, and only the
60 majority-class and 98 minority-class candidates were sent to the paid
judge — which is what kept the packet inside its ceiling. Judge and regex agree
0.8411 on that deliberately class-balanced pool, below §4.6's natural-mix figure and
the honest number for the set the pairs came from. **40 disjoint pairs** were formed
in each direction, against the 6 that §7.2's census made available a packet
earlier; the difference is one dropped constraint, and it is the whole reason the experiment
could run at all. Each pair's A-trace was teacher-forced to a cut point (median
355 tokens) under a hook that replaces the belief component, and the
continuation was regenerated under four arms — SWAP, SHAM, SELF, RAND.

**Nothing moves.** On the corrected-regex basis the four primary arms read 0.1500 /
**0.1500** / 0.1750 / 0.1750, and the mirror direction reads
0.0500 / **0.0500**. **Δ_swap = +0.0000 [+0.0000,
+0.0000]** in the primary direction and +0.0000 in the mirror, identical on the
judge basis. The two controls move as much as the treatment or more — Δ_self +0.0250,
Δ_rand +0.0250 — so Δ_swap − Δ_rand is −0.0250 [−0.0750, +0.0000], i.e.
**the value-carrying edit does slightly worse than a random direction of four times its norm.** The decision rule the
pre-freeze simulations forced — both signed contrasts, against RAND and against SELF — **fires on
neither landing nor verbalization, in either direction**. Coherence is 1.000 in every arm
and 0 generations truncated, **with §9's caveat attached: coherence is blind to
epistemic distortion.**

**The reason it does not move is measured, and it is larger than the null.** Three facts, in
ascending order of how much they cost:

| | value |
|---|---|
| continuation the frozen cut leaves, median | **33.5** tokens |
| reconstructions whose final estimate is *inside* that continuation | **6 of 40** — the rest were fixed in the prefix before any arm ran |
| SWAP continuations differing in text from SHAM | 12 of 40 |
| SWAP continuations differing in **final value** | **1 of 40** |

**And the pre-freeze simulation that declared the design powered had measured its own nuisance
parameter on the wrong object.** The locked fraction λ was measured as *"does the trace's own
final literal precede the cut"* — 0.2632, a correct measurement of that quantity —
when the statistic is computed on the **regenerated** continuation, where the locked fraction is
**0.85** (34 of 40). Re-running the frozen
simulator at the measured value takes the worst cell's power from 0.997 to
**0.000**. **The achieved power against the ordered alternative is
0.00–0.87, not the 0.97–1.00 the
pre-registration declared** — and that admission is attached to this null wherever it is cited.

**The edit is real and the contrast is not.** The perturbation norms are 2.7957 for
SWAP and 2.7582 for SELF, so **the two arms whose difference *is* the experiment
differ from each other by about 0.04 — the defining contrast is
5.8× smaller than the noise it sits in.** RAND moves 13.0453,
4.7× SWAP's, which by the frozen definition makes it a **conservative** control
that errs against the finding. Underneath all of it is the ceiling: at the frozen layer, over
prefix positions, the two belief classes' mean projections onto the direction are
12.7327 and 12.5905 — a separation of 0.1422 in the aggregate and
0.5391 as a mean per-grid-point magnitude — against a within-class spread of
3.1345. **Separation over sd is 0.1720.** The substitute decoded-belief probe built on that
coordinate is non-discriminative and is reported as an instrument failure, not as evidence.

**The bound, and it is a post-hoc one [suggested].** A null measured on no surface cannot
distinguish *"the belief is not transplantable"* from *"the operation had nothing to act on"*, so
the same pairs, arms, seeds and edit were re-run at a deeper cut. **This diagnostic was designed
after the frozen result was read** — its cut was chosen for legibility, not on its outcome — it
writes to its own directory, it never enters the frozen statistic, and it must be read as a
clearly-labelled post-hoc bound.

| | frozen cut | deep cut |
|---|---|---|
| median continuation | 33.5 tokens | **234.0** tokens |
| final estimate inside the continuation | 6 / 40 | **40 / 40** |
| SWAP text differs from SHAM | 12 / 40 | **35 / 40** |
| SWAP **final value** differs from SHAM | 1 / 40 | **26 / 40** |
| Δ_swap | +0.0000 [+0.0000, +0.0000] | **−0.0250 [−0.1750, +0.1500]** |
| Δ_swap − Δ_rand | −0.0250 | **−0.0250 [−0.2250, +0.1500]** |
| power against the ordered alternative | 0.00–0.87 | **0.954–0.995** (false-fire 0.013) |

**At full surface, with 26 of 40 pairs genuinely changing their final
number, the transplant still moves landing by −0.0250 and still fails to beat its
control.** The diagnostic reaches four-fifths power at δ ≈ 0.32, so an effect of the
size §4.4's belief-conditional cells show would have been seen. **The null survives its own
bound.** One of twenty diagnostic intervals excludes zero — SELF lowers verbalization by
−0.1750 [−0.3250, −0.0500] — which is the
expected count at this interval level, is the arm that installs a trace's *own* class mean, and
is reported as such rather than as a result.

**What is not claimed.** Not that the direction carries no belief information — §5.2 stands and
§5.4 defended it. Not that the operation was potent — its own anatomy measures it at
0.1720 of a within-class σ in the belief coordinate. And no decoded-belief result at
all, because that instrument failed.

### 7.6 What Wave 2 settles, and the one explanation it leaves standing

**At the text level the belief-mixture is causally load-bearing [measured].** It was confirmed
upward at a distinguishing power of 0.851 and downward by a landing collapse that does
not depend on the judge; the degraded point's *quantitative* coordinate is **[suggested]** for the
reason §7.4 gives. **At the activation level, three independent interventions — additive steering
at six doses, a low-dose ladder with matched nulls, and the belief transplant — produced no
direction-specific effect**, and the belief representation, real and defended against the length
confound, **remains correlational.**

**The project's answer to its own central question, stated once and plainly: the model's belief
about the favoured side drives its estimate through the text channel, demonstrably; no
one-dimensional activation-space handle on that belief was found, at any operation or power this
project could afford.**

**One candidate explanation survives, and it is [suggested].** The direction every intervention
here used is a **mean-difference direction in one dimension**, and §7.5 measures what that buys:
0.1720 of within-class σ of per-point separation between the two belief classes.
**Every intervention this project ran therefore operated through a channel with a low ceiling** —
which would produce exactly this pattern of results whether or not the belief is causal, and which
no experiment here can separate from a genuine absence. A distributed or nonlinear transplant is
the first item of the deferred programme in §10 for that reason.

---

## 8. Verdicts on the hypotheses

The hypotheses were restated when the interp target moved from the prompt-stated favoured side to
the trace-level believed side. The originals are mapped, not dropped. **These verdicts are the
amended ones: Wave 2 closed the causal section, and where it changed a verdict the change is
stated here rather than appended.**

**H1′ — the believed favoured side shifts the estimate computation. CAUSALLY SUPPORTED AT THE
TEXT LEVEL [measured]; UNRESOLVED AT THE ACTIVATION LEVEL [not tested at resolving power].** The
representational support is real and survives its own best attack (§5.2–5.4): the believed side is
linearly decodable at estimate positions on form B, at 42 of 48 layers,
96 % of the carrying points precede the first mention of a cause, and a
targeted length attack does not reduce it to trace length. **The causal support is text-level and
it is the strongest positive result in this document**: moving comprehension up and down against a
formula frozen on the original four cells moves the landing gap both times, inside prediction both
times, at distinguishing powers of 0.851 and 0.974 (§7.1, §7.4). **The
activation-level causal test failed three times** — six doses, a low-dose ladder with matched
nulls, and a belief transplant — and none of the three could distinguish the value direction from
its controls. **A representation that is decodable, a text intervention that works, and an
activation intervention that is null are all three facts**, and what this project cannot say is
whether the third is the world or the instrument. §7.5 measures one candidate for "the
instrument": the coordinate every intervention used separates the belief classes by
0.1720 of their own within-class spread.

**H2′ — the believed side gates the verbalization rather than the estimate. Untested, and now
untested at two operations rather than one.** The design's route was the belief-flip statistic,
and it did not clear its nulls: the interval includes zero, the entire contrast is one arm moving,
the mirrored condition shows nothing, and a screen-selected random direction moved the statistic
further than the value direction did. **The belief transplant re-asked the same question with a
different operation and the verbalized-mapping contrast is null there too**, in both directions
and at both cut depths (§7.5). **No intervention in this project moved verbalization above its
nulls, so the hypothesis has still never been put to a test that could have failed
informatively.** Recorded as untested rather than rejected, because rejection would claim power
no design here had.

**H3′ — the belief accumulates across the trace. AMENDED: tested, and null at the frozen
criterion [measured null].** The original verdict was **[not tested]** — the frozen dataset
carries about three in-window estimate points per trace, which cannot support an accumulation test
built on estimate positions, and it was declared before the intervention ran rather than after it
disappointed. **Wave 2 built the instrument the original design lacked**, replaying
238 labelled traces and sweeping a probe over every generated position on three
alignments. **The pre-registered onset criterion — 4 consecutive bins above the
null's 0.995 percentile — does not fire at any layer in any family, and there are
0 belief flips of 238** against a label-shuffled false-flip rate of
0.0000. **The one alignment that did rise is a length artefact** and is retracted in
§7.2, not defended. So: no readable onset and no flips at this resolving power, on a dataset where
the belief is decodable — which is a real constraint on any accumulation story, and is not the
same as showing the belief arrives all at once.

**The original hypotheses, over the prompt-stated favoured side.** Superseded by the two pivots,
with the mapping documented in the ledger. Their shared premise — that this model class shows a
prompt-stated landing gap large enough to localize — is itself now **[measured]** and the
measurement is unfavourable: +0.017 on the original surface form at
n = 150 per side and +0.120 on the reskin, with the reskin's pass
convention-dependent. **In this model class, at this n, the prompt-stated landing gap is fragile
to absent.** That is a finding about the phenomenon, not the apparatus, and it is why the
belief-conditional target was the right move even though it did not resolve the causal question.

---

## 9. What would have fooled us

Each of these was, at some point, the natural thing to write. Each was killed by a control that
existed before the result did — or, in the later cases, by a check that should have existed and
did not. **Wave 2 added five entries to this register and only one of them is about the
phenomenon; the rest are about instruments, and one is about a machine nobody was watching.**

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

**A judge that fails exactly where the model fails.** The direction judge is handed the prompt
and must work out the bet's mapping itself — a deliberate choice, so one prompt serves both
mirrored arms without a per-arm hint. Under §7.4's nested-negation wording it has to solve the same
puzzle the model does, and it fails the same way: **67 of the
86** traces it labelled `correct` on the `below_good` arm had landed on that
arm's *unfavoured* side. An independent regex instrument that never reads the mapping sentence
agrees with it 0.9032/0.9605 on natural wording and
0.2895/0.5000 on degraded. **The frozen interaction table for that
packet, read alone, says the belief-conditional cells collapsed and crossed (−0.0814);
the calibrated instrument says they did not move (0.5364 against
0.4520 on the same quantity in W3).** What would have been written is "degrading
comprehension destroys the belief-conditional structure", and it would have been an artefact of
the measuring device. **The general form: a judge and a subject that share a weakness cannot be
used to measure that weakness** — and the first warning came from the invoice, where those traces
made the judge emit an order of magnitude more output tokens than any prior packet's constant
predicted, days before the analysis noticed anything. The independent instrument is post-hoc and
resolves only 80 of 300 degraded traces; its calibration on natural
wording is what earns it the right to be believed about the *direction* of the discrepancy and
nothing more.

**An extractor choice that silently destroys a screen.** §7.5's harvest screens a thousand
rollouts with a regex so that the paid judge only ever sees candidates. Two frozen extractors were
available and the work order named neither: on the frozen dataset the corrected one agrees with
the judge 0.9467 and the raw one 0.6316. **Picking the wrong one would have
screened at chance and poisoned every pair the packet went on to build**, invisibly, because a
screen that mislabels produces pairs that look exactly like good pairs. It was caught by a dry run
of the screen on frozen data **on the laptop, before the pod existed** — ten minutes, zero
dollars. **The rule this yields: run every screen against a dataset whose answers you already
know, before renting the machine.**

**An unattended GPU job that nobody was watching.** The last packet's frozen stack could not run
on the machine the pod happened to land on — same script, same image, different driver. The
fallback worked and the packet's results are unaffected. **The finding is not the driver
mismatch; it is that 81 minutes passed before anyone noticed, which is
58 % of that packet's GPU bill and about $2.15 of real money,
and that compute occupied only 26.2 % of the billed window.** Nothing in this
project ever watched a long unattended job: no heartbeat, no timeout, no alert. That is a
one-afternoon fix that was never made, and it is recorded here rather than quietly absorbed
because the cost is the most legible number in the ledger.

**A pre-registration rule that can be unsatisfiable, and a packet that had to choose which error
to prefer.** By §5.4's packet the standing rule required a null simulation *and* a calibrated
alternative *and* a stated minimum detectable effect. **No rung of that packet's ladder satisfied
both gates**: the rung as ordered held power at 0.950 but false-fired
0.095 of the time in a pure-length world — an error in the finding's own
favour — while the rung that controls the confound to 0.030 could only reach
0.710. **The packet froze the conservative rung, whose errors run against the result it
was testing, published the other alongside, and pre-declared in writing that a non-firing primary
could never be read as the result failing at that power.** Both rungs then fired, which made the
asymmetry moot — but the rule was written when that could not have been known. **A design that
cannot resolve its question is fixed or not run; a design that can only half-resolve it must
declare in advance which half.**

**A test suite that writes where the results live.** One packet's smoke mode wrote its synthetic
outputs to the same five paths in `analysis/out/` that a real run uses, and a post-run re-smoke
on the laptop **silently overwrote the pulled copies of all five**. They were re-pulled from a pod
that happened to still be alive, and every number in that packet comes from the re-pulled files.
**Had the pod been terminated first — as every other packet in this project terminates it
immediately — the results would have been destroyed by their own test suite.** No number here is
affected and the near-miss is recorded rather than patched, because patching a smoke path
mid-packet is exactly the kind of in-flight instrument change §9's last entry forbids. **The
general rule: the only copy of a result must never live where a test can write.**

**Pre-registered knobs frozen outside the range their own design could resolve — four times.**
This is the methodological finding of the project, and it recurs in a different currency each
time.

| what was frozen | the knob | how it failed |
|---|---|---|
| the probe layer | ℓ\* = argmax of a curve never required to beat its own null | the argmax of a noise curve; the informative band is layers 21–36 |
| the injection dose | α in units of ‖Δμ‖, without asking what fraction of the residual stream that is | the whole grid may sit where generic distortion dominates: 22.8 % and 45.6 % of the residual norm |
| the distortion threshold | D̄ > 0.06 | below the statistic's own floor: E[D̄] = 0.0782 under a design doing nothing |
| the transplant's declared power | λ, the fraction of pairs no downstream edit can move | measured on the wrong object — 0.2632 on the traces the pairs came from, 0.85 on the continuations the statistic is computed from; power at the worst cell 0.997 → 0.000 |

**The fix for the first three is cheap and is named**: simulate the pre-registered statistic under
its own null *before* freezing the threshold, and set the line above the resulting floor. For the
distortion gate that is a few minutes of laptop arithmetic on a closed-form binomial convolution.
**No pre-registration before Wave 2 ever did this**; every pre-registration from Wave 2 on did,
and it changed the decision rule before the data in five consecutive packets.

**The fourth row is the one that matters most, because the rule was in force when it happened.**
That simulation was correct at every step — it measured a real quantity on committed files before
any token existed — and it measured it on the *original* traces when the statistic would be
computed on *regenerated* continuations, where the same quantity is 0.85 rather
than 0.2632. **A simulation is exactly as good as the object it is calibrated on**,
and for any design whose outcome is regenerated rather than observed, that object does not exist
until the experiment has partly run. **The named fix is a pilot**: a handful of pairs, taken all
the way through the pipeline, would have measured the true locked fraction for about
$0.05. **Freezing a rule before the data is necessary and is not sufficient;
simulating the statistic is necessary and is not sufficient either.**

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

## 10. Open questions, and the deferred programme

The activation-level causal question is open, and after Wave 2 the shape of the experiment that
would close it is much clearer, which is the most useful thing a null result produces.

**A distributed or nonlinear transplant is the first move, and it is first because §7.5 measured
why.** Every intervention in this project — six doses of additive steering, a low-dose ladder, and
a belief transplant — operated through **one direction in one dimension**, and the two belief
classes are separated along that coordinate by only 0.1720 of their own within-class
spread. **A channel that narrow would produce exactly this pattern of nulls whether or not the
belief is causal**, so the next experiment must not use it: the belief subspace should be
estimated with a method that can hold more than one dimension, and the transplant should move the
whole subspace rather than a single projection. That the frozen probe's *trained coefficients*
were never persisted — only the direction — is a reproducibility lesson of its own and the reason
this project could not fall back on the multivariate object it had already fitted.

**Whatever the operation, it must be piloted end to end before it is pre-registered.** §9's fourth
knob row is the cheapest lesson in this document: the parameter that governs a regenerative
design's power cannot be measured on the traces the design starts from, only on the continuations
it produces, so a handful of pairs taken all the way through the pipeline — about
$0.05 of compute — has to happen before the freeze, not after it.

**A properly powered low-dose ladder remains worth running**: the doses that matter are below the
ones run here, and the statistic that would read them is a landing rate at n far above
50 per arm.

**Small-model belief-tracking deserves study in its own right**, and Wave 2 raised rather than
lowered that claim. The comprehension asymmetry found here — one mirror of the same bet understood
most of the time, the other barely better than chance — is large, cheap to measure, moves
predictably in both directions under one rewritten sentence, and is what makes the aggregate
landing gap in this model class a mixture rather than an effect.

**LLM judges need validity evidence on the exact surface form they will be run on.** §9's judge
entry is a general result, not a local annoyance: the judge and the model failed the same
reasoning step, so agreement measured on one wording (0.9032–0.9605)
did not transfer to another (0.2895/0.5000). Human calibration of
this project's judge was commissioned as a blinded 70-row packet and had not returned
by submission, so the bound it would give is **[not tested]** here and is the single cheapest open
item on this list.

**And the covert–overt scale question is the one this project can only gesture at**: a model of
this size announces the bet in nearly every trace while the larger panel almost never does, and
nothing here can say whether that is scale, family, tuning, or prompt surface, because the
comparison spans two studies with two model families and no sweep.

---

## 11. Methods register

**Models and stack.** `Qwen/Qwen2.5-14B-Instruct` at snapshot `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8`, bf16, on one
A100-SXM4-80GB. The frozen dataset was generated with vLLM 0.28.0; activation replay and
every steered run used `transformers` 4.57.6 on torch 2.8.0+cu128, because the
intervention needs a hook that persists across decode steps and vLLM cannot carry one. **Wave 2's
last packet ran on the container's own torch through the same `transformers` path, because the
frozen vLLM build could not run on the driver the rented machine happened to carry** (§9); its
marginal generation rates are therefore not comparable to the frozen dataset's and no comparison
between them is made anywhere in this document. The
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

**Spend, final: $19.30 GPU + $30.87 API = $50.17** of a
$60 cap; balance $9.83. The API line overtook the GPU line at the
intervention packet and stayed there. **The $45 stop-and-surface threshold was
reached, surfaced at the end of the packet before it would have been crossed, and crossed only
with the owner's explicit written approval** — recorded in the ledger as a ruling that also
imposed a $10 ceiling on the packet that crossed it, which came in under at
$3.70 + $4.37.

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
| skepticism pass and build | $0.00 | $0.00 |
| comprehension intervention, upward | $0.38 | $4.59 |
| belief-formation timing | $1.32 | $0.00003 |
| the length attack | $0.00 | $0.00 |
| comprehension intervention, downward | $0.48 | $5.85 |
| the belief transplant | $3.70 | $4.37 |
| this document | $0.00 | $0.00 |

**Time.** Runner wall time per packet, in order: 7 min, 2 h 05 m, 2 h 05 m,
5 h 10 m, 1 h 20 m, 1 h 05 m, 51 m, 1 h 00 m, 45 m,
1 h 35 m, 1 h 05 m, 2 h 05 m, 5 h 05 m, 1 h 15 m, 3 h 05 m, and
1 h 15 m for this one. Billed GPU wall time: 1 h 17 m, 1 h 15 m, 4 h 52 m,
13 m 37 s, 33 m 02 s, 36 m 27 s, 31 m 29 s, 19 m 25 s, 0.273 h,
0.950 h, 0.000 h, 0.342 h, 2.324 h. Compute occupied
72.7 % of the intervention packet's billed pod time, 60.1 % of the follow-up's
and 26.2 % of the transplant's; the generation runs were 1373.1 s and
656.5 s, and all 700 activation-replay forward passes took 94.8 s.
**The single largest avoidable line in the whole project is 81 idle GPU minutes
in the last packet — 58 % of that packet's bill, about $2.15**
— and it is itemised in §9 rather than buried here.

**The owner clock was never supplied: 0 figures across
16 work orders.**
It was asked for repeatedly, and from Wave 2 onward a standing ruling required the courier to
supply it with every order; **9 requests produced 0
figures.** The 16-hour owner budget in the project's orientation document is
therefore **unauditable**, and all time accounting here rests on runner wall time and billed pod
time alone — both independently checkable against the provider's pod records. The empty fields
were recorded as empty in every packet rather than estimated, which is why this paragraph can be
this specific.

**Pre-registration precedence, from the commit graph rather than from memory.** The intervention's
pre-registration is commit `de12985` at 2026-08-30 05:45:19 UTC, and the first steered token
followed 13 m 11 s later. The follow-up's is `32667d7` at 06:44:14 UTC,
11 m 51 s before its first steered token. Neither run directory existed when its
pre-registration was written, and the same check was run and recorded for every Wave 2 packet:
each pre-registration's commit timestamp, the pod's creation time and the first token's timestamp
are all in the ledger, taken from `git log` and the provider's records rather than from
recollection. **From Wave 2 onward every pre-registration also carried its own null simulations,
pasted into the document that froze the rule, and in five consecutive packets those simulations
changed the decision rule before any data existed.** §9 records the one case where doing that was
still not enough.

**The workflow, disclosed plainly.** This project was executed by an LLM-agent structure with
three roles and no overlap. A **researcher** designed the experiments, audited each packet's
report, and promoted provisional results to established ones; it executed no code. A **runner** —
a Claude Code CLI agent on the owner's laptop, driving rented GPU pods over SSH — executed one
self-contained work order at a time and reported back; each order was self-contained because the
runner's context did not survive between packets, which is why the orientation document and the
ledger's tail had to be sufficient to restart the project from cold, and they were,
16 times.
A human **owner** relayed messages between the two and approved every dollar of spend; the one
budget decision that mattered — crossing the $45 line — was surfaced by the
runner, ruled on by the owner in writing, and bounded by a ceiling in the same ruling.

**This paragraph is checkable rather than decorative.** The 16 work orders are on
disk as written, one file each. Every number in this document comes from an **append-only** ledger
written by the runner and audited by the researcher, in which entries are never edited: a wrong
entry is corrected by a later entry that names it. Corrections were filed that way throughout,
including three while assembling this document's first version and, in Wave 2, a ruling-level
correction that amended the project's final verdicts after the last experiment reported. **The
provisional-to-established promotion path is visible in the ledger too** — every result in this
document was first written as provisional by the runner, then promoted by a researcher entry that
names what it recounted, and the write-up is built only from the promoted set.

**Regenerability.** Every number here is substituted at build time from a file in
`analysis/out/`, and a build-time check refuses to emit a digit that is neither substituted nor
matched by a structural whitelist. The document rebuilds byte-identically with
`python3 writeup/build.py`. The commands behind the generated files are
`python3 src/w10_skeptic.py`, `python3 src/w10_derived.py` and
`python3 src/w10_ledger_facts.py`, each reading only committed rollout files, committed CSVs, and
the ledger itself. **Wave 2's numbers enter the same way**: its analysis scripts write the CSVs
and JSONs in `analysis/out/` that the manifest names, and the figures that exist only as ledger
prose — spend, wall time, the achieved-power admission, the judge-calibration rates — are
extracted from `RESULTS.md` by a named regex per fact, so a fact whose wording moves breaks the
build loudly instead of silently going stale.
