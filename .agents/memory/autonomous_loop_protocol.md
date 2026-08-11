# Autonomous Loop Standard Protocol

> **STATUS: MANDATORY** — Every cycle of the autonomous loop MUST follow all 13 steps in order. No step may be skipped.

---

## Global Mandatory Tools (Always Active)

### /orchestrate — ALWAYS
- Every complex code task, review, or multi-file change MUST be handled via `/orchestrate`.
- Minimum 3 specialist agents required per orchestration (e.g. `backend-specialist` + `security-auditor` + `test-engineer`).
- Two-phase: PHASE 1 planning only → user approval gate → PHASE 2 parallel implementation.
- Never code directly without first routing through the orchestration protocol.

### /code-review-graph — ALWAYS
- Before ANY code patch is applied to `Engine_1.py`, `ensemble_strategy_predictor.py`, `binance_broker.py`, or `live_model_trainer.py`:
  1. Run `get_impact_radius` on changed function/class to compute blast radius
  2. Run `detect_changes` to get risk scores on all uncommitted changes
  3. Run `semantic_search_nodes` to locate callers/dependents before editing
- Graph query MUST precede every file read or edit. No exceptions.
- Tool priority: `code-review-graph` MCP → grep/glob → file read (fallback only)

---

## The 13-Step Protocol

### STEP 1 — Git Code Synchronization
Antigravity executes `git push` to sync the latest codebase to both GitHub remotes:
- `origin/autonomous-loop-engine`
- `origin/arena-seeding-fix`

### STEP 2 — Dynamic Prompt Generation
Antigravity writes the tailored improvement prompt to `send_to_arena.txt`.

**MANDATORY INSTRUCTION in every prompt:**
> "STRICT VERIFICATION REQUIREMENT: Any code changes, enhancements, or architectural modifications you suggest MUST be thoroughly verified, locally run, and strictly backtested on historic market data before sharing with us. Only share high-confidence, fully verified code blocks."

### STEP 3 — Trigger Autonomous Runner
Antigravity executes:
```
python -u autonomous_loop/autonomous_loop.py --single-run
```

### STEP 4 — Prompt Injection & Submission
`autonomous_loop` reads `send_to_arena.txt`, injects the prompt into Arena.ai's TipTap editor via Playwright, and clicks the Send button.
- **Target URL:** `https://arena.ai/agent/019fbc51-76db-79e8-b0d2-c8da2966516a`

### STEP 5 — Modal Feedback Dismissal
`autonomous_loop` monitors generation and waits for the "Yes" button to appear. Once it appears, waits 10 seconds and clicks "Yes".

### STEP 6 — Auto-Scroll & Copy Response
`autonomous_loop` auto-scrolls all chat containers (`scrollTop = scrollHeight + 10000`) to the absolute bottom and clicks the last visible Copy button.

### STEP 7 — Verbatim File Writing
`autonomous_loop` clears `autonomous_loop/arena_latest_copied_response.txt` and writes the full copied response verbatim.

### STEP 8 — Handshake & Antigravity Wakeup
`autonomous_loop` updates `relay_state.json` with `status: RESPONSE_READY` and exits so Antigravity takes over.

### STEP 9 — Code Patching & Compilation

**PRE-PATCH: Run `/code-review-graph` blast radius analysis FIRST:**
```
→ get_impact_radius on every function being patched
→ detect_changes to risk-score all pending edits
→ semantic_search_nodes to verify no callers will break
```

Then Antigravity reads `arena_latest_copied_response.txt`, applies code patches to the relevant engine files via `/orchestrate` (backend-specialist + security-auditor + test-engineer), and verifies via:
```
python -m py_compile Engine_1.py ensemble_strategy_predictor.py binance_broker.py live_model_trainer.py
```
Zero errors required before proceeding.

### STEP 10 — Engine_1 Live Launch (VISIBLE DESKTOP TERMINAL ONLY)

