"""Plan guard: the phase count and the review-round budget are numbers the model
picks for itself, so the guard makes the justification EXIST — it cannot judge
whether the reason is good, only whether the split was made silently."""
import os
import sys

import pytest

from conftest import HOOKS, hook_json, run_hook

sys.path.insert(0, HOOKS)
import diff_budget  # noqa: E402
import plan_guard  # noqa: E402
from plan_guard import MAX_BLOCKS  # noqa: E402

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "templates")

SIZE = "## Size estimate\n2 files, ~25 lines, no new structure.\n\n"
REVIEW_MAP = ("- Review map: 4 must-read / 0 skim / 10 skip of 14 changed lines\n"
              "  - MUST `api/orders.py:10-13` — default page → is page 1 the first 20?\n"
              "  - SKIP `tests/test_orders.py` — cited as evidence\n")


def one_phase(scope="add the page param", extra=""):
    return (f"# Plan: t\n\n{SIZE}"
            "### Phase 1 — do the thing\n"
            f"- Scope: {scope}\n"
            "- Files: `api/orders.py`\n"
            "- Done when: a request with no page param returns the first 20 orders\n"
            "- Verify: `pytest -q tests/test_orders.py`\n"
            "- Rollback: checkpoint before the edit\n" + extra)


def second_phase(why="<why this could NOT be merged>"):
    return ("\n### Phase 2 — the other thing\n"
            "- Scope: wire the caller\n"
            f"- Why separate: {why}\n"
            "- Files: `api/routes.py`\n"
            "- Done when: the route is registered\n"
            "- Verify: `pytest -q`\n"
            "- Rollback: checkpoint\n")


def write_docs(tmp_path, plan=None, log=None):
    """Lay down the feature docs WITHOUT running the hook — the read-only-counter
    test needs the files present while the counter file still does not exist."""
    d = tmp_path / ".dev-workflow" / "features" / "f"
    d.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".dev-workflow" / "active").write_text("f\n")
    if plan is not None:
        (d / "plan.md").write_text(plan)
    if log is not None:
        (d / "phase-log.md").write_text(log)


def stop(tmp_path, plan=None, log=None, payload=None):
    write_docs(tmp_path, plan, log)
    return run_hook("plan_guard.py", payload if payload is not None else {},
                    project_dir=tmp_path)


def blocked(proc):
    out = hook_json(proc)
    return bool(out) and out.get("decision") == "block"


def reason(proc):
    return (hook_json(proc) or {}).get("reason", "")


# --- silence when there is nothing to guard ---------------------------------

def test_no_plan_is_silent(tmp_path):
    assert hook_json(stop(tmp_path)) is None


def test_untouched_scaffold_is_silent(tmp_path):
    # THE false positive to avoid: plan.md is created at feature setup, but the plan
    # is not written until Stage 3. Gating the scaffold would block the research and
    # options conversation — turns that legitimately write no plan at all.
    tpl = open(os.path.join(TEMPLATES, "plan.md")).read()
    proc = stop(tmp_path, plan=tpl)
    assert hook_json(proc) is None, reason(proc)


def test_shipped_template_filled_in_passes(tmp_path):
    # The template must satisfy the guard once actually filled in: a template that
    # cannot pass its own hook would block every feature at Stage 3.
    tpl = open(os.path.join(TEMPLATES, "plan.md")).read()
    filled = (tpl.replace("<Files touched + rough lines, and what of that is NEW "
                          "structure vs edits to existing\ncode.",
                          "2 files, ~25 lines, no new structure. (")
                 .replace("- Scope: <what this phase does>", "- Scope: add the page param"))
    proc = stop(tmp_path, plan=filled)
    assert hook_json(proc) is None, reason(proc)


def test_commented_out_phase_does_not_count(tmp_path):
    # The template ships a commented-out `### Phase 2` block to copy. Counted
    # literally it would demand a `Why separate:` for a phase that does not exist,
    # and the guard would refuse a perfectly good single-phase plan.
    plan = one_phase() + "\n<!--\n### Phase 2 — sample\n- Scope:\n-->\n"
    proc = stop(tmp_path, plan=plan)
    assert hook_json(proc) is None, reason(proc)


def test_fenced_phase_heading_does_not_count(tmp_path):
    plan = one_phase() + "\n```\n### Phase 2 — quoted, not real\n```\n"
    assert hook_json(stop(tmp_path, plan=plan)) is None


def test_single_phase_needs_no_why_separate(tmp_path):
    assert hook_json(stop(tmp_path, plan=one_phase())) is None


