"""Checkpoint engine: snapshots to a shadow ref without touching the user's
index/HEAD/branch, rollback is reversible, and the approval gate is never
captured or clobbered."""
from conftest import hook_json, run_hook


def cp(repo, *args):
    """Run checkpoint.py as a CLI subcommand."""
    return run_hook("checkpoint.py", None, project_dir=repo, args=list(args))


def head(repo):
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def test_snapshot_creates_ref(git_repo):
    (git_repo / "a.txt").write_text("two\n")
    out = cp(git_repo, "snapshot").stdout
    assert "refs/dev-workflow/checkpoints" in out          # snapshot prints the full ref
    assert "dev-workflow/checkpoints" in cp(git_repo, "list").stdout  # list prints the short ref


def test_snapshot_does_not_move_head_or_branch(git_repo):
    before = head(git_repo)
    (git_repo / "a.txt").write_text("two\n")
    cp(git_repo, "snapshot")
    assert head(git_repo) == before  # branch/HEAD untouched


def test_identical_snapshot_is_deduped(git_repo):
    (git_repo / "a.txt").write_text("two\n")
    assert "refs/dev-workflow" in cp(git_repo, "snapshot").stdout
    # No change since the last snapshot -> skipped.
    assert "no change" in cp(git_repo, "snapshot").stdout.lower()


def test_rollback_restores_and_undo_reverses(git_repo):
    (git_repo / "a.txt").write_text("two\n")
    cp(git_repo, "snapshot")                 # checkpoint captures "two"
    (git_repo / "a.txt").write_text("three\n")
    cp(git_repo, "rollback")                 # -> working tree back to "two"
    assert (git_repo / "a.txt").read_text() == "two\n"
    cp(git_repo, "undo")                     # -> reverse, back to "three"
    assert (git_repo / "a.txt").read_text() == "three\n"


def test_rollback_preserves_live_gate(git_repo):
    (git_repo / ".approval-gate").write_text("LOCKED\n")
    (git_repo / "a.txt").write_text("two\n")
    cp(git_repo, "snapshot")
    (git_repo / ".approval-gate").write_text("UNLOCKED\n")  # user unlocks after the snapshot
    cp(git_repo, "rollback")
    # The gate reflects the LIVE state, never the snapshot's — rollback can't relock.
    assert (git_repo / ".approval-gate").read_text().strip() == "UNLOCKED"


