# Arena.ai Skill Directive & Master Guidelines

> **MANDATORY FOR ARENA.AI & ALL REVIEWING AGENTS**

This repository contains a comprehensive suite of **50+ AI engineering skills** located under `.agents/skills/`.

## How Arena.ai Must Use These Skills

1. **Always Read Skills Before Modifying Code:** When performing code reviews, optimizations, or refactoring in this repository, always check `.agents/skills/` for relevant domain skills:
   - `@[skills/clean-code]` — Anti-slop, concise, pragmatic coding standards.
   - `@[skills/code-review-graph]` — Token-efficient Tree-sitter AST & dependency analysis.
   - `@[skills/systematic-debugging]` — Root-cause debugging protocols before making fixes.
   - `@[skills/python-patterns]` — Production async, type hints, and exception handling.
   - `@[skills/performance-profiling]` — Measurement, memory safety, and event loop optimization.
   - `@[skills/tdd-workflow]` — Test-driven development and verification checks.

2. **Strict Backtest Parity Directive:**
   - Always preserve 100% parity with `run_all_6.py` (the OOS backtest baseline).
   - `sl_mult = 1.0` (1.0 × ATR)
   - `tp_mult = 5.0` (5.0 × ATR, 1:5 R:R)
   - `trail_atr = 0.8` (0.8 × ATR trailing stop after 5.0R)

3. **No Unchecked Code Fixes:**
   - Never apply raw or unverified code patches.
   - Verify all file edits against existing unit tests in `tests/test_engine_parity.py`.
