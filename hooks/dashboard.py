#!/usr/bin/env python3
"""CLI behind /dev-workflow:dashboard: a local web view of the workflow.

GET never writes. The one write is POST /api/mark-done, only with this server's Host and
Origin, a JSON body and the per-launch token, and only into a listed project's feature.

Claude can already Edit phase-log.md, so the new risk is a cross-site request from another
page; Origin + token + a JSON content type (none a plain form can send) close it.

Never call checkpoint.working_tree / snapshot / since_ship (they write git objects) or
any hook's main(); other actions are shown as `!` commands for the user's own shell.
"""
import datetime
import hmac
import itertools
import json
import os
import re
import secrets
import select
import shlex
import sys
import textwrap
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import _workflow
import checkpoint
import config
import diff_budget
import evidence_guard
import mark_done
import plan_guard
import status

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
PAGE_PATH = os.path.join(HOOKS_DIR, "dashboard.html")
CHECKPOINT_CLI = os.path.join(HOOKS_DIR, "checkpoint.py")
GATE_NAME = ".approval-gate"
IDLE_SECONDS = 1800
RECENT_CHECKPOINTS = 10
MAX_BODY_BYTES = 4096
EXCERPT_MAX_LINES = 80
MAP_ENTRY = re.compile(r"^[ \t]*-[ \t]*(MUST|SKIM|SKIP|ASSUME)\b[ \t]*(.*)$", re.MULTILINE)
MAP_LOCATION = re.compile(r"`([^`\s:]+)(?::(\d+)(?:-(\d+))?)?`")
# No framing: a page that framed the board could trick clicks onto Mark done.
CONTENT_SECURITY_POLICY = ("frame-ancestors 'none'; default-src 'self'; "
                           "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                           "connect-src 'self'")
TEMPLATE_TITLE = "<title>"


def projects(start_root):
    live_roots = []
    for candidate in [start_root] + status.registered():
        root = os.path.realpath(candidate)
        if root not in live_roots and os.path.isdir(os.path.join(root, _workflow.STATE_DIR)):
            live_roots.append(root)
    return live_roots


def overview(start_root):
    boards = [project_board(root) for root in projects(start_root)]
    waiting_boards = [board for board in boards if has_waiting(board["features"])]
    other_boards = [board for board in boards if not has_waiting(board["features"])]
    return {"projects": waiting_boards + other_boards}


def project_board(root):
    active_slug = _workflow.docs_dir(root)[1]
    features = guarded(list_features, root, active_slug)
    if isinstance(features, list):
        waiting = [feature for feature in features if feature["waiting"]]
        others = [feature for feature in features if not feature["waiting"]]
        features = waiting + others
    return {"root": root, "name": os.path.basename(root), "features": features,
            "resume": "cd %s && claude --continue" % shlex.quote(root)}


def has_waiting(features):
    return isinstance(features, list) and any(feature["waiting"] for feature in features)


def collect(root, requested_slug=None):
    active_dir, active_slug = _workflow.docs_dir(root)
    features = guarded(list_features, root, active_slug)
    listed_slugs = [feature["slug"] for feature in features] if isinstance(features, list) else []
    if requested_slug in listed_slugs:
        slug = requested_slug
        feature_dir = os.path.join(root, _workflow.STATE_DIR, "features", slug)
    else:
        slug = active_slug
        feature_dir = active_dir

    log = read_doc(feature_dir, "phase-log.md")
    spec = read_doc(feature_dir, "spec.md")
    plan = read_doc(feature_dir, "plan.md")
    checkpoints = guarded(recent_checkpoints, root)
    return {
        "root": root,
        "features": features,
        "selected": slug,
        "title": guarded(feature_title, log, spec, slug),
        "phases": guarded(phase_cards, log, plan, root, slug),
        "spec": spec,
        "plan": plan,
        "warnings": guarded(guard_warnings, log, plan, root),
        "gate": guarded(gate_state, root),
        "checkpoints": checkpoints,
        "config": guarded(config.show, root),
        "actions": guarded(copyable_actions, root, checkpoints),
    }


def guarded(build, *args):
    try:
        return build(*args)
    except Exception as exc:
        return {"error": str(exc) or type(exc).__name__}


def read_doc(feature_dir, name):
    return _workflow.read(os.path.join(feature_dir, name)) or ""


def list_features(root, active_slug):
    features_dir = os.path.join(root, _workflow.STATE_DIR, "features")
    if not os.path.isdir(features_dir):
        return []
    slugs = [slug for slug in sorted(os.listdir(features_dir))
             if os.path.isdir(os.path.join(features_dir, slug))]
    return [feature_summary(os.path.join(features_dir, slug), slug, active_slug)
            for slug in slugs]


def feature_summary(feature_dir, slug, active_slug):
    log = read_doc(feature_dir, "phase-log.md")
    sections = list(_workflow.iter_phases(log))
    approved = [title for title, _body, is_approved in sections if is_approved]
    current_title, current_body = first_unapproved(sections) or (None, "")
    feature = {
        "slug": slug,
        "active": slug == active_slug,
        "title": feature_title(log, read_doc(feature_dir, "spec.md"), slug),
        "approved": len(approved),
        "total": len(sections),
        "current": current_title,
        "waiting": bool(evidence_guard.REVIEW_DONE.search(current_body)),
        "coded": "[x] coded" in (field(current_body, "Status") or "").lower(),
    }
    feature["state"] = row_state(sections, feature)
    feature["track"] = phase_track(sections, feature["waiting"])
    return feature


def first_unapproved(sections):
    return next(((title, body) for title, body, approved in sections if not approved), None)


def row_state(sections, feature):
    if not sections or TEMPLATE_TITLE in sections[0][0]:
        return "No phases yet"
    if feature["current"] is None:
        return "Done"
    if feature["waiting"]:
        return "Needs approval"
    if feature["coded"]:
        return short_title(feature["current"]) + ", in review"
    return short_title(feature["current"]) + ", in progress"


def short_title(section_title):
    return section_title.split(" — ", 1)[0]


def phase_track(sections, is_waiting):
    current_index = next((index for index, (_title, _body, is_approved) in enumerate(sections)
                          if not is_approved), None)
    return [track_segment(is_approved, index == current_index, is_waiting)
            for index, (_title, _body, is_approved) in enumerate(sections)]


def track_segment(is_approved, is_current, is_waiting):
    if is_approved:
        return "done"
    if not is_current:
        return "todo"
    if is_waiting:
        return "waiting"
    return "current"


def feature_title(log, spec, slug):
    return (status.title_from(log, "Phase log:")
            or status.title_from(spec, "Spec:")
            or slug or "(unnamed)")


def phase_cards(log, plan, root, slug):
    cards = [phase_card(title, body, approved)
             for title, body, approved in _workflow.iter_phases(log)]
    current = next((card for card in cards if not card["approved"]), None)
    if current:
        current["current"] = True
        current["diff"] = diff_size(current["title"], plan, root, slug)
        for entry in current["review_map"]["entries"]:
            if entry["tier"] == "MUST":
                entry["excerpt"] = excerpt(root, entry)
    return cards


def phase_card(title, body, approved):
    return {
        "title": title,
        "approved": approved,
        "current": False,
        "status": field(body, "Status"),
        "review_rounds": field(body, "Review rounds"),
        "unresolved": field(body, "Unresolved"),
        "evidence": field(body, "Evidence"),
        "evidence_empty": evidence_guard.evidence_empty(body),
        "review_map": review_map(field(body, "Review map")),
        "over_budget": field(body, "Over budget"),
        "diff": None,
    }


def review_map(text):
    if not text or _workflow.is_unfilled(text):
        return {"summary": None, "entries": []}
    summary = text.splitlines()[0].strip()
    entries = [map_entry(match) for match in MAP_ENTRY.finditer(text)]
    return {"summary": None if MAP_ENTRY.match(summary) else summary, "entries": entries}


def map_entry(match):
    tier, text = match.group(1), match.group(2).strip()
    location = MAP_LOCATION.search(text)
    if location is None or tier == "ASSUME":
        return {"tier": tier, "text": text, "path": None, "start": None, "end": None}
    start = int(location.group(2)) if location.group(2) else None
    end = int(location.group(3)) if location.group(3) else start
    note = (text[:location.start()] + text[location.end():]).strip(" —-")
    return {"tier": tier, "text": note, "path": location.group(1), "start": start, "end": end}


def excerpt(root, entry):
    """The entry's lines from the working file, only for a regular file inside `root`."""
    if entry["start"] is None or entry["start"] < 1:
        return None
    real_root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(real_root, entry["path"]))
    inside = os.path.commonpath([path, real_root]) == real_root
    hidden = os.path.relpath(path, real_root).split(os.sep)[0] in (".git", _workflow.STATE_DIR)
    if not inside or hidden or not os.path.isfile(path):
        return None
    last = min(entry["end"], entry["start"] + EXCERPT_MAX_LINES - 1)
    with open(path, "r", encoding="utf-8", errors="replace") as source:
        lines = list(itertools.islice(source, entry["start"] - 1, last))
    return {"first": entry["start"], "lines": [line.rstrip("\n") for line in lines]}


