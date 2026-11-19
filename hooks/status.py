#!/usr/bin/env python3
"""SessionStart hook for the dev-workflow plugin.

Re-surfaces the workflow's file-based source of truth into context at the start
of every session (including resume and post-compact), so the current phase and
approval state are not lost to context rot. Prints a short status block to
stdout (which SessionStart injects into context). Stays SILENT when no workflow
is active (no phase-log.md), so it never adds noise to unrelated sessions.
"""
import json
import os
import re
import sys
import tempfile

import shim
import state as workflow_state
from _workflow import STATE_DIR, docs_dir, iter_phases, read

# Ensure UTF-8 output regardless of the host locale (Windows pipes default to
# cp1252, which mangles em dashes and other non-ASCII in feature names).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def read_input():
    """Return (project_dir, source). `source` is the SessionStart trigger —
    "startup" | "resume" | "clear" | "compact" — used to tailor the reminder."""
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        pass
    source = ""
    cwd = ""
    if raw.strip():
        try:
            data = json.loads(raw) or {}
            source = data.get("source", "") or ""
            cwd = data.get("cwd", "") or ""
        except Exception:
            pass
    root = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
    return root, source


def title_from(text, prefix):
    if not text:
        return None
    m = re.search(r"^#\s*" + re.escape(prefix) + r"\s*(.+)$", text, re.MULTILINE)
    if m:
        name = m.group(1).strip()
        return None if name.startswith("<") else name
    return None


def registry_path():
    return os.path.expanduser("~/.claude/dev-workflow/projects.json")


def registered():
    """Project roots that have started a session with the plugin; [] if unreadable."""
    raw = read(registry_path())
    if not raw:
        return []
    try:
        roots = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(roots, list):
        return []
    return [root for root in roots if isinstance(root, str)]


def register(root):
    # Silent on any failure: this hook's stdout is Claude's context, and HOME may be unwritable.
    try:
        if not os.path.isdir(os.path.join(root, STATE_DIR)):
            return
        project = os.path.realpath(root)
        known = registered()
        if project not in known:
            write_registry(known + [project])
    except Exception:
        pass


def write_registry(roots):
    path = registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".projects-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(roots, fh, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        os.remove(tmp_path)
        raise


def main():
    root, source = read_input()
    register(root)
    shim.write(root)
    ddir, slug = docs_dir(root)
    try:
        log = workflow_state.log_text(ddir)
    except workflow_state.Corrupt as problem:
        print("[dev-workflow] %s — the workflow hooks cannot see this feature until it is "
              "fixed." % problem)
        sys.exit(0)
    if not log:
        sys.exit(0)  # no active workflow -> stay silent

    feature = (title_from(log, "Phase log:")
               or title_from(read(os.path.join(ddir, "spec.md")) or "", "Spec:")
               or slug or "(unnamed)")

    # Phase headings (and the Final review section) and their approval state.
    phases = [(title, approved) for title, _body, approved in iter_phases(log)]
    current = next((name for name, ok in phases if not ok), None)

    gate = read(os.path.join(root, ".approval-gate"))
    if gate is None:
        gate_state = "no gate file"
    else:
        first = next((l.strip() for l in gate.splitlines() if l.strip()), "")
        gate_state = first.upper() or "empty"

    lines = []
    if source == "compact":
        # Context was just compacted; the summary may have dropped workflow state.
        lines.append("[dev-workflow] Context was just compacted — summarized memory "
                     "may have lost workflow state. The files below are the source of "
                     "truth; re-read them before acting.")
    lines.append("[dev-workflow] Active feature: " + feature)
    if phases:
        done = sum(1 for _, ok in phases if ok)
        lines.append(f"  Phases: {done}/{len(phases)} approved"
                     + (f"; current -> {current}" if current else "; all approved"))
    lines.append(f"  Approval gate: {gate_state}")
    lines.append("  Source of truth: spec.md / plan.md / phase-log.md "
                 "(re-read these, not conversation memory).")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
