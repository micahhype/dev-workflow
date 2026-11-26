"""The dw command line: every state change goes through it, and a refusal changes nothing."""
import json
import os
import subprocess
import sys

from conftest import HOOKS, phase, phase_log, run_hook

sys.path.insert(0, HOOKS)
import checkpoint  # noqa: E402
import diff_budget  # noqa: E402
import legacy  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(HOOKS), "templates", "phase-log.md")
EVIDENCE = "`pytest -q` -> 12 passed"
REVIEW_MAP = "3 must-read / 0 skim / 0 skip of 3 lines\n- MUST `a.py:1-3` — parses → empty input?\n"
OUTSIDE_CLAUDE = {"CLAUDECODE": ""}
INSIDE_CLAUDE = {"CLAUDECODE": "1"}


def dw(root, *args, stdin=None, env=None):
    return run_hook("dw.py", stdin, project_dir=root, args=list(args), env=env or INSIDE_CLAUDE)


def saved(root, slug="orders"):
    path = root / ".dev-workflow" / "features" / slug / "state.json"
    return json.loads(path.read_text())


def reviewed_feature(root):
    dw(root, "new", "orders", "Paginate orders")
    dw(root, "phases", "only")
    dw(root, "--by", "coder", "coded", "1", "--changed", "a.py", stdin=EVIDENCE)
    return dw(root, "reviewed", "1", "--security", stdin=REVIEW_MAP)


def test_new_creates_the_state_and_makes_the_feature_active(tmp_path):
    assert dw(tmp_path, "new", "orders", "Paginate orders", "--tier", "standard").returncode == 0
    assert saved(tmp_path)["tier"] == "standard"
    assert (tmp_path / ".dev-workflow" / "active").read_text().strip() == "orders"
    assert os.access(tmp_path / ".dev-workflow" / "dw", os.X_OK)


def test_new_refuses_a_slug_that_would_leave_the_features_directory(tmp_path):
    proc = dw(tmp_path, "new", "../escape", "x")
    assert proc.returncode == 1 and "Not a feature slug" in proc.stderr


def test_a_phase_is_coded_reviewed_and_recorded_with_who_did_it(tmp_path):
    assert reviewed_feature(tmp_path).returncode == 0
    state = saved(tmp_path)
    recorded = state["phases"][0]
    assert recorded["status"] == "reviewed" and recorded["security_scanned"] is True
    assert recorded["review_summary"].startswith("3 must-read")
    assert recorded["review_map"] == [{"tier": "MUST", "text": "`a.py:1-3` — parses → empty input?"}]
    assert [event["by"] for event in state["events"]] == ["orchestrator", "coder", "orchestrator"]


def test_a_refusal_exits_nonzero_says_why_and_changes_nothing(tmp_path):
    dw(tmp_path, "new", "orders", "Paginate orders")
    dw(tmp_path, "phases", "only")
    proc = dw(tmp_path, "reviewed", "1", stdin=REVIEW_MAP)
    assert proc.returncode == 1 and "pending, not coded" in proc.stderr
    assert saved(tmp_path)["phases"][0]["status"] == "pending"


def test_a_review_map_line_without_a_tier_is_refused(tmp_path):
    dw(tmp_path, "new", "orders", "Paginate orders")
    dw(tmp_path, "phases", "only")
    dw(tmp_path, "coded", "1", "--changed", "a.py", stdin=EVIDENCE)
    proc = dw(tmp_path, "reviewed", "1", stdin=REVIEW_MAP + "check the parser\n")
    assert proc.returncode == 1 and "Not a review-map line" in proc.stderr