def diff_size(title, plan, root, slug):
    number = plan_guard.PHASE_NUM.match(title)
    estimate = plan_guard.phase_estimates(plan).get(int(number.group(1))) if number and plan else None
    recorded = diff_budget.load(root).get(slug or "")
    lines = recorded.get("lines") if isinstance(recorded, dict) and recorded.get("phase") == title else None
    if estimate is None and lines is None:
        return None
    limit = plan_guard.budget_limit(estimate) if estimate is not None else None
    return {"lines": lines, "estimate": estimate, "limit": limit}


def field(body, name):
    text = _workflow.field_text(body, name)
    return textwrap.dedent(text).strip() if text is not None else None


def guard_warnings(log, plan, root):
    warnings = []
    if plan:
        warnings += plan_guard.plan_findings(plan)
    if log:
        warnings += plan_guard.budget_findings(log)
        warnings += plan_guard.map_findings(log, root)
        warnings += plan_guard.lessons_findings(log)
        warnings += plan_guard.review_map_findings(log)
        warnings += evidence_warnings(log)
    return warnings


def evidence_warnings(log):
    current_section = first_unapproved(_workflow.iter_phases(log))
    if current_section is None:
        return []
    title, body = current_section
    if evidence_guard.REVIEW_DONE.search(body) and evidence_guard.evidence_empty(body):
        return ["'%s' is marked reviewed but its Evidence ledger is empty; the evidence "
                "gate will refuse to end the turn until it cites proof." % title]
    return []


