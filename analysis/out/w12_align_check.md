# W12 position-alignment check — W4's `est` points decode in the W12 capture

Fixed rule: every 54th `est` point of the W4 form-B global index (`A`rm order `above_good, below_good`, then trace order, then parse order), first 10 taken. `w12 gen_pos` is `w4 token_index - n_prompt_tokens`; `w12 row` is the row of the concatenated W12 shards that holds it.

| # | arm | trace | w4 token idx | n_prompt | w12 gen_pos | w12 row | decoded span | w4 literal | same row in index | exact |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `above_good` | 0 | 417 | 197 | 220 | 220 | `12,000,000,000` | `12,000,000,000` | yes | **PASS** |
| 2 | `above_good` | 27 | 554 | 197 | 357 | 11415 | `2,500,000,000` | `2,500,000,000` | yes | **PASS** |
| 3 | `above_good` | 58 | 812 | 197 | 615 | 24877 | `4,000,000,000` | `4,000,000,000` | yes | **PASS** |
| 4 | `above_good` | 91 | 479 | 197 | 282 | 39242 | `300,000,000,000` | `300,000,000,000` | yes | **PASS** |
| 5 | `above_good` | 119 | 834 | 197 | 637 | 51673 | `4,500,000,001` | `4,500,000,001` | yes | **PASS** |
| 6 | `above_good` | 148 | 850 | 197 | 653 | 63950 | `3,500,000,000` | `3,500,000,000` | yes | **PASS** |
| 7 | `below_good` | 27 | 538 | 197 | 341 | 11836 | `20,000,000,000` | `20,000,000,000` | yes | **PASS** |
| 8 | `below_good` | 64 | 556 | 197 | 359 | 27634 | `360,000,000,000` | `360,000,000,000` | yes | **PASS** |
| 9 | `below_good` | 93 | 481 | 197 | 284 | 39889 | `125,000,000,000` | `125,000,000,000` | yes | **PASS** |
| 10 | `below_good` | 121 | 420 | 197 | 223 | 52495 | `50,000,000,000` | `50,000,000,000` | yes | **PASS** |

**10 / 10 exact.**

