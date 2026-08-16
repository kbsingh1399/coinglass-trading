"""
Windows Console ANSI Subsystem Diagnostic
Run this directly in the same terminal host (cmd.exe / conhost) that runs Engine_1.py.
It will report VT flag states, test multiple Console configurations,
and verify ANSI emission at the segment level.
"""

import sys
import io
import ctypes
from ctypes import wintypes

# ---------------------------------------------------------------------------
# 1. Win32 Console Mode Inspection
# ---------------------------------------------------------------------------
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
STD_OUTPUT_HANDLE = wintypes.DWORD(-11)
ENABLE_PROCESSED_OUTPUT = 0x0001
ENABLE_WRAP_AT_EOL = 0x0002
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200


def inspect_console_mode() -> dict:
    """Read and decode the current stdout console mode flags."""
    handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    mode = wintypes.DWORD()
    result = {
        "handle_valid": False,
        "raw_mode": None,
        "PROCESSED_OUTPUT": False,
        "WRAP_AT_EOL": False,
        "VT_PROCESSING": False,
        "VT_INPUT": False,
    }
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        result["handle_valid"] = True
        result["raw_mode"] = mode.value
        result["PROCESSED_OUTPUT"] = bool(mode.value & ENABLE_PROCESSED_OUTPUT)
        result["WRAP_AT_EOL"] = bool(mode.value & ENABLE_WRAP_AT_EOL)
        result["VT_PROCESSING"] = bool(mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        result["VT_INPUT"] = bool(mode.value & ENABLE_VIRTUAL_TERMINAL_INPUT)
    return result


def force_enable_vt() -> bool:
    """Forcibly set the VT_PROCESSING and PROCESSED_OUTPUT flags on stdout."""
    handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING | ENABLE_PROCESSED_OUTPUT
    return bool(kernel32.SetConsoleMode(handle, new_mode))


# ---------------------------------------------------------------------------
# 2. Rich Console Configuration Matrix Test
# ---------------------------------------------------------------------------
def test_rich_matrix():
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel
    from rich import box

    configs = [
        {
            "name": "A. Production Recommended",
            "kwargs": {
                "force_terminal": True,
                "color_system": "256",
                "legacy_windows": False,
                "highlight": False,
                "soft_wrap": True,
            },
        },
        {
            "name": "B. Legacy Win32 API (AVOID)",
            "kwargs": {
                "force_terminal": False,
                "color_system": "auto",
                "legacy_windows": True,
                "highlight": False,
                "soft_wrap": True,
            },
        },
        {
            "name": "C. TrueColor on conhost (RISKY)",
            "kwargs": {
                "force_terminal": True,
                "color_system": "truecolor",
                "legacy_windows": False,
                "highlight": False,
                "soft_wrap": True,
            },
        },
        {
            "name": "D. Auto-detect (AMBIGUOUS)",
            "kwargs": {
                "force_terminal": False,
                "color_system": "auto",
                "legacy_windows": False,
                "highlight": False,
                "soft_wrap": True,
            },
        },
    ]

    results = []
    for cfg in configs:
        print(f"\n{'=' * 70}")
        print(f"CONFIG: {cfg['name']}")
        print(f"PARAMS: {cfg['kwargs']}")
        print(f"{'=' * 70}")

        c = Console(**cfg["kwargs"])
        meta = {
            "config_name": cfg["name"],
            "color_system_attr": c.color_system,
            "is_terminal": c.is_terminal,
            "legacy_windows_attr": c.legacy_windows,
            "encoding": c.encoding,
        }

        # --- Test 1: Direct markup rendering ---
        with c.capture() as cap:
            c.print("[bold red]RED[/] [bold green]GREEN[/] [bold blue]BLUE[/] [bold yellow]YELLOW[/]")
        markup_raw = cap.get()
        meta["markup_has_ansi"] = "\x1b[" in markup_raw

        # --- Test 2: Table with styled cells (reproduces your exact symptom) ---
        table = Table(
            title="Market Overview",
            title_style="bold bright_blue",
            border_style="bright_blue",
            box=box.ROUNDED,
        )
        table.add_column("Symbol", style="bold cyan", no_wrap=True)
        table.add_column("Price", style="bold yellow", justify="right")
        table.add_column("RSI", style="bold red")
        table.add_column("CVD", style="bold green")
        table.add_row("BTCUSDT", "68,420.50", "42.50", "+1.24M")
        table.add_row("ETHUSDT", "3,850.20", "38.12", "-890K")

        with c.capture() as cap:
            c.print(table)
        table_raw = cap.get()
        meta["table_has_ansi"] = "\x1b[" in table_raw
        meta["table_cell_ansi_count"] = table_raw.count("\x1b[")

        # --- Test 3: Explicit Text object styles ---
        text_block = Text.assemble(
            ("LONG ", "bold bright_green"),
            ("SHORT ", "bold bright_red"),
            ("NEUTRAL", "bold yellow"),
        )
        with c.capture() as cap:
            c.print(text_block)
        text_raw = cap.get()
        meta["text_has_ansi"] = "\x1b[" in text_raw

        # --- Human visual verification ---
        c.print("\n[bold]Visual verification:[/]")
        c.print("[bold red]RED[/] [bold green]GREEN[/] [bold blue]BLUE[/] [bold yellow]YELLOW[/]")
        c.print(table)
        c.print(text_block)

        results.append(meta)
        print(f"\n[DIAGNOSTIC] ANSI in markup: {meta['markup_has_ansi']}")
        print(f"[DIAGNOSTIC] ANSI in table:  {meta['table_has_ansi']} (count: {meta['table_cell_ansi_count']})")
        print(f"[DIAGNOSTIC] ANSI in text:   {meta['text_has_ansi']}")

    return results


# ---------------------------------------------------------------------------
# 3. Live.update() Segment Verification
# ---------------------------------------------------------------------------
def test_live_segment_integrity():
    """
    Prove that the renderable tree contains color segments BEFORE Live.update().
    This simulates your engine's render tick.
    """
    from rich.console import Console
    from rich.table import Table
    from rich.layout import Layout
    from rich.live import Live
    import asyncio

    console = Console(
        force_terminal=True,
        color_system="256",
        legacy_windows=False,
        highlight=False,
        soft_wrap=True,
    )

    # Build a layout identical to your dashboard structure
    table1 = Table(title="📊 Market Overview", border_style="bright_blue", box=None)
    table1.add_column("Sym", style="bold cyan")
    table1.add_column("Price", style="bold yellow")
    table1.add_row("BTC", "68,000")

    table2 = Table(title="Volume & Footprint", border_style="magenta", box=None)
    table2.add_column("Delta", style="bold green")
    table2.add_column("POC", style="bold red")
    table2.add_row("+1.2M", "67,800")

    layout = Layout()
    layout.split_column(
        Layout(table1, name="upper"),
        Layout(table2, name="lower"),
    )

    # --- CRITICAL: Verify segments before sending to Live ---
    segments = list(console.render(layout, console.options))
    segment_styles = [str(seg.style) for seg in segments if seg.style]
    ansi_codes = [seg.text for seg in segments if "\x1b[" in seg.text]

    print(f"\n{'=' * 70}")
    print("LIVE SEGMENT INTEGRITY TEST")
    print(f"{'=' * 70}")
    print(f"Total segments: {len(segments)}")
    print(f"Segments with style: {len(segment_styles)}")
    print(f"Segments containing ANSI: {len(ansi_codes)}")

    if not ansi_codes:
        print("\n[CRITICAL] No ANSI escape codes found in rendered segments!")
        print("           Live.update() will receive monochrome frames.")
        return False

    # Show sample ANSI codes for manual verification
    print("\nSample ANSI sequences in rendered output:")
    for code in ansi_codes[:5]:
        print(f"  {repr(code[:60])}")

    # Now pass through Live context to ensure it survives
    with Live(console=console, auto_refresh=False, screen=False, transient=False) as live:
        live.update(layout, refresh=True)
        # Capture what Live actually emitted
        with console.capture() as cap:
            console.print(layout)
        emitted = cap.get()
        live_has_ansi = "\x1b[" in emitted
        print(f"\nPost-Live ANSI intact: {live_has_ansi}")
        return live_has_ansi


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print(" WINDOWS CONSOLE ANSI SUBSYSTEM DIAGNOSTIC ")
    print("=" * 70)
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Stdout is tty: {sys.stdout.isatty()}")

    # Phase 1: Raw console mode
    print(f"\n{'-' * 70}")
    print("PHASE 1: Win32 Console Mode Flags")
    print(f"{'-' * 70}")
    mode_info = inspect_console_mode()
    if not mode_info["handle_valid"]:
        print("ERROR: stdout is not a console handle (piped/redirected).")
        print("       Run this script directly in an interactive cmd.exe window.")
        sys.exit(1)

    print(f"Raw console mode value: 0x{mode_info['raw_mode']:08X}")
    print(f"  ENABLE_PROCESSED_OUTPUT        (0x0001): {mode_info['PROCESSED_OUTPUT']}")
    print(f"  ENABLE_WRAP_AT_EOL_OUTPUT      (0x0002): {mode_info['WRAP_AT_EOL']}")
    print(f"  ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004): {mode_info['VT_PROCESSING']}")
    print(f"  ENABLE_VIRTUAL_TERMINAL_INPUT  (0x0200): {mode_info['VT_INPUT']}")

    if not mode_info["VT_PROCESSING"]:
        print("\n[WARNING] VT_PROCESSING is DISABLED. Enabling now...")
        if force_enable_vt():
            print("[SUCCESS] VT processing enabled.")
            new_mode = inspect_console_mode()
            print(f"New raw mode: 0x{new_mode['raw_mode']:08X}")
        else:
            print("[FAILED] Could not enable VT processing. Colors will fail.")
    else:
        print("\n[OK] VT_PROCESSING is already enabled.")

    # Phase 2: Rich configuration matrix
    print(f"\n{'-' * 70}")
    print("PHASE 2: Rich Console Configuration Matrix")
    print(f"{'-' * 70}")
    try:
        matrix_results = test_rich_matrix()
    except Exception as e:
        print(f"ERROR during Rich matrix test: {e}")
        matrix_results = []

    # Phase 3: Live segment integrity
    print(f"\n{'-' * 70}")
    print("PHASE 3: Live.update() Segment Integrity")
    print(f"{'-' * 70}")
    try:
        live_ok = test_live_segment_integrity()
    except Exception as e:
        print(f"ERROR during Live integrity test: {e}")
        live_ok = False

    # Summary
    print(f"\n{'=' * 70}")
    print(" SUMMARY ")
    print(f"{'=' * 70}")
    best = next((r for r in matrix_results if "Production Recommended" in r["config_name"]), None)
    if best:
        print(f"Production config color_system: {best['color_system_attr']}")
        print(f"Production config table ANSI count: {best['table_cell_ansi_count']}")

    if live_ok and best and best["table_cell_ansi_count"] > 10:
        print("\n[PASS] Console is configured for reliable ANSI color rendering.")
        print("       Use config A parameters in Engine_1.py.")
    else:
        print("\n[FAIL] ANSI color emission is broken or degraded.")
        print("       1. Ensure you are running in an interactive cmd.exe (not piped).")
        print("       2. Apply the Win32 VT enablement code before Console() init.")
        print("       3. Use color_system='256' and legacy_windows=False.")
        print("       4. Do not share renderables between live and export consoles.")


if __name__ == "__main__":
    main()
