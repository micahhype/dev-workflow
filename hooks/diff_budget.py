#!/usr/bin/env python3
"""Lines the current phase has changed, measured from a baseline recorded at each Stop."""
import json
import os

import _workflow
import checkpoint

STATE_FILE = "diff-budget.json"


def state_path(root):
    return os.path.join(root, _workflow.STATE_DIR, STATE_FILE)


def load(root):
    data = _workflow.read(state_path(root))
    try:
        state = json.loads(data) if data else {}
    except ValueError:
        return {}
    return state if isinstance(state, dict) else {}


def save(root, state):
    os.makedirs(os.path.join(root, _workflow.STATE_DIR), exist_ok=True)
    with open(state_path(root), "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def measure(root, key, phase, coded):
    """Writes git objects, so only the Stop hook calls it — never the dashboard."""
    if not checkpoint.is_git_repo(root):
        return None
    _head, now = checkpoint.working_tree(root)
    state = load(root)
    seen = state.get(key) if isinstance(state.get(key), dict) else {}
    if not coded:
        base = now
    elif seen.get("phase") == phase:
        base = seen.get("base")
    else:
        # Approved and the next phase coded in one turn: it began where the last Stop left off.
        base = seen.get("last")
    lines = changed_lines(root, base, now) if base else None
    state[key] = {"phase": phase, "base": base, "last": now, "lines": lines}
    save(root, state)
    return lines


def changed_lines(root, base, now):
    _rc, out = checkpoint.git(root, ["diff", "--numstat", base, now])
    total = 0
    for row in out.splitlines():
        added, deleted = row.split("\t")[:2]
        if added.isdigit() and deleted.isdigit():  # binary files report "-"
            total += int(added) + int(deleted)
    return total
