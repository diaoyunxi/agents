---
name: progressive-research
description: Retrieve information progressively during a skill or task instead of loading all references up front. Use for research- or lookup-heavy tasks where you only know which material to fetch once you have made partial progress.
when_to_use: A task needs lookups whose targets are only known after earlier steps. Reference material is large; full pre-load would waste context. The answer depends on an iterative 'check → refine → fetch' loop.
---

# Progressive Research

Fetch references on demand, stage by stage, instead of preloading everything.

## When to use
- A task needs lookups whose targets are only known after earlier steps.
- Reference material is large; full pre-load would waste context.
- The answer depends on an iterative "check → refine → fetch" loop.

## Steps
1. **Plan the stages** — Split the task into stages; list what each stage may need to look up, but do not fetch it yet.
2. **Fetch minimally per stage** — At each stage, retrieve only the specific fact, file, or snippet needed to make the next decision.
3. **Cache what is stable** — Reuse values already fetched; do not re-query the same source.
4. **Refine queries** — Let partial results sharpen the next query (narrow domain, exact identifier, specific section).
5. **Record** — Keep a running list of what was fetched and why, so the final answer is auditable.

## Stop conditions
- All stages have the facts they need to produce the final answer → stop.
- A required source is unreachable → record it as a gap and report, do not invent it.
