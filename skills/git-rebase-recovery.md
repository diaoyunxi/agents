---
name: git-rebase-recovery
description: Recover from a failed or messy git rebase: understand state, continue/abort/skip, and restore the original branch. Use when a rebase is stuck on conflicts or the user is worried they lost work.
when_to_use: `git rebase` stopped on a conflict, the user says 'I'm stuck', or the history looks wrong mid-rebase.
---

# Git Rebase Recovery

Stay calm, read state, then act. Never force-push a shared branch to "fix" it.

## When to use
- `git rebase` stopped on a conflict, the user says "I'm stuck", or the history looks wrong mid-rebase.

## Steps
1. **Read the state** — Run:
   - `git status` (shows "rebase in progress", which commit is being applied).
   - `git rebase --interactive` then `abort` to list commits in the rebase todo if needed — or just `cat .git/rebase-merge/done` and `todo` when they exist.
   - `git log --oneline --graph` to see where you are.
2. **Decide the action**:
   - **Conflicts** → resolve them, `git add <files>`, then `git rebase --continue`.
   - **Skip a bad commit** → `git rebase --skip` (only if that commit's content is intentionally dropped).
   - **Edit a commit** → `git rebase --edit-todo` and change the command, or `git commit --amend` for the first one.
   - **Give up entirely** → `git rebase --abort`. This restores the pre-rebase branch head.
3. **Confirm the original is safe** — Before aborting or continuing, note `git reflog`. The original branch position is in the reflog, so nothing is permanently lost from a local rebase.
4. **Verify** — After finishing, `git log --oneline` and the test suite should match the intended state.

## Rules
- Do not `git reset --hard` to "fix" a rebase unless you have a confirmed reflog target.
- If the rebase already pushed to a shared branch, do not force-push; consult the user and the team's flow.
- If `abort` does not restore the expected state, stop and inspect `git reflog` before any further reset.

## Stop conditions
- Rebase finished cleanly and the branch matches the intended history → stop. Or the original state was fully restored via abort → stop.
