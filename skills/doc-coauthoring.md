---
name: doc-coauthoring
description: Co-author documents, proposals, or specs in three stages (draft → critique → revise), invoking subagents to act as readers. Use when the user wants to write or improve a substantial written document collaboratively.
when_to_use: 'help me write a proposal / spec / report / blog post', 'improve this draft'.
---

# Document Co-authoring

Write a substantial document through three staged passes with reader critique.

## When to use
- "help me write a proposal / spec / report / blog post", "improve this draft".

## Three stages
1. **Draft**
   - Agree on audience, goal, and outline first.
   - Write a complete first draft that covers the outline; err on the side of complete but rough.
   - Mark assumptions explicitly so they can be challenged.
2. **Critique (reader pass)**
   - Invoke a subagent (or a fresh read-through) to act as the intended reader.
   - The reader checks: Is the goal clear in the first paragraph? Are there gaps or jargon? Is the argument supported? What would a skeptical reader object to?
   - Collect concrete, location-anchored feedback, not vague impressions.
3. **Revise**
   - Apply the reader's findings; restructure, cut, or add as needed.
   - Re-run one more reader pass if the revision was substantial.

## Rules
- The reader must be a distinct pass (subagent or fresh reading), not the same context that drafted.
- Track which reader findings were adopted vs. dismissed and why.
- Keep a running version or diff of the document between stages.

## Stop conditions
- A reader pass returns no material objections and the document meets the stated goal → stop. Deliver the final document.
