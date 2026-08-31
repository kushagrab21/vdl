"""Extract the write-up's non-experimental facts FROM the ledger, so they are machine-sourced.

    python3 src/w10_ledger_facts.py          # -> analysis/out/w10_ledger_facts.json
    python3 src/w10_ledger_facts.py --print  # same, and print every (fact, entry, value)

Experimental numbers live in `analysis/out/*.csv` and are read from there by `writeup/build.py`.
Spend, time, commit hashes, stack versions and infrastructure facts live ONLY in RESULTS.md
prose, so this module makes RESULTS.md itself the machine source: every fact below is a
(ledger entry, regex) pair, the entry's section is located by its `## <ID> ·` heading, and the
regex CAPTURES the value out of the ledger text. Nothing is typed in.

A fact whose regex no longer matches is a hard error, not a silent default -- so if a later
ledger entry supersedes an earlier one and the wording moves, the build breaks loudly.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "RESULTS.md")
OUT = os.path.join(ROOT, "analysis", "out", "w10_ledger_facts.json")

# (fact name, ledger entry, occurrence index, regex with exactly one capture group)
FACTS = [
    # ---- project frame (ledger preamble, before the first entry) ----------------------
    ("date_opened", "HEADER", 0, r"\*\*Date opened:\*\* (\d{4}-\d\d-\d\d)"),
    ("submission_date", "HEADER", 0, r"submitted \*\*Friday (\d{4}-\d\d-\d\d)\*\*"),
    ("owner_clock_hours", "HEADER", 0, r"\*\*(\d+) h owner clock\*\*"),

    # ---- thresholds and conventions frozen in pre-registrations -----------------------
    ("ci_level_pct", "PR-001", 0, r"\*\*(\d+) % bootstrap CI excludes zero\*\*"),
    ("extractor_disagreement_threshold_pct", "PR-001", 0,
     r"Disagreement beyond \*\*(\d+) % of answers in any cell\*\*"),
    ("truncation_flag_threshold_pct", "PR-001", 0, r"If \*\*>(\d+) %\*\* of a model's rollouts truncate"),
    ("coherence_line_pct", "PR-005", 0, r"any v_p̂ arm's coherence is < (\d+) %"),
    ("g0_intermediate_min", "PR-002", 0, r"under the frozen PR-001 item-9 rule must be \*\*≥ (\d+)\*\*"),
    ("dbar_line", "PR-006", 0, r"D̄ ≤ (0\.\d+) AND"),

    # ---- prior work, as reported by the researcher ------------------------------------
    ("covert_disclosure_pct_122b", "R-008", 1, r"disclosure there ~([\d.]+)%"),
    ("w2_sample_bet_mentions", "R-008", 1, r"near-universal, (\d+) mentions"),
    ("w2_sample_traces", "R-008", 1, r"mentions across the\s*\n?(\d+) sampled traces"),
    ("panel_size_b", "R-008", 1, r"covert leakage of the (\d+)B panel"),

    # ---- freeze, stack, apparatus identity -------------------------------------------
    ("upstream_freeze_commit", "F-002", 0, r"HEAD = `([0-9a-f]{40})`"),
    ("pr001_freeze_commit", "F-014", 0, r"frozen at commit\s*\n\*\*`([0-9a-f]{40})`\*\*"),
    ("direction_judge_prompt_sha256", "P-005", 0, r"sha256 ([0-9a-f]{64})"),
    ("vphat_B_sha256", "PR-005", 0, r"sha256 `([0-9a-f]{64})`"),
    ("model_snapshot", "F-016", 0, r"snapshot \*\*`([0-9a-f]{40})`\*\*"),
    ("model_id", "PR-003", 0, r"\*\*1 · Model and surface forms\.\*\* `(Qwen/[\w.\-]+)`"),
    ("judge_model", "PR-001", 0, r"Judge model pinned: `([\w\-]+)`"),
    ("gpu_type", "F-016", 0, r"GPU \| \*\*NVIDIA ([\w\-]+)\*\*"),
    ("torch_version", "F-016", 0, r"torch \*\*([\w.+]+)\*\* \(image\)"),
    ("transformers_version", "F-016", 0, r"transformers \*\*([\d.]+)\*\*"),
    ("vllm_version", "D-018", 0, r"`vllm_version` \| ([\d.]+) \|"),
    ("dmu_norm_L27", "F-016", 0, r"‖Δμ‖ = ‖v_p̂\^B\(27\)‖ \| \*\*([\d.]+)\*\*"),
    ("resid_norm_L27", "F-016", 0, r"mean ‖h‖ at L27 = ([\d.]+)"),
    ("d_model", "P-006", 0, r"d_model (\d+)"),
    ("n_layers", "P-006", 0, r"\*\*(\d+) decoder layers"),

    # ---- pre-registration precedence -------------------------------------------------
    ("pr005_commit", "V-012", 0, r"`([0-9a-f]{7})` \(PR-005\) is committed at"),
    ("pr005_commit_time", "V-012", 0,
     r"\(PR-005\) is committed at \*\*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC)\*\*"),
    ("pr005_lead_to_first_token", "V-012", 0,
     r"first steered token of the 23-arm run was generated at\s*\n\*\*≈[\d:]+\*\* \(\+([\dm s]+)\)"),
    ("pr006_commit", "V-014", 0, r"`([0-9a-f]{7})` \(PR-006\) is committed"),
    ("pr006_commit_time", "V-014", 0, r"\(PR-006\) is committed \*\*(\d\d:\d\d:\d\d UTC)\*\*"),
    ("pr006_lead_to_first_token", "P-009", 0, r"\*\*(\d+ m \d+ s)\*\*\s*\nbefore the first steered token"),

    # ---- spend, per packet and cumulative --------------------------------------------
    ("spend_gpu_w0", "S-001", 0, r"Cumulative GPU spend: \$([\d.]+) of"),
    ("spend_gpu_w0b", "S-003", 0, r"Spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_gpu_w1", "S-004", 0, r"GPU spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_gpu_w2", "S-005", 0, r"GPU spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_gpu_w3", "S-006", 0, r"\*\*GPU spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_gpu_w4", "S-007", 0, r"\*\*GPU spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_gpu_w5", "S-008", 0, r"\*\*GPU spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_gpu_w7", "S-009", 0, r"\*\*GPU spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_gpu_w7b", "S-010", 0, r"\*\*GPU spend this packet: \$([\d.]+)\.\*\*"),
    ("spend_api_w1", "S-004", 0, r"tokens ≈ \$([\d.]+)\*\*"),
    ("spend_api_w2", "S-005", 0, r"\*\*API this packet ≈ \$([\d.]+)\.\*\*"),
    ("spend_api_w3", "S-006", 0, r"\*\*API this packet: \$([\d.]+)\."),
    ("spend_api_w4", "S-007", 0, r"\*\*API this packet: \$([\d.]+)\*\*"),
    ("spend_api_w5", "S-008", 0, r"\*\*API this packet: \$([\d.]+)\*\*"),
    ("spend_api_w7", "S-009", 0, r"\*\*API this packet: \$([\d.]+)\*\*"),
    ("spend_api_w7b", "S-010", 0, r"\*\*API this packet: \$([\d.]+)\*\*"),
    # cumulative spend is read from the LAST packet that spent (S-016), not from S-010
    ("spend_gpu_cumulative", "S-016", 0, r"\*\*Cumulative: \$([\d.]+) GPU"),
    ("spend_api_cumulative", "S-016", 0, r"\*\*Cumulative: \$[\d.]+ GPU \+ \$([\d.]+) API"),
    ("spend_total", "S-016", 0, r"API = \$([\d.]+) of the \$\d+ cap; balance"),
    ("spend_cap", "S-016", 0, r"of the \$(\d+) cap; balance"),
    ("spend_balance", "S-016", 0, r"cap; balance \$([\d.]+)\.\*\*"),
    ("spend_surfacing_threshold", "S-010", 0, r"The \*\*\$(\d+)\*\* surfacing threshold"),

    # ---- runner wall time, per packet -------------------------------------------------
    ("time_runner_w0", "T-002", 0, r"15:45 → 15:52 \+08, ≈(\d+) minutes"),
    ("time_runner_w0b", "T-004", 0, r"Runner wall time, W0b total: \*\*≈(\d h \d\d m)\*\*"),
    ("time_runner_w1", "T-005", 0, r"Runner wall time, W1: \*\*≈(\d h \d\d m)\*\*"),
    ("time_runner_w2", "T-006", 0, r"Runner wall time, W2: \*\*≈(\d h \d\d m)\*\*"),
    ("time_runner_w3", "T-007", 0, r"Runner wall time, W3: \*\*≈(\d h \d\d m)\*\*"),
    ("time_runner_w4", "T-008", 0, r"Runner wall time, W4: \*\*≈(\d h \d\d m)\*\*"),
    ("time_runner_w5", "T-010", 0, r"runner wall time for W5 is \*\*≈(\d\d m)\*\*"),
    ("time_runner_w7", "T-011", 0, r"Runner wall time, W7: \*\*≈(\d h \d\d m)\*\*"),
    ("time_runner_w7b", "T-012", 0, r"Runner wall time, W7b: \*\*≈ (\d\d m)\*\*"),

    # ---- billed GPU wall time, the packets that used a pod -----------------------------
    ("gpu_wall_w0b", "T-004", 0, r"GPU wall time \(pod running, all three pods\): \*\*≈(\d h \d\d m)\*\*"),
    ("gpu_wall_w1", "T-005", 0, r"GPU wall time \(pod running\): \*\*(\d h \d\d m)\*\*"),
    ("gpu_wall_w2", "T-006", 0, r"GPU wall time \(pods running\): \*\*(\d h \d\d m)\*\*"),
    ("gpu_wall_w3", "T-007", 0, r"GPU wall time \(pod running\): \*\*(\d\d m \d\d s)\*\*"),
    ("gpu_wall_w4", "T-008", 0, r"GPU wall time \(pod running, billed\): \*\*(\d\d m \d\d s)\*\*"),
    ("gpu_wall_w5", "T-009", 0, r"GPU wall time \(pod running, billed\): \*\*(\d\d m \d\d s)\*\*"),
    ("gpu_wall_w7", "T-011", 0, r"GPU wall time \(pod running, billed\): \*\*(\d\d m \d\d s)\*\*"),
    ("gpu_wall_w7b", "T-012", 0, r"GPU wall time \(pod running, billed\): \*\*(\d\d m \d\d s)\*\*"),
    ("compute_fraction_w7", "T-011", 0, r"\*\*W7 is ([\d.]+) % compute\*\*"),
    ("compute_fraction_w7b", "T-012", 0, r"\*\*W7b is ([\d.]+) % compute\*\*"),


    # ---- W5 analysis cell and timing split (prose-only in P-007) ----------------------
    ("w5_points_A", "P-007", 0, r"\*\*Form A: (\d+) points over"),
    ("w5_traces_A", "P-007", 0, r"Form A: \d+ points over (\d+)"),
    ("w5_pos_A", "P-007", 0, r"Form A: \d+ points over \d+\s*\ntraces \(p̂=\+1 (\d+)"),
    ("w5_neg_A", "P-007", 0, r"Form A: \d+ points over \d+\s*\ntraces \(p̂=\+1 \d+, p̂=−1 (\d+)\)"),
    ("w5_points_B", "P-007", 0, r"Form B: (\d+) points over"),
    ("w5_traces_B", "P-007", 0, r"Form B: \d+ points over (\d+) traces"),
    ("w5_pos_B", "P-007", 0, r"Form B: \d+ points over \d+ traces \(p̂=\+1 (\d+)"),
    ("w5_neg_B", "P-007", 0, r"Form B: \d+ points over \d+ traces \(p̂=\+1 \d+, p̂=−1 (\d+)\)"),
    ("w5_before_points_A", "P-007", 0, r"(\d+) of \d+ form-A est points"),
    ("w5_total_points_A", "P-007", 0, r"\d+ of (\d+) form-A est points"),
    ("w5_before_points_B", "P-007", 0, r"and (\d+) of \d+ form-B est"),
    ("w5_total_points_B", "P-007", 0, r"and \d+ of (\d+) form-B est"),
    ("w5_pre_verbalization_pct", "P-007", 0, r"~(\d+) % of the time before it says"),
    ("probe_split", "PR-004", 0, r"Split \*\*by trace\*\*, ([\d/]+),"),
    ("intermediate_floor", "PR-001", 0, r"reasoning text\*\* with value \*\*≥ (\d+)\*\*"),

    # ---- acceptance checks whose counts live only in audit prose ----------------------
    ("decode_check_k", "V-008", 0, r"\*\*(\d+) / \d+ exact"),
    ("decode_check_n", "V-008", 0, r"\*\*\d+ / (\d+) exact"),
    ("integrity_decode", "V-010", 0, r"\*\*(\d+ / \d+) sampled `est` points decode exactly"),
    ("smoke_s4_tolerance", "F-015", 0, r"max=([\d.]+e-\d+) over \d+ steps"),

    # ---- estimator-miss percentages ---------------------------------------------------
    ("api_projection_miss_w7_pct", "D-027", 0, r"\*\*\+([\d.]+) %\*\*, and \*\*above"),
    ("api_projection_miss_w7b_pct", "D-033", 0, r"\*\*\$1\.9334\*\* \| \*\*\+([\d.]+) %\*\*"),
    ("spend_api_w0b", "S-003", 0, r"Non-GPU spend this packet: \*\*\$([\d.]+)\*\*"),
    ("spend_gpu_w10", "S-011", 0, r"\*\*GPU spend this packet: \$([\d.]+)\."),
    ("spend_api_w10", "S-011", 0, r"API this packet: \$([\d.]+)\.\*\*"),
    ("time_runner_w10", "T-013", 0, r"Runner wall time, W10: \*\*≈ ([\dh m]+)\*\*"),

    # ---- generation wall clock ---------------------------------------------------------
    ("w7_generation_secs", "P-008", 0, r"pod `heenrekmx8f4da`, ([\d.]+) s"),
    ("w7b_generation_secs", "P-009", 0, r"pod `u3g0qm180kvqnd`, ([\d.]+) s"),
    ("w4_forward_pass_secs", "P-006", 0, r"all 700 forward passes in ([\d.]+) s"),
    ("w5_analysis_secs", "P-007", 0, r"pod `io6c1fhnarzoj9`, (\d+) s"),

    # ================= WAVE 2 (W11-W15) and the assembly packet (W16) =================

    # ---- spend, per Wave-2 packet -----------------------------------------------------
    ("spend_gpu_w11", "S-012", 0, r"\*\*GPU spend this packet: \$([\d.]+)\."),
    ("spend_api_w11", "S-012", 0, r"\*\*API this packet: \$([\d.]+)\*\*"),
    ("spend_gpu_w12", "S-013", 0, r"\*\*GPU this packet: \$([\d.]+)\."),
    ("spend_api_w12", "S-013", 0, r"\*\*API this packet: \$([\d.]+)\*\*"),
    ("spend_gpu_w13", "S-014", 0, r"\| GPU \| \*\*\$([\d.]+)\*\*"),
    ("spend_api_w13", "S-014", 0, r"\| API \| \*\*\$([\d.]+)\*\*"),
    ("spend_gpu_w14", "S-015", 0, r"\*\*GPU \$([\d.]+) \+ API \$[\d.]+ = "),
    ("spend_api_w14", "S-015", 0, r"\*\*GPU \$[\d.]+ \+ API \$([\d.]+) = "),
    ("spend_gpu_w15", "S-016", 0, r"\*\*GPU \$([\d.]+) \+ API \$[\d.]+ = "),
    ("spend_api_w15", "S-016", 0, r"\*\*GPU \$[\d.]+ \+ API \$([\d.]+) = "),
    ("spend_gpu_w16", "S-017", 0, r"\| GPU \| \*\*\$([\d.]+)\*\*"),
    ("spend_api_w16", "S-017", 0, r"\| API \| \*\*\$([\d.]+)\*\*"),
    ("spend_ceiling_w15", "S-016", 0, r"against R-017's \$(\d+) hard ceiling"),

    # ---- runner wall time and billed GPU wall, per Wave-2 packet -----------------------
    ("time_runner_w11", "T-014", 0, r"Runner wall time, W11: \*\*≈ (\d h \d\d m)\*\*"),
    ("time_runner_w12", "T-015", 0, r"Runner wall time, W12: \*\*≈ (\d h \d\d m)\*\*"),
    ("time_runner_w13", "T-016", 0, r"Runner wall time, W13: \*\*≈ (\d h \d\d m)\*\*"),
    ("time_runner_w14", "T-017", 0, r"Runner wall time, W14: \*\*≈ (\d h \d\d m)\*\*"),
    ("time_runner_w15", "T-018", 0, r"Runner wall time, W15: \*\*≈ (\d h \d\d m)\*\*"),
    ("time_runner_w16", "T-019", 0, r"Runner wall time, W16: \*\*≈ (\d h \d\d m)\*\*"),
    ("gpu_wall_w11", "T-014", 0, r"GPU wall time: \*\*([\d.]+ h)\*\*"),
    ("gpu_wall_w12", "T-015", 0, r"GPU wall \*\*([\d.]+ h)\*\*"),
    ("gpu_wall_w13", "T-016", 0, r"GPU wall \*\*([\d.]+ h)\*\*"),
    ("gpu_wall_w14", "T-017", 0, r"GPU wall \*\*([\d.]+ h)\*\*"),
    ("gpu_wall_w15", "T-018", 0, r"GPU wall \*\*([\d.]+ h)\*\*"),
    ("owner_minutes_supplied", "T-019", 0, r"owner-clock figures\s*\n?supplied: (\d+)\."),
    ("n_packets", "T-019", 0, r"Across all \*\*(\d+)\*\*\s*\n?work orders"),
    ("owner_requests", "T-019", 0, r"\*\*asked for it (\d+) times\*\*"),

    # ---- W12: the length confound (D-042), prose-only in P-011 s3 ----------------------
    ("w12_len_delta_tokens", "P-011", 0, r"p̂=−1 traces are \*\*(\d+) tokens longer\*\*"),
    ("w12_len_ncorr_tokens", "P-011", 0, r"tokens longer\*\* on\s*\n?average \((\d+\.\d)"),
    ("w12_len_corr_tokens", "P-011", 0, r"average \(\d+\.\d vs (\d+\.\d)"),
    ("w12_lenonly_acc", "P-011", 0, r"— reads \*\*(0\.\d+)\*\* on the same traces"),

    # ---- W14 / D-051: the judge fails where the model fails ----------------------------
    ("d051_judge_wrong_k", "D-051", 0, r"\*\*(\d+) of the \d+ `below_good` traces"),
    ("d051_judge_wrong_n", "D-051", 0, r"\*\*\d+ of the (\d+) `below_good` traces"),
    ("d051_agree_w3_below", "D-051", 0, r"\| \*\*W3 natural\*\* \| below_good \| \d+ \| \*\*(0\.\d+)\*\*"),
    ("d051_agree_w3_above", "D-051", 0, r"\| \*\*W3 natural\*\* \| above_good \| \d+ \| \*\*(0\.\d+)\*\*"),
    ("d051_agree_w14_below", "D-051", 0, r"\| \*\*W14 degraded\*\* \| below_good \| \d+ \| \*\*(0\.\d+)\*\*"),
    ("d051_agree_w14_above", "D-051", 0, r"\| \*\*W14 degraded\*\* \| above_good \| \d+ \| \*\*(0\.\d+)\*\*"),
    ("d051_regex_gap_w3", "D-051", 0, r"reproduces the frozen `corr` conditional gap to 0\.0064\s*\n?\(\+(0\.\d+) vs"),
    ("d051_judge_gap_w3", "D-051", 0, r"\(\+0\.\d+ vs \+(0\.\d+)\)"),
    ("d051_judge_gap_w14", "D-051", 0, r"\*\*collapsed and crossed to −(0\.\d+)\*\*"),
    ("d051_regex_gap_w14", "D-051", 0, r"independent basis says it is \*\*\+(0\.\d+)\*\*"),
    ("d051_resolved_k", "D-051", 0, r"resolves only \*\*(\d+) of \d+\*\* degraded traces"),
    ("d051_resolved_n", "D-051", 0, r"resolves only \*\*\d+ of (\d+)\*\* degraded traces"),

    # ---- W15 / D-053: the extractor the screen depends on -------------------------------
    ("d053_corrected_agree", "D-053", 0, r"`final_corrected`[^\n]*?(0\.9467)"),
    ("d053_raw_agree", "D-053", 0, r"`final_estimate`[^\n]*?\*\*(0\.6316)\*\*"),

    # ---- W15 / D-054: the idle GPU ------------------------------------------------------
    ("d054_idle_minutes", "S-016", 0, r"\*\*(\d+) minutes —"),
    ("d054_idle_pct", "S-016", 0, r"\*\*\d+ minutes —\s*\n?(\d+) % of the bill"),
    ("d054_idle_cost", "S-016", 0, r"% of the bill, ≈ \$([\d.]+)"),
    ("d054_compute_pct_w15", "S-016", 0, r"\*\*Compute was ([\d.]+) % of billed time\*\*"),

    # ---- W15 / D-055: the nuisance parameter measured on the wrong object ---------------
    ("d055_lam_declared", "D-055", 0, r"`20/76 = (0\.\d+)`"),
    ("d055_lam_measured", "D-055", 0, r"is\s*\n?\*\*34/40 = (0\.\d+)\*\*"),
    ("d055_locked_k", "D-055", 0, r"\*\*(\d+)/40 = 0\.85\*\*"),
    ("d055_power_declared_worst", "D-055", 0, r"δ_true \+0\.4456 \| \*\*(0\.\d+)\*\* \| \*\*0\.000\*\*"),
    ("d055_power_measured_worst", "D-055", 0, r"δ_true \+0\.4456 \| \*\*0\.\d+\*\* \| \*\*(0\.\d+)\*\*"),
    ("d055_pilot_cost", "D-055", 0, r"A pilot of 5 pairs would have measured λ = 0\.85 for \*\*\$([\d.]+)\*\*"),
    ("p014_power_achieved_lo", "P-014", 0, r"ordered alternative is (0\.\d\d)–0\.87"),
    ("p014_power_achieved_hi", "P-014", 0, r"ordered alternative is 0\.\d\d–(0\.\d\d)"),
    ("p014_power_declared_lo", "P-014", 0, r"not the (0\.\d\d)–1\.00 pre-registered"),
    ("p014_power_declared_hi", "P-014", 0, r"not the 0\.\d\d–(1\.00) pre-registered"),
    ("jc4_power_lo", "P-014", 0, r"\*\*(0\.\d+) – 0\.\d+\*\* \(false-fire"),
    ("jc4_power_hi", "P-014", 0, r"\*\*0\.\d+ – (0\.\d+)\*\* \(false-fire"),
    ("jc4_falsefire", "P-014", 0, r"\(false-fire (0\.\d+);"),
    ("jc4_mde", "P-014", 0, r"80 % power at δ ≈ (0\.\d+)\)"),
    ("w15_cut_median", "P-014", 0, r"\| cut point \| median \*\*(\d+)\*\*"),
    ("w15_n_labelled", "P-014", 0, r"regex-labelled \(`p̂ ∈ ±1`\) \| \*\*(\d+)\*\*"),
    ("w15_judge_regex_agree", "P-014", 0, r"agreement \| \*\*(0\.\d+)\*\* \(\d+/\d+\)"),
    ("w15_swap_self_delta", "P-014", 0, r"differ from each other\s*\n?by ~(0\.\d+) on average"),
    ("w15_contrast_ratio", "P-014", 0, r"is ([\d.]+)× smaller than the noise"),
    ("w15_rand_ratio", "P-014", 0, r"— \*\*4\.7× SWAP's\*\*|(4\.7)× SWAP's"),

    # ---- W15 / D-056: the belief coordinate's ceiling -----------------------------------
    ("d056_within_sd", "D-056", 0, r"\*\*within-class sd\*\* \| \*\*([\d.]+)\*\*"),
    ("d056_sep_over_sd", "D-056", 0, r"\*\*separation / sd\*\* \| \*\*([\d.]+)\*\*"),
    ("d056_sep_aggregate", "D-056", 0, r"separation \(aggregate / mean per-grid-point\) \| \*\*([\d.]+)"),

    ("w14_prompt_tokens", "F-019", 0, r"form B degraded \*\*(\d+)\*\* — \*\*exactly W3 form B's"),
    ("w3_prompt_tokens", "F-017", 0, r"form A \*\*\d+\*\* \(W3: (\d+)\)"),
    ("w11_prompt_tokens", "F-017", 0, r"form A \*\*\d+\*\* \(W3: \d+\), form B \*\*(\d+)\*\*"),
    ("w15_prompt_tokens", "F-020", 0, r"\| prompt tokens \| \*\*(\d+)\*\* — exactly W3's and W14's"),
    # ---- W16 / D-058: the hand-label fallback -------------------------------------------
    ("handlabel_rows", "D-058", 0, r"\*\*(\d+) rows, 0 of \d+ filled"),
    ("handlabel_filled", "D-058", 0, r"rows, (0) of \d+ filled in `direction`"),
]


def sections(text):
    """Map entry id -> [section text, ...] in document order (the ledger reuses some ids)."""
    out = {}
    parts = re.split(r"^## ", text, flags=re.M)
    out["HEADER"] = [parts[0]]
    for p in parts[1:]:
        eid = p.split(" ", 1)[0].strip()
        out.setdefault(eid, []).append("## " + p)
    return out


def main():
    text = open(LEDGER, encoding="utf-8").read()
    secs = sections(text)
    facts, failures = {}, []
    for name, entry, occ, pattern in FACTS:
        body = secs.get(entry, [None] * (occ + 1))[occ] if entry in secs else None
        if body is None:
            failures.append((name, entry, "entry not found"))
            continue
        m = re.search(pattern, body)
        if not m:
            failures.append((name, entry, "regex did not match"))
            continue
        facts[name] = {"value": m.group(1), "entry": entry}

    if failures:
        for n, e, why in failures:
            print("FAIL  %-32s %-8s %s" % (n, e, why), file=sys.stderr)
        print("%d of %d facts could not be extracted from RESULTS.md"
              % (len(failures), len(FACTS)), file=sys.stderr)
        return 1

    with open(OUT, "w") as fh:
        json.dump({"n_facts": len(facts), "source": "RESULTS.md", "facts": facts},
                  fh, indent=1, sort_keys=True)
        fh.write("\n")
    if "--print" in sys.argv:
        for k in sorted(facts):
            print("%-32s %-8s %s" % (k, facts[k]["entry"], facts[k]["value"]))
    print("w10_ledger_facts: %d/%d facts extracted from RESULTS.md -> %s"
          % (len(facts), len(FACTS), os.path.relpath(OUT, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
