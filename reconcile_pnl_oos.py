import os
import json
from collections import defaultdict

def run_reconciliation():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Load Live Trade Logs
    live_log_path = os.path.join(base_dir, "Engine_1_trade_logs.json")
    live_trades = []
    if os.path.exists(live_log_path):
        try:
            with open(live_log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                live_trades = data.get("trades", [])
        except Exception as e:
            print(f"Error reading live trades: {e}")
            
    # 2. Load OOS Backtest Benchmark Results
    oos_results_path = os.path.join(base_dir, "all_6_results.json")
    oos_benchmarks = {}
    if os.path.exists(oos_results_path):
        try:
            with open(oos_results_path, "r", encoding="utf-8") as f:
                oos_data = json.load(f)
                for strat, windows in oos_data.items():
                    if not windows:
                        continue
                    total_trades = sum(int(w.get("tr", 0)) for w in windows)
                    total_wins = sum(int(w.get("wins", 0)) for w in windows)
                    total_pnl = sum(float(w.get("pnl", 0.0)) for w in windows)
                    avg_wr = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0
                    avg_pnl_per_trade = (total_pnl / total_trades) if total_trades > 0 else 0.0
                    oos_benchmarks[strat] = {
                        "total_trades": total_trades,
                        "win_rate": avg_wr,
                        "total_pnl": total_pnl,
                        "avg_pnl_per_trade": avg_pnl_per_trade
                    }
        except Exception as e:
            print(f"Error reading OOS benchmarks: {e}")

    # 3. Analyze Live Trade Performance by Strategy
    live_by_strat = defaultdict(list)
    for t in live_trades:
        strat = t.get("strategy", "Unknown")
        live_by_strat[strat].append(t)

    print("=" * 85)
    print("           LIVE TRADING PNL vs OOS BACKTEST BENCHMARK RECONCILIATION")
    print("=" * 85)
    print(f"{'Strategy':<22} | {'Live Trades':<11} | {'Live WR':<8} | {'Live PnL':<11} | {'OOS WR':<8} | {'OOS $/Tr':<9}")
    print("-" * 85)

    strat_map = {
        "S1_Liquidation": ["S1_Liquidation", "S1_Liquidation_Cascade"],
        "S2_CVD_Momentum": ["S2_CVD_Momentum", "S2_CVD_Momentum_Shift"],
        "S3_Trend_Pull": ["S3_Trend_Pull", "S3_EMA_Trend_Pullback"],
        "S4_Mean_Reversion": ["S4_Mean_Reversion", "S4_RSI_Mean_Reversion"],
        "S5_Vol_Breakout": ["S5_Vol_Breakout", "S5_Volatility_Breakout"],
        "S6_Alpha_Squeeze": ["S6_Alpha_Squeeze", "S6_OI_Alpha_Squeeze"]
    }

    for benchmark_key, aliases in strat_map.items():
        matched_live = []
        for alias in aliases:
            if alias in live_by_strat:
                matched_live.extend(live_by_strat[alias])
        
        # Live Stats
        live_closed = [t for t in matched_live if t.get("exit_price")]
        live_cnt = len(live_closed)
        live_wins = sum(1 for t in live_closed if t.get("pnl_usd", 0) > 0)
        live_wr = (live_wins / live_cnt * 100.0) if live_cnt > 0 else 0.0
        live_pnl = sum(t.get("pnl_usd", 0) for t in live_closed)

        # OOS Stats
        oos_info = oos_benchmarks.get(benchmark_key, {})
        oos_wr = oos_info.get("win_rate", 0.0)
        oos_avg_pnl = oos_info.get("avg_pnl_per_trade", 0.0)

        print(f"{benchmark_key:<22} | {live_cnt:<11} | {live_wr:>6.1f}% | ${live_pnl:>9.2f} | {oos_wr:>6.1f}% | ${oos_avg_pnl:>7.2f}")

    print("-" * 85)
    total_live_closed = [t for t in live_trades if t.get("exit_price")]
    total_live_cnt = len(total_live_closed)
    total_live_wins = sum(1 for t in total_live_closed if t.get("pnl_usd", 0) > 0)
    total_live_wr = (total_live_wins / total_live_cnt * 100.0) if total_live_cnt > 0 else 0.0
    total_live_pnl = sum(t.get("pnl_usd", 0) for t in total_live_closed)
    
    print(f"{'TOTAL / PORTFOLIO':<22} | {total_live_cnt:<11} | {total_live_wr:>6.1f}% | ${total_live_pnl:>9.2f} |")
    print("=" * 85)

if __name__ == "__main__":
    run_reconciliation()
