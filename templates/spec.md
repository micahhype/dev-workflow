# Spec: <feature name>

> Source of truth for WHAT and WHY. Fill this before planning. Keep it updated
> if the decision changes.

## 1. Problem / idea
<What are we building and why. The user-facing goal — written as the orchestrator
restated it back to the user, not as the raw one-line request.>

<!-- BUG MODE ONLY — delete this block for a feature. Filled in Stage 0.5's bug
     branch, before anything is planned, so the CAUSE is reviewable at the plan
     checkpoint instead of living only in the conversation.
## 1a. Bug: reproduction & root cause
- Repro: <the smallest command / test / request that triggers it, verbatim>
- Observed: <actual output — pasted, not paraphrased. This is the "before" half of
  Stage 4's Evidence ledger.>
- Expected: <what should have happened>
- Root cause: <`file:line` + why THAT code produces THIS symptom. The cause, not the
  place the symptom surfaced.>
- Blast radius: <what else reaches this code path; what else the same cause is
  plausibly breaking that nobody reported>
- Data already written: <bad rows/records the bug produced, or "none". Repairing them
  is its own phase — never folded into the code fix.>
-->

## 1b. Acceptance criteria
<Concrete, checkable statements of what must be true when this is done. Each one
should be something an artifact can be pointed at: "a request with no `page` param
returns the first 20 orders", not "pagination works". Stage 4's Evidence ledger
cites one artifact per criterion, and each phase's `Done when:` in plan.md comes
from here.>

## 1c. Assumptions & answers
<What the user was ASKED and answered (question -> answer), and what was ASSUMED
without asking. Assumptions stay visible so they can be vetoed later — an
assumption nobody can see is just a guess. An assumption picks between readings of
the request; it never adds behaviour.>

Suggested, not built: <extras you think are worth it — a limit, a cache, a guard, a
business rule — one line each, or "none". NOT built unless the user opts in.>

## 2. Domain research summary
<Key findings from the domain-researcher: relevant patterns, pitfalls, links.>

## 2b. What already exists here
<From the domain-researcher's codebase survey + project-map.md: the closest
existing implementations (path:line), the building blocks to reuse, the extension
point this hooks into, and what would be DUPLICATED if built from scratch. "Nothing
yet" is a valid answer — write it explicitly rather than leaving this blank.>

## 3. Solution option and its deltas
<The core option as the architect returned it. Add a second column of rows (Core B)
only when two architects ran, and say where they disagree.>

| Core | Approach | Size (files, ~lines) | Risks covered | Complexity | Effort |
|------|----------|----------------------|---------------|------------|--------|
| A    |          |                      |               |            |        |

| Delta | Size | What it buys or loses |
|-------|------|-----------------------|
| Leaner: drop <X> | saves ~N lines | loses <what stops being covered> |
| Safer: add <Z>   | costs ~N lines | covers <W> |

## 4. Chosen solution + rationale
<The core (which one, when there were two) and the deltas the user took or turned
down, and WHY. Note the tradeoffs accepted.>

## 5. Non-goals / out of scope
<Explicitly what we are NOT doing in this feature.>

## 6. Project constraints that apply (from conventions.md)
<Relevant domain-specific correctness rules and conventions this feature must
respect.>
