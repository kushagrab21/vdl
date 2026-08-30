# MANIFEST.md — inventory of `runs/`

`runs/` holds raw generation data and is **gitignored**. Every directory created under it must
be listed here with: what produced it, the exact command, and its size. This file is committed;
the data is not.

| run dir | packet | produced by | size | notes |
|---|---|---|---|---|
| `smoke/` | W0b | `python src/smoke_vllm.py` and `python src/smoke_hooks.py` on pod `gwhn0ex0eeyntn`, rsync'd back | 60 KB | 2 files: `smoke_vllm_qwen3-8b.json` (F-012), `smoke_hooks_qwen3-8b.json` (F-013). **Committed by exception** — they are 60 KB, they are this packet's only experimental artefact, and F-012/F-013 cite them as evidence. Bulk rollout data from W2 on stays gitignored. |
| `w1_neutral/` | W1 | `python src/gen_neutral.py --model <hf-id>` on pod `gwhn0ex0eeyntn`, rsync'd back | 3.2 MB | 4 dirs x `neutral.json`, 50 baseline rollouts each. **Committed by exception** (3.2 MB, and P-001/P-002/D-011 are computed from them; `src/tau.py` must be re-runnable by the auditor). |
| `w2_screen/` | W2 | `python src/gen_mirrored.py --model <hf-id> --tau <τ>` on pod `axvdenxbcepd10`, rsync'd back | 3.7 MB | 2 dirs x {`below_good.json`,`above_good.json`}, 50 incentive rollouts per condition. **Committed by exception** (3.7 MB, and P-003 / G-001 / D-016 / V-003 are computed from them; `src/landing_gap.py` and `src/recount_w2.py` must be re-runnable by the auditor). |
| `w3_frozen/` | W3 | `python src/gen_w3.py --tau-a 15300000 [--tau-b 4500000000] --arms ...` on pod `bkl3m9ieis977o`, rsync'd back | 2.5 MB | `form_A/{below,above}_good.json` (150 each) + `form_B/{baseline,below_good,above_good}.json` (50/150/150). **The FROZEN DATASET** (PR-003 item 8): no resampling from these arms. **Committed by exception** — P-004/P-005/G-002/V-005 are computed from them and `src/behaviour_w3.py`, `src/direction_judge.py` and `src/recount_w3.py` must be re-runnable by the auditor. |
| `w4_acts/` | W4 | `python src/replay_w4.py` on pod `io6c1fhnarzoj9`, rsync'd back | **1.4 GB of 3.28 GB — INCOMPLETE** | 6 x `w4_acts_<form>_<arm>.safetensors`, fp16 `acts` tensor `[n_points, 48, 5120]` (post-block residual stream, all 48 decoder layers). **NOT committed** (too large; `runs/` is gitignored). The row index is `analysis/out/w4_positions/w4_positions_<form>_<arm>.json`, which IS committed and carries every position's trace id, kind, token index and span token ids. **Three arms are complete and integrity-verified** (rows == index `n_points`): `A_above_good` 558,858,544 B `sha256 abcde06b…`, `A_neutral` 133,693,736 B `sha256 14715479…`, `B_baseline` 203,981,096 B `sha256 f380fc05…`. **Three are truncated prefixes** because RunPod stopped the pod mid-rsync when the account balance went negative (D-020): `A_below_good` 170,754,048 of 585,892,144 B, `B_above_good` 181,272,576 of 881,295,664 B, `B_below_good` 216,236,032 of 913,735,984 B. Do not read the truncated three; regenerate them with `python src/replay_w4.py` on a funded pod. **Superseded — see the W5 note below: these files no longer exist.** |
| `w5_subsample/` | W5 | `python src/direction_w5.py` then `python src/w5_cell.py` on pod `io6c1fhnarzoj9`, rsync'd back in 4 parallel streams | 588 MB | **NOT committed** (`runs/` is gitignored). Two files of activations plus their JSON indexes, and the only activation data that survives the pod. (1) `w5_subsample.safetensors` — the PR-004 item-7 10 % subsample: **every 10th point of the global point index**, `[667, 48, 5120]` fp16, 327,844,104 B, `sha256 0e4b036a…`; index `w5_subsample_index.json` `sha256 f744ed54…`. (2) `w5_cell.safetensors` — the v_p̂ **analysis cell**: every `est` point of both `above_good` arms, `[528, 48, 5120]` fp16, 259,522,800 B, `sha256 55fd0a8d…`; index `w5_cell_index.json` `sha256 a7bb463b…`. Shipped as JC-4 after the frozen analysis completed, because the 10 % rule lands only 17 of 366 labelled cell points and cannot support PR-004's recount (D-024). `python3 src/w5_recount.py` rebuilds v_p̂(ℓ\*) from (2) alone. |

**W5 note — `w4_acts/` no longer exists anywhere.** Pod `io6c1fhnarzoj9` was terminated at
2026-08-30 05:28:18 UTC per R-010(2), and with it the 3.28 GB of W4 activation tensors. They
are **regenerable**: `python src/replay_w4.py` on a funded pod reproduces all six arms in
94.8 s of forward passes (~$0.12), and W5 verified before termination that the six pod-side
files matched their indexes row-for-row with 30/30 spans decoding exactly
(`python src/w5_integrity.py`, V-010). The three truncated laptop prefixes from D-020 were
deleted; the three complete laptop copies (`A_above_good`, `A_neutral`, `B_baseline`) are also
gone, since keeping half a dataset invites reading it. What remains on the laptop is
`w5_subsample/` above, which is what R-010(3) rules the laptop should hold.

**W4 note.** `w4_acts/` is the first run directory that is NOT committed by exception: at 3.28 GB it is three orders of magnitude past the previous largest. Everything the ledger cites about it — point counts, kinds, token indexes, the decode acceptance check — is computed from the committed positions indexes, not from the tensors.
