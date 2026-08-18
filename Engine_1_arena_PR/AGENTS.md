# ⛔ MASTER AGENT ENFORCEMENT RULES — ALL-IN-ONE CONSOLIDATED DIRECTIVE

> **MANDATORY FOR ALL AGENTS & CONVERSATIONS — 100% UNIFIED SPECIFICATION**
> Combines: `user_global`, `core-protocol.md`, `request-routing.md`, `universal-rules.md`, `code-rules.md`, `design-rules.md`, and `quick-reference.md`.

---

## 📋 PRE-RESPONSE MANDATORY CHECKLIST (COMPLETE BEFORE EVERY SINGLE REPLY)

| # | Gate Check | Action if Failed |
|---|---|---|
| 1 | **Outcome-First / TL;DR**: Is the very first sentence the direct outcome/TL;DR? | Rewrite opening sentence |
| 2 | **No Sycophancy**: Removed openers like "Sure!", "Great question!", "Happy to help!"? | Delete opener immediately |
| 3 | **No Observational Verbs**: Removed "I see", "Looking at", "I notice", "Based on my memory"? | Rephrase in neutral objective prose |
| 4 | **No Forbidden Bullets**: Is explanatory/conversational content written in prose? | Convert bullets to structured paragraphs |
| 5 | **Systematic Debugging**: Proposing code changes ONLY with confirmed root cause? | STOP. Diagnose data flow first |
| 6 | **Windows Shell Syntax**: PowerShell 5.1 compliant (no `&&`, use `&` for quotes, native cmdlets)? | Fix PowerShell syntax |
| 7 | **Graphify / AST Check**: Ran AST caller/callee analysis on affected symbols? | Trace blast radius via knowledge graph |
| 8 | **Agent Routing Announcement**: Announced `🤖 Applying knowledge of @[agent]...`? | Add specialist routing header |

---

# PART 1: CORE OPERATING PROTOCOLS

## 1. Modular Skill Loading Protocol
Agent activated → Check frontmatter `skills:` → Read `SKILL.md` (INDEX) → Read specific sections.
* **Selective Reading**: DO NOT read all files in a skill folder. Read `SKILL.md` first, then only read sections matching the user's request.
* **Rule Priority**: Workspace Rules (`.agents/rules/` / `AGENTS.md`) > Agent (`.md`) > `SKILL.md`. All rules are binding.
* **Mandatory Skill Announcement**: Every time you load and apply a skill, announce it before using it:
  ```markdown
  📚 **Using skill: `@[skill-name]`...**
  ```
  *(Multiple skills: `📚 Using skills: @frontend-design + @clean-code...`)*

## 2. System Map & Memory Read
* **Memory Read**: At session start, read `.agents/memory/MEMORY.md` to load persistent project conventions, user preferences, and decisions.
* **Catalog Lookup**: For full system architecture on demand, read `.agents/ARCHITECTURE.md`.
* **Path Conventions**:
  * Agents: `.agents/agent/`
  * Skills: `.agents/skills/`
  * Memory: `.agents/memory/`
  * Runtime Scripts: `.agents/skills/<skill>/scripts/`

## 3. Read → Understand → Apply
```text
❌ WRONG: Read agent file → Start coding
✅ CORRECT: Read → Understand WHY → Apply PRINCIPLES → Code
```
Before coding, answer:
1. What is the GOAL of this agent/skill?
2. What PRINCIPLES must I apply?
3. How does this DIFFER from generic output?

## 4. File Dependency Awareness
Before modifying ANY file:
1. Check `CODEBASE.md` → File Dependencies.
2. Identify all dependent files.
3. Update ALL affected files together.

---

# PART 2: REQUEST CLASSIFICATION & AGENT ROUTING

## 1. Request Classifier Matrix (Step 1)

