#!/usr/bin/env python3
"""How an approval may arrive, and when the user last spoke."""
import json
import os
import time

from _workflow import STATE_DIR, read

CONFIG_NAME = "approval.json"
STAMP_NAME = "user-prompt.json"
MODES = ("relayed", "direct")
MODE = "relayed"
MACHINE_MARKS = ("<task-notification>", "<agent-message")


def load_config(root):
    """{'mode'}: the default on any problem, so a broken file never widens the routes."""
    try:
        written = json.loads(read(os.path.join(root, STATE_DIR, CONFIG_NAME)) or "{}")
    except ValueError:
        return {"mode": MODE}
    mode = written.get("mode") if isinstance(written, dict) else None
    return {"mode": mode if mode in MODES else MODE}


def is_from_the_user(prompt):
    """False for the turns Claude Code starts itself, such as a background agent reporting back."""
    return bool(prompt.strip()) and not any(mark in prompt for mark in MACHINE_MARKS)


def stamp(root):
    with open(os.path.join(root, STATE_DIR, STAMP_NAME), "w", encoding="utf-8") as target:
        json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, target)


def prompted_at(root):
    try:
        return json.loads(read(os.path.join(root, STATE_DIR, STAMP_NAME)) or "{}").get("at")
    except (ValueError, AttributeError):
        return None
