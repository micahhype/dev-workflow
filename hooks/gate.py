#!/usr/bin/env python3
"""PreToolUse approval gate for the dev-workflow plugin.

Two protections:
1. The model may NEVER modify `.approval-gate` itself — not via Edit/Write/
   MultiEdit/NotebookEdit, and not via Bash. Only the user changes it from their own shell
   (`! echo UNLOCKED > .approval-gate`), which is not a Claude tool call and is
   therefore not intercepted.
2. While `.approval-gate` says LOCKED, block BOTH the edit tools on source files
   AND Bash entirely, so an unapproved phase cannot advance. Workflow working docs
   stay editable so the log can be maintained: anything under `.dev-workflow/` plus
   the doc basenames spec.md / plan.md / phase-log.md / conventions.md /
   project-map.md.

Why LOCKED denies Bash outright, rather than trying to spot the writes:
`coder` has Bash, and a denylist of write constructs cannot be closed — `>`, tee,
`sed -i`, here-docs, `patch`, `install`, `git checkout`, and any interpreter with
a `-c`/`-e` flag all write files, and no list of them is ever complete. Gating Bash
on "does this command look like a write?" therefore cannot hold, so we do not try:
while LOCKED, Bash is denied. The cost is nil, because LOCKED means "stop and wait
for the user to approve this phase" — there is nothing legitimate to run. The coder
does its work, tests and lint included, while UNLOCKED.

The same unclosable-denylist problem applies to protection 1, which matches the
gate's FILENAME. We normalize away shell quoting first (`.approval-gat"e"` is the
same file to the shell) but this stays best-effort by nature. It is not what makes
the gate hold: while LOCKED, no Bash runs at all, so the gate cannot be rewritten.
While UNLOCKED it is a guardrail against the model disabling the gate for the next
phase (`rm .approval-gate`), not a barrier against a determined attacker — and a
model that is already unlocked gains no privilege by writing UNLOCKED.

Gate states (first non-empty line of `.approval-gate`, case-insensitive):
  LOCKED    -> block source edits and all Bash
  UNLOCKED  -> allow
  (absent)  -> allow (the gate is opt-in; create the file to activate it)
"""
import fnmatch
import json
import os
import re
import sys

# The tools that write a file at a path this hook can inspect. NotebookEdit is an
# edit tool like the others — leaving it out routed .ipynb writes past the gate.
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# Doc basenames that are always workflow docs, wherever they live.
WORKING_DOC_NAMES = {"spec.md", "plan.md", "phase-log.md", "conventions.md",
                     "project-map.md"}
STATE_DIR = ".dev-workflow"
GATE_NAME = ".approval-gate"

STATE_NAME = "state.json"
LOG_NAME = "phase-log.md"
GENERATED_MSG = (
    "This file is written only by the `dw` command: state.json is the workflow state "
    "and phase-log.md is rendered from it, so an edit here is refused or overwritten.\n"
    "Change the state with `.dev-workflow/dw <command>` (`.dev-workflow/dw --help` "
    "lists them): coded, round, reviewed, set, reopen."
)

GATE_EDIT_MSG = (
    "Only you can change the approval gate. Run it in YOUR shell so it is not a "
    "Claude tool call:\n"
    "    ! echo UNLOCKED > .approval-gate   (to allow the next phase)\n"
    "    ! echo LOCKED > .approval-gate     (to re-lock)"
)

BASH_LOCKED_MSG = (
    "Bash is blocked while the approval gate is LOCKED.\n"
    "LOCKED means the current phase is waiting on YOUR review — Claude should not be "
    "running anything, and Bash can write source (`sed -i`, here-docs, `python -c`), "
    "which would advance the phase behind the gate.\n"
    "Review the phase, then unlock from YOUR shell (Claude cannot do this):\n"
    "    ! echo UNLOCKED > .approval-gate\n"
    "Re-lock before the next phase with:\n"
    "    ! echo LOCKED > .approval-gate"
)

