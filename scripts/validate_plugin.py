#!/usr/bin/env python3
"""Static validator for the dev-workflow Claude Code plugin.

Mimics what the plugin loader expects so structural / frontmatter / JSON
problems are caught in CI before anyone runs `/plugin install`.

Usage: python scripts/validate_plugin.py [PLUGIN_ROOT]   (default: ".")
Exit code 0 = PASS, 1 = FAIL.
"""
import glob
import json
import os
import re
import shutil
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
errors = []
warnings = []
ok = []

MODEL_ALLOWED = {
    "inherit", "opus", "sonnet", "haiku", "fable",
    "claude-opus-5-5", "claude-opus-4-8", "claude-sonnet-5",
    "claude-haiku-4-5-20251001", "claude-fable-5-1", "claude-fable-5",
}
KNOWN_TOOLS = {"Read", "Grep", "Glob", "Edit", "Write", "MultiEdit", "Bash",
               "WebSearch", "WebFetch", "Task", "NotebookEdit"}
KNOWN_HOOK_EVENTS = {
    "PreToolUse", "PostToolUse", "PostToolBatch", "UserPromptSubmit", "UserPromptExpansion",
    "SessionStart", "SessionEnd", "Stop", "SubagentStart", "SubagentStop",
    "PreCompact", "PostCompact", "Notification",
}


def parse_frontmatter(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---"):
        return None, "no YAML frontmatter (must start with ---)"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "frontmatter not closed with ---"
    fm = {}
    for line in parts[1].strip().splitlines():
        if not line.strip() or line.strip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.strip()
    return fm, None


def check_json(path, required_top):
    full = os.path.join(ROOT, path)
    if not os.path.isfile(full):
        errors.append(f"MISSING FILE: {path}")
        return None
    try:
        data = json.load(open(full, encoding="utf-8"))
    except Exception as e:
        errors.append(f"INVALID JSON: {path}: {e}")
        return None
    for key in required_top:
        if key not in data:
            errors.append(f"{path}: missing required key '{key}'")
    ok.append(f"JSON valid: {path}")
    return data


def resolve_hook_script(command):
    """Extract a ${CLAUDE_PLUGIN_ROOT}-relative script path from a hook command."""
    m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}([^\"']+)", command)
    if not m:
        return None
    rel = m.group(1).lstrip("/\\").strip().strip('"')
    return rel


def check_interpreter(cmd):
    """The interpreter a hook names must actually exist on PATH.

    Hooks fail open, so an unlaunchable interpreter disables the approval gate,
    the checkpoints and the evidence gate SILENTLY. `python` in particular does
    not exist on macOS or on a stock Debian/Ubuntu/Fedora box — only `python3`
    is portable — and a CI runner that happens to provide both hides this.
    """
    interp = cmd.split(None, 1)[0] if cmd.split() else ""
    if not interp or interp.startswith("$"):
        return
    if interp == "python":
        errors.append(
            f"hooks.json: command invokes `python`, which does not exist on macOS "
            f"or a stock Linux box — use `python3`: {cmd}")
    elif shutil.which(interp) is None:
        warnings.append(f"hooks.json: interpreter '{interp}' not found on PATH: {cmd}")


# --- plugin.json ---
check_json(".claude-plugin/plugin.json", ["name", "description"])

# --- marketplace.json ---
mkt = check_json(".claude-plugin/marketplace.json", ["name", "owner", "plugins"])
if mkt:
    if not isinstance(mkt.get("owner"), dict):
        errors.append("marketplace.json: 'owner' must be an object")
    for i, p in enumerate(mkt.get("plugins", [])):
        for key in ("name", "source"):
            if key not in p:
                errors.append(f"marketplace.json: plugins[{i}] missing '{key}'")

# --- hooks.json ---
hooks_path = os.path.join(ROOT, "hooks/hooks.json")
if os.path.isfile(hooks_path):
    hj = check_json("hooks/hooks.json", ["hooks"])
    if hj:
        events = hj.get("hooks")
        if not isinstance(events, dict):
            errors.append("hooks.json: top-level 'hooks' must be a record, e.g. "
                          "{\"hooks\": {\"PreToolUse\": [...]}}")
            events = {}
        for evt, arr in events.items():
            if evt not in KNOWN_HOOK_EVENTS:
                warnings.append(f"hooks.json: unknown hook event '{evt}'")
            for entry in arr:
                for h in entry.get("hooks", []):
                    cmd = h.get("command", "")
                    check_interpreter(cmd)
                    rel = resolve_hook_script(cmd)
                    if rel:
                        if not os.path.isfile(os.path.join(ROOT, rel)):
                            errors.append(f"hooks.json: referenced script not found: {rel}")
                    elif "${CLAUDE_PLUGIN_ROOT}" not in cmd:
                        warnings.append(f"hooks.json: command may not resolve portably: {cmd}")
        ok.append("hooks.json: events + referenced scripts + interpreters checked")


def lint_frontmatter_file(path, kind, require_desc=True):
    rel = os.path.relpath(path, ROOT)
    fm, err = parse_frontmatter(path)
    if err:
        # commands may legitimately have no frontmatter
        if kind == "command":
            ok.append(f"command OK (no frontmatter): {rel}")
            return
        errors.append(f"{rel}: {err}")
        return
    if kind in ("agent", "skill") and "name" not in fm:
        errors.append(f"{rel}: frontmatter missing 'name'")
    if require_desc and "description" not in fm:
        (errors if kind != "command" else warnings).append(
            f"{rel}: frontmatter missing 'description'")
    if "model" in fm and fm["model"] not in MODEL_ALLOWED:
        warnings.append(f"{rel}: model '{fm['model']}' not in known set")
    if "tools" in fm:
        for t in [t.strip() for t in fm["tools"].strip("[]").split(",") if t.strip()]:
            if t not in KNOWN_TOOLS:
                warnings.append(f"{rel}: unknown tool '{t}'")
    ok.append(f"{kind} OK: {rel} (name={fm.get('name', '-')}, model={fm.get('model', 'inherit')})")


for path in sorted(glob.glob(os.path.join(ROOT, "agents", "*.md"))):
    lint_frontmatter_file(path, "agent")
for path in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))):
    lint_frontmatter_file(path, "skill")
for path in sorted(glob.glob(os.path.join(ROOT, "commands", "*.md"))):
    lint_frontmatter_file(path, "command", require_desc=False)

# --- report ---
print("== PASSED ==")
for x in ok:
    print("  [ok]", x)
if warnings:
    print("\n== WARNINGS ==")
    for x in warnings:
        print("  [warn]", x)
if errors:
    print("\n== ERRORS ==")
    for x in errors:
        print("  [ERR]", x)
    print(f"\nRESULT: FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
    sys.exit(1)
print(f"\nRESULT: PASS (0 errors, {len(warnings)} warning(s))")