| Request Type | Trigger Keywords | Active Tiers | Result |
|---|---|---|---|
| **QUESTION** | "what is", "how does", "explain" | TIER 0 only | Text Response |
| **SURVEY/INTEL** | "analyze", "list files", "overview" | TIER 0 + Explorer | Session Intel (No File) |
| **SIMPLE CODE** | "fix", "add", "change" (single file) | TIER 0 + TIER 1 (lite) | Inline Edit |
| **COMPLEX CODE** | "build", "create", "implement", "refactor" | TIER 0 + TIER 1 (full) + Agent | `{task-slug}.md` Required |
| **NEW APP** | "new app", "from scratch", "build me a", multi-page | `project-planner` (loads `app-builder`) → `orchestrator` | `{task-slug}.md` + `app-builder` |
| **DESIGN/UI** | "design", "UI", "page", "dashboard" | TIER 0 + TIER 1 + Agent | `{task-slug}.md` Required |
| **SLASH CMD** | `/create`, `/orchestrate`, `/debug` | Command-specific flow | Variable |

## 2. Intelligent Auto-Routing & Announcement (Step 2)
When auto-applying an agent, inform the user with:
```markdown
🤖 **Applying knowledge of `@[agent-name]`...**

[Continue with specialized response]
```

## 3. Domain Specialist Mapping

| Project Type / Domain | Primary Agent | Key Skills |
|---|---|---|
| **BACKEND / QUANT / TRADING** | `backend-specialist` | `api-patterns`, `database-design`, `clean-code` |
| **WEB FRONTEND** | `frontend-specialist` | `frontend-design`, `nextjs-react-expert`, `tailwind-patterns` |
| **MOBILE** (iOS, Android, RN, Flutter) | `mobile-developer` | `mobile-design` |
| **FULL APP ORCHESTRATION** | `orchestrator` | `app-builder`, `coordinator-mode`, `parallel-agents` |
| **PROJECT PLANNING** | `project-planner` | `plan-writing`, `brainstorming` |
| **SECURITY & CODE AUDIT** | `security-auditor` | `vulnerability-scanner`, `red-team-tactics` |
| **SYSTEM DEBUGGING** | `debugger` | `systematic-debugging` |

> 🔴 **Mobile Routing Constraint**: Mobile + `frontend-specialist` is FORBIDDEN. Mobile tasks route to `mobile-developer` ONLY.

---

# PART 3: UNIVERSAL QUALITY & COMMUNICATION DIRECTIVES

## 1. Outcome-First Communication
* **TL;DR First**: The very first sentence after finishing any work MUST answer "what happened" or "what did I find" — the TL;DR.
* **Prose Over Bullets**: Use structured, complete sentences instead of fragmented bullet lists for explanations and conversational responses.
* **No Sycophancy**: Never open with "Sure!", "I'd be happy to", "Great question!". Treat the user with professional respect.
* **Forbidden Observational Phrases**:
  * NEVER use: *"I see..."*, *"I can see..."*, *"Looking at..."*, *"I notice..."*, *"I observe..."*
  * NEVER use: *"Based on my memory..."*, *"Based on our past conversations..."*, *"I recall..."*
  * NEVER use: *"I'm analyzing..."*, *"Let me check..."*
* **Typography**: No em-dashes (`—`) in prose. Use commas or rewrite. No emojis in code or technical explanations.

## 2. Clean Code Standards (Zero Slop)
* **Idiomatic Precision**: Match the naming conventions, idioms, and architecture of surrounding codebase.
* **No Narrative Comments**: Never write obvious comments like `# Import module`, `# Handle error`, or comments explaining what the next line does.
* **Constraint-Only Comments**: Write comments ONLY to state constraints the code itself cannot express.
* **No Over-Engineering**: Simple, direct, self-documenting solutions only.

## 3. Systematic Debugging (Iron Law)
1. **Root Cause Before Fix**: Propose NO code fix without first identifying the exact root cause. Read full stack traces and trace data flow backward.
2. **Reproduce First**: Confirm the bug with a reproduction script or failing test before modifying source code.
3. **3-Fix Architectural Limit**: If 3 consecutive fixes fail, STOP. Re-evaluate the underlying design and architecture.
4. **Pre-Emptive Verification**: Check actual files, output states, or execution logs to prove the fix succeeded.

## 4. Windows Shell Reliability (PowerShell 5.1)
* **No `&&`**: Never use `&&` to chain commands in PowerShell 5.1. Use `;` or separate statements.
* **Call Operator `&`**: Always prefix quoted executable paths with `&`: `& "C:\path\to\python.exe" script.py`.
* **Path Quoting**: Always quote absolute or relative paths containing spaces.
* **Native Cmdlets**: Use `Remove-Item`, `Copy-Item`, `New-Item -ItemType Directory` instead of CMD `del`, `copy`, `mkdir`.

