# DEEPSEEK-V3 ARCHITECTURAL AUDIT PROMPT (REPOBRAIN ENABLED)

> **TARGET INTELLIGENCE:** DeepSeek-V3 (https://github.com/deepseek-ai/deepseek-v3) equipped with Repobrain (https://github.com/study8677/repobrain) for repository-scale code reasoning.
> **TASK:** Perform an exhaustive Architectural Audit, Concurrency Analysis, and DOM State Verification of the `Engine_1` quantitative trading pipeline directly from the repository source.

## Context
`Engine_1` is an asynchronous quantitative trading engine in Python 3.14. It ingests live order flow and derivatives metrics across 18 assets via CoinGlass, evaluates an ensemble of 84 machine learning strategy models, and executes risk-governed perpetual futures orders on Binance.

## Instructions
Please use your Repobrain capabilities to traverse the following repository and branch to audit the core components of the pipeline:

**Target Repository:** `https://github.com/kbsingh1399/coinglass-trading/tree/arena%2F019fec7a-coinglass-trading`

Specifically, audit the following areas:

### 1. DOM Scraping & Playwright Resilience
- Analyze `coinglass_scraper.py` and `Engine_1.py` for Playwright DOM interactions.
- Verify our new 4-badge extraction logic (Coin Bid, Coin Ask, Dollar Bid, Dollar Ask) which targets `div.valueValue-*` to avoid title text shadowing.
- Review the fallback logic for loading the `L_1` layout (force-clicking and `evaluate` fallbacks) to ensure we prevent actionability timeouts.

### 2. Concurrency & Thread Safety
- Audit the per-symbol `asyncio.Lock` mechanism in `SnapshotStore.update()`.
- Verify that concurrent updates from the Binance WebSocket (`price`, `fp_delta`) and CoinGlass DOM scrapers (`fut_cvd`, `spot_cvd`, etc.) are serialized safely.
- Confirm the ML inference dispatch runs outside these locks and correctly respects the 2.0s monotonic throttle.

### 3. Risk Governor & Broker Invariants
- Analyze `binance_broker.py` and the `LiveTradeTracker` logic.
- Verify the `modify_sltp` "place-then-cancel" invariant guarantees zero-naked-window exposure.
- Review the daily drawdown limits (-9.0% guardrail, 10% hard limit) and the strict UTC calendar day rollover logic at 00:00:00.

**Output Request:** Provide a structured 10-gate rating scorecard (PASS/FAIL) with mathematical and architectural justification for each subsystem based on the repository source code.
