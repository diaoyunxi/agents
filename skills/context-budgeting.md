---
name: context-budgeting
description: Manage the context budget when many skills or reference docs need to be loaded for one task. Use when a task could pull in multiple skills/large references and there is a risk they crowd out core working space.
when_to_use: Multiple skills are plausibly relevant. A skill references large templates, docs, or datasets. The task is long and the context is getting noisy.
---

# Context Budgeting

Keep the active context focused: load only what the task actually needs, and defer the rest.

## When to use
- Multiple skills are plausibly relevant.
- A skill references large templates, docs, or datasets.
- The task is long and the context is getting noisy.

## Steps
1. **Triage** — Rank candidate skills/references by: (a) does the task truly require this now? (b) is it cheap to re-derive later? (c) how large is it?
2. **Load the minimum** — Load only skills that are definitely needed for the current step. Use `load_skill` (or equivalent) for one at a time, not a bulk load of everything.
3. **Summarize, don't inline** — For large reference material, extract only the specific command, path, or rule you need rather than pasting the whole document into context.
4. **Defer** — Queue lower-priority items for later turns or subagent context where they can be loaded and discarded.
5. **Delegate heavy context** — When a chunk of work needs a lot of reference material, hand it to a subagent that loads it in isolation and returns a compact result.
6. **Prune** — If context is near a limit, drop already-applied guidance and keep only what the next step needs.

## Stop conditions
- Core task has the skills it needs and context stays well under the limit → stop.
- Never silently drop a skill the current step depends on; if you must, note the gap.
