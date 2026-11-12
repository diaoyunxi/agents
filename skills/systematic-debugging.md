---
name: systematic-debugging
description: Debug methodically: form hypotheses, gather evidence, isolate root cause, then fix. Use when a bug or failing behavior resists a quick fix and guessing a patch would be unreliable.
when_to_use: A failure, error, or wrong behavior that a first guess didn't fix. Flaky or intermittent issues.
---

# Systematic Debugging

No guess-and-check. Find the root cause before proposing a fix.

## When to use
- A failure, error, or wrong behavior that a first guess didn't fix.
- Flaky or intermittent issues.

## Steps
1. **Reproduce** — Get a reliable, minimal reproduction. If you cannot, gather as much runtime detail as possible.
2. **Observe** — Collect evidence: exact error text, stack trace, state, inputs, timing. Record what you see, not what you expect.
3. **Hypothesize** — List plausible root causes, ranked. Each hypothesis must be testable.
4. **Isolate** — Design the smallest experiment that distinguishes hypotheses. Binary-search code paths, add targeted logs, or change one variable at a time.
5. **Confirm** — Identify the actual cause with evidence. Explain the causal chain.
6. **Fix** — Apply the minimal fix that addresses the cause, not the symptom. Add a regression test.
7. **Verify** — Re-run the reproduction and the suite; confirm the fix holds.

## Rules
- Do not ship a fix you cannot explain.
- One change at a time; otherwise you cannot attribute the effect.

## Stop conditions
- Root cause confirmed and fixed with a regression test → stop.
- If the issue is out of reach (third-party, infra), report the evidence and hand off with the cause statement.
