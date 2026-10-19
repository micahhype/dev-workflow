# Plan: <feature name>

> Source of truth for HOW. Derived from spec.md. Approved in Plan Mode before any
> code is written.
>
> **Start from ONE phase and justify every additional one.** A phase costs a full
> coder + review + user-approval loop, so it must earn itself: it crosses a
> subsystem boundary, it needs its own rollback point because the step is risky, or
> it is genuinely too big to review in one sitting. "It has three logical steps" is
> not a reason — steps a reviewer checks in one pass, that touch the same files, or
> that only make sense together are ONE phase. There is deliberately no target count
> here: a range reads as a quota to fill.

## Size estimate
<Files touched + rough lines, and what of that is NEW structure vs edits to existing
code. Stated up front so an over-built plan is visible before it is approved.
MACHINE-CHECKED: the plan guard refuses to end a turn while this is still the
placeholder.>

## Structure
> The SHAPE of the change, decided here — not left to the coder to improvise.
> Reviewed by the plan-reviewer and the user before any code is written.
- Pattern: <the existing feature this one is shaped like, by path — e.g. "same as
  `src/orders/` (controller → service → repository)". The coder mirrors it. If
  nothing in the project fits, say so and name the pattern you chose and why.>
- Files:
  - `path/to/file` — NEW / EDIT — <its one responsibility>
- Flow: <the main path in 3–6 steps, entry point to output, naming the file each
  step lives in — e.g. `route (api/orders.ts)` → `validate (orders/schema.ts)` →
  `OrderService.create (orders/service.ts)` → `repo.insert`>
- Deviations: <where this change departs from the pattern above and why, or "none">

## Phases
> Order by dependency, then risk (uncertain phases early). One reviewable diff each.
> Every phase independently verifiable, with a rollback point. Between them, the
> phases must cover every acceptance criterion in `spec.md` section 1b — a criterion
> no phase delivers is a missing phase; a phase that serves no criterion is scope
> creep. Copy the block below for a second phase ONLY once it has earned itself —
> and then it needs a `- Why separate:` line, which the plan guard enforces.

### Phase 1 — <title>
- Scope: <what this phase does>
- Files: <exact paths + the function/symbol or line range to touch where known — so
  the coder Reads the spot directly instead of searching for it>
- Done when: <the acceptance criteria from `spec.md` 1b that THIS phase delivers,
  quoted — not a restatement of the scope>
- Size: <~N changed lines (added + deleted, tests included). MACHINE-CHECKED: the
  plan guard measures the phase's real diff and refuses past 2× this (min +40) until
  `- Over budget:` in phase-log.md says why. Aim for one sitting of review.>
- Verify: <test/command/output that proves it — becomes the Evidence ledger>
- Rollback: <checkpoint / how to revert this phase cleanly>

<!-- Second and later phases only. `- Why separate:` is MACHINE-CHECKED — the plan
     guard refuses to end a turn while any phase after the first lacks it.
### Phase 2 — <title>
- Scope:
- Why separate: <why this could NOT be merged into the phase before it — crosses a
  subsystem boundary / needs its own rollback point / too big to review in one
  sitting. "It is a separate step" is not a reason; if there is none, merge it.>
- Files:
- Done when:
- Size:
- Verify:
- Rollback:
-->


## Open questions for the user
<Only what is STILL unresolved. Questions already asked and answered, and
assumptions already stated, live in `spec.md` section 1c — don't re-ask them here.>
