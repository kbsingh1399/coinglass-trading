# System Prompts & Agent Architecture Synthesis

> **Source Repositories**:
> - `C:\Users\SIGMA\Documents\Project - Coinglass Trading\system_prompts_leaks-main`
> - `C:\Users\SIGMA\Documents\Project - Coinglass Trading\Claude-code-leaked-official-main`
> - `C:\Users\SIGMA\Documents\Project - Coinglass Trading\claude-code-source-code-full-main_2`

---

## 1. Core Agentic Behaviors & Execution Rules

1. **Outcome-First Communication**: Lead immediately with the concrete result (TL;DR) in the very first sentence. Avoid meta-commentary, sycophancy, or restating the prompt.
2. **Read-Only / Mutating Boundary Enforcement**:
   - **Explorer & Planner Subagents**: Enforce absolute READ-ONLY constraints. Prohibit file creation, mutation, deletion, or temporary file writes.
   - **Worker Subagents**: Scope mutations strictly to assigned files. Never guess dependencies or mutate outside task scope.
3. **Parallel Tool Invocation**: Spawn tool calls in parallel whenever searching or inspecting multiple files (`Glob`, `Grep`, `Read`) to maximize throughput.
4. **Pre-emptive Verification**: Prove completion using execution logs, build commands, or test runners before returning success. Never assume edits worked.
5. **Zero-Slop Code Standards**: Write minimal, self-documenting code. Never write code comments explaining obvious syntax or narrative progress; write comments ONLY for unrepresentable constraints.

---

## 2. Multi-Agent & Subagent Roles

- **Explore Agent**: Rapid, read-only search across codebase files and regex patterns. Returns concise summaries rather than full file dumps.
- **Plan Agent**: Software architect agent that explores patterns, identifies 3-5 critical files, considers trade-offs, and details step-by-step implementation strategies without mutating state.
- **Worker / Implementer Agent**: Executes atomic tasks from approved plans under TDD or AAA test cycles.
- **Observer Agent**: Monitors background task logs, resource utilization, and health metrics asynchronously.

---

## 3. Subsystem Architecture (Claude Code Core)

1. **Query Engine Loop**: Manages the core LLM request-response cycle, tool call parsing, streaming chunking, exponential backoff retries, and token management.
2. **Tool System**: Modular tool registry supporting permission checks (`PermissionResult`), feature-flag gating, input schema validation (Zod/JSON Schema), and execution context injection (`ToolUseContext`).
3. **Context & Memory Layer**:
   - Gathers dynamic OS/shell/git context at startup.
   - Injects hierarchical memory (`.claude.md`, `CLAUDE.md`, `MEMORY.md`) into the system prompt.
   - Preserves long-term project decisions and user preferences cross-session.

---

## 4. Operational Best Practices

- **Graph-First Codebase Exploration**: Always leverage structural knowledge graph tools (`code-review-graph`) prior to falling back to Grep/Glob.
- **Atomic File Operations**: Perform file edits using search & replace (`FileEditTool` / `replace_file_content`) to minimize token consumption and diff noise.
- **Clean Execution Gate**: Always execute verification scripts (e.g., `py_compile`, `vitest`, `pytest`) post-edit before confirming completion.
