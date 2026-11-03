#!/usr/bin/env python3
"""CLI behind /dev-workflow:config — the effective configuration, and where it came from.

Not a hook; nothing in hooks.json runs this. It is invoked by the `config` skill.

The plugin's knobs live in four JSON files, two environment variables and a gate
file, and every one of them fails SILENTLY. `comment_guard.load_config`,
`test_guard.load_config` and the feature skill's read of `models.json` all swallow a
parse error and return defaults, deliberately: a malformed preference must never
crash an edit or trap a turn. The cost is that a stray comma disables nothing, warns
nobody, and leaves the project believing it configured something. That is the hole
this fills — `show` is mostly a report about the DIFFERENCE between what the file
says and what the guards actually do.

Defaults are never restated here. This module IMPORTS the guards and reads their own
constants and their own `load_config`, so a report that disagrees with the running
hook is not possible. Agent names and their default models are likewise scraped from
`agents/*.md` frontmatter rather than copied.

  python3 config.py show
  python3 config.py set <key> <value>     e.g. comment-guard.density.floor 4
  python3 config.py set <key> default     drop the key, return to the default
"""
import glob
import json
import os
import re
import sys

import comment_guard
import plan_guard
import test_guard

STATE_DIR = ".dev-workflow"
GATE_NAME = ".approval-gate"
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_ALIASES = ("opus", "sonnet", "haiku", "fable", "inherit")
BOOL_WORDS = {"on": True, "true": True, "yes": True, "1": True,
              "off": False, "false": False, "no": False, "0": False}


# --- reading ----------------------------------------------------------------

def read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def read_json(path):
    """-> (obj, problem). `obj` is {} when the file is missing OR unusable, which
    mirrors what the guards do; `problem` is what to tell the user about it."""
    raw = read(path)
    if raw is None:
        return {}, None
    if not raw.strip():
        return {}, "the file is empty"
    try:
        obj = json.loads(raw)
    except Exception as exc:
        return {}, "invalid JSON — %s" % exc
    if not isinstance(obj, dict):
        return {}, "the top level is %s, not an object" % type(obj).__name__
    return obj, None


def agents():
    """-> [(name, default_model)] from the plugin's own agent frontmatter."""
    found = []
    for path in sorted(glob.glob(os.path.join(PLUGIN_ROOT, "agents", "*.md"))):
        head = (read(path) or "")[:800]
        name = re.search(r"^name:\s*(\S+)", head, re.MULTILINE)
        model = re.search(r"^model:\s*(\S+)", head, re.MULTILINE)
        if name:
            found.append((name.group(1), model.group(1) if model else "inherit"))
    return found


def env_off(var):
    return (os.environ.get(var) or "").strip().lower() in ("off", "0", "false", "no")


# --- shaping ----------------------------------------------------------------

