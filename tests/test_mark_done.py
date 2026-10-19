"""mark_done.py: the user's own command for closing a feature they already finished."""
import os
import subprocess
import sys

import pytest
from conftest import HOOKS, phase, phase_log

sys.path.insert(0, HOOKS)
import _workflow  # noqa: E402

NOTE = "- Marked done from the dashboard: "


def run(root, slug, claude_code=False):
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    if claude_code:
        env["CLAUDECODE"] = "1"
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS, "mark_done.py"), str(root), slug],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def write_log(root, *sections, slug="topup"):
    log_path = root / ".dev-workflow" / "features" / slug / "phase-log.md"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(phase_log(*sections))
    return log_path


APPROVED_SECTION = phase("Phase 1 — ledger", approved=True, evidence="pytest -> 12 passed")


def test_every_open_section_is_ticked_and_noted_and_approved_ones_are_untouched(tmp_path):
    continued_notes = "- User notes: shipped on Friday\n  after the demo\n"
    api_section = phase("Phase 2 — api", reviewed=True).replace("- User notes:\n", continued_notes)
    log_path = write_log(tmp_path, APPROVED_SECTION, api_section, phase("Final review"))
    proc = run(tmp_path, "topup")
    log = log_path.read_text()

    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["ticked: Phase 2 — api", "ticked: Final review"]
    assert all(approved for _title, _body, approved in _workflow.iter_phases(log))
    assert APPROVED_SECTION in log
    for title, body, _approved in list(_workflow.iter_phases(log))[1:]:
        assert body.count(NOTE) == 1, title
    assert "  after the demo\n" + NOTE in log
    assert "- User notes:\n" + NOTE in log


def test_claude_code_is_refused_and_nothing_is_written(tmp_path):
    log_path = write_log(tmp_path, phase("Phase 1 — a", reviewed=True))
    before = log_path.read_bytes()
    proc = run(tmp_path, "topup", claude_code=True)
    assert proc.returncode != 0
    assert "your own terminal" in proc.stderr
    assert log_path.read_bytes() == before


@pytest.mark.parametrize("slug,reason", [
    ("missing", "not a feature"), ("../x", "not a feature"), ("..", "not a feature"),
    ("linked", "symlink"),
])
def test_a_slug_that_is_not_a_real_feature_dir_is_refused(tmp_path, slug, reason):
    log_path = write_log(tmp_path, phase("Phase 1 — a", reviewed=True))
    (tmp_path / ".dev-workflow" / "x").mkdir()
    (tmp_path / ".dev-workflow" / "features" / "linked").symlink_to(log_path.parent)
    before = log_path.read_bytes()
    proc = run(tmp_path, slug)
    assert proc.returncode != 0
    assert reason in proc.stderr
    assert log_path.read_bytes() == before


def test_only_a_real_approval_checkbox_is_ticked(tmp_path):
    freeform = "## Phase 1 — odd\n- Status: coded, reviewed, waiting on user\n- Evidence: pytest ok\n\n"
    in_prose = ("## Phase 2 — prose\n- Status: reviewed\n"
                "- Evidence: the `[ ] USER APPROVED` box is the user's\n\n")
    checklist = ("## Phase 3 — checklist\n- [x] coded\n- [x] code-reviewed\n- [ ] security-scanned\n"
                 "- [ ] USER APPROVED\n- Changed: foo.py\n\n")
    log_path = write_log(tmp_path, freeform, in_prose, checklist, phase("Phase 4 — normal", reviewed=True))
    proc = run(tmp_path, "topup")
    log = log_path.read_text()
    skip_reason = "(no '[ ] USER APPROVED' checkbox on its Status line or as a '- [ ] USER APPROVED' item)"
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == [
        "skipped: Phase 1 — odd " + skip_reason,
        "skipped: Phase 2 — prose " + skip_reason,
        "ticked: Phase 3 — checklist",
        "ticked: Phase 4 — normal"]
    assert freeform in log and in_prose in log
    assert "- [x] USER APPROVED\n- Changed: foo.py\n" + NOTE in log
    assert [approved for _t, _b, approved in _workflow.iter_phases(log)] == [False, False, True, True]


def test_an_already_done_feature_is_left_alone(tmp_path):
    log_path = write_log(tmp_path, APPROVED_SECTION)
    before = log_path.read_bytes()
    proc = run(tmp_path, "topup")
    assert proc.returncode == 0
    assert "No open sections in topup" in proc.stdout
    assert log_path.read_bytes() == before