# --- the phase budget -------------------------------------------------------

def test_second_phase_without_a_reason_is_blocked(tmp_path):
    proc = stop(tmp_path, plan=one_phase() + second_phase())
    assert blocked(proc)
    assert "Why separate" in reason(proc) and "Phase 2" in reason(proc)


def test_second_phase_with_a_reason_passes(tmp_path):
    plan = one_phase() + second_phase("touches the auth subsystem; needs its own rollback point")
    proc = stop(tmp_path, plan=plan)
    assert hook_json(proc) is None, reason(proc)


def test_reason_is_not_judged_only_required(tmp_path):
    # Deliberate: the guard removes the SILENT split. Whether the reason is any good
    # is the user's call at the plan checkpoint — a hook that tried to judge it would
    # be guessing, and would block good plans.
    plan = one_phase() + second_phase("it is a separate step")
    assert hook_json(stop(tmp_path, plan=plan)) is None


def test_missing_size_estimate_is_blocked(tmp_path):
    plan = one_phase().replace(SIZE, "")
    proc = stop(tmp_path, plan=plan)
    assert blocked(proc) and "Size estimate" in reason(proc)


def test_placeholder_size_estimate_is_blocked(tmp_path):
    plan = one_phase().replace(SIZE, "## Size estimate\n<files + rough lines>\n\n")
    assert blocked(stop(tmp_path, plan=plan))


# --- the review-round budget ------------------------------------------------

def log_with(rounds, unresolved):
    return ("# Phase log: t\n\n## Phase 1 — do the thing\n"
            "- Status: [x] coded  [x] code-reviewed  [ ] security-scanned  [ ] USER APPROVED\n"
            + REVIEW_MAP +
            f"- Review rounds: {rounds}\n"
            f"- Unresolved: {unresolved}\n"
            "- Evidence: `pytest -q` -> 53 passed\n"
            "- User notes:\n")


def test_over_budget_without_escalation_is_blocked(tmp_path):
    proc = stop(tmp_path, log=log_with("3/2", ""))
    assert blocked(proc)
    assert "3 review rounds" in reason(proc)


def test_over_budget_with_the_users_call_recorded_passes(tmp_path):
    proc = stop(tmp_path, log=log_with("3/2", "user chose to ship with the risk; see notes"))
    assert hook_json(proc) is None, reason(proc)


def test_within_budget_passes(tmp_path):
    assert hook_json(stop(tmp_path, log=log_with("2/2", ""))) is None


def test_placeholder_rounds_line_is_not_a_number(tmp_path):
    # The template's own `<N/2 — ...>` placeholder must not read as a blown budget.
    assert hook_json(stop(tmp_path, log=log_with("<N/2 — how many rounds>", ""))) is None


# --- keeping project-map.md alive -------------------------------------------

def done_log(*, map_line=None, first_map_line=None, lessons="none"):
    """A finished two-phase feature (every section approved)."""
    def sec(title, extra):
        return (f"## {title}\n"
                "- Status: [x] coded  [x] code-reviewed  [ ] security-scanned  [x] USER APPROVED\n"
                + REVIEW_MAP +
                f"{extra}"
                "- Evidence: `pytest -q` -> 53 passed\n")
    a = sec("Phase 1 — a", f"- Project map updated: {first_map_line}\n" if first_map_line else "")
    b = sec("Phase 2 — b", (f"- Project map updated: {map_line}\n" if map_line else "")
            + (f"- Lessons: {lessons}\n" if lessons else ""))
    return "# Phase log: t\n\n" + a + "\n" + b


def with_map(tmp_path):
    (tmp_path / "project-map.md").write_text("# Project map\n")


def test_finished_feature_without_a_map_line_is_blocked(tmp_path):
    with_map(tmp_path)
    proc = stop(tmp_path, log=done_log())
    assert blocked(proc) and "Project map updated" in reason(proc)


def test_no_project_map_in_the_project_means_nothing_to_keep_up(tmp_path):
    # A project that declined `init` has no map; demanding a line about it would be
    # noise on every feature, forever.
    assert hook_json(stop(tmp_path, log=done_log())) is None


def test_no_structural_change_is_a_complete_answer(tmp_path):
    with_map(tmp_path)
    proc = stop(tmp_path, log=done_log(map_line="no structural change"))
    assert hook_json(proc) is None, reason(proc)