def dig(obj, path):
    """-> (value, present). `present` says the key was written, not that it is valid."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None, False
        cur = cur[key]
    return cur, True


def fmt(value):
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return "(none)" if not value else " | ".join(str(v) for v in value)
    if isinstance(value, float):
        return ("%g" % value) if value else "0"
    return str(value)


class Knob:
    def __init__(self, label, path, effective, default):
        self.label = label
        self.path = path
        self.effective = effective
        self.default = default


def source_of(knob, raw, env_var):
    """Where the running value came from — the question no file can answer alone.
    "file, IGNORED" = the key was written and the value is the default anyway."""
    if env_var and knob.label == "enabled" and env_off(env_var):
        return "env " + env_var
    val, present = dig(raw, knob.path)
    if not present:
        return "default"
    if val != knob.effective:
        return "file, IGNORED"
    return "file"


def load_past_env(module, var, root):
    """The config the FILE yields, ignoring the env kill switch that would otherwise
    short-circuit load_config into returning defaults without ever reading it."""
    saved = os.environ.pop(var, None)
    try:
        return module.load_config(root)
    finally:
        if saved is not None:
            os.environ[var] = saved


def comment_section(root):
    cfg = load_past_env(comment_guard, "DEV_WORKFLOW_COMMENT_GUARD", root)
    if env_off("DEV_WORKFLOW_COMMENT_GUARD"):
        cfg["enabled"] = False
    return [
        Knob("enabled", ["enabled"], cfg["enabled"], True),
        Knob("density.floor", ["density", "floor"], cfg["floor"], comment_guard.FLOOR),
        Knob("density.min_ratio", ["density", "min_ratio"], cfg["min_ratio"],
             comment_guard.MIN_RATIO),
        Knob("max_block", ["max_block"], cfg["max_block"], comment_guard.MAX_BLOCK),
        Knob("allow", ["allow"], [p.pattern for p in cfg["allow"]], []),
    ]


def test_section(root):
    cfg = load_past_env(test_guard, "DEV_WORKFLOW_TEST_GUARD", root)
    if env_off("DEV_WORKFLOW_TEST_GUARD"):
        cfg["enabled"] = False
    return [
        Knob("enabled", ["enabled"], cfg["enabled"], True),
        Knob("checks.fakes", ["checks", "fakes"], cfg["checks"]["fakes"], True),
        Knob("checks.assertions", ["checks", "assertions"],
             cfg["checks"]["assertions"], True),
        Knob("max_empty_args", ["max_empty_args"], cfg["max_empty_args"],
             test_guard.MAX_EMPTY_ARGS),
        Knob("allow", ["allow"], [p.pattern for p in cfg["allow"]], []),
    ]


def plan_section(root):
    cfg = plan_guard.load_config(root)
    return [Knob("pr_cap", ["pr_cap"], cfg["pr_cap"], plan_guard.PR_CAP)]


# --- problems ---------------------------------------------------------------
# Everything a guard shrugs off in silence. Each entry is (severity, text) where
# severity "!" means the file is not doing what it looks like it does.

def check_common(problems, label, raw, problem, knobs, env_var):
    if problem:
        problems.append(("!", "%s — %s. Every value below is a DEFAULT; the file is "
                              "being ignored in full." % (label, problem)))
        return
    known = set()
    for knob in knobs:
        known.add(knob.path[0])
    for key in raw:
        if key not in known:
            problems.append(("?", "%s — unknown key %r, silently ignored. Known keys: %s"
                             % (label, key, ", ".join(sorted(known)))))
    for knob in knobs:
        val, present = dig(raw, knob.path)
        if not present:
            continue
        if isinstance(knob.default, bool) and not isinstance(val, bool):
            problems.append(("!", "%s — %s is %r, a %s. Only the literal JSON true/false "
                                  "counts here, so this line does nothing."
                             % (label, knob.label, val, type(val).__name__)))
        elif isinstance(knob.default, list) and not isinstance(val, list):
            problems.append(("!", "%s — %s must be a list of patterns; %r is ignored."
                             % (label, knob.label, val)))
    for pat in raw.get("allow") or []:
        try:
            re.compile(pat)
        except Exception as exc:
            problems.append(("!", "%s — allow pattern %r does not compile (%s) and is "
                                  "dropped; the rest of the list still applies."
                             % (label, pat, exc)))
    if env_var and env_off(env_var):
        problems.append(("i", "%s — %s is set, which is checked FIRST and returns "
                              "immediately. Nothing in the file can switch it back on."
                         % (label, env_var)))


def check_models(problems, raw, problem, known):
    label = "models.json"
    if problem:
        problems.append(("!", "%s — %s. Every agent is running its default model."
                         % (label, problem)))
        return
    for key, val in raw.items():
        if key.startswith("_"):
            continue
        if key not in known:
            problems.append(("?", "%s — %r is not an agent in this plugin, so the line "
                                  "does nothing. Agents: %s"
                             % (label, key, ", ".join(sorted(known)))))
        if not isinstance(val, str) or not (
                val in MODEL_ALIASES or val.startswith("claude-")):
            problems.append(("?", "%s — %r for %r is not an alias (%s), a claude-* model "
                                  "id, or inherit."
                             % (label, val, key, "/".join(MODEL_ALIASES))))


# --- show -------------------------------------------------------------------

def render_section(out, title, path, knobs, raw, env_var):
    out.append("")
    out.append("  %-22s %s" % (title, path))
    for knob in knobs:
        src = source_of(knob, raw, env_var)
        mark = " " if src == "default" else "<"
        out.append("    %-20s %-26s %s %s"
                   % (knob.label, fmt(knob.effective), mark, src))


def show(root):
    out = []
    problems = []

    cg_path = os.path.join(root, STATE_DIR, "comment-guard.json")
    tg_path = os.path.join(root, STATE_DIR, "test-guard.json")
    pg_path = os.path.join(root, STATE_DIR, plan_guard.CONFIG_NAME)
    md_path = os.path.join(root, STATE_DIR, "models.json")

    cg_raw, cg_problem = read_json(cg_path)
    tg_raw, tg_problem = read_json(tg_path)
    pg_raw, pg_problem = read_json(pg_path)
    md_raw, md_problem = read_json(md_path)

    cg_knobs = comment_section(root)
    tg_knobs = test_section(root)
    pg_knobs = plan_section(root)

    check_common(problems, "comment-guard.json", cg_raw, cg_problem, cg_knobs,
                 "DEV_WORKFLOW_COMMENT_GUARD")
    check_common(problems, "test-guard.json", tg_raw, tg_problem, tg_knobs,
                 "DEV_WORKFLOW_TEST_GUARD")
    check_common(problems, "plan-guard.json", pg_raw, pg_problem, pg_knobs, None)

    agent_list = agents()
    check_models(problems, md_raw, md_problem, {a for a, _ in agent_list})

    out.append("dev-workflow config — %s" % root)

    if problems:
        out.append("")
        out.append("  PROBLEMS")
        for mark, text in problems:
            out.append("    %s %s" % (mark, text))

    render_section(out, "comment guard", ".dev-workflow/comment-guard.json",
                   cg_knobs, cg_raw, "DEV_WORKFLOW_COMMENT_GUARD")
    render_section(out, "test guard", ".dev-workflow/test-guard.json",
                   tg_knobs, tg_raw, "DEV_WORKFLOW_TEST_GUARD")
    render_section(out, "plan guard", ".dev-workflow/plan-guard.json",
                   pg_knobs, pg_raw, None)

    out.append("")
    out.append("  %-22s %s" % ("agent models", ".dev-workflow/models.json"))
    for name, default in agent_list:
        override = md_raw.get(name) if not md_problem else None
        effective = override if isinstance(override, str) else default
        mark = " " if override is None else "<"
        out.append("    %-20s %-26s %s %s"
                   % (name, effective, mark, "default" if override is None else "file"))

    gate = read(os.path.join(root, GATE_NAME))
    if gate is None:
        gate_state = "not set (gate is off)"
    else:
        first = next((l.strip() for l in gate.splitlines() if l.strip()), "")
        gate_state = first.upper() or "empty file"
    active = read(os.path.join(root, STATE_DIR, "active"))
    slug = next((l.strip() for l in (active or "").splitlines() if l.strip()), "")

    out.append("")
    out.append("  %-22s %s" % ("workflow state", "not configuration"))
    out.append("    %-20s %-26s   %s" % ("approval gate", gate_state, GATE_NAME))
    out.append("    %-20s %-26s   %s"
               % ("active feature", slug or "(none)", ".dev-workflow/active"))
    return "\n".join(out)


# --- set --------------------------------------------------------------------

TARGETS = {
    "comment-guard": ("comment-guard.json", {
        "enabled": (["enabled"], bool),
        "density.floor": (["density", "floor"], int),
        "density.min_ratio": (["density", "min_ratio"], float),
        "max_block": (["max_block"], int),
    }),
    "test-guard": ("test-guard.json", {
        "enabled": (["enabled"], bool),
        "checks.fakes": (["checks", "fakes"], bool),
        "checks.assertions": (["checks", "assertions"], bool),
        "max_empty_args": (["max_empty_args"], int),
    }),
    "plan-guard": ("plan-guard.json", {"pr_cap": (["pr_cap"], int)}),
}

SECTIONS = {"comment-guard": comment_section, "test-guard": test_section,
            "plan-guard": plan_section}


def coerce(value, kind):
    if kind is bool:
        if value.lower() not in BOOL_WORDS:
            raise ValueError("expected on/off, got %r" % value)
        return BOOL_WORDS[value.lower()]
    if kind is int:
        return int(value)
    if kind is float:
        return float(value)
    return value


def prune(obj, path, defaults):
    """Drop the key at `path`, then any container it leaves empty. Config here is a
    diff against the defaults, so a value equal to its default is not written."""
    cur = obj
    for key in path[:-1]:
        if not isinstance(cur.get(key), dict):
            return
        cur = cur[key]
    cur.pop(path[-1], None)
    if len(path) > 1 and not obj.get(path[0]):
        obj.pop(path[0], None)


def default_for(root, group, key):
    for knob in SECTIONS[group](root):
        if knob.label == key:
            return knob.default
    return None


def set_value(root, dotted, value):
    parts = dotted.split(".", 1)
    if len(parts) != 2:
        return "Not a key: %r. Try comment-guard.density.floor, test-guard.checks.fakes, plan-guard.pr_cap, or models.coder." % dotted
    group, key = parts

    if group == "models":
        return set_model(root, key, value)
    if group not in TARGETS:
        return "Unknown group %r. Groups: comment-guard, test-guard, plan-guard, models." % group

    fname, keys = TARGETS[group]
    if key not in keys:
        return "Unknown key %r for %s. Keys: %s" % (key, group, ", ".join(sorted(keys)))

    path, kind = keys[key]
    file_path = os.path.join(root, STATE_DIR, fname)
    raw, problem = read_json(file_path)
    if problem:
        return ("Refusing to write: %s is unusable (%s). Fix or delete it first — "
                "overwriting would throw away whatever is in there." % (fname, problem))

    if value.lower() == "default":
        prune(raw, path, None)
        note = "%s.%s -> default" % (group, key)
    else:
        try:
            parsed = coerce(value, kind)
        except ValueError as exc:
            return "Bad value for %s: %s" % (dotted, exc)
        if parsed == default_for(root, group, key):
            prune(raw, path, None)
            note = "%s.%s -> %s (the default, so the key is omitted)" % (group, key, value)
        else:
            cur = raw
            for part in path[:-1]:
                if not isinstance(cur.get(part), dict):
                    cur[part] = {}
                cur = cur[part]
            cur[path[-1]] = parsed
            note = "%s.%s -> %s" % (group, key, json.dumps(parsed))

    return write_json(file_path, raw, note)


def set_model(root, agent, value):
    known = dict(agents())
    if agent not in known:
        return "Unknown agent %r. Agents: %s" % (agent, ", ".join(sorted(known)))
    if value != "default" and not (value in MODEL_ALIASES or value.startswith("claude-")):
        return ("Bad model %r. Use one of %s, a claude-* model id, or 'default'."
                % (value, "/".join(MODEL_ALIASES)))

    file_path = os.path.join(root, STATE_DIR, "models.json")
    raw, problem = read_json(file_path)
    if problem:
        return ("Refusing to write: models.json is unusable (%s). Fix or delete it "
                "first — overwriting would throw away whatever is in there." % problem)

    if value == "default":
        raw.pop(agent, None)
        note = "models.%s -> default (%s)" % (agent, known[agent])
    else:
        raw[agent] = value
        note = "models.%s -> %s" % (agent, value)
    return write_json(file_path, raw, note)


def write_json(path, obj, note):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except Exception as exc:
        return "Could not write %s: %s" % (path, exc)
    rel = os.path.basename(path)
    if not obj:
        return "%s\n%s is now empty — every value is the default." % (note, rel)
    return "%s\n%s now reads:\n%s" % (note, rel, json.dumps(obj, indent=2, sort_keys=True))


# --- entry ------------------------------------------------------------------

USAGE = ("usage: config.py show\n"
         "       config.py set <key> <value>\n"
         "keys:  comment-guard.enabled | comment-guard.density.floor |\n"
         "       comment-guard.density.min_ratio | comment-guard.max_block |\n"
         "       test-guard.enabled |\n"
         "       test-guard.checks.fakes | test-guard.checks.assertions |\n"
         "       test-guard.max_empty_args | plan-guard.pr_cap | models.<agent>\n"
         "value: on | off | a number | a model alias | default")


def main(argv):
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    cmd = argv[1] if len(argv) > 1 else "show"

    if cmd == "show":
        print(show(root))
        return 0
    if cmd == "set":
        if len(argv) != 4:
            print(USAGE)
            return 2
        print(set_value(root, argv[2], argv[3]))
        return 0
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
