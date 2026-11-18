#!/usr/bin/env python3
"""Checkpoint engine for the dev-workflow plugin.

As a PreToolUse hook (no args, JSON on stdin): before a mutating tool
(Edit/Write/MultiEdit/NotebookEdit/Bash) runs, snapshot the working tree to an immutable
commit on a shadow ref `refs/dev-workflow/checkpoints/<ts>` WITHOUT touching the
user's index, HEAD, branch, or working tree. Always exits 0 and never denies —
it is a side-effecting recorder, not a gate. Fails open on any error.

As a CLI: `checkpoint.py snapshot | list | rollback [ref] | undo | prune [days] |
ship <slug> | since-ship <slug> [path...]`.

`ship` records the tree a feature was handed over in, at
`refs/dev-workflow/shipped/<slug>`; `since-ship` diffs that tree against the
working tree now. What the user changed in the agent's code after accepting it is
the most honest review the agent ever gets, and the feature workflow reads it at
the start of the next feature to propose rules for `conventions.md`.

Snapshot mechanism (never mutates the user's real index):
  GIT_INDEX_FILE=<tmp> git read-tree HEAD      # seed tmp index from HEAD
  GIT_INDEX_FILE=<tmp> git add -A              # stage working tree into tmp index
  tree=$(GIT_INDEX_FILE=<tmp> git write-tree)
  commit=$(git commit-tree $tree -p HEAD -m <json>)
  git update-ref refs/dev-workflow/checkpoints/<ts> $commit

Rollback restores the working tree to a checkpoint's tree WITHOUT moving the
branch, after first capturing the current state as a `pre-rollback` checkpoint so
the rollback itself is reversible (`undo`). Nothing is ever hard-deleted from git.

Safety: operates only inside CLAUDE_PROJECT_DIR (never an arbitrary cwd); git is
run with a timeout, non-interactive, and fsmonitor disabled. v1 scope: git repos
only (silent no-op otherwise).

Retention: each new snapshot deletes checkpoint refs older than KEEP_DAYS
(`DEV_WORKFLOW_CHECKPOINT_KEEP_DAYS`, `0` keeps everything). Ship points are kept.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

REF_PREFIX = "refs/dev-workflow/checkpoints"
SHIPPED_PREFIX = "refs/dev-workflow/shipped"
KEEP_DAYS = 14
KEEP_ENV = "DEV_WORKFLOW_CHECKPOINT_KEEP_DAYS"
STAMP = re.compile(r"^\d{8}T\d{6}\.")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MUTATING_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}
# Both are kept OUT of checkpoints and preserved live across a rollback: they are
# the workflow's own memory, not part of the code being rolled back.
GATE_NAME = ".approval-gate"
STATE_DIR = ".dev-workflow"
_GIT = shutil.which("git") or "git"
# Defense-in-depth: never let repo config run commands or prompt/block us.
_HARDEN = ["-c", "core.fsmonitor="]
_TIMEOUT = 15


def git(project_dir, args, env_extra=None, check=True, stdin=None):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    # Shadow-ref commits are internal plumbing; give them a stable identity so a
    # snapshot never fails just because the user hasn't configured git
    # user.name/user.email yet (e.g. a freshly `git init`ed repo, or a CI runner).
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "dev-workflow"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "dev-workflow@localhost"
    if env_extra:
        env.update(env_extra)
    try:
        p = subprocess.run(
            [_GIT] + _HARDEN + args,
            cwd=project_dir, env=env, input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"git unavailable or timed out: {e}")
    if check and p.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {p.stderr.decode('utf-8','replace').strip()}")
    return p.returncode, p.stdout.decode("utf-8", "replace").strip()


def is_git_repo(project_dir):
    try:
        rc, out = git(project_dir, ["rev-parse", "--is-inside-work-tree"], check=False)
    except RuntimeError:
        return False
    return rc == 0 and out == "true"


def head_sha(project_dir):
    rc, out = git(project_dir, ["rev-parse", "HEAD"], check=False)
    return out if rc == 0 else None  # None on an unborn branch


def last_snapshot(project_dir):
    """(ref, tree) of the newest existing snapshot, or (None, None)."""
    rc, out = git(project_dir, [
        "for-each-ref", "--sort=-refname", "--count=1",
        "--format=%(refname) %(objectname)", REF_PREFIX,
    ], check=False)
    if rc != 0 or not out:
        return None, None
    ref, commit = out.split()
    _, tree = git(project_dir, ["rev-parse", commit + "^{tree}"])
    return ref, tree


def working_tree(project_dir):
    """(head, tree) — the working tree written as a tree object, via a temp index."""
    head = head_sha(project_dir)
    # A fresh temp DIRECTORY (mode 0700) with a never-preexisting index path,
    # so git creates a valid index and there is no shared-temp TOCTOU/symlink.
    tmpdir = tempfile.mkdtemp(prefix="dwf-idx-")
    tmp_index = os.path.join(tmpdir, "index")
    try:
        env = {"GIT_INDEX_FILE": tmp_index}
        if head:
            git(project_dir, ["read-tree", "HEAD"], env_extra=env)
        git(project_dir, ["add", "-A"], env_extra=env)
        # Never capture the approval-gate or the workflow state dir into a
        # checkpoint: otherwise a later rollback could restore an UNLOCKED gate
        # or clobber the phase log. (restore_tree independently preserves the
        # live gate too, so even pre-existing refs cannot flip it.)
        git(project_dir, ["rm", "-r", "--cached", "--ignore-unmatch", "-q",
                          "--", ":/" + GATE_NAME, ":/" + STATE_DIR],
            env_extra=env, check=False)
        _, tree = git(project_dir, ["write-tree"], env_extra=env)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return head, tree


def snapshot(project_dir, tool_name="", force=False):
    """Create a snapshot ref if the tree changed (or force). Returns ref or None."""
    if not is_git_repo(project_dir):
        return None

    head, tree = working_tree(project_dir)

    # Dedup: skip if the working tree is identical to the newest snapshot.
    if not force:
        _, prev_tree = last_snapshot(project_dir)
        if prev_tree == tree:
            return None

    meta = json.dumps({"timestamp": _now(), "tool": tool_name, "head_before": head},
                      separators=(",", ":"))
    commit_args = ["commit-tree", tree, "-m", meta]
    if head:
        commit_args += ["-p", head]
    _, commit = git(project_dir, commit_args)

    ref = f"{REF_PREFIX}/{_ref_stamp()}"
    git(project_dir, ["update-ref", ref, commit])
    return ref


def keep_days():
    """Days a checkpoint is kept; the default when the env value is not a whole number."""
    raw = (os.environ.get(KEEP_ENV) or "").strip()
    if not raw.isdigit():
        return KEEP_DAYS
    return int(raw)


def prune(project_dir, days=None):
    """Delete checkpoint refs older than `days`; 0 keeps everything. Returns the count."""
    days = keep_days() if days is None else days
    if not days:
        return 0
    cutoff = time.strftime("%Y%m%dT%H%M%S", time.gmtime(time.time() - days * 86400))
    _, out = git(project_dir, ["for-each-ref", "--format=%(refname)", REF_PREFIX], check=False)
    expired = [ref for ref in out.splitlines() if is_older(ref, cutoff)]
    if expired:
        deletes = "".join(f"delete {ref}\n" for ref in expired).encode()
        git(project_dir, ["update-ref", "--stdin"], stdin=deletes)
    return len(expired)


def is_older(ref, cutoff):
    stamp = ref.rsplit("/", 1)[-1]
    return bool(STAMP.match(stamp)) and stamp < cutoff


def shipped_ref(slug):
    if not SLUG.match(slug or ""):
        raise RuntimeError(f"not a feature slug: {slug!r}")
    return f"{SHIPPED_PREFIX}/{slug}"


def ship(project_dir, slug):
    """Record the tree `slug` was handed over in. Re-shipping overwrites it."""
    ref = shipped_ref(slug)
    if not is_git_repo(project_dir):
        return None
    head, tree = working_tree(project_dir)
    meta = json.dumps({"timestamp": _now(), "slug": slug, "head_before": head},
                      separators=(",", ":"))
    commit_args = ["commit-tree", tree, "-m", meta]
    if head:
        commit_args += ["-p", head]
    _, commit = git(project_dir, commit_args)
    git(project_dir, ["update-ref", ref, commit])
    return ref


def since_ship(project_dir, slug, paths=()):
    """Unified diff from the shipped tree of `slug` to the working tree now."""
    ref = shipped_ref(slug)
    rc, _ = git(project_dir, ["rev-parse", "--verify", "-q", ref], check=False)
    if rc != 0:
        raise RuntimeError(f"feature {slug!r} was never shipped")
    _, tree = working_tree(project_dir)
    _, out = git(project_dir, ["diff", ref + "^{tree}", tree, "--", *paths])
    return out


def list_snapshots(project_dir):
    if not is_git_repo(project_dir):
        return []
    rc, out = git(project_dir, [
        "for-each-ref", "--sort=-refname",
        "--format=%(refname:short)\t%(subject)", REF_PREFIX,
    ], check=False)
    if rc != 0 or not out:
        return []
    rows = []
    for line in out.splitlines():
        ref, _, subject = line.partition("\t")
        try:
            meta = json.loads(subject)
        except ValueError:
            meta = {}
        rows.append({"ref": ref, "timestamp": meta.get("timestamp"), "tool": meta.get("tool")})
    return rows


def _resolve_target(project_dir, ref):
    """Resolve a checkpoint arg to a commit, or default to the most recent
    non-`pre-rollback` checkpoint. Only refs under REF_PREFIX are accepted — a
    bare `HEAD`/`main`/tag/SHA is rejected so rollback can only target checkpoints."""
    if ref:
        stamp = ref.rsplit("/", 1)[-1]  # accept full ref, short ref, or bare stamp
        full = f"{REF_PREFIX}/{stamp}"
        rc, out = git(project_dir, ["rev-parse", "--verify", "-q", full + "^{commit}"], check=False)
        if rc == 0 and out:
            return out
        raise RuntimeError(f"unknown checkpoint: {ref}")
    for r in list_snapshots(project_dir):
        if r.get("tool") != "pre-rollback":
            _, c = git(project_dir, ["rev-parse", r["ref"]])
            return c
    raise RuntimeError("no checkpoints to roll back to")


def restore_tree(project_dir, commit):
    """Set the working tree (and index) to `commit`'s tree WITHOUT moving the
    branch; then reset the index back to HEAD so the delta shows as unstaged.
    Untracked files created since the checkpoint are left in place (never deleted).

    The live `.approval-gate` AND `.dev-workflow/` are preserved across the restore.
    Both are excluded from snapshots, and `git read-tree -u --reset` DELETES tracked
    paths the target tree does not contain — so in a repo that commits its workflow
    docs (a normal thing to do; they are the durable source of truth) a rollback
    would otherwise wipe `.dev-workflow/` outright. That took the phase log with it,
    including the Evidence ledger written during the phase, which exists nowhere
    else; `undo` could not bring it back, because the pre-rollback snapshot excludes
    it too. `status.py` and the evidence gate would then both fail open and go
    silent, so a single rollback disarmed the rest of the safety net.

    Rolling code back must never roll the WORKFLOW's own memory back — the log
    records what happened, and reverting the code does not un-happen it.
    """
    gate = os.path.join(project_dir, GATE_NAME)
    state = os.path.join(project_dir, STATE_DIR)

    saved_gate = None
    if os.path.isfile(gate):
        with open(gate, "rb") as f:
            saved_gate = f.read()

    stash = None
    if os.path.isdir(state):
        stash = tempfile.mkdtemp(prefix="dwf-state-")
        shutil.copytree(state, os.path.join(stash, "state"), symlinks=True)

    try:
        git(project_dir, ["read-tree", "-u", "--reset", commit])
        if head_sha(project_dir):
            git(project_dir, ["reset", "-q", "HEAD"])
        # Put the live workflow state back exactly as it was, overwriting whatever
        # read-tree may have restored from an older tree.
        if stash is not None:
            shutil.rmtree(state, ignore_errors=True)
            shutil.copytree(os.path.join(stash, "state"), state, symlinks=True)
    finally:
        if stash is not None:
            shutil.rmtree(stash, ignore_errors=True)

    # Restore the gate to exactly the state it was in before the rollback.
    if saved_gate is None:
        try:
            os.unlink(gate)
        except OSError:
            pass
    else:
        with open(gate, "wb") as f:
            f.write(saved_gate)


def rollback(project_dir, ref=None):
    """Restore to a checkpoint, first saving current state as a reversible
    `pre-rollback` checkpoint."""
    if not is_git_repo(project_dir):
        raise RuntimeError("not a git repository")
    target = _resolve_target(project_dir, ref)
    undo_ref = snapshot(project_dir, "pre-rollback", force=True)
    restore_tree(project_dir, target)
    return {"target": target, "undo_ref": undo_ref}


def undo(project_dir):
    """Reverse the most recent rollback by restoring its `pre-rollback` snapshot."""
    for r in list_snapshots(project_dir):
        if r.get("tool") == "pre-rollback":
            return rollback(project_dir, r["ref"])
    raise RuntimeError("nothing to undo")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ref_stamp():
    # Nanosecond precision so lexicographic refname order == creation order
    # (needed for "reverse the LAST rollback"); random suffix breaks any tie and
    # prevents a collision silently overwriting an earlier snapshot.
    ns = time.time_ns()
    return (time.strftime("%Y%m%dT%H%M%S", time.gmtime())
            + f".{ns % 1_000_000_000:09d}-" + os.urandom(3).hex())


def resolve_project_dir(payload=None):
    """Only ever operate inside the trusted CLAUDE_PROJECT_DIR. Honor the hook
    payload's cwd only when it resolves inside that root (else ignore it), so a
    session that cd'd into an untrusted repo cannot redirect our git ops there."""
    base = os.environ.get("CLAUDE_PROJECT_DIR")
    cwd = (payload or {}).get("cwd")
    if base:
        base_r = os.path.realpath(base)
        if cwd:
            try:
                cwd_r = os.path.realpath(cwd)
                if os.path.commonpath([base_r, cwd_r]) == base_r:
                    return cwd_r
            except Exception:
                pass
        return base_r
    return os.path.realpath(cwd) if cwd else os.getcwd()