def test_unfinished_feature_is_not_asked_yet(tmp_path):
    with_map(tmp_path)
    log = done_log().replace("[x] USER APPROVED", "[ ] USER APPROVED", 1)
    assert hook_json(stop(tmp_path, log=log)) is None


def test_an_early_phase_cannot_answer_for_the_whole_feature(tmp_path):
    # The loophole the "last section" rule closes: Phase 1 says "no structural
    # change", Phase 2 adds a whole module, and the feature ships with a stale map.
    with_map(tmp_path)
    proc = stop(tmp_path, log=done_log(first_map_line="no structural change"))
    assert blocked(proc) and "Phase 2" in reason(proc)


# --- lessons ----------------------------------------------------------------

def test_finished_feature_without_a_lessons_line_is_blocked(tmp_path):
    proc = stop(tmp_path, log=done_log(lessons=None))
    assert blocked(proc) and "Lessons" in reason(proc)


def test_lessons_placeholder_is_not_an_answer(tmp_path):
    proc = stop(tmp_path, log=done_log(lessons="<rules added, or none>"))
    assert blocked(proc)


def test_none_is_a_complete_lessons_answer(tmp_path):
    assert hook_json(stop(tmp_path, log=done_log(lessons="none"))) is None


def test_unfinished_feature_is_not_asked_for_lessons(tmp_path):
    log = done_log(lessons=None).replace("[x] USER APPROVED", "[ ] USER APPROVED", 1)
    assert hook_json(stop(tmp_path, log=log)) is None


# --- review map -------------------------------------------------------------

def reviewed_log(review_map=REVIEW_MAP, reviewed=True):
    box = "[x]" if reviewed else "[ ]"
    return ("# Phase log: t\n\n## Phase 1 — do the thing\n"
            f"- Status: [x] coded  {box} code-reviewed  [ ] security-scanned  [ ] USER APPROVED\n"
            + review_map +
            "- Evidence: `pytest -q` -> 53 passed\n")


def test_reviewed_phase_without_a_map_is_blocked(tmp_path):
    proc = stop(tmp_path, log=reviewed_log(review_map=""))
    assert blocked(proc) and "Review map" in reason(proc)


def test_the_templates_example_entries_are_not_a_map(tmp_path):
    tpl = open(os.path.join(TEMPLATES, "phase-log.md")).read()
    template_map = tpl[tpl.index("- Review map:"):tpl.index("- Over budget:")]
    assert blocked(stop(tmp_path, log=reviewed_log(review_map=template_map)))


def test_a_map_with_entries_passes(tmp_path):
    proc = stop(tmp_path, log=reviewed_log())
    assert hook_json(proc) is None, reason(proc)


def test_a_phase_not_yet_reviewed_needs_no_map(tmp_path):
    assert hook_json(stop(tmp_path, log=reviewed_log(review_map="", reviewed=False))) is None


# --- phase Size against the lines actually changed ---------------------------

def budget_plan(size="~10 lines"):
    return one_phase().replace("- Verify:", f"- Size: {size}\n- Verify:")


def coded_log(coded=True, over_budget=None):
    box = "[x]" if coded else "[ ]"
    return ("# Phase log: t\n\n## Phase 1 — do the thing\n"
            f"- Status: {box} coded  [ ] code-reviewed  [ ] security-scanned  [ ] USER APPROVED\n"
            + (f"- Over budget: {over_budget}\n" if over_budget else "") +
            "- Evidence:\n")


def grow(repo, lines):
    (repo / "big.py").write_text("".join(f"x{i} = {i}\n" for i in range(lines)))


def test_phase_estimates_reads_each_phases_size():
    plan = budget_plan("~1,200 lines") + second_phase("own rollback").replace(
        "- Verify:", "- Size: 30\n- Verify:")
    assert plan_guard.phase_estimates(plan) == {1: 1200, 2: 30}


def test_a_diff_past_its_budget_is_blocked(git_repo):
    assert hook_json(stop(git_repo, plan=budget_plan(), log=coded_log(coded=False))) is None
    grow(git_repo, 120)
    proc = stop(git_repo, plan=budget_plan(), log=coded_log())
    assert blocked(proc) and "120 lines" in reason(proc) and "limit 50" in reason(proc)


def test_a_diff_within_its_budget_passes(git_repo):
    stop(git_repo, plan=budget_plan(), log=coded_log(coded=False))
    grow(git_repo, 45)
    proc = stop(git_repo, plan=budget_plan(), log=coded_log())
    assert hook_json(proc) is None, reason(proc)