def gate_state(root):
    gate = _workflow.read(os.path.join(root, GATE_NAME))
    if gate is None:
        return "no gate file"
    first = next((line.strip() for line in gate.splitlines() if line.strip()), "")
    return first.upper() or "empty"


def recent_checkpoints(root):
    return checkpoint.list_snapshots(root)[:RECENT_CHECKPOINTS]


def copyable_actions(root, checkpoints):
    in_project = "! cd %s && " % shlex.quote(root)
    # checkpoint.py picks CLAUDE_PROJECT_DIR over cwd, so cd alone does not pin the project.
    pinned_project = "CLAUDE_PROJECT_DIR=%s " % shlex.quote(root)
    listed = checkpoints if isinstance(checkpoints, list) else []
    rollback = {}
    for row in listed:
        rollback[row["ref"]] = in_project + pinned_project + "python3 %s rollback %s" % (
            shlex.quote(CHECKPOINT_CLI), shlex.quote(row["ref"]))
    return {"unlock_gate": in_project + "echo UNLOCKED > " + GATE_NAME,
            "rollback": rollback}


class Handler(BaseHTTPRequestHandler):
    # Per connection: a browser's idle preconnect must not stall this single thread.
    timeout = 5

    def do_GET(self):
        if not self.is_own_host():
            self.send(403, "text/plain; charset=utf-8", b"forbidden host\n")
            return
        url = urlsplit(self.path)
        if url.path == "/":
            with open(PAGE_PATH, "rb") as page:
                self.send(200, "text/html; charset=utf-8", page.read())
        elif url.path == "/api/overview":
            board = overview(self.server.project_root)
            board["token"] = self.server.token
            self.send_json(board)
        elif url.path == "/api/state":
            self.send_state(parse_qs(url.query))
        else:
            self.send_not_found()

    def send_state(self, query):
        requested_project = query.get("project", [None])[0]
        requested_slug = query.get("feature", [None])[0]
        if requested_project is None:
            self.send_json(collect(self.server.project_root, requested_slug))
        elif requested_project in projects(self.server.project_root):
            self.send_json(collect(requested_project, requested_slug))
        else:
            self.send_not_found()

    def do_POST(self):
        if not self.is_own_host():
            self.send(403, "text/plain; charset=utf-8", b"forbidden host\n")
            return
        if urlsplit(self.path).path != "/api/mark-done":
            self.send_not_found()
            return
        code, payload = self.mark_done_response()
        self.send_json(payload, code)

    def mark_done_response(self):
        refusal = self.write_refusal()
        if refusal:
            return 403, {"error": refusal}
        try:
            return self.apply_mark_done()
        except (OSError, ValueError, RecursionError) as exc:
            return 500, {"error": str(exc) or type(exc).__name__}

    def apply_mark_done(self):
        request = self.mark_done_request()
        if request is None:
            return 400, {"error": "expected a JSON object {project, feature} of at most %d bytes"
                                  % MAX_BODY_BYTES}
        if request["project"] not in projects(self.server.project_root):
            return 404, {"error": "not a project on this dashboard"}
        today = datetime.date.today().isoformat()
        try:
            report = mark_done.apply(request["project"], request["feature"], today)
        except mark_done.NotAFeature as refusal:
            return 404, {"error": str(refusal)}
        except mark_done.Refused as refusal:
            return 409, {"error": str(refusal)}
        return 200, {"report": report}

    def write_refusal(self):
        if self.headers.get("Origin") != "http://" + self.headers.get("Host", ""):
            return "Origin must be this dashboard"
        media_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        if media_type != "application/json":
            return "Content-Type must be application/json"
        token = self.headers.get("X-Dashboard-Token", "")
        if not hmac.compare_digest(token.encode("utf-8"), self.server.token.encode("utf-8")):
            return "missing or wrong X-Dashboard-Token"
        return None

    def mark_done_request(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return None
        if not 0 < length <= MAX_BODY_BYTES:
            return None
        body = self.rfile.read(length)
        try:
            request = json.loads(body)
        except ValueError:
            return None
        if not isinstance(request, dict):
            return None
        has_names = isinstance(request.get("project"), str) and isinstance(request.get("feature"), str)
        return request if has_names else None

    def send_json(self, payload, code=200):
        self.send(code, "application/json", json.dumps(payload).encode("utf-8"))

    def send_not_found(self):
        self.send(404, "text/plain; charset=utf-8", b"not found\n")

    def is_own_host(self):
        # Any other Host is a DNS-rebinding page trying to read the state.
        port = self.server.server_address[1]
        allowed = {"127.0.0.1:%d" % port, "localhost:%d" % port}
        return self.headers.get("Host", "") in allowed

    def send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def make_server(root):
    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.project_root = root
    server.token = secrets.token_urlsafe(32)
    return server


def serve(server):
    # One request at a time: config.show swaps os.environ while it runs.
    while True:
        ready, _, _ = select.select([server], [], [], IDLE_SECONDS)
        if not ready:
            return
        server.handle_request()


USAGE = "usage: dashboard.py [--detach]"


def announce(url, pid):
    print("Dashboard: %s (pid %d; stops after %d min idle)" % (url, pid, IDLE_SECONDS // 60))
    sys.stdout.flush()


def detach(url):
    child_pid = os.fork()
    if child_pid:
        announce(url, child_pid)
        os._exit(0)
    os.setsid()
    # The launcher reads our stdout until EOF, so the child must let go of the real fds.
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    os.close(devnull)


def main(argv):
    args = argv[1:]
    if args not in ([], ["--detach"]):
        print(USAGE)
        return 2
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    server = make_server(root)
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    if args == ["--detach"] and hasattr(os, "fork"):
        detach(url)
    else:
        announce(url, os.getpid())
    with server:
        serve(server)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
