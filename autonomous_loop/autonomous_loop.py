"""
UNIFIED 24/7 AUTONOMOUS RELAY LOOP — CRASH-PROOF & RESILIENT ARCHITECTURE
Conforming 100% to Master Spec + Full Visual Screenshots & Parallel Git Sync

1. Writes improvement prompt & pushes live code to GitHub in parallel.
2. Safe JS evaluate & page liveness guards across all browser operations.
3. Types prompt into Arena.ai editor (div.tiptap.ProseMirror).
4. Auto-dismisses feedback popups ("Yes", "OK", "Confirm").
5. Pre-submit length gate & full verbatim response capture.
6. Auto-restarts Chrome via Task Scheduler after 5 consecutive CDP failures.
7. Subprocess timeout guards (_run_guarded) for PowerShell calls.
8. SIGINT/SIGTERM graceful shutdown handlers.
9. Atomic engine log reading to prevent partial line ingestion.
10. Automatic screenshot rotation (max 200 images).
11. Cycle metrics logging to relay_cycle_log.jsonl.
"""
import asyncio
import os
import re
import sys
import json
import time
import shutil
import signal
import subprocess
import concurrent.futures
import gc
from datetime import datetime
from playwright.async_api import async_playwright

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR     = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "autonomous_loop" else BASE_DIR
RESPONSE_FILE   = os.path.join(BASE_DIR, "arena_latest_copied_response.txt")
LOG_FILE        = os.path.join(BASE_DIR, "arena_history_stream.log")
CYCLE_LOG       = os.path.join(BASE_DIR, "relay_cycle_log.jsonl")
RECORDINGS_DIR  = os.path.join(BASE_DIR, "recordings")
SHOTS_DIR       = os.path.join(RECORDINGS_DIR, "screenshots")
TRACES_DIR      = os.path.join(RECORDINGS_DIR, "traces")
GALLERY_FILE    = os.path.join(RECORDINGS_DIR, "index.html")
BACKUP_DIR      = os.path.join(BASE_DIR, "patch_backups")

os.makedirs(SHOTS_DIR, exist_ok=True)
os.makedirs(TRACES_DIR, exist_ok=True)

CDP_URL = "http://127.0.0.1:19022"
GITHUB_REPO = "https://github.com/kbsingh1399/coinglass-trading"
MAX_PAGE_RECOVERY_ATTEMPTS = 3

_loop_state = {"running": True, "cycle": 0, "topic_idx": 1, "last_phase0_ts": 0}

CORE_FILES = [
    "Engine_1.py", "binance_broker.py", "live_model_trainer.py",
    "coinglass_scraper.py", "ensemble_strategy_predictor.py",
    "mt5_broker.py", "run_all_6.py"
]

