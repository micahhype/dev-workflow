#!/usr/bin/env python3
"""Stop hook: plan-and-budget guard for the dev-workflow plugin.

The workflow's two cheapness levers are both NUMBERS the model chooses for itself:
how many phases a plan has (each one costs the user an implement-review-approve
round-trip) and how many fix rounds a phase is allowed to burn arguing with its
reviewer. Prompt text alone kept losing to the model's instinct to split work and
to keep reviewing, which is how a twenty-line change grew a three-phase plan.

No hook can judge whether four phases were warranted — that is a design opinion.
What a hook CAN do is make the justification EXIST, and make an exceeded budget
visible instead of silent. So this gate refuses to let a turn end when:

  1. `plan.md` has been drafted but its `## Size estimate` is still the template
     placeholder — the size is what makes an over-built plan visible at the
     approval checkpoint, so a plan without it hides exactly what it must show.
  2. A plan has more than one phase and some phase after the first carries no
     `- Why separate:` reason. Splitting stays allowed; splitting SILENTLY does not.
  3. A phase-log section records more than 2 review rounds with an empty
     `- Unresolved:` — the budget was blown and nothing was escalated to the user,
     which is the failure mode the budget exists to prevent.
  4. A FINISHED feature (every section approved) never said what it did to
     `project-map.md`. Stage 5 is what maintains the map, and single-phase features
     skip Stage 5 — which, now that phases have to earn themselves, is most of them.
  5. A FINISHED feature never said what it LEARNED: no `- Lessons:` line on its
     last section. The review findings, the user's corrections and the suggestions
     they turned down die with the feature unless someone turns them into rules, and
     the step that does it runs at the one moment everyone wants to be done.
  6. The current phase is reviewed but has no `- Review map:` — the map is what
     spares the user reading the whole diff, so it must exist before they approve.
  7. The current phase's diff outgrew its plan `- Size:` budget and `- Over budget:`
     does not say why — a diff too big to review is the bottleneck this prevents.

Like the evidence gate, this raises the floor; it cannot judge whether what was
written is TRUE. "Because it is separate" satisfies (2) — it is the user reading
the plan at the checkpoint who judges the reason. What it removes is the silent
case, which nobody can review.

Safety: fails open on any error, silent unless a drafted plan.md is present, and
bounded — after MAX_BLOCKS refusals it yields, LOUDLY, so it can never trap a turn.
"""
import json
import os
import re
import sys

import _workflow
import diff_budget
from _workflow import docs_dir, field_text, is_unfilled, iter_phases, read

# `#{2,3}` because the template writes `### Phase 1 — ...` but a hand-written plan
# often uses `##`; `\b` keeps the `## Phases` container heading from matching.
PLAN_PHASE = re.compile(r"^#{2,3}[ \t]+Phase\b[^\n]*$", re.MULTILINE | re.IGNORECASE)
SIZE_HEADING = re.compile(r"^#{2,3}[ \t]+Size estimate[ \t]*$", re.MULTILINE | re.IGNORECASE)
ANY_HEADING = re.compile(r"^#{1,3}[ \t]+", re.MULTILINE)
ROUNDS_NUM = re.compile(r"(\d+)")
PHASE_NUM = re.compile(r"^Phase\s+(\d+)", re.IGNORECASE)
CODED = re.compile(r"\[[xX]\]\s*coded")
REVIEWED = re.compile(r"\[[xX]\]\s*code-reviewed")
# `(?!`?<)`: the template's own example entries are `<placeholders>`, not a map.
MAP_ENTRY = re.compile(r"^[ \t]*-[ \t]*(?:MUST|SKIM|SKIP)[ \t]+(?!`?<)\S", re.MULTILINE)

MAX_ROUNDS = 2  # keep in step with the review-round budget in skills/feature/SKILL.md
MAX_BLOCKS = 3
BUDGET_FACTOR = 2
BUDGET_SLACK = 40  # lines; a 10-line estimate should not refuse a 25-line phase
COUNTER_FILE = "plan-guard.json"

# Content that is present but not part of the plan. The template ships a
# commented-out `### Phase 2` block to copy, and a plan may quote a heading inside a
# fence — counted literally, either would demand a `Why separate:` for a phase that
# does not exist, and the guard would refuse a perfectly good single-phase plan.
_NOISE = re.compile(r"<!--.*?-->|^```.*?^```", re.DOTALL | re.MULTILINE)


