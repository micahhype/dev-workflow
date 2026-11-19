#!/usr/bin/env python3
"""Per-feature workflow state: `state.json`, its validated transitions, the rendered phase-log.md."""
import contextlib
import json
import os
import tempfile
import time

try:
    import fcntl
except ImportError:
    fcntl = None

VERSION = 1
STATE_FILE = "state.json"
LOCK_FILE = "state.lock"
LOG_FILE = "phase-log.md"
FINAL = "final"
FINAL_TITLE = "Final review (all phases)"
MAX_ROUNDS = 2
MIN_EVIDENCE = 15
MAP_TIERS = ("MUST", "SKIM", "SKIP", "ASSUME")
APPROVAL_ROUTES = ("user", "relayed")
PHASE_TEXT = ("changed", "evidence", "review_summary", "review_result", "unresolved",
              "deferred_nits", "over_budget", "user_notes")
FEATURE_TEXT = ("project_map", "lessons", "post_ship_reviewed")
GENERATED_NOTE = "> Generated from state.json by `dw`. Do not edit: the next write overwrites it."


class Refused(Exception):
    """A change whose preconditions do not hold; the message says what is missing."""


class Corrupt(Exception):
    """state.json exists but cannot be used."""


# --- shape ------------------------------------------------------------------

def new_state(slug, title, tier="trivial"):
    state = {"version": VERSION, "slug": slug, "title": title, "tier": tier,
             "phases": [], "final_review": None}
    state.update({field: None for field in FEATURE_TEXT})
    state["events"] = []
    return state


def new_phase(number, title):
    phase = {"id": number, "title": title, "status": "pending", "rounds": 0,
             "security_scanned": False, "review_map": [], "approval": None}
    phase.update({field: None for field in PHASE_TEXT})
    return phase


def sections(state):
    final = state["final_review"]
    return state["phases"] + ([final] if final else [])


def section(state, target):
    for candidate in sections(state):
        if candidate["id"] == target:
            return candidate
    if target == FINAL:
        raise Refused("A single-phase feature has no final review.")
    raise Refused("No phase %s in this feature." % target)


def is_final(phase):
    return phase["id"] == FINAL


def working_status(phase):
    """The status a section is reviewed from: the final review is never coded."""
    return "pending" if is_final(phase) else "coded"


def filled(text):
    return bool(text and text.strip())


# --- changes ----------------------------------------------------------------

def set_phases(state, titles):
    if not titles:
        raise Refused("A feature needs at least one phase.")
    started = [phase["title"] for phase in sections(state) if phase["status"] != "pending"]
    if started:
        raise Refused("Work has started on: %s. Add a phase instead of replacing the list."
                      % "; ".join(started))
    state["phases"] = []
    state["final_review"] = None
    for title in titles:
        add_phase(state, title)


def add_phase(state, title):
    final = state["final_review"]
    if final and final["status"] != "pending":
        raise Refused("The final review has started; reopen it before adding a phase.")
    state["phases"].append(new_phase(len(state["phases"]) + 1, title))
    if len(state["phases"]) > 1 and not final:
        state["final_review"] = new_phase(FINAL, FINAL_TITLE)


def mark_coded(state, number, record):
    """`record` carries `changed` and `evidence`, what the coder did and what it ran."""
    phase = section(state, number)
    if is_final(phase):
        raise Refused("The final review is not coded; record its review instead.")
    require_status(phase, "pending")
    require_earlier_approved(state, phase)
    missing = [field for field in ("changed", "evidence") if not filled(record.get(field))]
    if missing:
        raise Refused("Phase %s cannot be coded without: %s." % (number, ", ".join(missing)))
    phase["changed"] = record["changed"]
    phase["evidence"] = record["evidence"]
    phase["status"] = "coded"


def start_round(state, target):
    phase = section(state, target)
    require_status(phase, working_status(phase))
    phase["rounds"] += 1


def mark_reviewed(state, target, review):
    """`review` carries `entries` (the review map) and `security_scanned`."""
    phase = section(state, target)
    require_status(phase, working_status(phase))
    if is_final(phase):
        require_earlier_approved(state, phase)
    else:
        phase["review_map"] = checked_map(review.get("entries") or [])
    if phase["rounds"] > MAX_ROUNDS and not filled(phase["unresolved"]):
        raise Refused("%s took %d review rounds (budget %d). Record what the user decided "
                      "in `unresolved` first." % (label(phase), phase["rounds"], MAX_ROUNDS))
    phase["security_scanned"] = bool(review.get("security_scanned"))
    phase["status"] = "reviewed"


