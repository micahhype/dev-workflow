#!/usr/bin/env python3
"""UserPromptSubmit / UserPromptExpansion hook: the two things only the user's own input can do.

UserPromptSubmit stamps when the user last spoke, which a relayed approval is checked against.
UserPromptExpansion fires only for a command the user typed, so `/dev-workflow:approve` is
recorded here as a direct approval; Claude calling the command does not reach this hook.
"""
import json
import os
import sys

import approval
import state as workflow_state
from _workflow import STATE_DIR, docs_dir

APPROVE_COMMAND = "dev-workflow:approve"
FALLBACK = "Run `! .dev-workflow/dw approve` in your own shell instead."


def approve_directly(root, wanted):
    """-> what happened, as a sentence for Claude to relay."""
    directory, slug = docs_dir(root)
    if slug is None:
        return "No approval recorded: there is no active feature."
    state = workflow_state.load(directory)
    if state is None:
        return ("No approval recorded by the hook: %s has no state.json. The user typed "
                "/dev-workflow:approve, so tick `[x] USER APPROVED` for the current phase "
                "in phase-log.md." % slug)
    waiting = [phase for phase in workflow_state.sections(state) if phase["status"] != "approved"]
    if not waiting:
        return "No approval recorded: every phase of %s is already approved." % slug
    target = target_of(wanted) or waiting[0]["id"]
    event = {"by": "user", "do": "approve", "phase": target}
    try:
        workflow_state.update(
            directory, lambda state: workflow_state.approve(state, target, {"via": "user"}), event)
    except workflow_state.Refused as refusal:
        return "No approval recorded: %s" % refusal
    return "The user's approval is recorded for %s of %s (via user)." % (
        "the final review" if target == workflow_state.FINAL else "phase %s" % target, slug)


def target_of(wanted):
    word = wanted.strip().split()[0] if wanted.strip() else ""
    if word == workflow_state.FINAL:
        return word
    return int(word) if word.isdigit() else None


def main():
    payload = json.load(sys.stdin)
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    if not os.path.isdir(os.path.join(root, STATE_DIR)):
        return
    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit" and approval.is_from_the_user(payload.get("prompt") or ""):
        approval.stamp(root)
    if event == "UserPromptExpansion" and payload.get("command_name") == APPROVE_COMMAND:
        try:
            outcome = approve_directly(root, payload.get("command_args") or "")
        except Exception as problem:
            outcome = "No approval recorded: %s. %s" % (problem, FALLBACK)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                                 "additionalContext": "[dev-workflow] " + outcome}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