def strip_noise(text):
    return _NOISE.sub("", text)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def iter_plan_phases(plan):
    """Yield (title, body) per phase block in plan.md, in document order."""
    heads = list(PLAN_PHASE.finditer(plan))
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(plan)
        yield h.group(0).lstrip("# \t").strip(), plan[h.end():end]


def section_text(doc, heading_re):
    """Body of a `## <heading>` section up to the next heading, or None if absent."""
    m = heading_re.search(doc)
    if not m:
        return None
    rest = doc[m.end():]
    nxt = ANY_HEADING.search(rest)
    return rest[:nxt.start()] if nxt else rest


def plan_findings(plan):
    """Contract violations in a DRAFTED plan.md; [] when the plan is still the
    untouched scaffold (the feature has not reached Stage 3 yet — gating then would
    block the research and options conversation, which writes no plan)."""
    plan = strip_noise(plan)
    phases = list(iter_plan_phases(plan))
    drafted = [(t, b) for t, b in phases if not is_unfilled(field_text(b, "Scope"))]
    if not drafted:
        return []

    out = []
    if is_unfilled(section_text(plan, SIZE_HEADING)):
        out.append("`## Size estimate` in plan.md is empty or still the placeholder. "
                   "State files touched + rough lines, and how much is NEW structure "
                   "— it is what lets the user see an over-built plan before approving it.")

    if len(phases) > 1:
        missing = [t for t, b in phases[1:] if is_unfilled(field_text(b, "Why separate"))]
        if missing:
            out.append(
                "These phases have no `- Why separate:` reason: " + "; ".join(missing) +
                ". Every phase after the first costs the user a full "
                "implement-review-approve round-trip, so each one has to name why it "
                "could not be merged into the phase before it (crosses a subsystem "
                "boundary / needs its own rollback point / too big to review in one "
                "sitting). If there is no such reason, merge it.")
    return out


def budget_findings(log):
    """Phases that blew the review-round budget without escalating to the user."""
    out = []
    for title, body, _approved in iter_phases(log):
        raw = field_text(body, "Review rounds")
        if is_unfilled(raw):
            continue
        m = ROUNDS_NUM.search(raw)
        if not m or int(m.group(1)) <= MAX_ROUNDS:
            continue
        if is_unfilled(field_text(body, "Unresolved")):
            out.append(
                f"'{title}' records {m.group(1)} review rounds (budget is {MAX_ROUNDS}) "
                "but its `- Unresolved:` line is empty. Going past the budget means the "
                "coder and reviewer did not converge — that goes to the USER as an "
                "explicit decision, and what they decided is recorded there. Escalate it "
                "or record the call; do not let the extra rounds pass silently.")
    return out


def map_findings(log, root):
    """A finished feature that never said what it did to `project-map.md`.

    The map is the project's memory of what exists; it is worth having only if it
    keeps up. Stage 5 appends to it — but single-phase features SKIP Stage 5, and
    since phases now have to earn themselves, single-phase is the common case. So
    the one stage that maintained the map is the one most features no longer run.

    Enforced only where it can mean something: the project actually HAS a map, and
    the feature is finished (every section approved). Like every other check here it
    requires the STATEMENT, not the truth — "no structural change" is a complete and
    often correct answer."""
    if not os.path.isfile(os.path.join(root, "project-map.md")):
        return []  # no map in this project; nothing to keep up to date
    sections = list(iter_phases(log))
    if not sections or not all(approved for _t, _b, approved in sections):
        return []  # still in flight
    title, body, _ = sections[-1]
    # The LAST section specifically: allowing it anywhere would let an early phase
    # answer "no structural change" and cover for whatever the later phases added.
    if is_unfilled(field_text(body, "Project map updated")):
        return [f"'{title}' is the last section of a finished feature, but it has no "
                "`- Project map updated:` line. Say what this feature added to "
                "`project-map.md` — the feature row, any new module, building block or "
                "extension point — or write \"no structural change\" if it genuinely "
                "added nothing to know. A map that stops keeping up stops being read."]
    return []


def lessons_findings(log):
    """A finished feature with no `- Lessons:` line on its last section.

    Requires the statement, not a rule: "none" is a complete answer, and the
    common one. What it removes is the feature that ended without anyone asking."""
    sections = list(iter_phases(log))
    if not sections or not all(approved for _t, _b, approved in sections):
        return []
    title, body, _ = sections[-1]
    if is_unfilled(field_text(body, "Lessons")):
        return [f"'{title}' is the last section of a finished feature, but it has no "
                "`- Lessons:` line. Run the lessons step: propose at most three rules "
                "for `conventions.md` from what this feature's reviews and the user "
                "corrected, let the user pick, and record what was added — or write "
                "\"none\" if nothing recurred."]
    return []

