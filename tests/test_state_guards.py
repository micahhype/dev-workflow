"""The guards on a feature that has state.json: they judge the state, name an unreadable one,
and the gate refuses direct edits to the generated files."""
from conftest import hook_json, run_hook

EVIDENCE = "`pytest -q` -> 12 passed"
REVIEW_MAP = "- MUST `a.py:1-3` — parses → empty input?\n"
OUTSIDE_CLAUDE = {"CLAUDECODE": ""}


def dw(root, *args, stdin=None):
    return run_hook("dw.py", stdin, project_dir=root, args=list(args), env=OUTSIDE_CLAUDE)


def feature_dir(root):
    return root / ".dev-workflow" / "features" / "orders"


def reviewed_feature(root):
    dw(root, "new", "orders", "Paginate orders")
    dw(root, "phases", "only")
    dw(root, "coded", "1", "--changed", "a.py", stdin=EVIDENCE)
    dw(root, "reviewed", "1", stdin=REVIEW_MAP)


def blocked(proc):
    out = hook_json(proc)
    return out["reason"] if out and out.get("decision") == "block" else None


def edit(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}


def denied(proc):
    out = hook_json(proc)
    return bool(out) and out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_evidence_gate_judges_the_state_not_the_file_on_disk(tmp_path):
    reviewed_feature(tmp_path)
    assert blocked(run_hook("evidence_guard.py", {}, project_dir=tmp_path)) is None

    dw(tmp_path, "set", "1", "evidence", stdin="")
    (feature_dir(tmp_path) / "phase-log.md").write_text("# Phase log: hand edited\n")
    reason = blocked(run_hook("evidence_guard.py", {}, project_dir=tmp_path))
    assert reason and "Phase 1 — only" in reason


def test_a_finished_feature_owes_its_lessons_line_until_the_state_has_it(tmp_path):
    reviewed_feature(tmp_path)
    dw(tmp_path, "approve")
    reason = blocked(run_hook("plan_guard.py", {}, project_dir=tmp_path))
    assert reason and "Lessons" in reason
    assert "Lessons" in dw(tmp_path, "check").stdout

    dw(tmp_path, "set", "feature", "lessons", stdin="none")
    assert blocked(run_hook("plan_guard.py", {}, project_dir=tmp_path)) is None
    assert dw(tmp_path, "check").stdout.strip() == "Nothing missing."


def test_check_reports_a_reviewed_phase_with_no_evidence(tmp_path):
    reviewed_feature(tmp_path)
    dw(tmp_path, "set", "1", "evidence", stdin="")
    assert "'Phase 1 — only' is reviewed but its evidence is empty" in dw(tmp_path, "check").stdout


def test_an_unreadable_state_lets_the_turn_end_but_names_the_file(tmp_path):
    reviewed_feature(tmp_path)
    (feature_dir(tmp_path) / "state.json").write_text("{not json")
    for guard in ("evidence_guard.py", "plan_guard.py"):
        out = hook_json(run_hook(guard, {}, project_dir=tmp_path))
        assert "decision" not in out
        assert "state.json is unreadable" in out["systemMessage"]


def test_the_gate_refuses_edits_to_the_state_and_its_rendered_log(tmp_path):
    reviewed_feature(tmp_path)
    for name in ("state.json", "phase-log.md"):
        proc = run_hook("gate.py", edit(feature_dir(tmp_path) / name), project_dir=tmp_path)
        assert denied(proc)
    reason = hook_json(proc)["hookSpecificOutput"]["permissionDecisionReason"]
    assert ".dev-workflow/dw" in reason


def test_the_gate_leaves_hand_written_logs_and_unrelated_state_files_alone(tmp_path):
    legacy = tmp_path / ".dev-workflow" / "features" / "old"
    legacy.mkdir(parents=True)
    (legacy / "phase-log.md").write_text("# Phase log: old\n")
    for path in (legacy / "phase-log.md", legacy / "spec.md", tmp_path / "state.json",
                 tmp_path / "src" / "state.json"):
        assert hook_json(run_hook("gate.py", edit(path), project_dir=tmp_path)) is None


def test_the_gate_refuses_edits_to_the_prompt_stamp(tmp_path):
    reviewed_feature(tmp_path)
    stamp = tmp_path / ".dev-workflow" / "user-prompt.json"
    assert denied(run_hook("gate.py", edit(stamp), project_dir=tmp_path))
