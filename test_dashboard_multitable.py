import os
import sys
import time
from rich.console import Console

# Test multi-table terminal dashboard rendering
from Engine_1 import AssetSnapshot, ALL_SYMBOLS, render_table, LiveTradeTracker

def test_multitable_rendering():
    console = Console(width=160, color_system="truecolor", record=True)
    snap = {}
    
    for i, sym in enumerate(ALL_SYMBOLS):
        base_price = 50000.0 / (i + 1)
        snap[sym] = AssetSnapshot(
            symbol=sym,
            price=base_price,
            ema_8=base_price * 1.002,
            ema_21=base_price * 1.005,
            ema_50=base_price * 1.010,
            ema_200=base_price * 0.990,
            ema_800=base_price * 0.980,
            atr_14=base_price * 0.008,
            rsi=45.5 + i * 2.0,
            p8=0.45,
            p21=-0.22,
            p50=-0.85,
            fut_cvd=1250000.0 * (1 if i % 2 == 0 else -1),
            spot_cvd=850000.0 * (1 if i % 3 == 0 else -1),
            zc4=1.85 * (1 if i % 2 == 0 else -1),
            zc10=0.95 * (1 if i % 2 == 0 else -1),
            zc20=-1.45 * (1 if i % 2 == 0 else -1),
            zb4=0.75,
            zb20=-0.35,
            vr=1.65 if i % 4 == 0 else 0.45,
            zoi=1.20,
            zls=-0.80,
            zfr=0.40,
            liq_long=150000.0 if i % 3 == 0 else 0.0,
            liq_short=-95000.0 if i % 2 == 0 else 0.0,
            strategy_armed="S1:LONG" if i == 0 else ("S3:SHORT" if i == 1 else "READY"),
            ts_ns=time.time_ns()
        )

    tt = LiveTradeTracker(initial_capital=4303.27)
    tt.trigger_entry("BTCUSDT", "S1_Liquidation", 1, 63000.0, 62500.0, 65000.0, 500.0, 1, 0.5)
    tt.trigger_entry("ETHUSDT", "S2_CVD_Momentum", -1, 3100.0, 3150.0, 2950.0, 25.0, -1, 0.2)

    rendered_group = render_table(snap, tt)
    console.print(rendered_group)
    
    svg_path = "terminal_multitable_preview.svg"
    console.save_svg(svg_path, title="Engine 1 Multi-Table Dashboard")
    print(f"[OK] Multi-table rendered successfully. Saved SVG preview to {svg_path}")

if __name__ == "__main__":
    test_multitable_rendering()
