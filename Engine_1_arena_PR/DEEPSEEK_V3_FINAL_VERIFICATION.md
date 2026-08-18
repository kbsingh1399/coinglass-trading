# Open-Ended System Audit and Parity Check

We have just pushed the latest parity fixes to the `arena/019fec7a-coinglass-trading` branch of `https://github.com/kbsingh1399/coinglass-trading.git`.

We need you to pull the latest code from this repository and perform an open-ended, unrestricted, "wild move in every direction" audit of our trading system. Do not limit your audit to specific methods, files, or constraints. 

**The Core Issue:**
We are taking trades and keep losing money on live execution (`Engine_1.py` / `six_strategy_engine.py`), even though our Out-Of-Sample (OOS) backtesting in `run_all_6.py` performs very well. 

**Your Task:**
1. Fetch the latest code from the GitHub repository linked above.
2. Review the trades we took and the entire pipeline from signal generation, feature extraction, all the way down to live execution.
3. Hunt for ANY possible bugs, parity discrepancies, or logic flaws that could explain why the live execution diverges so severely and negatively from `run_all_6.py`'s performance.
4. Report back with any and all issues you find, big or small. Give us the unvarnished truth.
