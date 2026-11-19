#!/usr/bin/env python3
"""`.dev-workflow/dw`: a project-local launcher for this plugin's dw.py."""
import os

from _workflow import STATE_DIR, read

SCRIPT = ('#!/bin/sh\n'
          'DEV_WORKFLOW_ROOT="$(cd "$(dirname "$0")/.." && pwd)" exec python3 "%s" "$@"\n')


def write(root):
    """Rewritten whenever the plugin's path changed; silent when it cannot be written."""
    try:
        if not os.path.isdir(os.path.join(root, STATE_DIR)):
            return
        cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dw.py")
        path = os.path.join(root, STATE_DIR, "dw")
        if read(path) != SCRIPT % cli:
            with open(path, "w", encoding="utf-8") as launcher:
                launcher.write(SCRIPT % cli)
        os.chmod(path, 0o755)
    except OSError:
        pass
