#!/usr/bin/env python3
"""Stop hook: evidence gate for the dev-workflow plugin.

Enforces "evidence-gated completion": when the orchestrator ends its turn with
the current phase marked reviewed but its Evidence ledger in phase-log.md still
empty, block and ask it to fill cited proof before yielding to the user for
approval — and KEEP blocking while the ledger stays empty.

Why not `stop_hook_active`: Claude Code sets that flag on any Stop that happens
*because* a stop hook blocked the previous one. Exiting on it meant the gate could
be defeated by simply stopping twice — block, change nothing, stop again, and the
phase sailed through with an empty ledger. That made the gate advisory. Instead we
count consecutive refusals for the current phase in our own state file, so
"unchanged" is met with another refusal.

The counter exists to bound the loop, not to be an escape hatch: a Stop hook that
can refuse forever can trap a turn with no way out, which is worse than the hole it
closes. So after MAX_BLOCKS refusals the gate yields — but says loudly that it is
giving up on an unproven phase, so this can never happen SILENTLY.

Safety: fail-open on any error; stays silent unless a dev-workflow phase-log is
active and a phase is in the specific reviewed-but-unproven state. Only gates the
main turn (Stop), never subagents.
"""
import json
import os
import re
import sys

import _workflow
import state as workflow_state
from _workflow import docs_dir, field_text, is_unfilled, iter_phases

REVIEW_DONE = re.compile(r"\[[xX]\]\s*(?:code-reviewed|full code review)")

# Consecutive refusals allowed for one phase before the gate yields to avoid
# trapping the turn. Enough to outlast a model that stops reflexively; small
# enough that a genuinely stuck turn escapes in seconds.
MAX_BLOCKS = 3
COUNTER_FILE = "evidence-gate.json"

# Counters live in _workflow (shared with the plan guard); these keep this hook's
# own signature — keyed PER phase and per feature, so two concurrent features never
# reset each other's budget.


def load_counter(root, key):
    return _workflow.load_counter(root, COUNTER_FILE, key)


def save_counter(root, key, count):
    return _workflow.save_counter(root, COUNTER_FILE, key, count)


def clear_counter(root, key):
    return _workflow.clear_counter(root, COUNTER_FILE, key)


def evidence_empty(body):
    """True if the section's `- Evidence:` field is missing, a placeholder, or too
    short to be real cited proof. The field-extraction rules (where a field ends,
    what counts as a placeholder) live in `_workflow`; the 15-character floor is
    this gate's own — "ok" is technically content but is not proof."""
    return is_unfilled(field_text(body, "Evidence"), min_len=workflow_state.MIN_EVIDENCE)


def current_section(log):
    """(title, body) of the first unapproved section, or None when all are approved."""
    return next(((title, body) for title, body, approved in iter_phases(log) if not approved),
                None)


def unproven(body):
    return bool(REVIEW_DONE.search(body)) and evidence_empty(body)


def unreadable(problem):
    print(json.dumps({"systemMessage": "[dev-workflow] %s — the workflow guards cannot "
                                       "check this feature until it is fixed." % problem}))
    sys.exit(0)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # can't parse -> fail open

    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    ddir, slug = docs_dir(root)
    try:
        log = workflow_state.log_text(ddir)
    except workflow_state.Corrupt as problem:
        unreadable(problem)
    if not log:
        sys.exit(0)  # no active workflow

    current = current_section(log)
    if current is None:
        sys.exit(0)  # every section is approved
    title, body = current
    current_key = f"{slug or ''}::{title}"
    if unproven(body):
        count = load_counter(root, current_key) + 1
        # Persist BEFORE deciding, including past the limit: forgetting the
        # count on give-up would re-arm the gate on the next stop, so it would
        # oscillate (block, block, block, pass, block...) instead of staying
        # given up — and the give-up warning would never survive to be seen.
        saved = save_counter(root, current_key, count)

        # Give up when the count reaches the bound — OR when we could not even
        # persist the count AND have already blocked once this turn (the flag
        # Claude Code sets on a stop that a hook blocked). The second clause is
        # the backstop: if `.dev-workflow/` is read-only or full, `count` is
        # pinned at 1 forever, so without it the gate would block on every stop
        # and trap the turn. It bounds a broken counter at one block.
        unproven_msg = json.dumps({"systemMessage":
            "[dev-workflow evidence gate] GAVE UP: '" + title + "' is marked "
            "reviewed but its Evidence ledger is still empty. Letting the turn "
            "end so it cannot be trapped — but this phase is UNPROVEN. Do not "
            "approve it on the strength of the summary alone."})
        if count > MAX_BLOCKS or (not saved and payload.get("stop_hook_active")):
            print(unproven_msg)
            sys.exit(0)

        block(
            "[dev-workflow evidence gate] '" + title + "' is marked "
            "reviewed but its Evidence ledger in phase-log.md is empty. Before "
            "yielding for the user's approval, fill this phase's `- Evidence:` line "
            "with CITED proof — test/command output, file:line, the concrete cases "
            "verified — mapping to each acceptance criterion (not \"looks fine\"). "
            "Run the tests and paste what they actually printed; if you cannot prove "
            "it, say so to the user instead of ending the turn. "
            f"(Refusal {count} of {MAX_BLOCKS}; stopping again without filling the "
            "ledger will simply be refused again.)"
        )

    # Reached only when the current phase is proven (or the feature is done): clear
    # just this phase's budget so a later re-emptying gets a fresh one.
    clear_counter(root, current_key)
    sys.exit(0)


if __name__ == "__main__":
    main()
