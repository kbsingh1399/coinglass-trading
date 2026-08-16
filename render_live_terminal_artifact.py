import os
import json
import time
from rich.console import Console
from Engine_1 import render_table, AssetSnapshot, LiveTradeTracker, ALL_SYMBOLS

def export_live_terminal_snapshot():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    snap_path = os.path.join(base_dir, "Seeding", "snapshot_debug.json")
    
    snaps = {}
    if os.path.exists(snap_path):
        try:
            with open(snap_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for sym, d in data.items():
                    snaps[sym] = AssetSnapshot(
                        symbol=sym,
                        price=d.get("price", 0.0),
                        volume=d.get("volume", 0.0),
                        rsi=d.get("rsi", 50.0),
                        fut_cvd=d.get("fut_cvd", 0.0),
                        spot_cvd=d.get("spot_cvd", 0.0),
                        liq_long=d.get("liq_long", 0.0),
                        liq_short=d.get("liq_short", 0.0),
                        funding=d.get("funding", 0.0),
                        ls_ratio=d.get("ls_ratio", 0.0),
                        oi=d.get("oi", 0.0),
                        coins_bid=d.get("coins_bid", 0.0),
                        coins_ask=d.get("coins_ask", 0.0),
                        dollars_bid=d.get("dollars_bid", 0.0),
                        dollars_ask=d.get("dollars_ask", 0.0),
                        whale_idx=d.get("whale_idx", 0.0),
                        tk_buy_cnt=d.get("tk_buy_cnt", 0.0),
                        tk_sell_cnt=d.get("tk_sell_cnt", 0.0),
                        ema_8=d.get("ema_8", 0.0),
                        ema_21=d.get("ema_21", 0.0),
                        ema_50=d.get("ema_50", 0.0),
                        ema_200=d.get("ema_200", 0.0),
                        ema_800=d.get("ema_800", 0.0),
                        atr_14=d.get("atr_14", 0.0),
                        atr_100=d.get("atr_100", 0.0),
                        zc4=d.get("zc4", 0.0),
                        zc10=d.get("zc10", 0.0),
                        zc20=d.get("zc20", 0.0),
                        zb4=d.get("zb4", 0.0),
                        zb10=d.get("zb10", 0.0),
                        zb20=d.get("zb20", 0.0),
                        vr=d.get("vr", 0.0),
                        zoi=d.get("zoi", 0.0),
                        zls=d.get("zls", 0.0),
                        zfr=d.get("zfr", 0.0),
                        p8=d.get("p8", 0.0),
                        p21=d.get("p21", 0.0),
                        p50=d.get("p50", 0.0),
                        fp_delta=d.get("fp_delta", 0.0),
                        fp_poc=d.get("fp_poc", 0.0),
                        strategy_armed=d.get("strategy_armed", "READY"),
                        ts_ns=d.get("ts_ns", time.time_ns())
                    )
        except Exception as e:
            print(f"Error loading {snap_path}: {e}")

    # Fallback for missing symbols
    for sym in ALL_SYMBOLS:
        if sym not in snaps:
            snaps[sym] = AssetSnapshot(symbol=sym, price=0.0, ts_ns=time.time_ns())

    tt = LiveTradeTracker(initial_capital=4303.27)
    
    console = Console(width=165, color_system="truecolor", record=True)
    rendered_group = render_table(snaps, tt)
    console.print(rendered_group)
    
    artifact_dir = r"C:\Users\SIGMA\.gemini\antigravity\brain\b0378007-cf33-45a3-a901-d12ca2793e08"
    svg_out = os.path.join(artifact_dir, "terminal_dashboard_live.svg")
    html_out = os.path.join(artifact_dir, "terminal_dashboard_live.html")
    
    svg_data = console.export_svg(title="Engine 1 Multi-Table Terminal (Live Execution)")
    with open(svg_out, "w", encoding="utf-8") as f:
        f.write(svg_data)
        
    html_data = console.export_html(inline_styles=True, theme=None)
    # Add dark background for high-contrast presentation
    html_data = html_data.replace("background-color: #ffffff;", "background-color: #0c0c0c; color: #ffffff;")
    with open(html_out, "w", encoding="utf-8") as f:
        f.write(html_data)
        
    print(f"[OK] Live terminal visual snapshot saved to {svg_out} and {html_out}")

if __name__ == "__main__":
    export_live_terminal_snapshot()