def test_rollback_does_not_destroy_the_workflow_docs(git_repo):
    # A repo that COMMITS its workflow docs — normal, since they are the durable
    # source of truth. Snapshots deliberately exclude `.dev-workflow/`, so the
    # snapshot tree has no such path, and `git read-tree -u --reset` DELETES tracked
    # paths that the target tree lacks. That silently destroyed the phase log — and
    # with it, the Evidence ledger written during the phase, which exists nowhere
    # else. `status.py` and the evidence gate then both fail open and go quiet, so
    # one rollback disarmed the rest of the safety net.
    import subprocess
    docs = git_repo / ".dev-workflow" / "features" / "f"
    docs.mkdir(parents=True)
    (docs / "phase-log.md").write_text("# Phase log\n- Evidence: committed\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "track workflow docs"], cwd=git_repo, check=True)

    (git_repo / "a.txt").write_text("two\n")
    cp(git_repo, "snapshot")
    # The ledger for the phase currently under way — written AFTER the snapshot.
    (docs / "phase-log.md").write_text("# Phase log\n- Evidence: pytest -q -> 12 passed\n")
    (git_repo / "a.txt").write_text("three\n")

    cp(git_repo, "rollback")
    assert (git_repo / "a.txt").read_text() == "two\n"      # code DID roll back
    assert (docs / "phase-log.md").is_file(), "rollback deleted the phase log"
    # ...and it is the LIVE ledger, not a stale snapshot of it: the log records what
    # happened, and rolling code back does not un-happen it.
    assert "12 passed" in (docs / "phase-log.md").read_text()


def test_non_git_dir_is_noop(tmp_path):
    out = cp(tmp_path, "snapshot").stdout
    assert "no change" in out.lower()
    assert "no checkpoints" in cp(tmp_path, "list").stdout.lower()


def test_unborn_branch_snapshots(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n")
    out = cp(tmp_path, "snapshot").stdout  # no commits yet -> parentless snapshot
    assert "refs/dev-workflow/checkpoints" in out


def test_hook_mode_snapshots_on_mutating_tool(git_repo):
    (git_repo / "a.txt").write_text("two\n")
    proc = run_hook("checkpoint.py", {"tool_name": "Edit", "cwd": str(git_repo)},
                    project_dir=git_repo)
    assert proc.returncode == 0
    assert "dev-workflow/checkpoints" in cp(git_repo, "list").stdout


def test_hook_mode_snapshots_on_notebook_edit(git_repo):
    # NotebookEdit mutates files like Edit but was missing from MUTATING_TOOLS
    # (and from hooks.json's matcher), so notebook edits got no pre-edit snapshot
    # — the one tool whose changes rollback could not recover.
    (git_repo / "a.txt").write_text("two\n")
    proc = run_hook("checkpoint.py", {"tool_name": "NotebookEdit", "cwd": str(git_repo)},
                    project_dir=git_repo)
    assert proc.returncode == 0
    assert "dev-workflow/checkpoints" in cp(git_repo, "list").stdout


def test_hook_mode_ignores_non_mutating_tool(git_repo):
    run_hook("checkpoint.py", {"tool_name": "Read", "cwd": str(git_repo)}, project_dir=git_repo)
    assert "no checkpoints" in cp(git_repo, "list").stdout.lower()


def test_ship_then_since_ship_shows_only_later_edits(git_repo):
    (git_repo / "a.txt").write_text("agent wrote this\n")
    (git_repo / "new.txt").write_text("agent file\n")
    assert "refs/dev-workflow/shipped/orders" in cp(git_repo, "ship", "orders").stdout
    assert "no edits" in cp(git_repo, "since-ship", "orders").stdout

    (git_repo / "a.txt").write_text("user rewrote this\n")
    diff = cp(git_repo, "since-ship", "orders").stdout
    assert "-agent wrote this" in diff and "+user rewrote this" in diff
    assert "new.txt" not in diff  # untracked agent files are part of the shipped tree


def test_since_ship_limits_to_paths(git_repo):
    (git_repo / "b.txt").write_text("b\n")
    cp(git_repo, "ship", "orders")
    (git_repo / "a.txt").write_text("changed\n")
    (git_repo / "b.txt").write_text("changed\n")
    diff = cp(git_repo, "since-ship", "orders", "b.txt").stdout
    assert "b.txt" in diff and "a.txt" not in diff


def test_ship_does_not_move_head_or_pollute_checkpoints(git_repo):
    before = head(git_repo)
    cp(git_repo, "ship", "orders")
    assert head(git_repo) == before
    assert "shipped" not in cp(git_repo, "list").stdout


def test_since_ship_of_an_unshipped_feature_fails_gracefully(git_repo):
    proc = cp(git_repo, "since-ship", "never")
    assert proc.returncode == 0 and "never shipped" in proc.stderr


def test_ship_rejects_a_slug_that_is_not_a_ref_name(git_repo):
    proc = cp(git_repo, "ship", "../../heads/main")
    assert "not a feature slug" in proc.stderr


def checkpoint_refs(repo):
    import subprocess
    out = subprocess.run(["git", "for-each-ref", "--format=%(refname)", "refs/dev-workflow"],
                         cwd=repo, text=True, stdout=subprocess.PIPE).stdout
    return out.split()


def add_ref(repo, name):
    import subprocess
    subprocess.run(["git", "update-ref", name, "HEAD"], cwd=repo, check=True)


OLD_CHECKPOINT = "refs/dev-workflow/checkpoints/20200101T000000.000000000-abcdef"


def test_a_new_snapshot_prunes_expired_checkpoints_but_not_ship_points(git_repo):
    add_ref(git_repo, OLD_CHECKPOINT)
    add_ref(git_repo, "refs/dev-workflow/shipped/old-feature")
    (git_repo / "a.txt").write_text("two\n")
    run_hook("checkpoint.py", {"tool_name": "Edit", "cwd": str(git_repo)}, project_dir=git_repo)
    refs = checkpoint_refs(git_repo)
    assert OLD_CHECKPOINT not in refs
    assert "refs/dev-workflow/shipped/old-feature" in refs
    assert len(refs) == 2  # the fresh snapshot and the ship point


def test_keep_days_zero_keeps_everything(git_repo):
    add_ref(git_repo, OLD_CHECKPOINT)
    (git_repo / "a.txt").write_text("two\n")
    run_hook("checkpoint.py", {"tool_name": "Edit", "cwd": str(git_repo)}, project_dir=git_repo,
             env={"DEV_WORKFLOW_CHECKPOINT_KEEP_DAYS": "0"})
    assert OLD_CHECKPOINT in checkpoint_refs(git_repo)


def test_prune_cli_reports_the_count(git_repo):
    add_ref(git_repo, OLD_CHECKPOINT)
    assert "Deleted 1 checkpoint" in cp(git_repo, "prune").stdout
    assert checkpoint_refs(git_repo) == []
