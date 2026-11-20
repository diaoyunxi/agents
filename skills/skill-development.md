---
name: skill-development
description: Manage the full lifecycle of an Agent skill: discover a candidate, author it, evaluate trigger accuracy, and iterate. Use when the user wants to improve, review, version, or refine an existing or new skill rather than just create one in a single shot.
when_to_use: The user wants to improve, review, version, or refine a skill. A skill keeps mis-firing or under-firing in real sessions. The user says 'make a skill better' / 'iterate on this skill'.
---

# Skill Development Lifecycle

Manage the full lifecycle of a skill: discover → author → evaluate → iterate.

## When to use
- The user wants to improve, review, version, or refine a skill.
- A skill keeps mis-firing or under-firing in real sessions.
- The user says "make a skill better" / "iterate on this skill".

## Steps
1. **Discover** — Identify repeated work in the current project that could become a skill. Look for workflows that recur, that have a clear trigger, and that carry non-obvious context.
2. **Author** — Follow the skill-creator quality bar:
   - kebab-case name, specific over generic.
   - `description` states the trigger, not a summary.
   - `content` is imperative, self-contained, with concrete commands/paths, `$ARGUMENTS` where runtime input belongs, stop conditions, and failure handling.
   - No reference to "the conversation above".
   - Move bulky reference material into supporting files under the skill directory.
3. **Evaluate** — Run 3-5 representative trigger phrases and 3-5 non-trigger phrases. Check the skill fires only for the intended triggers. Time-box; record misses.
4. **Iterate** — Adjust `description` wording, add/removing trigger keywords, tighten or split `content`. Keep it under 256 KB.
5. **Version** — Note changes in the content header or a `CHANGELOG.md` in the skill directory when it is installed and shared.

## Stop conditions
- Skill passes evaluation on both trigger and non-trigger phrases → stop.
- If a name collides with an existing skill, report the collision and stop; do not silently overwrite.