def test_claude_cannot_run_a_bare_approve_but_the_user_can(tmp_path):
    reviewed_feature(tmp_path)
    refused = dw(tmp_path, "approve", env=INSIDE_CLAUDE)
    assert refused.returncode == 1 and "YOUR approval" in refused.stderr
    assert saved(tmp_path)["phases"][0]["status"] == "reviewed"

    assert dw(tmp_path, "approve", env=OUTSIDE_CLAUDE).returncode == 0
    state = saved(tmp_path)
    assert state["phases"][0]["approval"]["via"] == "user"
    assert state["events"][-1] == {"by": "user", "do": "approve", "phase": 1,
                                   "at": state["events"][-1]["at"]}


def user_says(root, prompt):
    return run_hook("prompt.py", {"hook_event_name": "UserPromptSubmit", "prompt": prompt},
                    project_dir=root)


def test_a_relayed_approval_needs_the_user_to_have_spoken_since_the_review(tmp_path):
    reviewed_feature(tmp_path)
    stamp = tmp_path / ".dev-workflow" / "user-prompt.json"
    stamp.write_text('{"at": "2020-01-01T00:00:00Z"}')
    refused = dw(tmp_path, "approve", "1", "--said", "ok ship it")
    assert refused.returncode == 1 and "has not said anything since phase 1" in refused.stderr

    user_says(tmp_path, "<task-notification>reviewer finished</task-notification>")
    assert dw(tmp_path, "approve", "1", "--said", "ok ship it").returncode == 1

    user_says(tmp_path, "ok ship it")
    assert dw(tmp_path, "approve", "1", "--said", "ok ship it").returncode == 0
    approval = saved(tmp_path)["phases"][0]["approval"]
    assert approval["via"] == "relayed" and approval["quote"] == "ok ship it"


def test_direct_mode_refuses_a_relayed_approval(tmp_path):
    reviewed_feature(tmp_path)
    user_says(tmp_path, "ok ship it")
    (tmp_path / ".dev-workflow" / "approval.json").write_text('{"mode": "direct"}')
    refused = dw(tmp_path, "approve", "1", "--said", "ok ship it")
    assert refused.returncode == 1 and "direct approvals only" in refused.stderr
    assert saved(tmp_path)["phases"][0]["status"] == "reviewed"


def typed_approve(root, args=""):
    payload = {"hook_event_name": "UserPromptExpansion", "command_name": "dev-workflow:approve",
               "command_args": args, "prompt": "/dev-workflow:approve " + args}
    out = run_hook("prompt.py", payload, project_dir=root).stdout
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out.strip() else None


def test_typing_the_approve_command_records_a_direct_approval(tmp_path):
    reviewed_feature(tmp_path)
    assert "approval is recorded for phase 1 of orders" in typed_approve(tmp_path)
    state = saved(tmp_path)
    assert state["phases"][0]["approval"]["via"] == "user"
    assert state["events"][-1]["by"] == "user"
    assert "already approved" in typed_approve(tmp_path)


def test_the_approve_command_says_why_a_phase_cannot_be_approved_yet(tmp_path):
    dw(tmp_path, "new", "orders", "Paginate orders")
    dw(tmp_path, "phases", "only")
    assert "Phase 1 is pending, not reviewed" in typed_approve(tmp_path)
    assert saved(tmp_path)["phases"][0]["status"] == "pending"


def test_the_approve_command_on_a_hand_written_log_hands_the_tick_to_claude(tmp_path):
    legacy_feature(tmp_path, phase_log(phase("Phase 1 — parser", reviewed=True)))
    (tmp_path / ".dev-workflow" / "active").write_text("old\n")
    assert "has no state.json" in typed_approve(tmp_path)


def test_the_prompt_hook_ignores_other_commands_and_projects_without_the_workflow(tmp_path):
    payload = {"hook_event_name": "UserPromptExpansion", "command_name": "dev-workflow:status"}
    reviewed_feature(tmp_path)
    assert run_hook("prompt.py", payload, project_dir=tmp_path).stdout == ""
    bare = tmp_path / "elsewhere"
    bare.mkdir()
    user_says(bare, "hello")
    assert not (bare / ".dev-workflow").exists()


