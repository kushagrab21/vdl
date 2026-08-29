# MANIFEST.md — inventory of `runs/`

`runs/` holds raw generation data and is **gitignored**. Every directory created under it must
be listed here with: what produced it, the exact command, and its size. This file is committed;
the data is not.

| run dir | packet | produced by | size | notes |
|---|---|---|---|---|
| `smoke/` | W0b | `python src/smoke_vllm.py` and `python src/smoke_hooks.py` on pod `gwhn0ex0eeyntn`, rsync'd back | 60 KB | 2 files: `smoke_vllm_qwen3-8b.json` (F-012), `smoke_hooks_qwen3-8b.json` (F-013). **Committed by exception** — they are 60 KB, they are this packet's only experimental artefact, and F-012/F-013 cite them as evidence. Bulk rollout data from W2 on stays gitignored. |
| `w1_neutral/` | W1 | `python src/gen_neutral.py --model <hf-id>` on pod `gwhn0ex0eeyntn`, rsync'd back | 3.2 MB | 4 dirs x `neutral.json`, 50 baseline rollouts each. **Committed by exception** (3.2 MB, and P-001/P-002/D-011 are computed from them; `src/tau.py` must be re-runnable by the auditor). |
| `w2_screen/` | W2 | `python src/gen_mirrored.py --model <hf-id> --tau <τ>` on pod `axvdenxbcepd10`, rsync'd back | 3.7 MB | 2 dirs x {`below_good.json`,`above_good.json`}, 50 incentive rollouts per condition. **Committed by exception** (3.7 MB, and P-003 / G-001 / D-016 / V-003 are computed from them; `src/landing_gap.py` and `src/recount_w2.py` must be re-runnable by the auditor). |
