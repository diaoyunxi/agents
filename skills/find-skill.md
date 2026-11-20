---
name: find-skill
description: Discover, install, and validate Agent skills from a local path or a remote repository. Use when the user asks to install a skill, browse available skills, or pull a skill from a GitHub repo or shared skills directory.
when_to_use: 'install a skill', 'find a skill that does X', 'pull this skill from GitHub'.
---

# Find and Install Skills

Discover and install a skill from a local path or remote source into the current Agent environment.

## When to use
- "install a skill", "find a skill that does X", "pull this skill from GitHub".

## Steps
1. **Local first** — Check the local skills directories:
   - Global: `~/.agnes/skills` (or the configured user skills dir).
   - Project: `<workspace>/.agnes/skills`.
   List what exists; report matches.
2. **Remote** — If not found locally, search remote sources (e.g., a shared GitHub skills repo, a marketplace listing):
   - Clone or download the skill folder to a temp location.
   - Inspect `SKILL.md` (or `skill.md`) for valid YAML frontmatter: `name` (kebab-case) and `description`.
3. **Validate** — Confirm:
   - `name` is kebab-case, ≤64 chars, and does not collide with an existing skill.
   - `description` describes a trigger.
   - `content` is self-contained and under 256 KB.
   - Any referenced supporting files exist.
4. **Install** — Copy the skill folder into the target skills directory (ask global vs project if ambiguous). Report the final path.
5. **Verify** — Type `$<name>` in chat input to confirm it is discoverable, or call `load_skill` to load it.

## Failure handling
- Invalid frontmatter → stop and report exactly what is missing.
- Name collision → do not overwrite; suggest a new name or a deliberate update via the Skills UI.
- Missing supporting files → report the list of missing paths; do not install a half-complete skill silently.