def checked_map(entries):
    for entry in entries:
        if entry.get("tier") not in MAP_TIERS or not filled(entry.get("text")):
            raise Refused("Not a review-map entry: %r. Each needs a tier (%s) and text."
                          % (entry, " / ".join(MAP_TIERS)))
    if not any(entry["tier"] != "ASSUME" for entry in entries):
        raise Refused("The review map needs at least one MUST, SKIM or SKIP entry.")
    return [{"tier": entry["tier"], "text": entry["text"].strip()} for entry in entries]


def approve(state, target, approval):
    """`approval` carries `via` (user | relayed) and, when relayed, the user's `quote`."""
    phase = section(state, target)
    require_status(phase, "reviewed")
    if len((phase["evidence"] or "").strip()) < MIN_EVIDENCE:
        raise Refused("%s has no cited evidence; it cannot be approved." % label(phase))
    via = approval.get("via")
    if via not in APPROVAL_ROUTES:
        raise Refused("An approval arrives via %s." % " or ".join(APPROVAL_ROUTES))
    if via == "relayed" and not filled(approval.get("quote")):
        raise Refused("A relayed approval needs the user's words as its quote.")
    phase["approval"] = {"at": now(), "via": via, "quote": approval.get("quote")}
    phase["status"] = "approved"


def reopen(state, target):
    phase = section(state, target)
    if phase["status"] not in ("reviewed", "approved"):
        raise Refused("%s is %s; there is nothing to reopen." % (label(phase), phase["status"]))
    phase["approval"] = None
    phase["status"] = working_status(phase)


def force_approve(state):
    """Close a feature the user already finished: approve every open section, whatever
    its status. -> the titles approved."""
    closed = []
    for phase in sections(state):
        if phase["status"] != "approved":
            phase["approval"] = {"at": now(), "via": "marked-done", "quote": None}
            phase["status"] = "approved"
            closed.append(heading(phase))
    return closed


def heading(phase):
    return phase["title"] if is_final(phase) else "Phase %s — %s" % (phase["id"], phase["title"])


def set_phase_text(phase, field, text):
    if field not in PHASE_TEXT:
        raise Refused("Not a phase field: %s. Fields: %s." % (field, ", ".join(PHASE_TEXT)))
    phase[field] = text


def set_feature_text(state, field, text):
    if field not in FEATURE_TEXT:
        raise Refused("Not a feature field: %s. Fields: %s." % (field, ", ".join(FEATURE_TEXT)))
    state[field] = text


def require_status(phase, expected):
    if phase["status"] != expected:
        raise Refused("%s is %s, not %s." % (label(phase), phase["status"], expected))


def require_earlier_approved(state, phase):
    earlier = sections(state)[:sections(state).index(phase)]
    waiting = [label(other) for other in earlier if other["status"] != "approved"]
    if waiting:
        raise Refused("%s cannot start: not approved yet: %s."
                      % (label(phase), "; ".join(waiting)))


def label(phase):
    return "The final review" if is_final(phase) else "Phase %s" % phase["id"]


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- files ------------------------------------------------------------------

def load(feature_dir):
    """The feature's state, or None when it has no state.json; raises Corrupt."""
    path = os.path.join(feature_dir, STATE_FILE)
    try:
        with open(path, "r", encoding="utf-8") as source:
            state = json.load(source)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as problem:
        raise Corrupt("%s is unreadable: %s" % (path, problem))
    if not isinstance(state, dict) or not isinstance(state.get("phases"), list):
        raise Corrupt("%s is not a workflow state." % path)
    if state.get("version") != VERSION:
        raise Corrupt("%s is version %r; this plugin reads version %d."
                      % (path, state.get("version"), VERSION))
    return state


def log_text(feature_dir):
    """What readers parse: rendered from state.json when the feature has one, so a stale
    or hand-edited phase-log.md cannot mislead them; otherwise the hand-written log."""
    state = load(feature_dir) if in_features_dir(feature_dir) else None
    if state is not None:
        return render(state)
    try:
        with open(os.path.join(feature_dir, LOG_FILE), "r", encoding="utf-8") as source:
            return source.read()
    except OSError:
        return None