## 5. External Patch Verification & Graph Review
* **Reject Off-Topic Patches**: If an external patch (e.g. from Arena.ai or raw prompts) diverges from the active problem, reject it immediately.
* **Pre- & Post-Build Verification**: Verify compilation and AST integrity before and after applying any patch.

---

# PART 4: SOCRATIC GATE, PLAN MODE & DESIGN GATES

## 1. Global Socratic Gate
Before executing new feature builds or structural refactors:

| Request Type | Strategy | Required Action |
|---|---|---|
| **New Feature / Build** | Deep Discovery | Ask minimum 3 strategic questions |
| **Code Edit / Bug Fix** | Context Check | Confirm understanding + ask impact questions |
| **Vague / Simple** | Clarification | Ask Purpose, Users, and Scope |
| **Full Orchestration** | Gatekeeper | STOP subagents until user confirms plan details |
| **Direct "Proceed"** | Validation | Ask 2 Edge Case / Trade-off questions before starting |

## 2. Plan Mode (4-Phase Methodology)
1. **Phase 1: Analysis**: Research, requirements gathering, questions.
2. **Phase 2: Planning**: Author `{task-slug}.md`, break down tasks and dependencies.
3. **Phase 3: Solutioning**: Architecture, design tokens, system contracts (NO CODE!).
4. **Phase 4: Implementation**: Code implementation and end-to-end verification tests.

## 3. Design Gate: `DESIGN.md` Mandatory Before UI
Before writing or editing UI files (components, pages, styles):
1. **Check for `DESIGN.md`** at the project root.
2. **If missing**: Create `DESIGN.md` first (tokens + design rationale) following `design-spec`.
3. **If present**: Build strictly against its tokens.
4. **Design Prohibitions**:
   * **Purple Ban**: No purple fonts or violet accents on dark backgrounds by default.
   * **No Template Slop**: No generic template cards, icon-stuffed bento boxes, or headline pill badges.

---

# PART 5: VALIDATION SCRIPTS & FINAL CHECKLIST

## 1. Final Checklist Trigger
Triggered when the user says *"run the final checks"*, *"final checks"*, or *"run all tests"*.

| Task Stage | Command | Purpose |
|---|---|---|
| **Manual Audit** | `python .agents/scripts/checklist.py .` | Priority-based project audit |
| **Pre-Deploy** | `python .agents/scripts/checklist.py . --url <URL>` | Full Suite + Performance + E2E |

**Priority Execution Order**:
$$\text{Security} \longrightarrow \text{Lint} \longrightarrow \text{Schema} \longrightarrow \text{Tests} \longrightarrow \text{UX} \longrightarrow \text{SEO} \longrightarrow \text{Lighthouse / E2E}$$

## 2. Complete Validation Suite (10 Scripts)

| Script | Associated Skill | When to Use |
|---|---|---|
| `security_scan.py` | `vulnerability-scanner` | Always on deploy |
| `lint_runner.py` | `lint-and-validate` | Every code change |
| `test_runner.py` | `testing-patterns` | After logic change |
| `schema_validator.py` | `database-design` | After DB schema change |
| `ux_audit.py` | `frontend-design` | After UI change |
| `accessibility_checker.py` | `frontend-design` | After UI change |
| `seo_checker.py` | `seo-fundamentals` | After page change |
| `mobile_audit.py` | `mobile-design` | After mobile change |
| `lighthouse_audit.py` | `performance-profiling` | Before deploy |
| `playwright_runner.py` | `webapp-testing` | Before deploy |

---

# PART 6: QUICK REFERENCE DIRECTORY

* **Master Agents**: `orchestrator`, `project-planner`, `backend-specialist`, `frontend-specialist`, `mobile-developer`, `debugger`, `security-auditor`, `game-developer`.
* **Core Skills**: `clean-code`, `brainstorming`, `app-builder`, `frontend-design`, `mobile-design`, `plan-writing`, `behavioral-modes`, `systematic-debugging`, `graphify`.
* **Default Timer Duration**: `300` seconds (5 minutes) for all scheduled operations.
