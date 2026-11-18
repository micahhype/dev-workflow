---
name: rollback
description: Undo an AI agent's changes by restoring the git working tree to a checkpoint — snapshots taken automatically before each agent edit. Safe and reversible — saves current state first, never moves your branch, never hard-deletes. Pass `list` to only list the checkpoints, or a checkpoint ref to restore; defaults to the most recent.
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py" list)
---

Restore the working tree to a checkpoint, undoing recent agent changes. This is
safe: it first saves the current state as a reversible `pre-rollback` checkpoint,
never moves your branch/HEAD, and never hard-deletes anything from git.

The CLI is `python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py" <cmd>` (this
resolves to the plugin's `hooks/checkpoint.py`).

**`list` (or the user only wants to see the checkpoints):** run the `list` command
below, show the rows (`<ref>` `<timestamp>` `<tool>`) newest-first as a short table,
and stop — change nothing. Rows marked `pre-rollback` are recovery points a previous
rollback created. Checkpoints older than 14 days are deleted automatically.

Steps:
1. If the user did NOT name a checkpoint, first list them and show the user so
   they can confirm the target (default = most recent non-`pre-rollback`
   checkpoint):
   ```
   python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py" list
   ```
2. Perform the rollback (pass the chosen ref, or omit for the default):
   ```
   python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py" rollback [ref]
   ```
   This step is intentionally NOT pre-approved — because a rollback rewrites the
   working tree, Claude Code will ask the user to permit this exact command. That
   confirmation is expected; wait for it. `undo` is not pre-approved either: it is
   itself a rollback (to the `pre-rollback` checkpoint) and rewrites the working
   tree just the same, so it gets the same confirmation. Only `list` is read-only.
3. Relay the tool's output verbatim, including how to reverse it:
   ```
   python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py" undo
   ```
   Also note that files CREATED since the checkpoint are left in place (they show
   up in `git status`) and can be removed manually if unwanted.

Only meaningful in a git repository. If the CLI prints "not a git repository" or
"no checkpoints", relay that and stop. Do not attempt manual `git reset`/`checkout`
yourself — always go through the CLI so the operation stays safe and reversible.