> 🔴 **STRICT PROTOCOL RULE — NEVER RUN IN SANDBOX / SUBPROCESS:**
> Engine_1 MUST ALWAYS be launched in the user's visible interactive Desktop terminal via `C:\Users\SIGMA\Desktop\Engine1_Live.bat`.
> NEVER launch `Engine_1.py` as an agent background task, subagent process, or headless sandbox. The user must see the green live terminal running on their desktop at all times.

**STEP 10.0 — Kill Existing Instances (SELECTIVE CLEANUP — PROTECT RELAY CHROME):**
Before any launch, kill existing Engine_1 instances to prevent port conflicts and file-lock clashes.
> 🔴 **CRITICAL RULE — PRESERVE RELAY CHROME:**
> NEVER kill Chrome processes listening on port 19022 / 19222 (Arena.ai Relay session).
> ONLY target Engine_1's Python processes and Coinglass Chrome on port 9223:

```powershell
# Target Engine_1 Python processes specifically
Get-WmiObject Win32_Process -Filter "name='python.exe' and commandline like '%Engine_1.py%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# Target Engine_1's Coinglass Chrome on port 9223 ONLY (Preserves Relay Chrome on port 19022 / 19222)
Get-WmiObject Win32_Process -Filter "name='chrome.exe' and commandline like '%9223%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
```
Wait 3 seconds after kill for sockets and file handles to release.

**STEP 10.1 — Launch via Task Scheduler in Interactive Session 1:**
```powershell
$nextMin = (Get-Date).AddMinutes(1).ToString("HH:mm")
schtasks /Delete /TN "Engine1LiveRun" /F
schtasks /Create /TN "Engine1LiveRun" /TR "C:\Users\SIGMA\Desktop\Engine1_Live.bat" /SC ONCE /ST $nextMin /RU "SIGMA" /IT /F
schtasks /Run /TN "Engine1LiveRun"
```
The `/IT` flag ensures `Engine1_Live.bat` launches in the user's interactive Session 1 (visible desktop).
**STEP 10.1b — Dynamic Argument Verification Strategy:**
To optimize verification times, the loop dynamically updates the command line arguments in `autonomous_loop/live_cmd_args.txt` (which is read by `run_engine1_live.ps1` during startup):

| Patched File Types | Skipped Phases | Arguments | Time Saved |
|--------------------|----------------|-----------|------------|
| **Training Only** (`live_model_trainer.py`) | Skip Seeding | `--skip-seed` | Saves ~5 mins |
| **UI, Risk, or Connection** (`Engine_1.py`, `binance_broker.py`, `ensemble_strategy_predictor.py`) | Skip Seeding & Training | `--skip-seed --skip-train` | Saves ~15 mins |
| **Fallback / Combined / None** | Skip Seeding | `--skip-seed` | Saves ~5 mins |

*Note: Once verification passes cleanly (the log has no errors and connects successfully), `live_cmd_args.txt` is cleared to execute the **full pipeline** (no skip flags) in the live market.*

### STEP 10.2 — Set TIMER 1 (300s / 5 min, or dynamically shorter if training/seeding is skipped) — wait for seeding phase or initial connection to complete.

### STEP 10.3 — When TIMER 1 fires — apply the Dynamic Log-Check Gate:

#### 🔴 DYNAMIC LOG-CHECK GATE (MANDATORY DECISION POINT)

Audit `engine_log.txt` and check running processes:

| State / Condition | Action |
|-------------------|--------|
| **Errors found** (`ERROR`, `EXCEPTION`, `refit failed`, `WARN`) | → Write error-focused Arena prompt immediately. Proceed to Step 12. |
| **Still Retraining** (active CPU use on `Engine_1.py` python.exe process, log at Step 4/5) | → **Escalate Timer**: Set next timer to **10 minutes** (Timer 3), then **15 minutes** (Timer 4), then **20 minutes** (Timer 5), then **30 minutes** (Timer 6) until training is complete. |
| **Training Complete & Warm-up Active** (seeding complete, no errors, warm-up gate active) | → **Live Warm-up Timer**: Set a **15-minute timer** (or proceed with escalating intervals) to allow the full live evaluation loop to activate. |
| **Live Loop Confirmed Active** (live signal evaluation active in terminal) | → **Live Trading Watch**: Proceed to Step 11 screenshot, then transition to **Phase 2 (30-minute watch timer)** to monitor live market trades. |

**Only after the live loop is confirmed active in the terminal -> proceed to Step 11 screenshot.**

---

**PYTHON EXECUTABLE:** Always use `.venv`:
```
C:\Users\SIGMA\Documents\Project - Coinglass Trading\.venv\Scripts\python.exe
```

**BAT LAUNCHER:** `C:\Users\SIGMA\Desktop\Engine1_Live.bat`

### STEP 11 — Terminal Screenshot & Anomaly Audit

**MANDATORY GATE — DO NOT SKIP:**

After the 5-minute timer fires:
1. Take a desktop screenshot of the "Engine_1 Live Run" terminal window
2. Audit the screenshot for:
   - All 14 symbols showing `[OK]` seeding confirmation
   - No `ERROR`, `WARN`, or `EXCEPTION` lines
   - `close`, `vol`, `funding` values populated for all symbols
   - Live loop cycle timestamps incrementing
   - No stale/frozen timestamps
3. **Only proceed to Step 12 after screenshot is taken and analyzed.**

### STEP 12 — Telemetry Analysis & Next Prompt Selection

**Prompt Construction Rule (MANDATORY):**

The next Arena prompt MUST be built by combining BOTH sources:

| Source | Always? | How to Use |
|--------|---------|------------|
| **User verbal input** (e.g. "also check if retraining is happening") | Optional — only when user provides it | Take verbatim as a required focus area and weave into prompt |
| **Antigravity log/terminal analysis** (engine_log.txt tail + terminal screenshot) | Always — every cycle | Identify anomalies, bottlenecks, stalled phases, missing symbols, errors |

**When user gives input:** Combine their observation with your own log analysis into a single unified prompt.
**When user gives no input:** Rely entirely on log/terminal analysis to identify the highest-priority issue for the next prompt.

Write the combined prompt to `send_to_arena.txt` targeting specific files and functions, always including the STRICT VERIFICATION REQUIREMENT.

### STEP 13 — Git Commit & Push + Loop Continuation
1. Commit all verified patches:
   ```
   git add -A && git commit -m "feat(...): <description>"
   git push origin autonomous-loop-engine
   git push origin HEAD:arena-seeding-fix
   ```
2. Write next prompt to `send_to_arena.txt`
3. Return to **Step 3** — trigger `autonomous_loop.py --single-run` to continue the 24/7 loop

---

## Key Rules

| Rule | Detail |
|------|--------|
| **`/orchestrate` always** | ALL complex tasks use `/orchestrate` with minimum 3 agents — never code directly |
| **`/code-review-graph` always** | Query blast radius via MCP BEFORE any file edit — graph-first, grep as fallback |
| **Python executable** | Always `.venv\Scripts\python.exe` — NEVER system `python.exe` (WindowsApps stub) |
| **Engine_1 window** | Must be visible in user desktop Session 1, launched via Task Scheduler `/IT` flag |
| **Terminal wait** | MANDATORY 300s wait after launch before screenshot |
| **Screenshot gate** | MANDATORY — no next prompt until terminal is screenshotted and audited |
| **Backtest directive** | EVERY Arena prompt must include strict verification + backtesting requirement |
| **Git push** | BOTH remotes after every patch: `autonomous-loop-engine` AND `arena-seeding-fix` |
| **Compilation check** | ALWAYS run `python -m py_compile` on all patched files before live launch |
| **No Background Task Timers** | NEVER use `schedule` (timers) to wait for a background task or script (like `autonomous_loop.py`) to finish. The system automatically resumes execution when tasks complete. Stop calling tools and wait for the system wakeup. |