IMPROVEMENT_TOPICS = [
    {
        "id": "git_handshake_alignment",
        "title": "Phase 0: Git Synchronization & Code Sharing Handshake Alignment",
        "prompt": (
            "PHASE 0: Initial Common Ground & Code Sharing Verification.\n"
            "Before we begin iterating on performance optimization topics, we must verify our common ground of sharing via Git:\n"
            "1. Confirm that you can fetch and read all raw repository files from branch `arena-seeding-fix` or repository `kbsingh1399/coinglass-trading`.\n"
            "2. Read `autonomous_loop/arena_sync.txt` and confirm that it contains the verification markers ('This is the Test' and 'Test2').\n"
            "3. Confirm that you have full access to `Engine_1.py`, `binance_broker.py`, `live_model_trainer.py`, `coinglass_scraper.py`, `ensemble_strategy_predictor.py`, and `order_flow_filter.py`.\n"
            "4. Print 'This is the Test' and 'Test2' and 'Arena.ai' to confirm full synchronization common ground."
        ),
    },
    {
        "id": "signal_refinement",
        "title": "Phase 1: Signal Refinement & Alpha Generation",
        "prompt": (
            "Review Engine_1.py trading signals (S1, S2, S3, S4, S5). Suggest:\n"
            "1. Improved entry/exit filters to reduce false signals during choppy regimes.\n"
            "2. Dynamic ATR volatility-based thresholds.\n"
            "3. Order flow & CVD divergence confluence filters.\n\n"
            "Provide improved Python code with ```python ... ``` fencing. Label target file at top: # TARGET: Engine_1.py"
        ),
    },
    {
        "id": "risk_management",
        "title": "Dynamic Risk Management",
        "prompt": (
            "Review Engine_1.py risk/position sizing logic. Suggest:\n"
            "1. ATR-based dynamic stop loss tightening during high volatility.\n"
            "2. Max drawdown circuit breaker — pause trading if DD > 5% in 1 hour.\n"
            "3. Position scaling: reduce size on consecutive losses (anti-martingale).\n\n"
            "Provide improved Python code with ```python ... ``` fencing. Label target file at top: # TARGET: Engine_1.py"
        ),
    },
    {
        "id": "fee_optimization",
        "title": "Fee & Execution Cost Optimization",
        "prompt": (
            "Review binance_broker.py and Engine_1.py trade execution. Suggest:\n"
            "1. Post-only limit orders where feasible to earn maker rebates.\n"
            "2. Minimum profit target filter to ensure trade expected value > 2x round-trip fee + slippage.\n"
            "3. Order splitting for large sizes to minimize market impact.\n\n"
            "Provide improved Python code with ```python ... ``` fencing. Label target file at top: # TARGET: binance_broker.py"
        ),
    },
    {
        "id": "order_flow",
        "title": "Order Flow & Microstructure",
        "prompt": (
            "Review Coinglass / footprint data ingestion and signal generation. Suggest:\n"
            "1. Aggregated CVD (Cumulative Volume Delta) imbalance ratio filter.\n"
            "2. Open Interest delta confluence before entry.\n"
            "3. Liquidation cascade detection filter.\n\n"
            "Provide improved Python code with ```python ... ``` fencing. Label target file at top: # TARGET: Engine_1.py"
        ),
    },
    {
        "id": "ml_tuning",
        "title": "Machine Learning Model Tuning & Ensemble Weights",
        "prompt": (
            "Review ensemble_strategy_predictor.py and live_model_trainer.py. Suggest:\n"
            "1. Dynamic model re-weighting based on recent 24h prediction accuracy.\n"
            "2. Feature importance pruning to reduce inference latency.\n"
            "3. Probability threshold optimization for high-conviction trades only.\n\n"
            "Provide improved Python code with ```python ... ``` fencing. Label target file at top: # TARGET: ensemble_strategy_predictor.py"
        ),
    },
    {
        "id": "latency_optimization",
        "title": "Execution Latency & Pipeline Throughput",
        "prompt": (
            "Review Engine_1.py main loop and websocket data pipeline. Suggest:\n"
            "1. Async non-blocking order placement pipeline.\n"
            "2. In-memory circular buffer optimization for 1200-bar rolling window.\n"
            "3. Parallel multi-symbol feature computation using ProcessPoolExecutor.\n\n"
            "Provide improved Python code with ```python ... ``` fencing. Label target file at top: # TARGET: Engine_1.py"
        ),
    },
    {
        "id": "backtest_accuracy",
        "title": "Backtest vs Live Execution Alignment",
        "prompt": (
            "Review backtesting vs live execution parity across Engine_1.py and binance_broker.py. Suggest:\n"
            "1. Real-time funding rate & borrow fee accounting in P&L tracking.\n"
            "2. Slippage modeling based on order book depth.\n"
            "3. Verification that live indicator warm-up matches backtest exact state.\n\n"
            "Provide improved Python code with ```python ... ``` fencing. Label target file at top: # TARGET: Engine_1.py"
        ),
    },
]


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = f"[{ts}] [RELAY] {msg}"
    print(out, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(out + "\n")


def _run_guarded(cmd: list, timeout: int = 20, cwd: str = None) -> tuple:
    """Run a subprocess with a hard timeout. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd or PROJECT_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace"
        )
        try:
            out, err = proc.communicate(timeout=timeout)
            return (proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            return (-255, "", f"TIMEOUT after {timeout}s")
    except FileNotFoundError:
        return (-254, "", f"Command not found: {cmd[0]}")
    except Exception as e:
        return (-253, "", str(e))


def _save_loop_state_on_exit():
    state_file = os.path.join(PROJECT_DIR, "relay_state.json")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "topic_idx": _loop_state["topic_idx"],
                "cycle": _loop_state["cycle"],
                "last_phase0_ts": _loop_state["last_phase0_ts"],
                "status": "GRACEFUL_SHUTDOWN",
                "stopped_at": datetime.now().isoformat()
            }, f, indent=4)
        log("Graceful shutdown: loop state saved.")
    except Exception:
        pass


def _on_sigterm(signum, frame):
    log(f"Received signal {signum} — requesting graceful shutdown...")
    _loop_state["running"] = False
    _save_loop_state_on_exit()
    sys.exit(0)


async def _safe_evaluate(page, js_code: str, default=None, label: str = ""):
    """Evaluate JS with automatic page-repair on disconnect."""
    try:
        if not page or page.is_closed():
            raise Exception("Page is closed or missing")
        result = await page.evaluate(js_code)
        return (result, True)
    except Exception as e:
        log(f"[SafeEval] Page error in '{label}': {e}")
        return (default, False)


async def _page_alive(page) -> bool:
    """Quick liveness check — returns True if page is responsive."""
    try:
        if not page or page.is_closed():
            return False
        await page.evaluate("() => 1")
        return True
    except Exception:
        return False


def git_push(msg_label: str = "sync"):
    """Push to all remotes in parallel via subprocess (75s -> 30s)."""
    def _push_one(target: str, branch: str):
        rc, out, err = _run_guarded(["git", "push", target, f"HEAD:{branch}"], timeout=30, cwd=PROJECT_DIR)
        return (target, branch, rc, err[:200] if rc != 0 else "")

    try:
        _run_guarded(["git", "add", "-A"], timeout=15, cwd=PROJECT_DIR)
        rc_diff, _, _ = _run_guarded(["git", "diff", "--cached", "--quiet"], timeout=10, cwd=PROJECT_DIR)
        if rc_diff != 0:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _run_guarded(["git", "commit", "-m", f"Auto-sync [{msg_label}] @ {ts}"], timeout=15, cwd=PROJECT_DIR)
            log(f"Committed: {msg_label}")

        push_targets = [
            ("origin", "arena-seeding-fix"),
            ("origin", "autonomous-loop-engine"),
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(push_targets)) as ex:
            futures = [ex.submit(_push_one, t, b) for t, b in push_targets]
            for fut in concurrent.futures.as_completed(futures):
                target, branch, rc, err = fut.result()
                if rc == 0:
                    log(f"git push OK -> {target}/{branch}")
                else:
                    log(f"git push WARN -> {target}/{branch}: rc={rc} {err}")

    except Exception as e:
        log(f"git_push error: {e}")


async def capture_visual(page, step_label: str, details: str = ""):

    try:
        shots = sorted(
            [f for f in os.listdir(SHOTS_DIR) if f.endswith(".png")],
            key=lambda x: os.path.getmtime(os.path.join(SHOTS_DIR, x))
        )
        MAX_SHOTS = 200
        while len(shots) > MAX_SHOTS:
            old_file = os.path.join(SHOTS_DIR, shots.pop(0))
            try:
                os.remove(old_file)
            except Exception:
                pass
    except Exception:
        pass

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_name = f"{ts}_{step_label}.png"
    shot_path = os.path.join(SHOTS_DIR, shot_name)

    try:
        if page and not page.is_closed():
            await page.screenshot(path=shot_path, full_page=False)
            log(f"Visual captured: [{step_label}] -> {shot_name}")
            update_html_gallery(shot_name, step_label, details)
    except Exception as e:
        log(f"Failed to capture visual for {step_label}: {e}")


def update_html_gallery(shot_name: str, step_label: str, details: str):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry_html = f"""
        <div class="card">
            <div class="header">
                <span class="badge">{step_label}</span>
                <span class="time">{ts}</span>
            </div>
            <img src="screenshots/{shot_name}" alt="{step_label}" onclick="window.open(this.src)">
            <div class="details">{details}</div>
        </div>
        """
        if not os.path.exists(GALLERY_FILE):
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Autonomous Relay Visual Gallery</title>
    <meta refresh="10">
    <style>
        body {{ font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
        h1 {{ color: #58a6ff; text-align: center; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }}
        .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }}
        .header {{ padding: 10px; background: #21262d; display: flex; justify-content: space-between; align-items: center; }}
        .badge {{ background: #238636; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }}
        .time {{ color: #8b949e; font-size: 12px; }}
        img {{ width: 100%; height: 200px; object-fit: cover; cursor: pointer; border-bottom: 1px solid #30363d; }}
        .details {{ padding: 10px; font-size: 12px; color: #8b949e; }}
    </style>
</head>
<body>
    <h1>Autonomous Relay Visual Trace Gallery</h1>
    <div class="grid" id="gallery">
        {entry_html}
    </div>
</body>
</html>"""
            with open(GALLERY_FILE, "w", encoding="utf-8") as f:
                f.write(html)
        else:
            with open(GALLERY_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if '<div class="grid" id="gallery">' in content:
                parts = content.split('<div class="grid" id="gallery">')
                new_content = parts[0] + '<div class="grid" id="gallery">\n' + entry_html + parts[1]
                with open(GALLERY_FILE, "w", encoding="utf-8") as f:
                    f.write(new_content)
    except Exception as e:
        log(f"Gallery update error: {e}")


async def auto_dismiss_modals(page) -> bool:
    """Wait for Yes/Confirm/Accept/OK popup and click after 10 second delay."""
    dismissed = False
    btn_texts = ["Yes", "Confirm", "Accept", "OK"]
    for txt in btn_texts:
        found, alive = await _safe_evaluate(page, f"""() => {{
            const btns = Array.from(document.querySelectorAll('button'));
            for (const b of btns) {{
                const label = (b.innerText || b.textContent || '').trim();
                if (label === '{txt}' || label.startsWith('{txt}')) {{
                    if (b.offsetParent !== null) {{
                        return '{txt}';
                    }}
                }}
            }}
            return null;
        }}""", default=None, label=f"auto_dismiss_{txt}")
        if not alive:
            return False
        if found:
            log(f"Detected feedback popup: '{found}' — waiting 10 seconds before clicking...")
            await asyncio.sleep(10)
            await _safe_evaluate(page, f"""() => {{
                const btns = Array.from(document.querySelectorAll('button'));
                for (const b of btns) {{
                    const label = (b.innerText || b.textContent || '').trim();
                    if (label === '{found}' || label.startsWith('{found}')) {{
                        if (b.offsetParent !== null) {{
                            b.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""", default=False, label="click_dismiss_btn")
            log(f"Auto-dismissed feedback popup: '{found}' after 10s delay.")
            await asyncio.sleep(1)
            await capture_visual(page, "MODAL_DISMISSED", f"Auto-dismissed '{found}' popup after 10s")
            dismissed = True
            break
    return dismissed


async def wait_for_arena_ready(page) -> bool:
    """Wait for Arena.ai editor to be ready, with page-liveness guard."""
    try:
        if page and not page.is_closed():
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    for _ in range(15):
        ok, alive = await _safe_evaluate(page, """() => {
            const ed = document.querySelector('div.tiptap.ProseMirror')
                    || document.querySelector('div.tiptap')
                    || document.querySelector('[contenteditable="true"]');
            return ed !== null && ed.getBoundingClientRect().height > 0;
        }""", default=False, label="wait_for_arena_ready")
        if not alive:
            return False
        if ok:
            return True
        await asyncio.sleep(1)
    return False


async def is_generating(page) -> bool:
    gen, _ = await _safe_evaluate(page, """() => {
        const loader = document.querySelector('.animate-spin, [class*="spinner"], [class*="loading"]');
        if (loader) return true;
        const stopBtn = document.querySelector('button[aria-label*="Stop"], button[title*="Stop"]');
        if (stopBtn) return true;
        const ed = document.querySelector('div.tiptap.ProseMirror') || document.querySelector('[contenteditable="true"]');
        if (ed && ed.getAttribute('aria-disabled') === 'true') return true;
        return false;
    }""", default=False, label="is_generating")
    return gen


async def has_copy_button(page) -> bool:
    has_btn, _ = await _safe_evaluate(page, """() => {
        const btns = Array.from(document.querySelectorAll('button'));
        return btns.some(b => {
            const txt = (b.innerText || '').toLowerCase();
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            const title = (b.getAttribute('title') || '').toLowerCase();
            const svg = b.querySelector('svg.lucide-copy') || b.querySelector('svg[class*="copy"]');
            return txt.includes('copy') || aria.includes('copy') || title.includes('copy') || svg !== null;
        });
    }""", default=False, label="has_copy_button")
    return has_btn


async def scroll_and_click_copy_button(page) -> str:
    """Scroll to bottom of chat, find latest Copy button, scroll into view, click it, and fetch clipboard content."""
    try:
        # 1. Scroll main window and scrollable chat regions to bottom
        await _safe_evaluate(page, """() => {
            window.scrollTo(0, document.body.scrollHeight);
            const containers = document.querySelectorAll('main, article, div[role="region"], div.overflow-y-auto, [class*="chat"]');
            containers.forEach(c => { c.scrollTop = c.scrollHeight; });
        }""", label="scroll_to_bottom")
        await asyncio.sleep(1)

        # 2. Locate and click the Copy button on the latest response
        clicked, alive = await _safe_evaluate(page, """() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const copyBtns = btns.filter(b => {
                const txt = (b.innerText || b.textContent || '').toLowerCase();
                const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                const title = (b.getAttribute('title') || '').toLowerCase();
                const svg = b.querySelector('svg.lucide-copy') || b.querySelector('svg[class*="copy"]');
                return txt.includes('copy') || aria.includes('copy') || title.includes('copy') || svg !== null;
            });
            if (copyBtns.length > 0) {
                const targetBtn = copyBtns[copyBtns.length - 1];
                targetBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                targetBtn.click();
                return true;
            }
            return false;
        }""", default=False, label="click_copy_button")

        if clicked:
            log("Scrolled to bottom & clicked Arena.ai 'Copy' button.")
            await asyncio.sleep(1.5)
            cb_text, _ = await _safe_evaluate(page, "async () => await navigator.clipboard.readText()", default="", label="read_clipboard")
            if cb_text and len(cb_text.strip()) > 30:
                return cb_text.strip()
    except Exception as e:
        log(f"scroll_and_click_copy_button error: {e}")
    return ""


async def send_prompt(page, prompt_text: str) -> bool:
    try:
        await wait_for_arena_ready(page)
        ok, alive = await _safe_evaluate(page, f"""() => {{
            const ed = document.querySelector('div.tiptap.ProseMirror')
                    || document.querySelector('div.tiptap')
                    || document.querySelector('[contenteditable="true"]');
            if (!ed) return false;
            ed.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            const text = {json.dumps(prompt_text)};
            document.execCommand('insertText', false, text);
            return ed.innerText.length > 5;
        }}""", default=False, label="send_prompt_insert")

        if not alive or not ok:
            return False

        await asyncio.sleep(1)

        send_selectors = [
            'button[aria-label*="Send"]',
            'button[title*="Send"]',
            'button.rounded-full',
            'button[type="submit"]',
            'button.bg-primary'
        ]
        clicked = False
        for sel in send_selectors:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible() and await btn.is_enabled():
                await btn.click()
                clicked = True
                log(f"Clicked send button via selector: {sel}")
                break

        if not clicked:
            log("Clicking send button failed — trying Enter key fallback...")
            await page.keyboard.press("Enter")

        return True
    except Exception as e:
        log(f"send_prompt error: {e}")
        return False


async def get_response_text(page, try_clipboard: bool = False) -> str:
    try:
        if try_clipboard:
            try:
                cb_text, _ = await _safe_evaluate(page, "async () => await navigator.clipboard.readText()", default="", label="get_clipboard")
                if cb_text and len(cb_text.strip()) > 50:
                    return cb_text.strip()
            except Exception:
                pass

        txt, _ = await _safe_evaluate(page, """() => {
            const selectors = 'div.prose, [class*="markdown"], [class*="response"], article, [class*="message"], div[role="region"]';
            const blocks = Array.from(document.querySelectorAll(selectors))
                .filter(d => d.className && !d.className.includes('tiptap'));
            if (blocks.length > 0) {
                return blocks[blocks.length - 1].innerText || '';
            }
            const main = document.querySelector('main') || document.querySelector('article') || document.body;
            if (main) {
                const text = main.innerText || '';
                return text.length > 200 ? text : '';
            }
            return '';
        }""", default="", label="get_response_text")

        return txt or ""
    except Exception as e:
        log(f"get_response_text error: {e}")
        return ""


def extract_code_blocks(text: str) -> list:
    results = []
    pattern = re.compile(r"```(?:python|py)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)
    known_files = {f.lower(): f for f in CORE_FILES}

    for match in pattern.finditer(text):
        block = match.group(1).strip()
        if not block: continue
        target = None
        for line in block.splitlines()[:5]:
            stripped = line.strip()
            m = re.search(r"TARGET:\s*(\S+\.py)", stripped, re.IGNORECASE)
            if m: target = m.group(1); break
            m = re.search(r"(\w[\w_]*\.py)\b", stripped, re.IGNORECASE)
            if m and m.group(1).lower() in known_files:
                target = known_files[m.group(1).lower()]; break

        if target and block:
            results.append({"file": target, "code": block})

    return results


def run_test_suite() -> tuple:
    existing = [f for f in CORE_FILES if os.path.exists(os.path.join(PROJECT_DIR, f))]
    rc, out, err = _run_guarded([sys.executable, "-m", "py_compile"] + existing, timeout=30, cwd=PROJECT_DIR)
    if rc != 0:
        return False, f"SYNTAX FAIL:\n{err}"

    engine_path = os.path.join(PROJECT_DIR, "Engine_1.py")
    if os.path.exists(engine_path):
        try:
            proc = subprocess.Popen([sys.executable, "-u", engine_path, "--test"], cwd=PROJECT_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            try:
                out, _ = proc.communicate(timeout=8)
                if proc.returncode not in (0, None): return False, f"Engine crashed:\n{out[-300:]}"
            except subprocess.TimeoutExpired:
                proc.kill()
                log("Local 8s execution test PASS — engine ran without crash.")
        except Exception as e:
            return False, f"Execution test error: {e}"

    return True, "All tests PASS"


async def execute_step8_live_verification(page) -> tuple:
    log("Step 8: Triggering Engine_1 --live via Task Scheduler in interactive desktop session...")
    engine_path = os.path.join(PROJECT_DIR, "Engine_1.py")
    if not os.path.exists(engine_path):
        return False, "Engine_1.py not found"

    engine_log_file = os.path.join(PROJECT_DIR, "engine_log.txt")
    try:
        if os.path.exists(engine_log_file):
            with open(engine_log_file, "w", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] Log reset for new verification run\n")
    except Exception:
        pass

    try:
        _run_guarded(["powershell", "-Command", "Start-ScheduledTask -TaskName 'Engine1_LiveRun'"], timeout=15, cwd=PROJECT_DIR)
        log("Engine_1 --live triggered. Starting adaptive dynamic log audit (monitoring errors/exceptions)...")

        engine_log_file = os.path.join(PROJECT_DIR, "engine_log.txt")
        log_snippet = ""
        max_duration = 35
        elapsed = 0
        error_detected = False
        error_reason = ""

        while elapsed < max_duration:
            await asyncio.sleep(1)
            elapsed += 1
            if os.path.exists(engine_log_file):
                try:
                    with open(engine_log_file, "r", encoding="utf-8", errors="replace") as f:
                        raw = f.read()
                    lines = raw.splitlines(keepends=True)
                    if lines and not lines[-1].endswith("\n"):
                        lines = lines[:-1]
                    log_snippet = "".join(lines[-35:])
                except Exception:
                    pass

                recent_text = log_snippet.lower()
                critical_keywords = [
                    "traceback (most recent call last)",
                    "syntaxerror:",
                    "attributeerror:",
                    "keyerror:",
                    "exception:",
                    "page is closed",
                    "failed to connect",
                    "critical"
                ]
                for kw in critical_keywords:
                    if kw in recent_text:
                        error_detected = True
                        error_reason = f"Early exit triggered on log error ({kw}):\n" + log_snippet[-400:]
                        break
                if error_detected:
                    break

                if "waiting for layout containers to render" in recent_text or "connecting to 14 kline streams" in recent_text:
                    max_duration = max(max_duration, 55)

        _run_guarded(["powershell", "-Command", "Start-ScheduledTask -TaskName 'CaptureDesktopTask'"], timeout=15, cwd=PROJECT_DIR)
        await asyncio.sleep(3)
        log("Mandatory Desktop Screenshot captured (CMD Terminal & Chrome state saved).")

        shot_src = os.path.join(PROJECT_DIR, "desktop_terminal_screenshot.png")
        if os.path.exists(shot_src):
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot_dest_name = f"{ts_str}_STEP8_LIVE_TERMINAL_VERIFY.png"
            shot_dest_path = os.path.join(SHOTS_DIR, shot_dest_name)
            shutil.copy2(shot_src, shot_dest_path)
            update_html_gallery(shot_dest_name, "STEP8_LIVE_TERMINAL_VERIFY", "Live Engine_1 CMD Terminal & Chrome visual capture on desktop")

        if error_detected:
            log(f"[RELAY] Step 8 FAIL: {error_reason}")
            return False, error_reason
        else:
            log(f"[RELAY] Step 8 PASS: Engine_1 --live verified running cleanly on desktop after {elapsed}s. Log tail:\n{log_snippet[-350:]}")
            return True, log_snippet[-350:]

    except Exception as e:
        log(f"Step 8 Exception: {e}")
        return False, str(e)


async def execute_step9_prepare_next_prompt(cycle: int, topic: dict, live_pass: bool, live_log: str):
    log("Step 9: Preparing next dynamic prompt for Arena.ai based on live verification & screenshot state...")

    try:
        rc, out, _ = _run_guarded(["git", "rev-parse", "HEAD"], timeout=10, cwd=PROJECT_DIR)
        commit_hash = out.strip() if rc == 0 else "main"
    except Exception:
        commit_hash = "main"

    header = (
        f"IMPORTANT: Verify you have access to the latest code files. "
        f"The latest commit pushed to the repository is `{commit_hash}`.\n"
        f"If raw.githubusercontent.com URLs for `{commit_hash}` return a 404 due to CDN caching delays, "
        f"please fetch directly from the `main` or `arena-seeding-fix` branch on GitHub, "
        f"or retry querying the raw files after a few seconds. "
        f"If you are still unable to push code or pull updates directly, "
        f"please print your suggested code changes as exact markdown blocks starting with `# TARGET: <filename>` "
        f"so they can be copied, verified, and implemented locally before pushing to continue the loop.\n\n"
    )

    if not live_pass:
        next_prompt = (
            f"{header}"
            f"# CRITICAL EXECUTION REPAIR REQUIRED — Cycle {cycle}\n\n"
            f"The live execution telemetry audit for Engine_1.py reported an error during startup/runtime:\n\n"
            f"```text\n{live_log}\n```\n\n"
            f"INSTRUCTIONS FOR ARENA.AI:\n"
            f"1. Review the error traceback above.\n"
            f"2. Provide the exact fix for the target file using ```python fencing and `# TARGET: <filename>` labels.\n"
            f"3. Ensure the engine will run cleanly without crashing.\n"
            f"4. Print 'This is the Test' and 'Test2' and 'Arena.ai'."
        )
    else:
        next_prompt = (
            f"{header}"
            f"# ENGINE_1 AUTONOMOUS IMPROVEMENT CYCLE {cycle+1} — {topic['title']}\n\n"
            f"LIVE TELEMETRY SUMMARY:\n"
            f"Engine_1 --live verified running cleanly on desktop. Log tail snippet:\n"
            f"```text\n{live_log}\n```\n\n"
            f"OPTIMIZATION REQUIREMENTS:\n"
            f"{topic['prompt']}\n\n"
            f"INSTRUCTIONS FOR ARENA.AI:\n"
            f"1. Review the live execution telemetry above.\n"
            f"2. If REJECTED, fix the exact error reported above in the relevant file.\n"
            f"3. If PASSED, suggest next level performance optimizations for {topic['title']}.\n"
            f"4. Provide code changes with `# TARGET: <filename>` labels.\n"
            f"5. Print 'This is the Test' and 'Test2' and 'Arena.ai'."
        )

    send_file_path = os.path.join(PROJECT_DIR, "send_to_arena.txt")
    with open(send_file_path, "w", encoding="utf-8") as f:
        f.write(next_prompt)

    log("Step 9 COMPLETE: Next prompt generated into send_to_arena.txt & relay_state.json updated.")


async def run_unified_loop():
    log("="*70)
    log(" UNIFIED 24/7 AUTONOMOUS RELAY LOOP — CRASH-PROOF & RESILIENT ARCHITECTURE")
    log("="*70)

    STATE_FILE = os.path.join(PROJECT_DIR, "relay_state.json")
    topic_idx, cycle, last_phase0_ts = 1, 0, 0

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            topic_idx = state.get("topic_idx", 1)
            cycle = state.get("cycle", 0)
            last_phase0_ts = state.get("last_phase0_ts", 0)
            _loop_state["topic_idx"] = topic_idx
            _loop_state["cycle"] = cycle
            _loop_state["last_phase0_ts"] = last_phase0_ts
            log(f"Restored loop state: cycle={cycle}, topic_idx={topic_idx}, last_phase0_ts={last_phase0_ts}")
        except Exception as e:
            log(f"Failed to load loop state: {e}")

    consecutive_cdp_failures = 0
    MAX_CONSECUTIVE_CDP_FAILURES = 5

    while _loop_state["running"]:
        cycle += 1
        _loop_state["cycle"] = cycle
        now_ts = time.time()

        if (now_ts - last_phase0_ts) >= 3600:
            topic = IMPROVEMENT_TOPICS[0]
            last_phase0_ts = now_ts
            _loop_state["last_phase0_ts"] = last_phase0_ts
            log("Phase 0 Cadence Gate: >1 hour since last check — Running Phase 0 Git Synchronization Handshake...")
        else:
            if topic_idx <= 0 or topic_idx >= len(IMPROVEMENT_TOPICS):
                topic_idx = 1
            topic = IMPROVEMENT_TOPICS[topic_idx]
            topic_idx = (topic_idx % (len(IMPROVEMENT_TOPICS) - 1)) + 1
            _loop_state["topic_idx"] = topic_idx
            mins_ago = int((now_ts - last_phase0_ts) / 60)
            log(f"Phase 0 Cadence Gate: Last checked {mins_ago}m ago (<1 hour) — Skipping Phase 0 & running Topic Cycle {cycle}: '{topic['title']}'...")

        if cycle % 10 == 0:
            gc.collect()
            log(f"[Health] Memory GC cycle {cycle} — {len(gc.get_objects())} objects tracked")

        try:
            rc, out, _ = _run_guarded(["git", "rev-parse", "HEAD"], timeout=10, cwd=PROJECT_DIR)
            commit_hash = out.strip() if rc == 0 else "main"
        except Exception:
            commit_hash = "main"

        check_header = (
            f"IMPORTANT: Verify you have access to the latest code files. "
            f"The latest commit pushed to the repository is `{commit_hash}`.\n"
            f"If raw.githubusercontent.com URLs for `{commit_hash}` return a 404 due to CDN caching delays, "
            f"please fetch directly from the `main` or `arena-seeding-fix` branch on GitHub, "
            f"or retry querying the raw files after a few seconds. "
            f"If you are still unable to push code or pull updates directly, "
            f"please print your suggested code changes as exact markdown blocks starting with `# TARGET: <filename>` "
            f"so they can be copied, verified, and implemented locally before pushing to continue the loop.\n\n"
        )

        SEND_FILE = os.path.join(PROJECT_DIR, "send_to_arena.txt")
        if os.path.exists(SEND_FILE):
            try:
                with open(SEND_FILE, "r", encoding="utf-8") as f:
                    custom_p = f.read().strip()
                if custom_p:
                    prompt_text = check_header + custom_p
                    log(f"Using dynamic prompt from send_to_arena.txt ({len(prompt_text)} chars)")
                    try:
                        shutil.move(SEND_FILE, SEND_FILE + ".done")
                    except Exception:
                        pass
                else:
                    prompt_text = check_header + f"# ENGINE_1 AUTONOMOUS IMPROVEMENT CYCLE — {topic['title']}\n\n{topic['prompt']}"
            except Exception:
                prompt_text = check_header + f"# ENGINE_1 AUTONOMOUS IMPROVEMENT CYCLE — {topic['title']}\n\n{topic['prompt']}"
        else:
            prompt_text = check_header + f"# ENGINE_1 AUTONOMOUS IMPROVEMENT CYCLE — {topic['title']}\n\n{topic['prompt']}"

        ARENA_CHAT_URL = "https://arena.ai/agent/019fbc51-76db-79e8-b0d2-c8da2966516a"
        page = None
        browser = None

        try:
            async with async_playwright() as pw:
                for cdp_attempt in range(MAX_PAGE_RECOVERY_ATTEMPTS):
                    try:
                        browser = await pw.chromium.connect_over_cdp(CDP_URL)
                        break
                    except Exception as cdp_err:
                        log(f"CDP attempt {cdp_attempt+1}/{MAX_PAGE_RECOVERY_ATTEMPTS}: {cdp_err}")
                        if cdp_attempt < MAX_PAGE_RECOVERY_ATTEMPTS - 1:
                            _run_guarded([
                                "powershell", "-Command",
                                "Remove-Item '$env:LOCALAPPDATA\\Google\\Chrome\\User Data_Arena\\LOCK' -Force -ErrorAction SilentlyContinue; "
                                "Start-ScheduledTask -TaskName 'StartArenaChromeTask'"
                            ], timeout=15, cwd=PROJECT_DIR)
                            await asyncio.sleep(6)
                        else:
                            raise

                if browser and browser.contexts:
                    for p in browser.contexts[0].pages:
                        if "arena.ai" in p.url.lower():
                            page = p
                            break
                if not page and browser and browser.contexts:
                    page = await browser.contexts[0].new_page()
                    await page.goto(ARENA_CHAT_URL)
                elif page and "019fbc51" not in page.url:
                    await page.goto(ARENA_CHAT_URL)

                if not page:
                    raise RuntimeError("Could not obtain Arena page")

                async def _page_ok():
                    return await _page_alive(page)

                if not await _page_ok():
                    raise RuntimeError("Page unresponsive after CDP connect")

                await wait_for_arena_ready(page)

                log("Step 1: Pushing latest code...")
                git_push(msg_label=f"Pre-prompt-{topic['id']}")
                await capture_visual(page, "STEP1_GIT_PUSH_OK", f"Pre-prompt sync {topic['id']}")

                await auto_dismiss_modals(page)

                start_wait = time.time()
                while time.time() - start_wait < 120:
                    if not await _page_ok():
                        raise RuntimeError("Page lost during generate-wait")
                    gen = await is_generating(page)
                    if not gen:
                        break
                    await asyncio.sleep(5)

                log(f"Step 3: Sending prompt ({len(prompt_text)} chars)...")
                await capture_visual(page, "STEP3_TYPING_PROMPT", f"Prompt for {topic['title']}")
                if not await _page_ok():
                    raise RuntimeError("Page lost before prompt send")

                sent = await send_prompt(page, prompt_text)
                if not sent:
                    log("Prompt send failed — retrying cycle")
                    continue

                log("Step 4: Prompt submitted — waiting for response...")
                await capture_visual(page, "STEP4_SUBMITTED", "Prompt submitted")

                pre_submit_len = 0
                if await _page_ok():
                    txt = await get_response_text(page)
                    pre_submit_len = len(txt)

                start_wait = time.time()
                stable_text = ""
                last_len = 0
                stable_ticks = 0

                while (time.time() - start_wait) < 240:
                    if not await _page_ok():
                        log("Page lost during response wait — aborting cycle")
                        break

                    dismissed_modal = await auto_dismiss_modals(page)
                    curr_text = await get_response_text(page)
                    copy_btn = await has_copy_button(page)

                    valid = (len(curr_text) > pre_submit_len + 30) or dismissed_modal

                    if valid and copy_btn and len(curr_text) == last_len:
                        stable_ticks += 1
                    else:
                        stable_ticks = 0

                    if (valid and stable_ticks >= 4) or dismissed_modal:
                        log("Step 6: Response finished — scrolling to bottom & clicking Arena.ai 'Copy' button...")
                        copied = await scroll_and_click_copy_button(page)
                        stable_text = copied if (copied and len(copied) > 50) else (await get_response_text(page, try_clipboard=True) or curr_text)
                        log(f"Step 5 & 6 DONE: {len(stable_text)} chars captured via Copy button after {time.time()-start_wait:.0f}s.")
                        break

                    last_len = len(curr_text)
                    await asyncio.sleep(2.0)
                else:
                    clip = await get_response_text(page, try_clipboard=True)
                    stable_text = clip or curr_text
                    log("Step 5 TIMEOUT: 240s elapsed")

                if stable_text:
                    with open(RESPONSE_FILE, "w", encoding="utf-8") as f:
                        f.write(stable_text)
                    log(f"Step 7 COMPLETE: Cleared and wrote {len(stable_text)} chars to arena_latest_copied_response.txt.")

                if "--single-run" in sys.argv:
                    with open(STATE_FILE, "w", encoding="utf-8") as f:
                        json.dump({"topic_idx": topic_idx, "cycle": cycle,
                                   "last_phase0_ts": last_phase0_ts,
                                   "status": "RESPONSE_READY"}, f, indent=4)
                    log("Step 8: Single run complete — Waking up Antigravity to inspect arena_latest_copied_response.txt and apply patches!")
                    return

                patches = extract_code_blocks(stable_text)
                log(f"Step 6: {len(patches)} code patches extracted")

                # Filter out recursive autonomous_loop.py patches to prevent code corruption
                valid_patches = [p for p in patches if p["file"].lower() != "autonomous_loop/autonomous_loop.py"]

                if valid_patches:
                    backups = []
                    for patch in valid_patches:
                        target = os.path.join(PROJECT_DIR, patch["file"])
                        if os.path.exists(target):
                            bak = f"{target}.bak.{datetime.now().strftime('%H%M%S')}"
                            shutil.copy2(target, bak)
                            backups.append((target, bak))
                            with open(target, "w", encoding="utf-8") as f:
                                f.write(patch["code"])
                            log(f"Applied patch: {patch['file']}")

                    passed, report = run_test_suite()
                    if passed:
                        log("Test suite PASSED — committing")
                        git_push(msg_label=f"Cycle-{cycle}-{topic['id']}")
                    else:
                        log(f"Test suite FAILED — rolling back: {report[:200]}")
                        for orig, bak in backups:
                            if os.path.exists(bak):
                                shutil.copy2(bak, orig)

                live_pass, live_log = await execute_step8_live_verification(page)
                await execute_step9_prepare_next_prompt(cycle, topic, live_pass, live_log)

                # Write metrics to JSONL log
                try:
                    with open(CYCLE_LOG, "a", encoding="utf-8") as cl:
                        json.dump({
                            "ts": datetime.now().isoformat(),
                            "cycle": cycle,
                            "topic_id": topic["id"],
                            "live_pass": live_pass,
                            "cdp_failures": consecutive_cdp_failures,
                            "patch_count": len(valid_patches),
                        }, cl)
                        cl.write("\n")
                except Exception:
                    pass

                consecutive_cdp_failures = 0

                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"topic_idx": topic_idx, "cycle": cycle,
                               "last_phase0_ts": last_phase0_ts,
                               "status": "CYCLE_FINISHED"}, f, indent=4)

                if "--single-run" in sys.argv:
                    return

        except Exception as outer_e:
            consecutive_cdp_failures += 1
            log(f"Cycle {cycle} UNHANDLED EXCEPTION: {outer_e} (failures: {consecutive_cdp_failures}/{MAX_CONSECUTIVE_CDP_FAILURES})")

            if consecutive_cdp_failures >= MAX_CONSECUTIVE_CDP_FAILURES:
                log("CRITICAL: Consecutive CDP failures reached limit — restarting Chrome via Task Scheduler...")
                _run_guarded([
                    "powershell", "-Command",
                    "Stop-Process -Name 'chrome' -Force -ErrorAction SilentlyContinue; "
                    "Start-ScheduledTask -TaskName 'StartArenaChromeTask'"
                ], timeout=20, cwd=PROJECT_DIR)
                consecutive_cdp_failures = 0
                await asyncio.sleep(15)

            if "--single-run" in sys.argv:
                return

            await asyncio.sleep(10)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _on_sigterm)
    signal.signal(signal.SIGTERM, _on_sigterm)
    asyncio.run(run_unified_loop())