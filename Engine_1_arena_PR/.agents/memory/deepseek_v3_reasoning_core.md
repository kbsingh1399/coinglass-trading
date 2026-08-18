# 🧠 DeepSeek-V3 & R1 Cognitive Reasoning Core

This directive permanently embeds the DeepSeek-V3 architectural and reasoning methodology directly into the agent's core thinking patterns.

---

## 1. DeepSeek-V3 Reasoning & Reflection Protocol

### 1.1 Long-Chain-of-Thought (CoT) Pre-Flight Decomposition
Before executing any action or proposing a modification:
1. **Deconstruct the Invariant:** State the exact mathematical and physical invariant that must hold (e.g., `coins_bid = dollars_bid / price`, `15m` candle timeframe lock, atomic order state transitions).
2. **Trace Failure Vectors:** Explicitly identify how previous implementations failed (DOM selector mismatch, parenthetical regex stripping, OS focus thrashing).
3. **Adversarial Edge Case Enumeration:** Check 0, negative values, missing indicators, race conditions, disconnection, and staleness bounds.

---

## 2. Multi-Token / Multi-Step Verification (MTP Architecture)
1. **Step-by-Step State Assertion:** For every step in a workflow (e.g., Login -> S9 Navigation -> L_1 Layout Load -> Frame Resolution Lock), assert the exact expected DOM state and cookies before proceeding to the next step.
2. **Dual-Gate Verification:** Every change must produce a passing reproduction test and runtime/log validation evidence before being marked complete.
3. **Zero Hallucination Grounding:** Ground all statements in line numbers, exact AST graph symbols, and physical execution outputs.

---

## 3. Cognitive Self-Correction & Reflection Cycle
1. **Observe Empirical Result:** Run the test or scraper.
2. **Reflect on Discrepancies:** If any column, value, or behavior deviates by even 1 digit or 1 millisecond, stop and re-examine the data flow backwards from the symptom to the root cause.
3. **Apply Minimal Invariant-Preserving Fix:** Update the code to satisfy the invariant without introducing dead code or narrative comments.