---

## Arena Target
- **URL:** `https://arena.ai/agent/019fbc51-76db-79e8-b0d2-c8da2966516a`
- **Model:** ML_Strategy_Optimization agent

## File Locations
- **Prompt file:** `send_to_arena.txt`
- **Response file:** `autonomous_loop/arena_latest_copied_response.txt`
- **Relay state:** `autonomous_loop/relay_state.json`
- **Engine log:** `engine_log.txt`
- **Trade log:** `Engine_1_trade_logs.json`
- **Bat launcher:** `C:\Users\SIGMA\Desktop\Engine1_Live.bat`

---

## PHASE 2 — Live Trade Watch (Full Trading Surveillance)

> **Antigravity takes full charge of live trading. Beyond startup auditing — ongoing monitoring of actual trades, PnL, fill quality, and live market anomalies. Autonomous decisions to surface issues to Arena.ai.**

### When to Activate

After Engine_1 warm-up gate clears and live evaluation loop is confirmed active (Step 11 terminal confirmed), let it run **uninterrupted for minimum 30 minutes** before any analysis or restart.

### Step A — Live Trade Log Audit (`Engine_1_trade_logs.json`)

After 30 minutes of live runtime, analyze the `trades` array for:

| Metric | Anomaly Threshold | Action |
|--------|------------------|--------|
| Fill rate (filled / attempted) | < 70% | FLAG → Arena.ai prompt on GTX fill rate |
| SL hit rate (SL exits / total) | > 70% | FLAG → Strategy not profitable |
| TP hit rate | < 10% in 60 min | FLAG → Targets too far or bad entry timing |
| Trades per symbol | 0 after 60 min of warm-up | FLAG → Signal generation broken for symbol |
| MFE avg (mfe_pct) | < 0.1% average | FLAG → Wrong entry timing |
| sl_dist | < 0.001 | FLAG → SL too tight, noise-stopped |
| Consecutive losses same symbol | ≥ 3 | FLAG → Regime mismatch for that symbol |

### Step B — Runtime Anomaly Detection (`engine_log.txt` live tail)

During live session watch for **mid-session** (not startup) anomalies:
- WebSocket disconnects or reconnects (`[WS] Disconnected`)
- HTTP 429 / 502 Binance errors during live trading
- `refit failed` during online model update
- Any symbol showing `ERROR` or `WARN` mid-session
- Warm-up gate never clearing after 200 bars

### Step C — Autonomous Decision & Arena.ai Discussion

```
IF any anomaly found (trade log OR runtime log):
    → Compose targeted Arena.ai prompt:
       1. Exact anomaly (metric, symbol, timestamps, values)
       2. Suspected root cause from code analysis
       3. Request FIND/REPLACE patch with strict verification
    → write send_to_arena.txt → trigger autonomous_loop.py --single-run
    → Apply patches → py_compile → git push → relaunch Engine_1

ELSE (all metrics healthy):
    → Continue to next Phase 1 improvement cycle
```

### Step D — Watch Timer Schedule

| Timer | Duration | Purpose |
|-------|----------|---------|
| Watch Timer 1 | 1800s (30 min) | First trade log analysis post warm-up |
| Watch Timer 2 | 3600s (60 min) | Second analysis — multiple signal cycles |
| Ongoing | Every 60 min | Continuous surveillance during extended run |

> **Do NOT restart Engine_1 during Watch window unless CRITICAL (naked position, WS disconnect, consecutive SL hits).**

### Phase 2 → Phase 1 Decision Gate

After each watch audit:
- **Anomalies found** → Address via Arena.ai first, then restart loop
- **All clean** → Proceed directly to next Phase 1 improvement cycle (Step 2 → send new improvement prompt)
