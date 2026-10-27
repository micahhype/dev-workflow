"""Config report: the effective value, where it came from, and — the reason this
exists — which config lines the guards are silently ignoring."""
import json
import os
import subprocess
import sys

import pytest
from conftest import HOOKS

sys.path.insert(0, HOOKS)
import config  # noqa: E402


def run(project_dir, *args, **envextra):
    env = os.environ.copy()
    env.pop("DEV_WORKFLOW_COMMENT_GUARD", None)
    env.pop("DEV_WORKFLOW_TEST_GUARD", None)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env.update(envextra)
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS, "config.py")] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def write_cfg(root, name, body):
    d = root / ".dev-workflow"
    d.mkdir(exist_ok=True)
    (d / name).write_text(body if isinstance(body, str) else json.dumps(body, indent=2))


def read_cfg(root, name):
    return json.loads((root / ".dev-workflow" / name).read_text())


def line_for(out, key, section=None):
    """The report row for a knob, so assertions read like the terminal does.
    Both guards have an `enabled` and an `allow`, so a row is only unambiguous
    together with the section heading above it."""
    current = None
    for line in out.splitlines():
        if line.startswith("    ") and line.strip():
            if line.strip().startswith(key + " ") and section in (None, current):
                return " ".join(line.split())
        elif line.startswith("  ") and line.strip():
            current = line.strip().split("  ")[0]
    return ""


# --- the report agrees with the guards -------------------------------------

def test_defaults_are_taken_from_the_guards_not_restated(tmp_path):
    """The one invariant that matters: this tool imports the hooks rather than
    keeping its own copy of their defaults, so the two cannot drift apart."""
    import comment_guard
    import test_guard
    out = run(tmp_path, "show").stdout
    assert line_for(out, "density.floor") == "density.floor %s default" % comment_guard.FLOOR
    assert line_for(out, "max_empty_args") == "max_empty_args %s default" % test_guard.MAX_EMPTY_ARGS


def test_a_clean_project_reports_everything_as_default(tmp_path):
    out = run(tmp_path, "show").stdout
    assert "PROBLEMS" not in out
    assert "file" not in out.replace(".dev-workflow", "").replace("config file", "")


def test_agents_and_their_models_come_from_the_plugins_own_frontmatter(tmp_path):
    out = run(tmp_path, "show").stdout
    for name, model in config.agents():
        assert line_for(out, name) == "%s %s default" % (name, model)
    assert len(config.agents()) >= 6


# --- provenance -------------------------------------------------------------

def test_a_real_override_is_attributed_to_the_file(tmp_path):
    write_cfg(tmp_path, "comment-guard.json", {"density": {"floor": 4}})
    out = run(tmp_path, "show").stdout
    assert line_for(out, "density.floor") == "density.floor 4 < file"


def test_the_env_switch_is_named_as_the_source(tmp_path):
    out = run(tmp_path, "show", DEV_WORKFLOW_TEST_GUARD="off").stdout
    assert "env DEV_WORKFLOW_TEST_GUARD" in line_for(out, "enabled", "test guard")


def test_the_env_switch_does_not_make_the_file_look_wrong(tmp_path):
    """`load_config` returns defaults without opening the file once the switch is
    set. Reporting that straight would show `floor 1` for a file that says 4 and
    blame the file for it."""
    write_cfg(tmp_path, "comment-guard.json", {"density": {"floor": 9}})
    out = run(tmp_path, "show", DEV_WORKFLOW_COMMENT_GUARD="off").stdout
    assert line_for(out, "density.floor") == "density.floor 9 < file"
    assert "env DEV_WORKFLOW_COMMENT_GUARD" in line_for(out, "enabled", "comment guard")


# --- the silent failures ----------------------------------------------------

def test_an_unparseable_file_is_reported_loudly(tmp_path):
    write_cfg(tmp_path, "comment-guard.json", '{"density": {"floor": 4},}')
    out = run(tmp_path, "show").stdout
    assert "PROBLEMS" in out
    assert "invalid JSON" in out
    assert "being ignored in full" in out
    assert line_for(out, "density.floor").endswith("default")


def test_an_empty_file_is_reported(tmp_path):
    write_cfg(tmp_path, "test-guard.json", "   \n")
    assert "the file is empty" in run(tmp_path, "show").stdout


def test_a_json_list_where_an_object_belongs_is_reported(tmp_path):
    write_cfg(tmp_path, "test-guard.json", "[]")
    assert "not an object" in run(tmp_path, "show").stdout


def test_a_string_false_does_not_disable_and_says_so(tmp_path):
    """Only the literal JSON false disables a guard. `"false"` is the quiet mistake
    this report exists to catch: it reads as configured and changes nothing."""
    write_cfg(tmp_path, "comment-guard.json", {"enabled": "false"})
    out = run(tmp_path, "show").stdout
    assert "does nothing" in out
    assert line_for(out, "enabled", "comment guard") == "enabled on < file, IGNORED"


def test_a_misspelled_key_is_reported(tmp_path):
    write_cfg(tmp_path, "test-guard.json", {"check": {"fakes": False}})
    out = run(tmp_path, "show").stdout
    assert "unknown key 'check'" in out
    assert line_for(out, "checks.fakes").endswith("default")