def test_set_writes_phase_and_feature_text_and_refuses_an_unknown_field(tmp_path):
    reviewed_feature(tmp_path)
    assert dw(tmp_path, "set", "1", "user_notes", stdin="rename the helper\n").returncode == 0
    assert dw(tmp_path, "set", "feature", "lessons", stdin="none").returncode == 0
    assert dw(tmp_path, "set", "1", "status", stdin="approved").returncode == 1
    state = saved(tmp_path)
    assert state["phases"][0]["user_notes"] == "rename the helper"
    assert state["lessons"] == "none" and state["phases"][0]["status"] == "reviewed"


def test_status_lists_the_sections_and_marks_the_current_one(tmp_path):
    reviewed_feature(tmp_path)
    out = dw(tmp_path, "status").stdout
    assert "Paginate orders (orders)" in out
    assert "[reviewed] Phase 1 — only  <- current" in out


def legacy_feature(root, log):
    directory = root / ".dev-workflow" / "features" / "old"
    directory.mkdir(parents=True)
    (directory / "phase-log.md").write_text(log)
    return directory


def test_import_converts_a_legacy_log_and_keeps_the_original(tmp_path):
    log = phase_log(phase("Phase 1 — parser", reviewed=True, approved=True, evidence=EVIDENCE),
                    phase("Phase 2 — wiring", reviewed=True, evidence=EVIDENCE),
                    feature="Old feature")
    directory = legacy_feature(tmp_path, log)
    assert dw(tmp_path, "import", "old").returncode == 0
    state = saved(tmp_path, "old")
    assert state["title"] == "Old feature"
    assert [(p["title"], p["status"]) for p in state["phases"]] == [
        ("parser", "approved"), ("wiring", "reviewed")]
    assert state["phases"][1]["evidence"] == EVIDENCE
    assert (directory / "phase-log.legacy.md").read_text() == log
    assert "Generated from state.json" in (directory / "phase-log.md").read_text()

    again = dw(tmp_path, "import", "old")
    assert again.returncode == 1 and "already has a state.json" in again.stderr


def test_the_untouched_template_imports_as_one_pending_phase():
    with open(TEMPLATE, encoding="utf-8") as source:
        state = legacy.state_from_log(source.read(), "fresh")
    assert state["title"] == "fresh"
    assert [p["status"] for p in state["phases"]] == ["pending"]
    assert state["phases"][0]["evidence"] is None and state["phases"][0]["review_map"] == []
    assert state["final_review"]["status"] == "pending" and state["lessons"] is None


def test_session_start_writes_a_launcher_that_works_from_a_subdirectory(tmp_path):
    reviewed_feature(tmp_path)
    (tmp_path / ".dev-workflow" / "dw").unlink()
    run_hook("status.py", {"source": "startup"}, project_dir=tmp_path)
    (tmp_path / "src").mkdir()
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    out = subprocess.run([str(tmp_path / ".dev-workflow" / "dw"), "status"], cwd=tmp_path / "src",
                         env=env, text=True, stdout=subprocess.PIPE).stdout
    assert "Phase 1 — only" in out


def test_a_two_phase_feature_runs_through_its_final_review_and_closing_lines(tmp_path):
    dw(tmp_path, "new", "orders", "Paginate orders")
    assert "no phases yet" in dw(tmp_path, "coded", "1", "--changed", "a.py", stdin=EVIDENCE).stderr
    dw(tmp_path, "phases", "query", "wiring")
    for number in ("1", "2"):
        dw(tmp_path, "--by", "coder", "coded", number, "--changed", "a.py", stdin=EVIDENCE)
        dw(tmp_path, "reviewed", number, "--security", stdin=REVIEW_MAP)
        assert dw(tmp_path, "approve", number, env=OUTSIDE_CLAUDE).returncode == 0

    dw(tmp_path, "round", "final")
    dw(tmp_path, "set", "final", "evidence", stdin="`pytest -q` -> 40 passed, end to end")
    assert dw(tmp_path, "reviewed", "final", "--security", stdin="").returncode == 0
    assert dw(tmp_path, "approve", "final", env=OUTSIDE_CLAUDE).returncode == 0
    assert "Lessons" in dw(tmp_path, "check").stdout

    dw(tmp_path, "set", "feature", "lessons", stdin="none")
    assert dw(tmp_path, "check").stdout.strip() == "Nothing missing."
    state = saved(tmp_path)
    assert state["final_review"]["status"] == "approved" and state["final_review"]["rounds"] == 1


