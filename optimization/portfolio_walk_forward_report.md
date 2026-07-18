# Three-strategy strict expanding walk-forward report

This report is generated from `optimization/portfolio_walk_forward.py`. The OOS metrics are not used to select parameters.

## Fixed execution specification

| Item | Value |
|---|---:|
| Window starting capital | $5,000.00 (reset every window) |
| Risk per trade | $50.00 (1.0% initial capital) |
| Profit locks | $1,000 per sleeve; $3,000 account |
| Stop / target | 1.0 ATR / 5.0 ATR (5.0R) |
| Round-trip friction | 0.10% |
| Entry | next 15-minute bar open after a close signal |

## Window results

| # | Dates | Alpha Squeezer | ML_liquidation | Trend Pull | Combined |
|---:|---|---:|---:|---:|---:|
| 1 | 2020-03-18 → 2020-04-18 | $1,147 / 22.9% / 33.3% / 24 FAIL | $-80 / -1.6% / 17.2% / 64 FAIL | $1,211 / 24.2% / 41.2% / 17 PASS | $3,144 / 62.9% / 38.8% / 49 FAIL |
| 2 | 2020-11-07 → 2020-12-07 | $1,070 / 21.4% / 20.6% / 141 FAIL | $-1,583 / -31.7% / 13.7% / 139 FAIL | $1,122 / 22.4% / 21.8% / 101 FAIL | $608 / 12.2% / 18.4% / 381 FAIL |
| 3 | 2021-01-24 → 2021-02-24 | $1,049 / 21.0% / 26.2% / 42 FAIL | $-339 / -6.8% / 17.7% / 130 FAIL | $1,132 / 22.6% / 20.0% / 160 FAIL | $1,843 / 36.9% / 19.9% / 332 FAIL |
| 4 | 2021-06-13 → 2021-07-13 | $1,024 / 20.5% / 21.1% / 114 FAIL | $3 / 0.1% / 18.4% / 114 FAIL | $1,032 / 20.6% / 28.6% / 35 FAIL | $2,058 / 41.2% / 20.9% / 263 FAIL |
| 5 | 2021-10-29 → 2021-11-29 | $1,149 / 23.0% / 19.5% / 287 FAIL | $1,173 / 23.5% / 22.4% / 85 FAIL | $1,013 / 20.3% / 21.4% / 112 FAIL | $3,090 / 61.8% / 20.3% / 483 FAIL |
| 6 | 2022-02-08 → 2022-03-08 | $1,133 / 22.7% / 21.0% / 124 FAIL | $1,076 / 21.5% / 27.8% / 36 FAIL | $1,193 / 23.9% / 21.8% / 101 FAIL | $3,154 / 63.1% / 21.9% / 260 FAIL |
| 7 | 2022-05-21 → 2022-06-21 | $1,063 / 21.3% / 21.3% / 108 FAIL | $1,040 / 20.8% / 22.9% / 70 FAIL | $1,084 / 21.7% / 25.0% / 52 FAIL | $3,047 / 60.9% / 23.1% / 199 FAIL |
| 8 | 2022-09-14 → 2022-10-14 | $1,078 / 21.6% / 23.5% / 68 FAIL | $1,076 / 21.5% / 22.5% / 89 FAIL | $1,122 / 22.4% / 29.4% / 34 FAIL | $3,022 / 60.4% / 26.7% / 120 FAIL |
| 9 | 2022-12-03 → 2023-01-03 | $1,124 / 22.5% / 20.8% / 240 FAIL | $1,064 / 21.3% / 22.7% / 88 FAIL | $1,184 / 23.7% / 31.2% / 32 FAIL | $3,136 / 62.7% / 22.0% / 359 FAIL |
| 10 | 2023-04-17 → 2023-05-17 | $1,148 / 23.0% / 33.3% / 27 FAIL | $1,220 / 24.4% / 33.3% / 27 FAIL | $1,206 / 24.1% / 38.1% / 21 FAIL | $3,189 / 63.8% / 33.8% / 71 FAIL |
| 11 | 2023-08-25 → 2023-09-25 | $1,116 / 22.3% / 21.4% / 220 FAIL | $-2,665 / -53.3% / 13.0% / 131 FAIL | $1,029 / 20.6% / 38.9% / 18 FAIL | $-519 / -10.4% / 19.2% / 369 FAIL |
| 12 | 2023-11-10 → 2023-12-10 | $1,189 / 23.8% / 24.2% / 66 FAIL | $1,063 / 21.3% / 21.1% / 133 FAIL | $1,099 / 22.0% / 25.0% / 52 FAIL | $3,124 / 62.5% / 25.7% / 136 FAIL |
| 13 | 2024-02-19 → 2024-03-19 | $1,128 / 22.6% / 29.4% / 34 FAIL | $1,046 / 20.9% / 20.1% / 149 FAIL | $1,087 / 21.7% / 46.2% / 13 PASS | $3,006 / 60.1% / 23.6% / 178 FAIL |
| 14 | 2024-07-06 → 2024-08-06 | $1,111 / 22.2% / 21.2% / 132 FAIL | $1,011 / 20.2% / 27.0% / 37 FAIL | $1,210 / 24.2% / 25.5% / 55 FAIL | $3,054 / 61.1% / 22.9% / 218 FAIL |
| 15 | 2024-10-28 → 2024-11-28 | $1,057 / 21.1% / 22.9% / 83 FAIL | $-1,606 / -32.1% / 15.5% / 193 FAIL | $1,036 / 20.7% / 30.0% / 30 FAIL | $487 / 9.7% / 19.0% / 306 FAIL |
| 16 | 2025-01-15 → 2025-02-15 | $1,009 / 20.2% / 22.7% / 75 FAIL | $1,081 / 21.6% / 26.2% / 42 FAIL | $1,019 / 20.4% / 23.4% / 64 FAIL | $3,109 / 62.2% / 23.8% / 181 FAIL |
| 17 | 2025-05-03 → 2025-06-03 | $1,062 / 21.2% / 22.0% / 118 FAIL | $28 / 0.6% / 18.4% / 190 FAIL | $1,036 / 20.7% / 33.3% / 24 FAIL | $2,125 / 42.5% / 20.8% / 332 FAIL |
| 18 | 2025-09-22 → 2025-10-22 | $1,186 / 23.7% / 54.5% / 11 PASS | $1,224 / 24.5% / 38.1% / 21 FAIL | $1,068 / 21.4% / 46.2% / 13 PASS | $3,018 / 60.4% / 50.0% / 32 PASS |
| 19 | 2026-02-11 → 2026-03-11 | $1,050 / 21.0% / 36.8% / 19 FAIL | $1,117 / 22.3% / 23.5% / 68 FAIL | $1,134 / 22.7% / 50.0% / 12 PASS | $3,106 / 62.1% / 28.9% / 97 FAIL |
| 20 | 2026-06-09 → 2026-07-09 | $-9,089 / -181.8% / 17.5% / 661 FAIL | $-193 / -3.9% / 17.8% / 101 FAIL | $1,115 / 22.3% / 22.6% / 195 FAIL | $-8,166 / -163.3% / 18.6% / 957 FAIL |

Legend: each cell is `PnL / ROI / win rate / trades PASS|FAIL`; individual PASS means win rate >40% and ROI >20%, while combined PASS means win rate >40% and ROI ≥60%.

## Gate summary

- Combined: **1/20** windows passed; all passed = **False**.
- Alpha Squeezer: **1/20** windows passed; all passed = **False**.
- ML_liquidation: **0/20** windows passed; all passed = **False**.
- Trend Pull: **4/20** windows passed; all passed = **False**.

## Reproduction

```bash
python scripts/download_backtesting_data.py --verify-only
python optimization/portfolio_walk_forward.py
```

The limited-history XAUUSDT/XAGUSDT files are included when their data covers a window; earlier windows correctly have no eligible training prefix for those assets.