def in_features_dir(path):
    """False for the legacy layout, whose docs sit at the project root beside any
    unrelated state.json the project may own."""
    return os.path.basename(os.path.dirname(os.path.abspath(path))) == "features"


def create(feature_dir, state):
    os.makedirs(feature_dir, exist_ok=True)
    with locked(feature_dir):
        for name in (STATE_FILE, LOG_FILE):
            if os.path.exists(os.path.join(feature_dir, name)):
                raise Refused("%s already has a %s." % (feature_dir, name))
        save(feature_dir, state)


def update(feature_dir, change, event):
    """Apply `change(state)` under the lock and record `event` (`by`, `do`, `phase`)."""
    with locked(feature_dir):
        state = load(feature_dir)
        if state is None:
            raise Refused("%s has no %s." % (feature_dir, STATE_FILE))
        change(state)
        state["events"].append(dict(event, at=now()))
        save(feature_dir, state)
    return state


def save(feature_dir, state):
    write_atomically(os.path.join(feature_dir, STATE_FILE), json.dumps(state, indent=2) + "\n")
    write_atomically(os.path.join(feature_dir, LOG_FILE), render(state))


@contextlib.contextmanager
def locked(feature_dir):
    with open(os.path.join(feature_dir, LOCK_FILE), "w") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def write_atomically(path, text):
    handle, temporary = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".state-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as target:
            target.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


# --- phase-log.md -----------------------------------------------------------

def render(state):
    """phase-log.md in the layout the legacy parser and people already read."""
    all_sections = sections(state)
    blocks = ["# Phase log: %s\n\n%s\n" % (state["title"], GENERATED_NOTE)]
    for phase in all_sections:
        lines = render_final(phase) if is_final(phase) else render_phase(phase)
        if phase is all_sections[-1]:
            lines += feature_lines(state)
        blocks.append("\n".join(lines) + "\n")
    return "\n".join(blocks)


def render_phase(phase):
    ticks = [("coded", phase["status"] != "pending"),
             ("code-reviewed", phase["status"] in ("reviewed", "approved")),
             ("security-scanned", phase["security_scanned"]),
             ("USER APPROVED", phase["status"] == "approved")]
    return (["## " + heading(phase), status_line(ticks),
             field_line("Changed", phase["changed"]),
             field_line("Review map", phase["review_summary"])]
            + ["  - %s %s" % (entry["tier"], entry["text"]) for entry in phase["review_map"]]
            + [field_line("Over budget", phase["over_budget"]),
               field_line("Code review result", phase["review_result"])]
            + shared_lines(phase))


def render_final(phase):
    ticks = [("full code review", phase["status"] in ("reviewed", "approved")),
             ("security-audit", phase["security_scanned"]),
             ("USER APPROVED", phase["status"] == "approved")]
    return (["## " + heading(phase), status_line(ticks),
             field_line("Cross-phase findings", phase["review_result"])]
            + shared_lines(phase))


def shared_lines(phase):
    lines = [field_line("Review rounds", "%d/%d" % (phase["rounds"], MAX_ROUNDS)),
             field_line("Unresolved", phase["unresolved"]),
             field_line("Deferred nits", phase["deferred_nits"]),
             field_line("Evidence", phase["evidence"]),
             field_line("User notes", phase["user_notes"])]
    approval = phase["approval"]
    if approval:
        lines.append(field_line("Approved", "%s, via %s" % (approval["at"], approval["via"])))
    return lines


def feature_lines(state):
    lines = [field_line("Project map updated", state["project_map"]),
             field_line("Lessons", state["lessons"])]
    if filled(state["post_ship_reviewed"]):
        lines.append(field_line("Post-ship reviewed", state["post_ship_reviewed"]))
    return lines


def status_line(ticks):
    return "- Status: " + "  ".join("[%s] %s" % ("x" if done else " ", name)
                                     for name, done in ticks)


def field_line(name, text):
    """Continuation lines are indented so a `- Word:` inside the text never ends the field."""
    lines = (text or "").strip().splitlines()
    return "\n".join(["- %s: %s" % (name, lines[0] if lines else "")]
                     + ["  " + line for line in lines[1:]]).rstrip()
