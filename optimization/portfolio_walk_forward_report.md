# Three-strategy strict expanding walk-forward report

This report is generated from `optimization/portfolio_walk_forward.py`. The OOS metrics are not used to select parameters.

## Fixed execution specification

| Item | Value |
|---|---:|
| Window starting capital | $5,000.00 (reset every window) |
| Risk per trade | $50.00 (1.0% initial capital) |
| Stop / target | 1.0 ATR / 5.0 ATR (5.0R) |
| Round-trip friction | 0.10% |
| Entry | next 15-minute bar open after a close signal |

## Window results

| # | Dates | Alpha Squeezer | ML_liquidation | Trend Pull | Combined |
|---:|---|---:|---:|---:|---:|
| 1 | 2020-03-18 → 2020-04-18 | $-866 / -17.3% / 16.9% / 295 FAIL | $-80 / -1.6% / 17.2% / 64 FAIL | $112 / 2.2% / 18.1% / 216 FAIL | $-834 / -16.7% / 17.4% / 575 FAIL |
| 2 | 2020-11-07 → 2020-12-07 | $524 / 10.5% / 18.5% / 286 FAIL | $-1,583 / -31.7% / 13.7% / 139 FAIL | $405 / 8.1% / 18.6% / 199 FAIL | $-654 / -13.1% / 17.5% / 624 FAIL |
| 3 | 2021-01-24 → 2021-02-24 | $2,721 / 54.4% / 21.3% / 277 FAIL | $-339 / -6.8% / 17.7% / 130 FAIL | $1,972 / 39.4% / 22.2% / 171 FAIL | $4,354 / 87.1% / 20.8% / 578 FAIL |
| 4 | 2021-06-13 → 2021-07-13 | $3,225 / 64.5% / 20.4% / 455 FAIL | $3 / 0.1% / 18.4% / 114 FAIL | $2,711 / 54.2% / 21.5% / 246 FAIL | $5,939 / 118.8% / 20.5% / 815 FAIL |
| 5 | 2021-10-29 → 2021-11-29 | $-160 / -3.2% / 18.2% / 478 FAIL | $913 / 18.3% / 21.1% / 90 FAIL | $3,165 / 63.3% / 22.7% / 251 FAIL | $3,918 / 78.4% / 19.9% / 819 FAIL |
| 6 | 2022-02-08 → 2022-03-08 | $9,997 / 199.9% / 25.6% / 450 FAIL | $472 / 9.4% / 19.0% / 105 FAIL | $3,245 / 64.9% / 22.0% / 264 FAIL | $13,714 / 274.3% / 23.6% / 819 FAIL |
| 7 | 2022-05-21 → 2022-06-21 | $7,780 / 155.6% / 22.2% / 582 FAIL | $1,537 / 30.7% / 21.8% / 133 FAIL | $3,548 / 71.0% / 21.8% / 289 FAIL | $12,865 / 257.3% / 22.0% / 1004 FAIL |
| 8 | 2022-09-14 → 2022-10-14 | $-700 / -14.0% / 18.3% / 633 FAIL | $823 / 16.5% / 21.8% / 101 FAIL | $1,330 / 26.6% / 19.8% / 384 FAIL | $1,454 / 29.1% / 19.1% / 1118 FAIL |
| 9 | 2022-12-03 → 2023-01-03 | $-1,760 / -35.2% / 18.2% / 499 FAIL | $1,856 / 37.1% / 25.0% / 104 FAIL | $2,572 / 51.4% / 22.7% / 256 FAIL | $2,668 / 53.4% / 20.4% / 859 FAIL |
| 10 | 2023-04-17 → 2023-05-17 | $1,469 / 29.4% / 19.7% / 528 FAIL | $2,248 / 45.0% / 25.0% / 124 FAIL | $3,393 / 67.9% / 22.0% / 337 FAIL | $7,111 / 142.2% / 21.1% / 989 FAIL |
| 11 | 2023-08-25 → 2023-09-25 | $-1,237 / -24.7% / 18.8% / 431 FAIL | $-2,665 / -53.3% / 13.0% / 131 FAIL | $4,761 / 95.2% / 25.6% / 273 FAIL | $859 / 17.2% / 20.1% / 835 FAIL |
| 12 | 2023-11-10 → 2023-12-10 | $4,461 / 89.2% / 21.6% / 468 FAIL | $1,051 / 21.0% / 20.9% / 134 FAIL | $4,083 / 81.7% / 23.2% / 271 FAIL | $9,595 / 191.9% / 22.0% / 873 FAIL |
| 13 | 2024-02-19 → 2024-03-19 | $1,904 / 38.1% / 20.2% / 400 FAIL | $1,137 / 22.7% / 20.0% / 170 FAIL | $4,273 / 85.5% / 24.2% / 236 FAIL | $7,314 / 146.3% / 21.3% / 806 FAIL |
| 14 | 2024-07-06 → 2024-08-06 | $9,278 / 185.6% / 24.2% / 562 FAIL | $1,532 / 30.6% / 21.4% / 145 FAIL | $7,469 / 149.4% / 28.1% / 267 FAIL | $18,280 / 365.6% / 24.8% / 974 FAIL |
| 15 | 2024-10-28 → 2024-11-28 | $855 / 17.1% / 18.8% / 527 FAIL | $-1,606 / -32.1% / 15.5% / 193 FAIL | $4,503 / 90.1% / 24.1% / 253 FAIL | $3,751 / 75.0% / 19.5% / 973 FAIL |
| 16 | 2025-01-15 → 2025-02-15 | $3,704 / 74.1% / 19.8% / 718 FAIL | $1,636 / 32.7% / 20.8% / 192 FAIL | $5,929 / 118.6% / 22.9% / 410 FAIL | $11,269 / 225.4% / 20.9% / 1320 FAIL |
| 17 | 2025-05-03 → 2025-06-03 | $8,654 / 173.1% / 23.4% / 594 FAIL | $28 / 0.6% / 18.4% / 190 FAIL | $9,446 / 188.9% / 28.4% / 313 FAIL | $18,128 / 362.6% / 24.0% / 1097 FAIL |
| 18 | 2025-09-22 → 2025-10-22 | $1,619 / 32.4% / 19.2% / 624 FAIL | $913 / 18.3% / 22.1% / 131 FAIL | $2,480 / 49.6% / 20.5% / 361 FAIL | $5,011 / 100.2% / 20.0% / 1116 FAIL |
| 19 | 2026-02-11 → 2026-03-11 | $-7,250 / -145.0% / 17.3% / 704 FAIL | $3,187 / 63.7% / 24.2% / 186 FAIL | $-3,304 / -66.1% / 17.6% / 391 FAIL | $-7,366 / -147.3% / 18.4% / 1281 FAIL |
| 20 | 2026-06-09 → 2026-07-09 | $-9,089 / -181.8% / 17.5% / 661 FAIL | $-193 / -3.9% / 17.8% / 101 FAIL | $-2,621 / -52.4% / 19.5% / 394 FAIL | $-11,903 / -238.1% / 18.3% / 1156 FAIL |

Legend: each cell is `PnL / ROI / win rate / trades PASS|FAIL`; individual PASS means win rate >40% and ROI >20%, while combined PASS means win rate >40% and ROI ≥60%.

## Gate summary

- Combined: **0/20** windows passed; all passed = **False**.
- Alpha Squeezer: **0/20** windows passed; all passed = **False**.
- ML_liquidation: **0/20** windows passed; all passed = **False**.
- Trend Pull: **0/20** windows passed; all passed = **False**.

## Reproduction

```bash
python scripts/download_backtesting_data.py --verify-only
python optimization/portfolio_walk_forward.py
```

The limited-history XAUUSDT/XAGUSDT files are included when their data covers a window; earlier windows correctly have no eligible training prefix for those assets.
