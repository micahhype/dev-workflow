"""Dashboard: the state it serves comes from the guards' own parsers, and the server
behind it can only read."""
import http.client
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import urllib.request
from urllib.parse import quote

import pytest
from conftest import HOOKS, phase, phase_log

sys.path.insert(0, HOOKS)
import checkpoint  # noqa: E402
import dashboard  # noqa: E402
import status  # noqa: E402

LONG_TEXT_KEYS = {"spec", "plan", "config", "checkpoints", "actions", "evidence"}


def make_features(root):
    features = root / ".dev-workflow" / "features"
    (features / "alpha").mkdir(parents=True)
    (features / "beta").mkdir()
    (features / "alpha" / "phase-log.md").write_text(phase_log(
        phase("Phase 1 — parser", approved=True, evidence="pytest -q -> 12 passed"),
        phase("Phase 2 — server", reviewed=True),
        feature="Alpha feature"))
    (features / "beta" / "phase-log.md").write_text(phase_log(phase("Phase 1 — only")))
    (root / ".dev-workflow" / "active").write_text("alpha\n")


def write_feature(root, slug, *sections):
    feature_dir = root / ".dev-workflow" / "features" / slug
    feature_dir.mkdir(parents=True)
    (feature_dir / "phase-log.md").write_text(phase_log(*sections, feature=slug.title()))


def write_registry(roots):
    path = status.registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump([str(root) for root in roots], fh)


