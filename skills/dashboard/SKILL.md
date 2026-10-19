---
name: dashboard
description: Open a local web board of the dev-workflow state across all projects — every feature's progress, the ones waiting for your approval first, and on click its phases, evidence, plan, spec, checkpoints and config — that refreshes itself while you work.
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/../../hooks/dashboard.py" --detach)
---

Start the dashboard and tell the user where it is.

The CLI is `python3 "${CLAUDE_SKILL_DIR}/../../hooks/dashboard.py"` (this resolves to
the plugin's `hooks/dashboard.py`). It serves a page on `127.0.0.1` only, built from the
guards' own functions, and polls every 2 seconds, so it tracks the working docs as
they change. Its one write is the drawer's **Mark done** button (ticks the remaining
phases of a feature the user already finished), accepted only from the page itself; every
other action it shows (unlocking the gate, rolling back) is a `!` command for the user to
run in their own shell. Never use that button or its route yourself: the approval tick is
the user's.

Run exactly:
```
python3 "${CLAUDE_SKILL_DIR}/../../hooks/dashboard.py" --detach
```

It prints one line: `Dashboard: <url> (pid <N>; stops after 30 min idle)`. Report the
URL for the user to open, and that `kill <N>` stops it early. Running the skill again
starts a second server on a new port; it does not reuse the first.

It shows all projects: every project that has started a Claude session with the plugin
and still has a `.dev-workflow/` directory, plus the one it is started from
(`CLAUDE_PROJECT_DIR`, or the current directory when that is unset).

## If Bash is denied

While `.approval-gate` says `LOCKED`, no Bash runs, so this command is refused too. Do
not suggest unlocking the gate to view the dashboard: the gate is holding a phase for
the user's review, and viewing needs no unlock. Instead give the user the command to
run themselves, with the project root and the plugin path written out in full (resolve
`${CLAUDE_SKILL_DIR}/../../hooks/dashboard.py` to its absolute path):
```
! cd /absolute/project/root && python3 /absolute/path/to/hooks/dashboard.py --detach
```
The dashboard always includes the directory it is started from, which is why the
command `cd`s into the project root first.
