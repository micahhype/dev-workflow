#!/usr/bin/env python3
"""The current phase's diff: its size against the plan, and the file a reviewer reads.

Both are measured from a baseline tree recorded at each Stop."""
import json
import os
import re

import _workflow
import checkpoint

STATE_FILE = "diff-budget.json"
REVIEWED_FILE = "review-diff.json"
PHASE_NUMBER = re.compile(r"Phase\s+(\d+)")
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def state_path(root, name=STATE_FILE):
    return os.path.join(root, _workflow.STATE_DIR, name)


def load(root, name=STATE_FILE):
    data = _workflow.read(state_path(root, name))
    try:
        state = json.loads(data) if data else {}
    except ValueError:
        return {}
    return state if isinstance(state, dict) else {}


def save(root, state, name=STATE_FILE):
    os.makedirs(os.path.join(root, _workflow.STATE_DIR), exist_ok=True)
    with open(state_path(root, name), "w", encoding="utf-8") as fh:
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


def phase_base(root, key, number):
    """The tree phase `number` started from, or None when no Stop recorded one."""
    seen = load(root).get(key)
    if not isinstance(seen, dict):
        return None
    recorded = PHASE_NUMBER.match(seen.get("phase") or "")
    if recorded and int(recorded.group(1)) == number:
        return seen.get("base")
    return seen.get("last")


def last_reviewed(root, key, number):
    """The tree the previous review diff of this phase ended at, or None."""
    seen = load(root, REVIEWED_FILE).get(key)
    if isinstance(seen, dict) and seen.get("phase") == number:
        return seen.get("tree")
    return None


def remember_reviewed(root, key, number, tree):
    state = load(root, REVIEWED_FILE)
    state[key] = {"phase": number, "tree": tree}
    save(root, state, REVIEWED_FILE)


def patch(root, base, now):
    """-> (unified diff text, [(added, deleted, path)]) between two trees."""
    _rc, rows = checkpoint.git(root, ["diff", "--numstat", base, now])
    _rc, text = checkpoint.git(root, ["diff", "--no-color", "--no-ext-diff", base, now])
    files = [tuple(row.split("\t", 2)) for row in rows.splitlines() if row.count("\t") >= 2]
    return text, files