def test_over_budget_with_a_reason_passes_but_none_does_not(git_repo):
    stop(git_repo, plan=budget_plan(), log=coded_log(coded=False))
    grow(git_repo, 120)
    assert blocked(stop(git_repo, plan=budget_plan(), log=coded_log(over_budget="none")))
    proc = stop(git_repo, plan=budget_plan(),
                log=coded_log(over_budget="the migration and its backfill must land together"))
    assert hook_json(proc) is None, reason(proc)


def test_a_phase_first_seen_already_coded_is_not_measured(git_repo):
    # Counting from HEAD would charge it with every earlier phase's uncommitted work.
    grow(git_repo, 500)
    proc = stop(git_repo, plan=budget_plan(), log=coded_log())
    assert hook_json(proc) is None, reason(proc)


def test_the_next_phase_coded_in_the_approval_turn_starts_from_the_last_stop(git_repo):
    two = budget_plan() + second_phase("own rollback").replace("- Verify:", "- Size: 10\n- Verify:")
    first_current = ("# Phase log: t\n\n## Phase 1 — do the thing\n"
                     "- Status: [x] coded  [ ] code-reviewed  [ ] security-scanned  [ ] USER APPROVED\n"
                     "- Evidence:\n\n## Phase 2 — the other thing\n"
                     "- Status: [ ] coded  [ ] code-reviewed  [ ] security-scanned  [ ] USER APPROVED\n")
    stop(git_repo, plan=two, log=first_current.replace("[x] coded", "[ ] coded", 1))
    grow(git_repo, 30)
    assert hook_json(stop(git_repo, plan=two, log=first_current)) is None
    second_current = (first_current.replace("[ ] USER APPROVED", "[x] USER APPROVED", 1)
                      .replace("[ ] coded", "[x] coded"))
    (git_repo / "small.py").write_text("y = 1\n")
    proc = stop(git_repo, plan=two, log=second_current)
    assert hook_json(proc) is None, reason(proc)
    recorded = diff_budget.load(str(git_repo))["f"]
    assert recorded["phase"] == "Phase 2 — the other thing" and recorded["lines"] == 1


# --- bounding, so it cannot trap the turn -----------------------------------

def test_gives_up_loudly_rather_than_hard_locking_the_turn(tmp_path):
    plan = one_phase() + second_phase()
    for i in range(MAX_BLOCKS):
        assert blocked(stop(tmp_path, plan=plan)), f"refusal {i + 1} should block"
    out = hook_json(stop(tmp_path, plan=plan))
    assert out is not None and "decision" not in out
    assert "GAVE UP" in out["systemMessage"] and "Why separate" in out["systemMessage"]


def test_fixing_the_plan_resets_the_budget(tmp_path):
    plan = one_phase() + second_phase()
    assert blocked(stop(tmp_path, plan=plan))
    fixed = one_phase() + second_phase("crosses the auth boundary")
    assert hook_json(stop(tmp_path, plan=fixed)) is None
    assert blocked(stop(tmp_path, plan=plan)), "counter should have restarted"


def test_unwritable_counter_cannot_trap_the_turn(tmp_path):
    # If `.dev-workflow/` is read-only (or full) the count cannot be persisted, so it
    # never reaches the give-up bound. The whole point of the bound is that the guard
    # cannot block forever — a broken counter must fall back to yielding, not to
    # blocking on every stop. The directory must be read-only BEFORE the first block,
    # or the counter file already exists and stays writable through it.
    if os.getuid() == 0:
        pytest.skip("root bypasses the directory write permission this test needs")
    write_docs(tmp_path, plan=one_phase() + second_phase())
    state = tmp_path / ".dev-workflow"
    os.chmod(state, 0o555)
    try:
        assert blocked(run_hook("plan_guard.py", {}, project_dir=tmp_path))
        out = hook_json(run_hook("plan_guard.py", {"stop_hook_active": True},
                                 project_dir=tmp_path))
        assert out is None or out.get("decision") != "block", "trapped the turn"
    finally:
        os.chmod(state, 0o755)


def test_malformed_stdin_fails_open(tmp_path):
    proc = run_hook("plan_guard.py", "{not json", project_dir=tmp_path)
    assert hook_json(proc) is None and proc.returncode == 0


def test_both_failures_reported_together(tmp_path):
    proc = stop(tmp_path, plan=one_phase().replace(SIZE, "") + second_phase(),
                log=log_with("4/2", ""))
    r = reason(proc)
    assert "Size estimate" in r and "Why separate" in r and "4 review rounds" in r
