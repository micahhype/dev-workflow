"""SessionStart status hook: re-inject the active feature / phase / gate state,
and stay silent when no workflow is active."""
import os
import sys

from conftest import HOOKS, phase, phase_log, run_hook

sys.path.insert(0, HOOKS)
import status  # noqa: E402


def write_log(tmp_path, *sections, feature="Wallet topup"):
    (tmp_path / "phase-log.md").write_text(phase_log(*sections, feature=feature))


def test_silent_without_workflow(tmp_path):
    proc = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path)
    assert proc.stdout.strip() == ""


def test_reports_feature_and_progress(tmp_path):
    write_log(tmp_path,
              phase("Phase 1 - a", approved=True, evidence="x.py:1"),
              phase("Phase 2 - b"))
    out = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path).stdout
    assert "Wallet topup" in out
    assert "1/2 approved" in out
    assert "Phase 2" in out  # the current (first unapproved) phase


def test_all_approved(tmp_path):
    write_log(tmp_path, phase("Phase 1 - a", approved=True, evidence="x.py:1"))
    out = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path).stdout
    assert "1/1 approved" in out and "all approved" in out


def test_compact_source_adds_reminder(tmp_path):
    write_log(tmp_path, phase("Phase 1 - a"))
    out = run_hook("status.py", {"source": "compact"}, project_dir=tmp_path).stdout
    assert "compacted" in out.lower()


def test_gate_state_surfaced(tmp_path):
    write_log(tmp_path, phase("Phase 1 - a"))
    (tmp_path / ".approval-gate").write_text("LOCKED\n")
    out = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path).stdout
    assert "Approval gate: LOCKED" in out


# --- project registry -------------------------------------------------------

def test_a_workflow_project_is_registered_once_and_silently(tmp_path):
    project = tmp_path / "project"
    (project / ".dev-workflow").mkdir(parents=True)
    first = run_hook("status.py", {"source": "startup"}, project_dir=project)
    run_hook("status.py", {"source": "startup"}, project_dir=project)
    assert first.stdout == ""
    assert status.registered() == [os.path.realpath(project)]


def test_a_project_without_workflow_state_is_not_registered(tmp_path):
    run_hook("status.py", {"source": "startup"}, project_dir=tmp_path)
    assert status.registered() == []


def test_an_unusable_home_leaves_the_readout_unchanged(tmp_path):
    (tmp_path / ".dev-workflow").mkdir()
    write_log(tmp_path, phase("Phase 1 - a"))
    usual = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path)
    home_is_a_file = tmp_path / "home-file"
    home_is_a_file.write_text("")
    broken = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path,
                      env={"HOME": str(home_is_a_file)})
    assert broken.returncode == 0
    assert broken.stdout == usual.stdout and "Wallet topup" in broken.stdout
    assert broken.stderr == ""


def state_feature(root, text):
    directory = root / ".dev-workflow" / "features" / "orders"
    directory.mkdir(parents=True)
    (directory / "state.json").write_text(text)
    (root / ".dev-workflow" / "active").write_text("orders\n")
    return directory


def test_a_feature_with_state_is_reported_from_the_state(tmp_path):
    import state as workflow_state
    feature = workflow_state.new_state("orders", "Paginate orders")
    workflow_state.set_phases(feature, ["query", "wiring"])
    state_feature(tmp_path, __import__("json").dumps(feature))
    out = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path).stdout
    assert "Paginate orders" in out
    assert "0/3 approved; current -> Phase 1 — query" in out


def test_an_unreadable_state_is_named_instead_of_silently_ignored(tmp_path):
    state_feature(tmp_path, "{not json")
    out = run_hook("status.py", {"source": "startup"}, project_dir=tmp_path).stdout
    assert "state.json is unreadable" in out