# Shell quoting can split the filename into pieces that are the same file to the
# shell but a different string to us (`.approval-gat"e"`), so strip quotes and
# escapes before matching.
_SHELL_QUOTES = re.compile(r"""['"\\]""")
# ...and shell GLOBBING can name the file without ever spelling it: `rm
# .approval-gat?` and `echo UNLOCKED > .approval*` both hit the gate. Split the
# command on shell separators and ask fnmatch whether any glob-carrying token
# would match the gate file.
_TOKEN_SPLIT = re.compile(r"[\s;|&<>()`]+")
_GLOB_CHARS = re.compile(r"[*?\[]")
# A quoted run is inert to globbing, so it is removed before the glob sweep.
_QUOTED_SPAN = re.compile(r"'[^']*'|\"[^\"]*\"")


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def glob_hits_gate(text, min_literal=0):
    """Tokens the shell would expand onto the gate. Only a leading literal dot can
    match a dotfile; `min_literal` demands that many literals before the wildcard."""
    for tok in _TOKEN_SPLIT.split(text):
        name = os.path.basename(tok)
        if not name.startswith(".") or not fnmatch.fnmatch(GATE_NAME, name):
            continue
        wild = _GLOB_CHARS.search(name)
        if wild and wild.start() >= min_literal:
            return True
    return False


def bash_touches_gate(command):
    # Deny-by-default: any Bash command that so much as references the gate file is
    # blocked — the model has no legitimate need to touch the gate via Bash. Match
    # the raw command AND a quote-stripped form, so the shell's own quoting cannot
    # smuggle the name past a plain substring test.
    stripped = _SHELL_QUOTES.sub("", command)
    if GATE_NAME in command or GATE_NAME in stripped:
        return True
    # Globs do not expand inside quotes, and sweeping the quote-STRIPPED form read
    # every quoted `(.*?)` as one, denying ordinary greps and one-liners.
    if glob_hits_gate(_QUOTED_SPAN.sub(" ", command)):
        return True
    # Quotes closed early to split the name (`'.approval-gat'?`) survive that.
    return glob_hits_gate(stripped, min_literal=6)


def is_generated(fp):
    """A feature's state.json, or the phase-log.md rendered beside one."""
    directory = os.path.dirname(os.path.abspath(fp))
    if os.path.basename(os.path.dirname(directory)) != "features":
        return False
    name = os.path.basename(fp)
    if name == STATE_NAME:
        return True
    return name == LOG_NAME and os.path.isfile(os.path.join(directory, STATE_NAME))


def target_path(tool_input):
    """The file an edit-tool call writes: `file_path` for Edit/Write/MultiEdit,
    `notebook_path` for NotebookEdit."""
    return tool_input.get("file_path") or tool_input.get("notebook_path") or ""


def is_working_doc(fp, project_dir):
    """True if the path is a workflow doc (safe to edit even when locked)."""
    if not fp:
        return False
    if os.path.basename(fp) in WORKING_DOC_NAMES:
        return True
    try:
        state = os.path.abspath(os.path.join(project_dir, STATE_DIR))
        return os.path.commonpath([state, os.path.abspath(fp)]) == state
    except Exception:
        return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # can't parse -> fail open

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    # --- Protection 1: the model may never modify the gate file. ---
    if tool in EDIT_TOOLS:
        fp = target_path(tool_input)
        if fp and os.path.basename(fp) == GATE_NAME:
            deny(GATE_EDIT_MSG)
        if fp and is_generated(fp):
            deny(GENERATED_MSG)
    elif tool == "Bash":
        if bash_touches_gate(tool_input.get("command", "")):
            deny(GATE_EDIT_MSG)
        # NB: no early exit. Bash must fall through to the LOCKED check below —
        # returning here is what let a here-doc write source while LOCKED.

    # --- Protection 2: LOCKED blocks source edits AND all Bash. ---
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    gate_path = os.path.join(project_dir, GATE_NAME)
    if not os.path.isfile(gate_path):
        sys.exit(0)  # gate not activated

    try:
        with open(gate_path, "r", encoding="utf-8") as fh:
            state = ""
            for line in fh:
                if line.strip():
                    state = line.strip().upper()
                    break
    except Exception:
        sys.exit(0)  # unreadable -> fail open

    if state != "LOCKED":
        sys.exit(0)  # UNLOCKED or anything else -> allow

    # Locked: Bash can write source in too many ways to filter, so none of it runs.
    if tool == "Bash":
        deny(BASH_LOCKED_MSG)

    # Locked: still allow workflow docs so the log can be updated.
    if is_working_doc(target_path(tool_input), project_dir):
        sys.exit(0)

    deny(
        "Coding is LOCKED pending your approval of the current phase.\n"
        "Review the phase, then unlock from YOUR shell (Claude cannot do this):\n"
        "    ! echo UNLOCKED > .approval-gate\n"
        "Re-lock before the next phase with:\n"
        "    ! echo LOCKED > .approval-gate"
    )


if __name__ == "__main__":
    main()
