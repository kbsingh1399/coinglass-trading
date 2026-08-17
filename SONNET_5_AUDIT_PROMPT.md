# Elite Trading Engine Audit: Systematic Code & Financial Logic Review

You are an elite quantitative trading systems engineer, site reliability engineer, and security researcher. You are tasked with performing an unrestricted, holistic audit of the Engine_1.py Quantitative Trading Pipeline and its associated components. 

## Context
This engine scrapes real-time TradingView indicators from CoinGlass using a Playwright grid layout (`coinglass_scraper.py` / `engine_components/coinglass_scraper.py`) and executes trades on Binance (`binance_broker.py` / `engine_components/binance_broker.py`). It predicts market direction using a scikit-learn model (`live_unified_predictor.py`).

Recently, we resolved several critical structural bugs including a naked-window vulnerability (missing Stop Losses) and unhandled Playwright disconnection exceptions that crashed the engine.

However, we are now facing a severe financial discrepancy: **The system performs exceptionally well in Out-Of-Sample (OOS) backtesting (as defined in `run_all_6.py`), but it is consistently losing money in live trading.**

**I have pushed the latest version of the code to the branch `arena/019fec7a-coinglass-trading` in the GitHub repository: https://github.com/kbsingh1399/coinglass-trading.git. Please fetch and review the source code directly from this repo.**

## Your Mission: Unrestricted Bug Hunt & Financial Audit
I am removing all constraints. Move wildly in every direction. Do not limit your review to just concurrency or the web scraper. Look at the entire architecture holistically. Find out why we are bleeding capital and what structural flaws still exist in the engine.

### Core Objectives:
1. **The Live vs. Backtest Gap (The Financial Bleed):**
   - Compare the live execution logic in `Engine_1.py` and `binance_broker.py` against typical assumptions made in a backtest like `run_all_6.py`.
   - Look for **Config Drift** or calculation mismatches: Are the features (e.g., EMA, RSI, CVD) calculated exactly the same way live as they were in training?
   - Analyze execution mechanics: Are we losing everything to taker fees, slippage, latency, or bid/ask spread? Is the engine crossing the spread inefficiently?
   - Look at Stop Loss / Take Profit execution: Is the live trailing stop or fixed SL triggering prematurely due to tick data noise that the backtest didn't see?

2. **Unrestricted System Audit (Logic, State, and Safety):**
   - Hunt for hidden state corruption, memory leaks, orphaned tasks, or race conditions.
   - Look for silent failures where an error is swallowed but leaves the trade tracker in an inconsistent state.
   - Analyze API rate limiting, timing offsets (e.g., UTC rollovers), and data staleness issues. What happens if the Coinglass scraper lags by 5 seconds?

### Deliverables
List every vulnerability, financial logic mismatch, and structural flaw you discover.
For each issue, classify it by severity (P0 = Critical Loss of Funds / Crash, P1 = High financial drag / Logic flaw, P2 = Optimization).

**For every issue you identify, provide the EXACT code block to fix it.**
- Use diff-style format or explicit Before / After blocks.
- Ensure the code you provide can be seamlessly copy-pasted directly into our local environment.
