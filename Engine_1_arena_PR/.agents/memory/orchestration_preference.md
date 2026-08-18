# Default Agent Methodology

**Directive**: The user explicitly requested to **default** to using the `/orchestrate` multi-agent coordination protocol and the `/agent-orchestrator` skill scanning methodology. 

**Execution Protocol**:
1. For any complex problem, DO NOT attempt to solve it solo as a monolithic agent.
2. ALWAYS use `agent-orchestrator` to auto-discover and match maximum relevant skills from the registry.
3. ALWAYS invoke a minimum of 3 specialized sub-agents (`frontend-specialist`, `backend-specialist`, `quant-analyst`, etc.) to execute the plan in parallel.
4. Synthesize their results to generate a final answer.
