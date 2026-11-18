"""Workflow state: transitions refuse what the markdown log used to accept silently, and the
rendered phase-log.md still reads correctly through the legacy parser."""
import sys

import pytest

from conftest import HOOKS

sys.path.insert(0, HOOKS)
import _workflow  # noqa: E402
import evidence_guard  # noqa: E402
import plan_guard  # noqa: E402
import state as workflow_state  # noqa: E402
from state import Refused  # noqa: E402

EVIDENCE = "`pytest -q` -> 12 passed\n- Tests: all green"
REVIEW = {"entries": [{"tier": "MUST", "text": "`src/a.py:1-9` — parses → empty input?"}],
          "security_scanned": True}
USER = {"via": "user"}


def feature(*titles):
    state = workflow_state.new_state("orders", "Paginate orders")
    workflow_state.set_phases(state, list(titles) or ["only"])
    return state


def code(state, number):
    workflow_state.mark_coded(state, number, {"changed": "src/a.py", "evidence": EVIDENCE})


def finish(state, number):
    code(state, number)
    workflow_state.mark_reviewed(state, number, REVIEW)
    workflow_state.approve(state, number, USER)


def test_a_phase_walks_from_pending_to_approved():
    state = feature()
    finish(state, 1)
    phase = state["phases"][0]
    assert phase["status"] == "approved"
    assert phase["approval"]["via"] == "user"
    assert phase["security_scanned"] is True


def test_a_phase_cannot_be_reviewed_before_it_is_coded():
    with pytest.raises(Refused, match="pending, not coded"):
        workflow_state.mark_reviewed(feature(), 1, REVIEW)


def test_coding_needs_changed_and_evidence():
    with pytest.raises(Refused, match="evidence"):
        workflow_state.mark_coded(feature(), 1, {"changed": "src/a.py", "evidence": " "})


def test_the_next_phase_waits_for_the_previous_approval():
    state = feature("one", "two")
    code(state, 1)
    with pytest.raises(Refused, match="not approved yet: Phase 1"):
        code(state, 2)


@pytest.mark.parametrize("entries", [[], [{"tier": "ASSUME", "text": "page size is 20"}],
                                     [{"tier": "READ", "text": "src/a.py"}]])
def test_review_needs_a_real_map_entry(entries):
    state = feature()
    code(state, 1)
    with pytest.raises(Refused, match="review-map|review map"):
        workflow_state.mark_reviewed(state, 1, {"entries": entries})


def test_rounds_over_budget_need_the_users_call_recorded():
    state = feature()
    code(state, 1)
    for _ in range(workflow_state.MAX_ROUNDS + 1):
        workflow_state.start_round(state, 1)
    with pytest.raises(Refused, match="3 review rounds"):
        workflow_state.mark_reviewed(state, 1, REVIEW)
    workflow_state.set_phase_text(state["phases"][0], "unresolved", "user accepted the risk")
    workflow_state.mark_reviewed(state, 1, REVIEW)
    assert state["phases"][0]["status"] == "reviewed"


def test_approval_needs_evidence_a_route_and_a_quote_when_relayed():
    state = feature()
    code(state, 1)
    workflow_state.mark_reviewed(state, 1, REVIEW)
    with pytest.raises(Refused, match="arrives via"):
        workflow_state.approve(state, 1, {"via": "orchestrator"})
    with pytest.raises(Refused, match="quote"):
        workflow_state.approve(state, 1, {"via": "relayed"})
    workflow_state.set_phase_text(state["phases"][0], "evidence", "looks fine")
    with pytest.raises(Refused, match="no cited evidence"):
        workflow_state.approve(state, 1, USER)


def test_reopen_clears_the_approval():
    state = feature()
    finish(state, 1)
    workflow_state.reopen(state, 1)
    assert state["phases"][0]["status"] == "coded"
    assert state["phases"][0]["approval"] is None


def test_only_a_multi_phase_feature_has_a_final_review():
    assert feature()["final_review"] is None
    state = feature("one", "two")
    finish(state, 1)
    with pytest.raises(Refused, match="not approved yet: Phase 2"):
        workflow_state.mark_reviewed(state, workflow_state.FINAL, {})
    finish(state, 2)
    workflow_state.mark_reviewed(state, workflow_state.FINAL, {"security_scanned": True})
    assert state["final_review"]["status"] == "reviewed"


def test_the_phase_list_is_not_replaced_once_work_started_but_a_phase_can_be_added():
    state = feature()
    code(state, 1)
    with pytest.raises(Refused, match="Work has started"):
        workflow_state.set_phases(state, ["a", "b"])
    workflow_state.add_phase(state, "follow-up")
    assert [phase["id"] for phase in state["phases"]] == [1, 2]
    assert state["final_review"]["status"] == "pending"


def test_update_persists_records_the_event_and_renders_the_log(tmp_path):
    workflow_state.create(str(tmp_path), feature())
    workflow_state.update(str(tmp_path), lambda state: code(state, 1),
                          {"by": "coder", "do": "coded", "phase": 1})
    saved = workflow_state.load(str(tmp_path))
    assert saved["phases"][0]["status"] == "coded"
    assert saved["events"][-1]["by"] == "coder" and saved["events"][-1]["at"]
    assert "[x] coded" in (tmp_path / "phase-log.md").read_text()


def test_a_refused_update_writes_nothing(tmp_path):
    workflow_state.create(str(tmp_path), feature())
    before = (tmp_path / "state.json").read_text()
    with pytest.raises(Refused):
        workflow_state.update(str(tmp_path), lambda state: workflow_state.reopen(state, 1),
                              {"by": "orchestrator", "do": "reopen", "phase": 1})
    assert (tmp_path / "state.json").read_text() == before


def test_create_refuses_a_directory_that_already_has_a_log(tmp_path):
    (tmp_path / "phase-log.md").write_text("# Phase log: legacy\n")
    with pytest.raises(Refused, match="already has"):
        workflow_state.create(str(tmp_path), feature())


def test_load_tells_missing_from_corrupt(tmp_path):
    assert workflow_state.load(str(tmp_path)) is None
    (tmp_path / "state.json").write_text("{not json")
    with pytest.raises(workflow_state.Corrupt):
        workflow_state.load(str(tmp_path))


def test_the_rendered_log_reads_the_same_through_the_legacy_parser():
    state = feature("one", "two")
    finish(state, 1)
    code(state, 2)
    workflow_state.mark_reviewed(state, 2, REVIEW)
    workflow_state.set_feature_text(state, "lessons", "none")
    parsed = list(_workflow.iter_phases(workflow_state.render(state)))

    assert [(title, approved) for title, _body, approved in parsed] == [
        ("Phase 1 — one", True), ("Phase 2 — two", False), ("Final review (all phases)", False)]
    reviewed_body = parsed[1][1]
    assert "- Tests: all green" in _workflow.field_text(reviewed_body, "Evidence")
    assert not evidence_guard.evidence_empty(reviewed_body)
    assert plan_guard.review_map_findings(workflow_state.render(state)) == []
    assert _workflow.field_text(parsed[2][1], "Lessons").strip() == "none"
    assert "Post-ship reviewed" not in parsed[2][1]
