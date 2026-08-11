# Claude Code Agentic Directives & Architecture Principles

> **Source**: `C:\Users\SIGMA\Documents\Project - Coinglass Trading\free-claude-code-main` (`AGENTS.md` / `CLAUDE.md` / `ARCHITECTURE.md`)

## 1. Identity & Core Engineering Standards
- **Role**: Expert Software Architect & Systems Engineer.
- **Goal**: Zero-defect, root-cause-oriented engineering for bugs; test-driven engineering for new features. Think carefully; no need to rush.
- **Code Principles**: Write the simplest code possible. Keep the codebase minimal and modular.
- **No Type Ignores**: Fix underlying type issues rather than adding `# type: ignore` or `# ty: ignore`.
- **Python 3.14 Standard**: Use Python 3.14+ native lazy annotations (do NOT add `from __future__ import annotations`).
- **Package Management**: Prefer `uv` and `uv run` for executing Python scripts and managing dependencies.

## 2. Architecture & Design Principles
- **Failure Ownership**: Keep canonical failure semantics and redaction SDK-free in core modules; providers/adapters own retries and error classification.
- **DRY & Encapsulation**: Extract shared base classes to eliminate duplication. Use accessor methods (`set_current_task()`) rather than direct private attribute assignment.
- **Model-Independent Reasoning**: Resolve client reasoning intent once at application boundaries; provider adapters translate documented provider capabilities without branching on upstream model string names.
- **Dead Code Eradication**: Remove unused code, legacy shims, and hardcoded literals. Use settings/config objects instead of hardcoded strings.
- **Performance**: Use list accumulation for strings (avoid `+=` in loops), cache environment variables at init, prefer iterative loops over recursive calls when stack depth matters.

## 3. Cognitive Workflow Protocol
1. **ANALYZE**: Read relevant files. Do not guess. Ground every decision in empirical code/logs.
2. **PLAN**: Map out logic, root cause, and required changes. Order changes strictly by dependency.
3. **EXECUTE**: Fix the root cause, not the symptom. Execute incrementally with clean, self-contained edits.
4. **VERIFY**: Run automated test suites and verify execution via logs and empirical outputs.
5. **SPECIFICITY**: Fulfill exact user requirements — no under-building, no over-engineering.
6. **PROPAGATION**: When modifying a signature or pattern, trace and update all dependent call sites together.

## 4. Technical Summary Standards
All summaries must be technical and granular, covering:
- `[Files Changed]`
- `[Logic Altered]`
- `[Verification Method]`
- `[Residual Risks]` (if none, explicitly state none).