def test_an_uncompilable_allow_pattern_is_reported(tmp_path):
    write_cfg(tmp_path, "test-guard.json", {"allow": ["(("]})
    out = run(tmp_path, "show").stdout
    assert "does not compile" in out
    assert "IGNORED" in line_for(out, "allow", "test guard")


def test_an_unknown_agent_name_is_reported(tmp_path):
    write_cfg(tmp_path, "models.json", {"codr": "opus"})
    assert "is not an agent" in run(tmp_path, "show").stdout


def test_an_unknown_model_value_is_reported(tmp_path):
    write_cfg(tmp_path, "models.json", {"coder": "gpt-4"})
    assert "is not an alias" in run(tmp_path, "show").stdout


def test_the_templates_underscore_comment_key_is_not_flagged(tmp_path):
    write_cfg(tmp_path, "models.json", {"_comment": "copy me", "coder": "opus"})
    out = run(tmp_path, "show").stdout
    assert "_comment" not in out


# --- workflow state ---------------------------------------------------------

def test_the_gate_and_active_feature_are_reported_as_state(tmp_path):
    (tmp_path / ".approval-gate").write_text("locked\n")
    write_cfg(tmp_path, "comment-guard.json", {})
    (tmp_path / ".dev-workflow" / "active").write_text("wallet-topup\n")
    out = run(tmp_path, "show").stdout
    assert "LOCKED" in out
    assert "wallet-topup" in out
    assert "not configuration" in out


# --- setting ----------------------------------------------------------------

def test_set_writes_only_the_changed_key(tmp_path):
    assert run(tmp_path, "set", "comment-guard.density.floor", "4").returncode == 0
    assert read_cfg(tmp_path, "comment-guard.json") == {"density": {"floor": 4}}


def test_set_to_default_removes_the_key_and_its_container(tmp_path):
    run(tmp_path, "set", "comment-guard.density.floor", "4")
    run(tmp_path, "set", "comment-guard.density.min_ratio", "0.5")
    run(tmp_path, "set", "comment-guard.density.floor", "default")
    assert read_cfg(tmp_path, "comment-guard.json") == {"density": {"min_ratio": 0.5}}
    run(tmp_path, "set", "comment-guard.density.min_ratio", "default")
    assert read_cfg(tmp_path, "comment-guard.json") == {}


def test_setting_a_value_that_equals_the_default_omits_it(tmp_path):
    """The file is a diff against the defaults; writing one back explicitly would
    freeze a value that is supposed to follow the plugin."""
    out = run(tmp_path, "set", "test-guard.max_empty_args", "3").stdout
    assert "the default, so the key is omitted" in out
    assert read_cfg(tmp_path, "test-guard.json") == {}


def test_set_preserves_the_keys_it_is_not_touching(tmp_path):
    write_cfg(tmp_path, "test-guard.json", {"allow": ["legacy"], "max_empty_args": 8})
    run(tmp_path, "set", "test-guard.checks.fakes", "off")
    assert read_cfg(tmp_path, "test-guard.json") == {
        "allow": ["legacy"], "max_empty_args": 8, "checks": {"fakes": False}}


def test_set_writes_a_model_override(tmp_path):
    run(tmp_path, "set", "models.coder", "sonnet")
    assert read_cfg(tmp_path, "models.json") == {"coder": "sonnet"}
    run(tmp_path, "set", "models.coder", "default")
    assert read_cfg(tmp_path, "models.json") == {}


def test_set_refuses_to_overwrite_a_file_it_cannot_parse(tmp_path):
    """Rewriting it would silently destroy whatever the user was trying to write."""
    write_cfg(tmp_path, "test-guard.json", "{oops")
    out = run(tmp_path, "set", "test-guard.checks.fakes", "off").stdout
    assert "Refusing to write" in out
    assert (tmp_path / ".dev-workflow" / "test-guard.json").read_text() == "{oops"


@pytest.mark.parametrize("key,value,expected", [
    ("comment-guard.enabled", "maybe", "expected on/off"),
    ("test-guard.checks.fake", "off", "Unknown key"),
    ("nope.thing", "1", "Unknown group"),
    ("bare", "1", "Not a key"),
    ("models.codr", "opus", "Unknown agent"),
    ("models.coder", "gpt-4", "Bad model"),
])
def test_bad_input_is_refused_with_the_valid_options(tmp_path, key, value, expected):
    out = run(tmp_path, "set", key, value).stdout
    assert expected in out
    assert not (tmp_path / ".dev-workflow" / "models.json").exists()


def test_set_round_trips_through_show(tmp_path):
    run(tmp_path, "set", "test-guard.checks.assertions", "off")
    assert line_for(run(tmp_path, "show").stdout, "checks.assertions") == \
        "checks.assertions off < file"


# --- entry ------------------------------------------------------------------

def test_show_is_the_default_command(tmp_path):
    assert run(tmp_path).stdout == run(tmp_path, "show").stdout


@pytest.mark.parametrize("args", [("set",), ("set", "a"), ("bogus",)])
def test_a_malformed_invocation_prints_usage(tmp_path, args):
    proc = run(tmp_path, *args)
    assert proc.returncode == 2
    assert "usage: config.py" in proc.stdout