@pytest.fixture
def served(tmp_path, monkeypatch):
    """A live server on a thread; yields a GET helper returning (status, body)."""
    monkeypatch.setattr(dashboard, "IDLE_SECONDS", 1.0)
    with dashboard.make_server(str(tmp_path)) as server:
        port = server.server_address[1]
        thread = threading.Thread(target=dashboard.serve, args=(server,))
        thread.start()

        def request(path, method="GET", host="127.0.0.1:%d" % port, headers=None, body=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(method, path, body=body, headers=dict(headers or {}, Host=host))
            response = conn.getresponse()
            result = response.status, response.read()
            conn.close()
            return result

        request.origin = "http://127.0.0.1:%d" % port
        yield request
        thread.join(timeout=5)


def padded_request(root):
    return json.dumps({"project": os.path.realpath(root), "feature": "alpha", "pad": "x" * 5000})


def mark_done_post(served, root, feature="alpha", changes=None, **request_options):
    """POST /api/mark-done the way the page does; `changes` overrides or (None) drops a header."""
    token = json.loads(served("/api/overview")[1])["token"]
    headers = {"Origin": served.origin, "Content-Type": "application/json", "X-Dashboard-Token": token}
    headers.update(changes or {})
    sent_headers = {name: value for name, value in headers.items() if value is not None}
    body = request_options.pop("body", json.dumps({"project": os.path.realpath(root), "feature": feature}))
    return served("/api/mark-done", method="POST", headers=sent_headers, body=body, **request_options)


def test_collect_reads_features_and_phases_through_the_workflow_parsers(git_repo):
    make_features(git_repo)
    ref = checkpoint.snapshot(str(git_repo), "Edit", force=True).replace("refs/", "", 1)
    state = dashboard.collect(str(git_repo))

    assert [(f["slug"], f["active"], f["approved"], f["total"]) for f in state["features"]] == [
        ("alpha", True, 1, 2), ("beta", False, 0, 1)]
    assert state["selected"] == "alpha"
    assert state["title"] == "Alpha feature"
    done, current = state["phases"]
    assert done["approved"] and not done["current"] and not done["evidence_empty"]
    assert current["current"] and current["evidence_empty"]
    assert current["status"].startswith("[x] coded  [x] code-reviewed")
    assert [w for w in state["warnings"] if "'Phase 2 — server'" in w]
    assert state["gate"] == "no gate file"
    project = shlex.quote(str(git_repo))
    assert state["actions"]["rollback"] == {ref: "! cd %s && CLAUDE_PROJECT_DIR=%s python3 %s rollback %s" % (
        project, project, shlex.quote(os.path.join(HOOKS, "checkpoint.py")), shlex.quote(ref))}

    assert dashboard.collect(str(git_repo), "beta")["selected"] == "beta"
    assert dashboard.collect(str(git_repo), "../..")["selected"] == "alpha"

    alpha, beta = state["features"]
    assert (alpha["title"], alpha["current"], alpha["waiting"]) == ("Alpha feature", "Phase 2 — server", True)
    assert alpha["track"] == ["done", "waiting"]
    assert (beta["current"], beta["waiting"], beta["coded"]) == ("Phase 1 — only", False, True)

    write_feature(git_repo, "gamma", phase("Phase 1 — all", approved=True, evidence="\n  - a\n  - b"))
    write_feature(git_repo, "delta", phase("Phase 1 — draft", coded=False))
    write_feature(git_repo, "epsilon", phase("Phase 1 — <title>", coded=False))
    states = {f["slug"]: f["state"] for f in dashboard.list_features(str(git_repo), "alpha")}
    assert states == {
        "alpha": "Needs approval",
        "beta": "Phase 1, in review",
        "delta": "Phase 1, in progress",
        "epsilon": "No phases yet",
        "gamma": "Done",
    }
    assert dashboard.collect(str(git_repo), "gamma")["phases"][0]["evidence"] == "- a\n- b"


def test_the_current_phase_shows_its_review_map_with_the_must_read_code(tmp_path):
    (tmp_path / "api.py").write_text("".join("line %d\n" % n for n in range(1, 11)))
    (tmp_path.parent / "secret.txt").write_text("outside\n")
    review_map = ("- Review map: 3 must-read / 1 skim / 2 skip of 6 changed lines\n"
                  "  - MUST `api.py:4-6` — default page → is page 1 the first 20?\n"
                  "  - MUST `../secret.txt:1` — reaches outside the project\n"
                  "  - SKIM `api.py:9` — wiring\n"
                  "  - SKIP `tests/test_api.py` — cited as evidence\n"
                  "  - ASSUME a page holds 20 orders\n")
    section = phase("Phase 1 — pages", reviewed=True).replace("- Evidence:", review_map + "- Evidence:")
    write_feature(tmp_path, "pages", section)
    feature_dir = tmp_path / ".dev-workflow" / "features" / "pages"
    (feature_dir / "plan.md").write_text("### Phase 1 — pages\n- Scope: pages\n- Size: ~40 lines\n")
    (tmp_path / ".dev-workflow" / "diff-budget.json").write_text(
        json.dumps({"pages": {"phase": "Phase 1 — pages", "lines": 130}}))

    current = dashboard.collect(str(tmp_path), "pages")["phases"][0]
    review = current["review_map"]
    assert review["summary"] == "3 must-read / 1 skim / 2 skip of 6 changed lines"
    assert [entry["tier"] for entry in review["entries"]] == ["MUST", "MUST", "SKIM", "SKIP", "ASSUME"]
    must, outside = review["entries"][:2]
    assert (must["path"], must["start"], must["end"]) == ("api.py", 4, 6)
    assert must["text"] == "default page → is page 1 the first 20?"
    assert must["excerpt"] == {"first": 4, "lines": ["line 4", "line 5", "line 6"]}
    assert outside["excerpt"] is None
    assert review["entries"][4]["text"] == "a page holds 20 orders"
    assert current["diff"] == {"lines": 130, "estimate": 40, "limit": 80}


def test_overview_shows_each_live_project_once_waiting_first(tmp_path):
    quiet = tmp_path / "quiet"
    write_feature(quiet, "one", phase("Phase 1 — a"))
    busy = tmp_path / "busy"
    make_features(busy)
    write_feature(busy, "aaa", phase("Phase 1 — a"))
    gone = tmp_path / "gone"
    gone.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(busy)
    write_registry([alias, gone, busy])

    board = dashboard.overview(str(quiet))["projects"]
    assert [project["root"] for project in board] == [os.path.realpath(busy), os.path.realpath(quiet)]
    assert [feature["slug"] for feature in board[0]["features"]] == ["alpha", "aaa", "beta"]
    assert board[0]["name"] == "busy"
    assert board[0]["resume"] == "cd %s && claude --continue" % shlex.quote(os.path.realpath(busy))


def test_a_failing_section_does_not_take_the_others_down(tmp_path, monkeypatch):
    make_features(tmp_path)

    def broken_show(root):
        raise ValueError("config exploded")

    monkeypatch.setattr(dashboard.config, "show", broken_show)
    state = dashboard.collect(str(tmp_path))
    assert state["config"] == {"error": "config exploded"}
    assert len(state["phases"]) == 2
    assert state["features"][0]["slug"] == "alpha"


def test_the_server_serves_the_page_and_live_state_and_nothing_else(tmp_path, served):
    make_features(tmp_path)
    log_path = tmp_path / ".dev-workflow" / "features" / "alpha" / "phase-log.md"

    code, page = served("/")
    assert code == 200 and b"/api/state" in page
    code, before = served("/api/state")
    assert code == 200 and json.loads(before)["selected"] == "alpha"

    log_path.write_text(log_path.read_text().replace("[ ] USER APPROVED", "[x] USER APPROVED"))
    code, after = served("/api/state?feature=alpha")
    assert all(p["approved"] for p in json.loads(after)["phases"])

    assert served("/", host="evil.example:80")[0] == 403
    with urllib.request.urlopen(served.origin + "/", timeout=5) as response:
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert served("/api/state", method="POST")[0] == 404

    other = tmp_path / "other"
    make_features(other)
    status.register(str(other))
    unregistered = tmp_path / "unregistered"
    make_features(unregistered)
    code, body = served("/api/overview")
    board = json.loads(body)["projects"]
    assert code == 200 and len(board) == 2
    for project in board:
        assert not LONG_TEXT_KEYS & set(project)
        assert not any(LONG_TEXT_KEYS & set(feature) for feature in project["features"])

    for foreign in ("/etc", "..", str(unregistered)):
        assert served("/api/state?project=" + quote(foreign))[0] == 404
    code, body = served("/api/state?project=%s&feature=beta" % quote(os.path.realpath(other)))
    assert code == 200 and json.loads(body)["selected"] == "beta"


def tree_fingerprint(root):
    fingerprint = {}
    for directory, _subdirs, files in os.walk(root):
        for name in files:
            path = os.path.join(directory, name)
            with open(path, "rb") as fh:
                fingerprint[path] = (os.stat(path).st_mtime_ns, fh.read())
    return fingerprint


def test_hitting_every_route_writes_nothing_not_even_in_git(git_repo, served):
    make_features(git_repo)
    (git_repo / ".approval-gate").write_text("LOCKED\n")
    assert checkpoint.snapshot(str(git_repo), "Edit", force=True)
    status.register(str(git_repo))
    home = os.environ["HOME"]
    before = tree_fingerprint(git_repo)
    home_before = tree_fingerprint(home)

    code, body = served("/api/state")
    assert len(json.loads(body)["checkpoints"]) == 1
    project = quote(os.path.realpath(git_repo))
    for path in ("/", "/api/state?feature=beta", "/missing", "/api/overview",
                 "/api/state?project=%s&feature=beta" % project, "/api/state?project=/etc"):
        served(path)
    served("/api/state", method="POST")
    served("/api/state", host="evil.example")
    assert mark_done_post(served, git_repo, changes={"Origin": None})[0] == 403
    assert mark_done_post(served, git_repo, changes={"X-Dashboard-Token": "guess"})[0] == 403
    assert mark_done_post(served, git_repo, feature="../x")[0] == 404
    assert mark_done_post(served, git_repo, body=padded_request(git_repo))[0] == 400

    assert tree_fingerprint(git_repo) == before
    assert home_before and tree_fingerprint(home) == home_before


def test_mark_done_writes_only_through_the_guarded_post(tmp_path, served):
    make_features(tmp_path)
    log_path = tmp_path / ".dev-workflow" / "features" / "alpha" / "phase-log.md"
    before = log_path.read_bytes()
    rejections = [
        (403, {"changes": {"Origin": None}}),
        (403, {"changes": {"Origin": "http://evil.example"}}),
        (403, {"changes": {"X-Dashboard-Token": None}}),
        (403, {"changes": {"X-Dashboard-Token": "guess"}}),
        (403, {"changes": {"Content-Type": "text/plain"}}),
        (403, {"host": "evil.example", "changes": {"Origin": "http://evil.example"}}),
        (404, {"feature": "../x"}),
        (400, {"body": padded_request(tmp_path)}),
    ]
    for expected_code, options in rejections:
        assert mark_done_post(served, tmp_path, **options)[0] == expected_code, options
    assert log_path.read_bytes() == before

    unlisted = tmp_path / "unlisted"
    make_features(unlisted)
    unlisted_log = unlisted / ".dev-workflow" / "features" / "alpha" / "phase-log.md"
    unlisted_before = unlisted_log.read_bytes()
    assert mark_done_post(served, unlisted)[0] == 404
    assert unlisted_log.read_bytes() == unlisted_before

    code, body = mark_done_post(served, tmp_path)
    assert (code, json.loads(body)) == (200, {"report": ["ticked: Phase 2 — server"]})
    board = json.loads(served("/api/overview")[1])["projects"]
    alpha = next(feature for feature in board[0]["features"] if feature["slug"] == "alpha")
    assert alpha["state"] == "Done"


@pytest.mark.skipif(not hasattr(os, "fork"), reason="--detach needs fork")
def test_detach_returns_at_once_and_leaves_a_server_running(tmp_path):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path))
    proc = subprocess.run([sys.executable, os.path.join(HOOKS, "dashboard.py"), "--detach"],
                          stdout=subprocess.PIPE, text=True, env=env, timeout=5)
    match = re.search(r"(http://127\.0\.0\.1:\d+/) \(pid (\d+);", proc.stdout)
    assert match, proc.stdout
    url, pid = match.group(1), int(match.group(2))
    try:
        os.kill(pid, 0)
        with urllib.request.urlopen(url + "api/state", timeout=5) as response:
            assert json.loads(response.read())["root"] == str(tmp_path)
    finally:
        os.kill(pid, signal.SIGTERM)


def test_serve_returns_once_idle(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "IDLE_SECONDS", 0.3)
    with dashboard.make_server(str(tmp_path)) as server:
        thread = threading.Thread(target=dashboard.serve, args=(server,))
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