def current_phase(log):
    """(title, body) of the first unapproved `## Phase N` section, or None."""
    for title, body, approved in iter_phases(log):
        if not approved:
            return (title, body) if PHASE_NUM.match(title) else None
    return None


def review_map_findings(log):
    current = current_phase(log)
    if current is None:
        return []
    title, body = current
    if not REVIEWED.search(body) or MAP_ENTRY.search(field_text(body, "Review map") or ""):
        return []
    return [f"'{title}' is reviewed but has no `- Review map:` with MUST / SKIM / SKIP "
            "entries. Record code-reviewer's map in phase-log.md and lead the approval "
            "checkpoint with it: the user reads the MUST hunks, not the whole diff."]


def phase_estimates(plan):
    """{phase number: changed lines} from each plan phase's `- Size:`."""
    estimates = {}
    for title, body in iter_plan_phases(strip_noise(plan)):
        number = PHASE_NUM.match(title)
        size = field_text(body, "Size")
        if number and not is_unfilled(size):
            lines = ROUNDS_NUM.search(size.replace(",", ""))
            if lines:
                estimates[int(number.group(1))] = int(lines.group(1))
    return estimates


def budget_limit(estimate):
    return max(estimate * BUDGET_FACTOR, estimate + BUDGET_SLACK)


def diff_budget_findings(root, slug, plan, log):
    current = current_phase(log)
    if current is None:
        return []
    title, body = current
    estimate = phase_estimates(plan).get(int(PHASE_NUM.match(title).group(1)))
    if estimate is None:
        return []
    try:
        lines = diff_budget.measure(root, slug or "", title, bool(CODED.search(body)))
    except Exception:
        return []  # git trouble must not trap the turn
    if lines is None or lines <= budget_limit(estimate):
        return []
    reason = field_text(body, "Over budget")
    if not is_unfilled(reason) and reason.strip().lower() not in ("none", "n/a"):
        return []
    return [f"'{title}' has changed {lines} lines; its plan `- Size:` budgeted ~{estimate} "
            f"(limit {budget_limit(estimate)}). A diff this size is what makes the user's "
            "review the bottleneck. Split what is left into its own phase (plan.md and "
            "phase-log.md, with a `- Why separate:`), or, if it must land together, say why "
            "in this section's `- Over budget:` line and tell the user before they review."]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # can't parse -> fail open

    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    ddir, slug = docs_dir(root)

    findings = []
    plan = read(os.path.join(ddir, "plan.md"))
    if plan:
        findings += plan_findings(plan)
    log = read(os.path.join(ddir, "phase-log.md"))
    if log:
        findings += budget_findings(log)
        findings += map_findings(log, root)
        findings += lessons_findings(log)
        findings += review_map_findings(log)
        if plan:
            findings += diff_budget_findings(root, slug, plan, log)

    key = f"{slug or ''}::plan"
    if not findings:
        _workflow.clear_counter(root, COUNTER_FILE, key)
        sys.exit(0)

    count = _workflow.load_counter(root, COUNTER_FILE, key) + 1
    # Persist BEFORE deciding, including past the limit: forgetting the count on
    # give-up would re-arm the guard on the next stop, so it would oscillate instead
    # of staying given up, and the give-up warning would never survive to be seen.
    saved = _workflow.save_counter(root, COUNTER_FILE, key, count)

    body = "\n".join("  - " + f for f in findings)
    # Give up at the bound — or when the count cannot be persisted AND we have
    # already blocked once this turn. Without that second clause a read-only
    # `.dev-workflow/` pins the count at 1 forever and the guard traps the turn,
    # the exact hard-lock the bound exists to prevent.
    if count > MAX_BLOCKS or (not saved and payload.get("stop_hook_active")):
        print(json.dumps({"systemMessage":
                          "[dev-workflow plan guard] GAVE UP after " + str(MAX_BLOCKS) +
                          " refusals. Letting the turn end so it cannot be trapped — but "
                          "these are UNFIXED:\n" + body}))
        sys.exit(0)

    block("[dev-workflow plan guard] The plan's own budget lines are not filled in:\n"
          + body +
          f"\n(Refusal {count} of {MAX_BLOCKS}; stopping again without fixing these will "
          "simply be refused again.)")


if __name__ == "__main__":
    main()
