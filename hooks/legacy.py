#!/usr/bin/env python3
"""Read a hand-written phase-log.md into the state.json structure."""
import re
import textwrap

import _workflow
import state as workflow_state

LOG_TITLE = re.compile(r"^#\s*Phase log:\s*(.+)$", re.MULTILINE)
PHASE_TITLE = re.compile(r"^Phase\s+\d+\s*[—–:-]*\s*(.*)$", re.IGNORECASE)
MAP_ENTRY = re.compile(r"^[ \t]*-[ \t]*(MUST|SKIM|SKIP|ASSUME)[ \t]+(?!`?<)(\S.*)$", re.MULTILINE)
REVIEWED = re.compile(r"\[[xX]\]\s*(?:code-reviewed|full code review)")
CODED = re.compile(r"\[[xX]\]\s*coded")
SCANNED = re.compile(r"\[[xX]\]\s*(?:security-scanned|security-audit)")
ROUNDS = re.compile(r"\d+")
PHASE_FIELDS = {"changed": "Changed", "evidence": "Evidence", "unresolved": "Unresolved",
                "deferred_nits": "Deferred nits", "over_budget": "Over budget",
                "user_notes": "User notes"}
FEATURE_FIELDS = {"project_map": "Project map updated", "lessons": "Lessons",
                  "post_ship_reviewed": "Post-ship reviewed"}
RESULT_FIELDS = ("Code review result", "Cross-phase findings")


def state_from_log(log, slug):
    titled = LOG_TITLE.search(log)
    title = titled.group(1).strip() if titled else ""
    state = workflow_state.new_state(slug, slug if not title or title.startswith("<") else title,
                                     tier=None)
    last_body = ""
    for heading, body, approved in _workflow.iter_phases(log):
        last_body = body
        if heading.lower().startswith("final"):
            state["final_review"] = section_from(workflow_state.FINAL, heading, body)
            state["final_review"]["status"] = status_of(body, approved, final=True)
        else:
            phase = section_from(len(state["phases"]) + 1, phase_title(heading), body)
            phase["status"] = status_of(body, approved, final=False)
            state["phases"].append(phase)
    for field, name in FEATURE_FIELDS.items():
        state[field] = text(last_body, name)
    return state


def phase_title(heading):
    return PHASE_TITLE.match(heading).group(1).strip() or heading


def section_from(number, title, body):
    phase = workflow_state.new_phase(number, title)
    for field, name in PHASE_FIELDS.items():
        phase[field] = text(body, name)
    phase["review_result"] = next(filter(None, (text(body, name) for name in RESULT_FIELDS)), None)
    review_map = text(body, "Review map") or ""
    summary = review_map.splitlines()[0].strip() if review_map else ""
    phase["review_summary"] = None if not summary or MAP_ENTRY.match(summary) else summary
    phase["review_map"] = [{"tier": tier, "text": entry.strip()}
                           for tier, entry in MAP_ENTRY.findall(review_map)]
    rounds = ROUNDS.search(text(body, "Review rounds") or "")
    phase["rounds"] = int(rounds.group(0)) if rounds else 0
    phase["security_scanned"] = bool(SCANNED.search(body))
    return phase


def status_of(body, approved, final):
    if approved:
        return "approved"
    if REVIEWED.search(body):
        return "reviewed"
    return "coded" if CODED.search(body) and not final else "pending"


def text(body, name):
    value = _workflow.field_text(body, name)
    if _workflow.is_unfilled(value):
        return None
    return textwrap.dedent(value).strip()
