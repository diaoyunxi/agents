---
name: changelog-generator
description: Generate a release changelog from git commit history. Use when the user asks to write a changelog, release notes, or what''s-new summary for a version or date range.
when_to_use: 'write the changelog for v1.2.0', 'summarize what changed since last release'.
---

# Changelog Generator

Produce a clean, user-facing changelog from git history.

## When to use
- "write the changelog for v1.2.0", "summarize what changed since last release".

## Steps
1. **Determine the range** —
   - For a tag: `git log <prev-tag>..<tag>`.
   - For a date range: `git log --since=... --until=...`.
   - Unreleased: compare against the last tag on the branch.
   Run `git tag` to find the last release if the range is unknown.
2. **Collect commits** — `git log --pretty=format:'%h %s' <range>` for a first pass.
3. **Classify** each commit into categories:
   - **Added / Features**
   - **Changed / Improvements**
   - **Fixed / Bug fixes**
   - **Deprecated / Removed / Breaking changes** (flag breaking changes prominently)
   Use conventional-commit prefixes (`feat:`, `fix:`, `refactor:`, `perf:`, `docs:`, `chore:`) to classify. Ignore pure `chore:`/`docs:` commits in the user-facing log unless they matter.
4. **Rewrite for humans** — Convert terse commit subjects into clear, reader-facing sentences. Remove internal jargon, ticket ids, and "wip"/"fix typo"-style noise. Keep a link to the full diff for details.
5. **Format the output** — A sectioned markdown changelog:
   ```
   ## [1.2.0] - 2026-01-15
   ### Added
   - ...
   ### Fixed
   - ...
   ### Breaking changes
   - ...
   ```
   Or update the project's existing `CHANGELOG.md` in its established format.
6. **Verify** — No commit that introduced a user-visible change is silently dropped; breaking changes are called out.

## Rules
- "User-facing" means the reader is a consumer of the product, not the developer.
- If a commit is ambiguous about impact, keep it with a clear note or ask.
- Preserve the project's existing changelog conventions (Keep-a-Changelog, etc.) when one exists.

## Stop conditions
- Every significant commit is represented and the changelog reads cleanly → stop.