def hook_main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # fail open
    if payload.get("tool_name", "") not in MUTATING_TOOLS:
        return
    try:
        project_dir = resolve_project_dir(payload)
        if snapshot(project_dir, payload.get("tool_name", "")):
            prune(project_dir)
    except Exception:
        pass  # never block the tool call


def cli_main(argv):
    cmd = argv[0]
    project_dir = resolve_project_dir()
    try:
        if cmd == "snapshot":
            ref = snapshot(project_dir, "cli")
            print(ref or "(no change; snapshot skipped)")
        elif cmd == "list":
            rows = list_snapshots(project_dir)
            if not rows:
                print("(no checkpoints)")
            for r in rows:
                tag = "  <- pre-rollback" if r.get("tool") == "pre-rollback" else ""
                print(f"{r['ref']}\t{r.get('timestamp','?')}\t{r.get('tool','?')}{tag}")
        elif cmd == "rollback":
            ref = argv[1] if len(argv) > 1 else None
            res = rollback(project_dir, ref)
            print(f"Rolled back the working tree to checkpoint {res['target'][:12]}.")
            if res["undo_ref"]:
                print(f"Prior state saved as {res['undo_ref'].split('/')[-1]} "
                      f"- run `undo` (or rollback to it) to reverse this.")
            print("Files created since that checkpoint are left in place "
                  "(see `git status`).")
        elif cmd == "undo":
            undo(project_dir)
            print("Reversed the last rollback.")
        elif cmd == "prune":
            days = int(argv[1]) if len(argv) > 1 else None
            print(f"Deleted {prune(project_dir, days)} checkpoint(s).")
        elif cmd == "ship":
            ref = ship(project_dir, argv[1] if len(argv) > 1 else "")
            print(ref or "(not a git repo; nothing recorded)")
        elif cmd == "since-ship":
            diff = since_ship(project_dir, argv[1] if len(argv) > 1 else "", argv[2:])
            print(diff or "(no edits since ship)")
        else:
            print(f"unknown command: {cmd}", file=sys.stderr)
            sys.exit(2)
    except Exception as e:
        print(f"checkpoint: {e}", file=sys.stderr)  # fail gracefully


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        cli_main(args)
    else:
        hook_main()
    sys.exit(0)
