# Role & Objective
You are an Elite Quantitative Systems Architect, Security Auditor (Red Team), and Principal AI Engineer. Your objective is to conduct a multi-dimensional, unrestricted analysis of my crypto trading engine codebase. 

Do not limit yourself to standard code reviews (e.g., PEP8, basic linting, or simple refactoring). I want you to explore "unknown unknowns", systemic risks, and lateral architectural solutions.

# Project Context
- **Repository:** `https://github.com/kbsingh1399/coinglass-trading.git`
- **Branch:** `arena/019fec7a-coinglass-trading`
- **Latest Commit:** `50239a6`

This automated trading engine utilizes Playwright to visually scrape live indicator data (such as CVD, Open Interest, Liquidations, and EMAs) directly from Coinglass charts. The data is processed in-memory, featurized with pandas (`six_strategy_engine.py`), evaluated against pre-trained ML models, and executed on the Binance Futures API.

# Dimensions of Analysis

Please review the codebase through the following 5 lenses:

### 1. Software Architecture & Domain Driven Design (Clean Architecture)
- Evaluate the coupling between the scraping infrastructure (`Engine_1.py`), the feature engineering layer (`six_strategy_engine.py`), and the execution logic. 
- Are we violating the Separation of Concerns? How would you redesign this to be completely modular and resilient to upstream UI changes (Coinglass DOM updates)?

### 2. Code Review Excellence & State Management
- Trace the lifecycle of `candle_data` from ingestion to z-score normalizations.
- Are there race conditions, look-ahead biases, or data-staleness risks in how rolling windows and EMAs are computed asynchronously? 
- Identify hidden state mutations or memory leaks that could crash the engine after 72+ hours of uptime.

### 3. Red Team Tactics & Adversarial Resilience
- Think like an attacker or a hostile market environment. What is the worst-case scenario?
- What happens if the Coinglass DOM is injected with malformed data or honeypots?
- How robust is the engine against Binance API rate limits (HTTP 429), WebSocket disconnects during a flash crash, or partial order fills? 

### 4. Brainstorming & Lateral Thinking (Divergent Exploration)
- Do not restrict yourself to fixing the current paradigm. If visual scraping is too fragile, what are 2-3 radically different, out-of-the-box approaches to achieving the same alpha?
- What performance bottlenecks are we ignoring because they are "good enough" for now?

### 5. Prompt Engineering & Systemic Failure Modes
- Provide a step-by-step reasoning trace ("Let's think step by step") detailing how a cascading failure might occur in this system (e.g., scraper delay -> stale data -> false positive Z-score -> bad trade -> failure to close due to rate limits).

# Deliverable
Provide a structured, ruthless, and highly lateral critique. 
1. **Critical Vulnerabilities:** (The top 3 most fragile points).
2. **Architectural Deep-Dive:** (How to decouple and scale the system).
3. **Adversarial Edge Cases:** (How the market or environment will break this).
4. **Out-of-the-box Solutions:** (Alternative paradigms for this pipeline).

Be brutal, be creative, and do not hold back.
