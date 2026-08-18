# MISSION DIRECTIVE: Execution Parity & Desync Audit
**Repository Information:**
- **Repository URL:** `https://github.com/kbsingh1399/coinglass-trading.git`
- **Branch:** `arena/019fec7a-coinglass-trading`
- **Latest Commit (Parity Fixes):** `f0ec12f`

I have a Python-based quantitative trading system consisting of a backtester (`run_all_6.py`) and a live execution engine (`Engine_1.py`) connected to Binance Testnet.

**The Problem:**
My backtester is highly profitable and passes strict walk-forward optimization across multiple years of data. However, the live engine (`Engine_1.py`) is bleeding capital. It currently has a 0% win rate across recent trades. Trades are exiting almost exclusively via `SL` (Stop Loss) or `BROKER_SYNC`. 
*Note: `BROKER_SYNC` is an emergency fallback exit that triggers when the local engine thinks a position is open, but the Binance API reports no active position for that symbol.*

**Your Task:**
Perform an adversarial code review and data-flow analysis to identify the exact cause of this "Sim-to-Live" gap. Specifically, investigate the following failure vectors:

1. **Order Submission & Silent Failures (The `BROKER_SYNC` Mystery):**
   - Review how `Engine_1.py` handles order execution. Is the engine registering trades locally *before* confirming the Binance API response?
   - Are market orders failing due to precision errors, lot size limits, or insufficient margin on Binance Testnet, causing the local engine to track a ghost position?

2. **Stop Loss (SL) & Liquidation Proximity:**
   - Review how SL distances are calculated and submitted. Are the SLs being placed so tightly that Binance Testnet's native spread or slippage instantly triggers them?
   - In `run_all_6.py`, SL is assumed to be exactly `entry +/- ATR`. In `Engine_1.py`, how is the SL submitted to the exchange? Is there a discrepancy in decimal precision or tick size?

3. **Data Drift & Real-Time Feature Calculation:**
   - The backtester uses static 15-minute Parquet files. The live engine constructs features (CVD, Orderflow, Liquidation, OI) in real-time via WebSockets.
   - Look for "Live Data Leakage" or "Drift": Are the live features (like `zoi`, `zls`, `zc20`) being calculated differently in memory compared to the pandas-based `featurize()` function in the backtester? 

4. **Latency & Race Conditions:**
   - Could the WebSocket streams be lagging behind the Binance Broker execution threads, causing the engine to execute on stale prices and instantly get stopped out?

**Output Requirements:**
Do not give generic advice. Provide specific line-by-line theories on why `BROKER_SYNC` is triggering and why trades hit `SL` immediately. Propose precise code modifications to `Engine_1.py` to add strict order-fill verification before a trade is registered locally.
