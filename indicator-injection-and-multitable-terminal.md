# Task Plan: Indicator Injection, Rolling Architecture & Multi-Table Terminal Redesign

## Objective
1. Inject all required technical studies (EMA 8, 21, 50, 200, 800, ATR 14, RSI 14) natively into CoinGlass TradingView charts across all 18 symbols.
2. Update `SINGLE_FRAME_EXTRACTION_JS` in `Engine_1.py` with period-aware regex matching to extract and disambiguate each indicator into `AssetSnapshot` fields.
3. Optimize Chromium performance by injecting lightweight styling (hiding redundant UI overlays, animations, and non-essential DOM elements) to maximize frame extraction throughput and prevent browser lag.
4. Redesign the live terminal into a multi-table single-screen layout:
   - **Table 1 (Price & Trend)**: Symbol, Price, EMAs (8, 21, 50, 200, 800), ATR 14, RSI 14, Pullback Distances (p8, p21, p50), Strategy Armed state.
   - **Table 2 (Order Flow & Z-Scores)**: Symbol, FutCVD, SpotCVD, CVD Z-scores (zc4, zc10, zc20), BTC CVD Z-scores (zb4, zb10, zb20), Volatility Regime (VR), OI Z-score (zoi), Long/Short Z-score (zls), Funding Rate Z-score (zfr), Liquidations (LiqL, LiqS).
   - **Table 3 (Account & Execution Summary)**: Initial Capital, Live Capital, Daily PnL ($ and %), Active Positions (with live SL/TP and PnL), Recent Trade History, Pipeline Health.
5. Verify end-to-end functionality via test suites, compilation, and autonomous execution.

## Phase Breakdown

### Phase 1: Study Injection & Disambiguated Extraction
- Modify `Engine_1.py` `singleStudies` injection in `launch_and_login` to create:
  - Moving Average Exponential (periods 8, 21, 50, 200, 800)
  - Average True Range (period 14)
  - Relative Strength Index (period 14)
  - Derivatives studies (CVD, Liquidations, OI, Funding, LS Ratio, Whale Index, Taker Buy/Sell, Bid/Ask)
- Update `SINGLE_FRAME_EXTRACTION_JS` to parse each EMA period cleanly into `ema_8`, `ema_21`, `ema_50`, `ema_200`, `ema_800`, `atr_14`, and `rsi`.
- Update `AssetSnapshot` with explicit fields for these indicators.

### Phase 2: Chromium Performance Optimization
- Inject DOM cleanup CSS into each tab to hide heavy UI sidebars, promotional banners, and non-essential chart toolbars while keeping the chart canvas and legend status bars fully visible.

### Phase 3: Terminal Multi-Table Single-Screen Redesign
- Replace the monolithic single-table render in `render_table()` with an organized three-table stack using Rich `Table` and `Group`.
- Apply clear, high-contrast formatting with column-level freshness and stale detection.

### Phase 4: Verification & Autonomous Execution
- Run `test_engine_parity.py` and compilation tests.
- Launch the autonomous batch execution and verify data flow, indicators, and terminal rendering.