def test_another_feature_is_addressed_by_slug(tmp_path):
    dw(tmp_path, "new", "orders", "Paginate orders")
    dw(tmp_path, "new", "refunds", "Refund flow")
    dw(tmp_path, "--feature", "orders", "set", "feature", "post_ship_reviewed",
       stdin="2026-11-19 — no user edits")
    assert saved(tmp_path)["post_ship_reviewed"] == "2026-11-19 — no user edits"
    assert saved(tmp_path, "refunds")["post_ship_reviewed"] is None


# --- dw diff: the reviewer reads the phase's diff from a file -----------------

def diff_file(root, name="phase-1.diff"):
    return root / ".dev-workflow" / "features" / "orders" / name


def coded_in_git(root):
    dw(root, "new", "orders", "Paginate orders")
    dw(root, "phases", "only")
    (root / "a.txt").write_text("one\ntwo\n")
    (root / "new.py").write_text("x = 1\n")


def test_diff_writes_the_phase_diff_and_reports_its_size(git_repo):
    coded_in_git(git_repo)
    proc = dw(git_repo, "diff", "1")
    assert proc.returncode == 0, proc.stderr
    assert "phase-1.diff: 2 files, +2 -0" in proc.stdout and "new.py" in proc.stdout
    written = diff_file(git_repo).read_text()
    assert "+two" in written and "+x = 1" in written and ".dev-workflow" not in written


def test_diff_starts_from_the_baseline_the_stop_hook_recorded(git_repo):
    coded_in_git(git_repo)
    _head, before_phase = checkpoint.working_tree(str(git_repo))
    diff_budget.save(str(git_repo), {"orders": {"phase": "Phase 1 — only", "base": before_phase,
                                                 "last": before_phase}})
    (git_repo / "later.py").write_text("y = 2\n")
    proc = dw(git_repo, "diff", "1")
    assert "1 files" in proc.stdout and "since the phase started" in proc.stdout
    assert "+x = 1" not in diff_file(git_repo).read_text()


def test_since_review_writes_only_what_changed_after_the_last_diff(git_repo):
    coded_in_git(git_repo)
    dw(git_repo, "diff", "1")
    (git_repo / "new.py").write_text("x = 2\n")
    proc = dw(git_repo, "diff", "1", "--since-review")
    assert proc.returncode == 0, proc.stderr
    fix = diff_file(git_repo, "phase-1.fix.diff").read_text()
    assert "+x = 2" in fix and "+two" not in fix


def test_since_review_without_an_earlier_diff_is_refused(git_repo):
    coded_in_git(git_repo)
    proc = dw(git_repo, "diff", "1", "--since-review")
    assert proc.returncode == 1 and "without" in proc.stderr


def test_diff_with_nothing_changed_is_refused(git_repo):
    dw(git_repo, "new", "orders", "Paginate orders")
    dw(git_repo, "phases", "only")
    proc = dw(git_repo, "diff", "1")
    assert proc.returncode == 1 and "Nothing has changed" in proc.stderr


def test_diff_outside_a_git_repo_is_refused(tmp_path):
    dw(tmp_path, "new", "orders", "Paginate orders")
    dw(tmp_path, "phases", "only")
    proc = dw(tmp_path, "diff", "1")
    assert proc.returncode == 1 and "Not a git repository" in proc.stderr
