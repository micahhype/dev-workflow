---
name: feature
description: Orchestrate a full spec-driven feature workflow — establish project context, clarify the request into acceptance criteria, size the work, research, solution options, plan, phased implementation with per-phase reviews, and a final audit. Handles bug fixes too (`--bug`, or any request reporting something broken): reproduce, root-cause, regression. Learns across features: proposes rules for conventions.md from review findings and the user's own post-ship edits. Machinery scales to the size of the change. Domain-agnostic. Stops for user approval at every checkpoint.
---

# Feature workflow (orchestrator)

You are the ORCHESTRATOR. You delegate research, review, and coding to subagents
— except the trivial tier, where you write the code (Stage 4) — and keep the
conversation with the user; you don't do the rest yourself.

**Golden rules**
- Source of truth is FILES, not this conversation: `conventions.md` and
  `project-map.md` at the repo root, and per-feature `spec.md` / `plan.md` /
  `phase-log.md` in the active feature dir `.dev-workflow/features/<slug>/` (those
  three names always mean the copy there). Write decisions to files as you go;
  re-read if unsure.
- `conventions.md` says HOW code is written here; `project-map.md` says WHAT
  already exists and where. Never plan a feature without knowing what the project
  already does — from the map, or from the survey when there is no map. An agent
  that doesn't know rebuilds it.
- STOP at every checkpoint and wait for the user. NEVER skip one or advance an
  unapproved phase.
- Use the feature description from arguments if given; otherwise ask first.
- `--bug` in the arguments — or a request that is plainly a report of something
  already broken — switches Stage 0.5 to its **Bug mode** branch. Nothing else in
  the workflow changes: same tiers, same phases, same hooks, same checkpoints.

## The phase-log checkboxes are MACHINE-PARSED — write them literally

`phase-log.md` is not just prose for humans. The hooks parse it with regexes, and
the exact strings below are load-bearing. Keep every phase section in the shape
`templates/phase-log.md` defines; a phase you write up in freeform prose is a phase
the safety hooks cannot see, and they fail SILENTLY when they can't see it.

| String | Who writes it | When | What reads it |
|---|---|---|---|
| `## Phase N — <title>` | you | at scaffold | all hooks — a heading that doesn't start with `## Phase` or `## Final review` (case-insensitive) is not a section, and its content is absorbed into the phase above |
| `[x] coded` | the `coder` (you, in a trivial phase) | when it finishes implementing | — |
| `- Evidence: <cited proof>` | the `coder` (you, in a trivial phase) pre-fills what it RAN (test/command output); you AUGMENT with what the reviewers verified | coder on return, you after reviews, before yielding | the Stop evidence gate — an empty or placeholder ledger is refused |
| `[x] code-reviewed` (Final review uses `full code review`) | you | after `code-reviewer` returns AND its findings are resolved | **the Stop evidence gate** — ticking either string ARMS it: from here on, ending your turn with an empty `- Evidence:` line is blocked |
| `[x] security-scanned` | you | after `code-reviewer` returns a `Security pass:` line; leave unticked when the phase's surface didn't warrant the pass | — |
| `[x] USER APPROVED` | **you, but ONLY after the user actually said so** | at the approval checkpoint | `status.py`, and the evidence gate's "which phase is current" logic |

The `coder` owns `[x] coded` and the first draft of `- Evidence:` because it is the
one that ran the code. Everything a REVIEW or the USER attests to is yours: the
review boxes, the augmented evidence, and `USER APPROVED`. The coder must never tick
a review box or `USER APPROVED` — see `agents/coder.md`. In a trivial phase you are
the coder: you tick `[x] coded` and draft `- Evidence:`, and the review boxes still
wait on a freshly spawned reviewer.

`[x] USER APPROVED` is the one box you must never tick on your own initiative. No
hook can tell your tick from the user's — writing it without an explicit approval
from the user forges their sign-off, advances the phase, and switches the evidence
gate to the NEXT phase. If you are unsure whether they approved, they did not: ask.

Tick each box as its step completes, not in a batch at the end — the gate can only
protect a phase it knows has been reviewed.

## `plan.md` has a machine-checked contract too

The plan guard (`hooks/plan_guard.py`, a `Stop` hook) refuses to let a turn end
while any of these is missing. It cannot judge whether a reason is GOOD — that is
the user's call at the plan checkpoint — only whether you made the choice silently.

| Field | Where | Why it is enforced |
|---|---|---|
| `## Size estimate` | `plan.md`, once any phase's `- Scope:` is filled | It is what makes an over-built plan visible at the checkpoint. A plan that hides its size hides the thing the user needs to reject it. |
| `- Why separate:` | every phase AFTER the first | Each extra phase costs the user an implement-review-approve round-trip. Splitting stays allowed; splitting without naming why does not. |
| `- Unresolved:` | any `phase-log.md` phase whose `- Review rounds:` exceeds 2 | Going past the budget means coder and reviewer did not converge — that is a decision for the USER, and the extra rounds must not pass silently. |
| `- Project map updated:` | the LAST section of a finished feature, when the project has a `project-map.md` | Stage 5 is what maintains the map — and single-phase features skip Stage 5, which is now most of them. `"no structural change"` is a complete answer; saying nothing is not. |
| `- Lessons:` | the LAST section of a finished feature | Stage 6 is where the workflow learns, and it runs when everyone wants to be done. `"none"` is a complete answer; skipping the step is not. |

Until a phase has a real `- Scope:`, the plan is still the untouched scaffold and
the guard stays silent — Stages 0.5–2 legitimately end turns with no plan written.

## Setup — feature workspace
1. Derive a short kebab-case `slug` (e.g. `wallet-topup`).
2. Create `.dev-workflow/features/<slug>/` and scaffold `spec.md`, `plan.md`,
   `phase-log.md` — copy from the plugin's `templates/` if reachable, else create
   them with the standard sections.
3. Write `<slug>` to `.dev-workflow/active` (the status hook and
   `/dev-workflow:status` read this). Switch active features by updating this file;
   multiple can coexist.

## Model routing — per-agent, user-overridable
Each agent has a sensible default model in its `agents/*.md` frontmatter (Opus
wherever the job is judgement). If `.dev-workflow/models.json` exists, read
it ONCE now: it maps agent name → model (aliases `opus`/`sonnet`/`haiku`/`fable`, a
full model ID, or `inherit`; keys starting with `_` are ignored). When you spawn an
agent named there, pass that model as the spawn-time model override; for any agent
NOT listed, use its frontmatter default. If the file is absent or unparseable,
every agent keeps its default — never block on this.

## Stage 0 — Establish project context
Read `conventions.md` (domain + engineering rules) and `project-map.md` (module
map, existing features, shared building blocks, extension points) if they exist.

- If `project-map.md` is missing, say so and offer `/dev-workflow:init` — it
  drafts both files. If the user declines, DON'T guess the project's shape:
  Stage 1's researcher surveys the relevant part of the codebase instead, and you
  work from that survey.
- If it exists, treat it as a map, not as gospel: it can be stale. When something
  you read in the code contradicts it, the CODE wins — fix the entry in
  `project-map.md` as you go, and tell the user what you corrected.
- From the map, pull the entries this feature plausibly touches (modules,
  existing features that overlap, building blocks to reuse, the extension point
  to hook into) and carry THOSE forward. You hand agents excerpts, never "go read
  project-map.md" — the point of the file is that they don't each pay for it.
- **Read what the user changed after the last feature shipped** — see "Post-ship
  edits" under Stage 6. Do it before Stage 0.5, so an approved rule already binds
  this feature.

## Stage 0.5 — Clarify the request (this part is yours; you are the analyst)
**You are the only party in this workflow who can talk to the user.** Subagents
cannot stop to ask — they will silently pick an interpretation and build it, and a
plan built on a wrong reading survives every review in this workflow, because
reviewers check whether the code matches the plan, not whether the plan matches what
was wanted. So requirements work happens HERE, before anything is delegated, and it
is never delegated itself.

**If the request is a bug, take the Bug mode branch at the end of this stage instead
of steps 1-5** — a bug report's unknown is not what to build, so the front end is
different.

1. **Restate the request** in your own words, concretely: what the user wants, who or
   what will use it, and what visibly changes for them when it ships. A restatement
   the user corrects in one line has already paid for the whole stage.
2. **Write acceptance criteria** into `spec.md` section 1b — concrete and checkable,
   each one something you could later point an artifact at ("a request with no
   `page` param returns the first 20 orders"), not a goal ("pagination works").
   These are what Stage 4's Evidence ledger cites one artifact per, and what
   `plan.md`'s per-phase `Done when:` lines come from. Two to five is normal; a
   trivial change may have one.
   **Every criterion must trace to something the user said.** Do not invent
   business rules: a limit, a cap, a quota, an extra status, a permission, a
   "partial" flag, an abuse guard, a cache. Each one you write becomes code, tests
   and review rounds, and none of it was asked for. If you think one is genuinely
   needed, list it in `spec.md` 1c under `Suggested, not built:` — the user opts
   in with a word, and silence means it is not built.
3. **Surface conflicts with what exists** — from the map and the survey. "The orders
   endpoint already caps at 50; do you want pagination on top of that cap or
   replacing it?" is the kind of question only someone who read the code can ask,
   and it is the highest-value thing you do in this stage.
4. **Ask only what changes what gets built**, and batch it: ONE `AskUserQuestion`
   round, at most 3–4 questions, the ones whose answers actually fork the design.
   For everything else **state an assumption instead of asking** — an assumption in
   writing is faster for the user than a question, because vetoing takes one word and
   silence means yes. Record them in `spec.md` section 1c. An assumption picks
   between readings of the request; it never ADDS behaviour — that is a suggestion,
   and suggestions are not built unless the user says so.
   Do NOT ask: implementation details the user has no stake in, anything the code
   already answers (go read it), or ceremonial questions ("should I add tests?" —
   yes). An interrogation is a worse failure than a wrong assumption you stated,
   because the user can catch the assumption.
5. **CHECKPOINT — only if you actually asked something.** If the restatement,
   criteria and assumptions raise no real fork, say them and keep going; do not
   manufacture a stop. A trivial change is usually one line of restatement, one
   criterion, and straight on.

Scale this like everything else: trivial changes get a sentence, complex features get
the full conversation. And this stage does not close — if an ambiguity appears later,
at planning or mid-implementation, YOU resolve it with the user then. Never guess, and
never hand the guess to a subagent to make for you.

### Bug mode — the request is a bug, not a feature
Enter this branch on `--bug`, or when the request describes something that already
exists and is behaving wrong ("the orders endpoint 500s on an empty cart", "the total
is off after a refund"). If it is genuinely unclear which it is, ask in one line — the
two front ends diverge immediately, and correcting the mode later costs a stage.

**The unknown is different, so the stage is different.** A feature request's risk is
building the wrong thing; steps 1–5 above exist to pin down WHAT. A bug report's risk
is fixing the wrong PLACE: the symptom is visible and the cause is not, and a patch
aimed at the symptom passes every review in this workflow — reviewers check the code
against the plan, and the plan would say "stop the 500". Nothing downstream can catch
it. So this branch buys the cause before anything is planned, and it is yours: a
subagent that cannot reproduce and cannot ask will hand you a plausible cause.

1. **Reproduce it first, and paste the proof.** The smallest command, test or request
   that makes the bug happen, plus its actual output. Reproduce BEFORE you diagnose —
   a cause you reasoned out from reading code is a hypothesis, and this workflow will
   spend an implementation, a review and a user approval on it.
   **If you cannot reproduce it, STOP and go to the user** with what you tried and
   what you need (the failing input, the env, the log line, the version). Do not
   proceed on a report alone: an unreproducible bug has no way to prove it was fixed,
   which means Stage 4 has no Evidence to cite and the gate is measuring nothing.
   The repro output you capture here is the "before" half of that evidence — keep it
   verbatim.
2. **Localize, then name the root cause with evidence.** Give the `file:line` and say
   in one or two sentences why THAT code produces THIS symptom. Distinguish the two
   out loud: a null check that would suppress the crash is the symptom; the write
   that left the field null is the cause. Fixing the symptom is sometimes the right
   call — under time pressure, or when the cause sits in someone else's code — but it
   is then a decision the user makes at step 4, recorded as one, not a diagnosis you
   quietly stopped short of.
3. **State the blast radius.** What else reaches that code path, what else the same
   cause is plausibly breaking that nobody reported yet, and — the one that gets
   missed — **whether bad data was already written.** Fixing the code does not repair
   rows the bug already corrupted; if any exist, say so here, because that is a
   separate piece of work with its own risk and its own approval, never a silent
   extra in the fix.
4. **CHECKPOINT — only when something actually forks.** Stop and use
   `AskUserQuestion` if the root cause is uncertain, if the honest fix reaches beyond
   the reported symptom, if cause and symptom fixes are both defensible, or if there
   is data to repair. Otherwise state the repro, the cause and where the fix belongs,
   and keep going — the fix itself gets proposed where it normally is (inline for
   trivial, the architect panel above trivial), not here.
   **If the diagnosis shows there is no bug** — the behaviour is intended, or the
   caller is wrong — say that and stop. Do not build the change that would make the
   report true; that is a feature request, and it goes back through steps 1–5.
5. **Turn it into acceptance criteria** in `spec.md` 1b, same as any feature. The
   first one is always the regression, and it names the repro verbatim: "`pytest
   tests/test_cart.py::test_empty` fails on the current commit and passes after the
   fix". Add one criterion per behaviour that must NOT change — the callers from
   step 3 — because a fix that breaks a neighbour is the second most common way this
   goes wrong.
6. **Write section 1a of `spec.md`** — repro, root cause with `file:line`, blast
   radius, and (if any) the data-repair question and its answer. This is what makes
   the cause reviewable at the plan checkpoint instead of living only in this
   conversation; the coder and the reviewers get it quoted inline like everything
   else.

Then continue at Stage 0.8 — a bug fix is TRIVIAL by default, and usually stays there.

## Stage 0.8 — Size it: the machinery must be proportional to the change
**The user pays for this workflow in wall-clock time and approval round-trips.** A
20-line change that runs a research agent, an architect panel, three phases and five
checkpoints is not thoroughness — it is a workflow failure, and it is the failure
this stage exists to prevent. Every stage you run must be one you could justify to
someone waiting on a 20-line fix.

**First, estimate the diff.** You could not do this before Stage 0.5 — you cannot
size a request you have not pinned down. Use the `project-map.md` excerpts and a
quick read of the files involved: how many files, roughly how many lines, one
subsystem or several. Say the estimate out loud to the user along with the tier. An
estimate you refuse to make is how a small change ends up on the heavy path.

**A feature is TRIVIAL by default.** Moving up a tier requires you to NAME the signal
that puts it there. "It feels like a real feature" is not a signal — most requests
feel like real features and most of them are twenty lines.

| Tier | It is this tier only if you can name one of these | What actually runs |
|---|---|---|
| **trivial** | *(default)* one subsystem, one reviewable diff, no new interface, no new dependency, no new persistent state — a validation rule, an added field, a config value, a bug fix, a new parameter with a default | codebase survey (map excerpts + read the files) → propose inline → **1 phase**, coded by you (no `coder`) → `code-reviewer` (with its security pass if the surface warrants) → your approval. **No researcher, no panel, no plan-reviewer, no Stage 5.** |
| **standard** | a new interface others will call (endpoint, command, screen, public function), OR new persistent state/schema, OR several files across one subsystem | survey, plus external research **only if there is a real external question** → simplicity-first architect (+ one signalled angle) → plan + `plan-reviewer` → phases → Stage 5 only if the plan ended up with more than one phase |
| **complex** | crosses a subsystem or trust boundary, OR changes a data model other code depends on, OR the design itself is security-sensitive, OR wide blast radius | full machinery — simplicity-first + the signalled angles, full final audit |

**For a bug, the ROOT CAUSE sets the tier — not the severity of the symptom.** A
production outage caused by a one-line off-by-one is still one reviewable diff and
still trivial; urgency is a reason to move fast, not a reason to run more machinery.
Move up only when the cause says so: it sits in shared code many callers depend on,
or the fix changes a contract others rely on (**standard**); the bug IS a
vulnerability, or the cause crosses a trust boundary or a data model (**complex**).
Data already corrupted by the bug is not a tier signal — it is its own phase, with
its own `- Why separate:`, its own rollback point and its own approval, and it is
never folded into the code fix.

**Re-check the tier after the plan is drafted, and DOWNGRADE without ceremony.** This
estimate is a guess; the plan is when you actually know. If the work turned out to be
one small diff, collapse it: drop the remaining phases into one, skip Stage 5, and
tell the user you scaled it down and why. Downgrading needs no permission. Upgrading
does: name the signal and tell the user before you spend their time on it.

The tier scales research and option-panel depth — NOT security coverage:
`code-reviewer` runs every phase in every tier, and runs its security pass
whenever a phase touches a security-sensitive surface (see Stage 4), trivial or
complex alike. Nor does it scale the approval checkpoints: a cheaper tier means less
machinery between the checkpoints, never fewer of them.

## Stage 1 — Research  (skip for trivial)
**Two switches, not one.** The codebase survey is almost always worth it — it is
cheap, targeted, and it is what stops us rebuilding something. External research is
NOT: it is only worth a subagent and a web round-trip when there is a real external
question — an unfamiliar protocol/format, a domain rule with a standard answer, a
library choice, a known-pitfall area (auth, money, time zones, concurrency). Adding
a field to a response has no external question. When there isn't one, tell the
researcher to skip the web work and return the survey only, and say so to the user.

1. Spawn `domain-researcher` with the feature description AND the `project-map.md`
   excerpts from Stage 0. It returns TWO things: external research (patterns,
   pitfalls) and a survey of what THIS codebase already has for this feature —
   what exists, what to reuse, what would be duplicated, which map entries are
   stale.
2. Write both into `spec.md` — research in section 2, the existing-implementation
   survey in section 2b. Correct any stale `project-map.md` entry it found.
3. Summarize for the user, leading with what already exists (that is the part that
   changes what we build). **CHECKPOINT: stop; confirm the research direction
   before proposing solutions.**

**Trivial tier skips this stage — but not the survey.** Before proposing inline,
read the `project-map.md` entries for the area and the files they name, so a
"trivial" change doesn't quietly duplicate an existing helper. Two minutes of
Reads, not a subagent.

## Stage 2 — Solution options (independent panel)
1. Spawn a `solution-architect` panel IN PARALLEL. **Simplicity-first always
   runs.** Add `performance-first` only when you can name a real load signal (a hot
   path, a large data set, a latency budget), and `risk-first` only when the change
   touches money, auth, a trust boundary or irreversible data. Standard tier with
   no such signal is ONE architect; skip the panel for trivial. Give each a
   DIFFERENT angle (simplicity-, performance-, risk-first) with the description + the acceptance criteria from
   `spec.md` 1b (an option is only valid if it satisfies them) + research summary + the
   existing-implementation survey and the building blocks / extension points from
   the map — independent context reduces single-thread bias, but an architect
   blind to what already exists designs a parallel copy of it. **Tell every
   architect your diff estimate and that the option must be proportional to it**
   — an angle is a lens, not a licence to grow the change. Left unanchored, a
   performance-first architect will invent a cache for a fifteen-line fix, and the
   synthesis then lands somewhere between "what was asked" and "what was invented".
2. Synthesize into `spec.md` section 3 as a comparison table (**size — files and
   rough lines** / complexity / performance / security risk / effort). The size
   column is the point: it makes an over-built option visible to the user at the
   checkpoint instead of three phases later. Merge near-duplicates. Present the
   options the panel ACTUALLY returned — one per architect, minus merges. Do NOT
   invent an extra option to hit a count: a synthesized option you wrote yourself
   carries the single-thread bias the panel exists to remove. If you think the
   panel missed an angle, say so to the user and offer to spawn another architect
   for it; don't quietly fill the gap.
3. Give your recommendation first, but don't decide for the user. If the smallest
   option satisfies the request, recommend it and say plainly what the larger ones
   buy — "handles 100× the traffic we have" is a cost, not a feature. The
   Simplicity contract in `conventions.md` binds this stage: no speculative
   options, config, or abstraction for imagined future needs.
4. **CHECKPOINT: use AskUserQuestion so the user picks. Stop and wait.** Record
   the choice + rationale in `spec.md` sections 4–5.

## Stage 3 — Plan
1. Enter Plan Mode (ask the user to press Shift+Tab twice, or hold a read-only
   planning stance — Plan Mode is behavioral, not a hard write-lock).
2. Map the files to change; split the work into phases. Write `plan.md`, following
   these rules:
   - **Start from ONE phase and justify every additional one — in writing, on a
     `- Why separate:` line the plan guard enforces.** A phase costs a full loop —
     coder, reviewers, an evidence ledger and a user approval round-trip — so the
     count is the single biggest lever on how long this feels to the user. Add a
     second phase only when you can NAME the reason: it crosses a subsystem
     boundary, it needs its own rollback point because the step is risky, or it is
     genuinely too big to review in one sitting. "It has three
     logical steps" is not a reason — steps a reviewer checks in one pass, that
     touch the same files, or that only make sense together are ONE phase.
     (Deliberately no target count: a range here reads as a quota to fill, and the
     plan comes back with the number rather than the work. If the honest answer is
     one phase for a standard feature, that is the plan.) The failure in the other
     direction is real too — a phase too big to review in one sitting hides bugs —
     but it is far rarer than over-splitting, and the reviewer will catch it.
   - **Order by dependency, then risk.** No phase depends on something a later
     phase builds; among independent phases, schedule the risky or uncertain ones
     EARLY so the plan fails fast, not late.
   - **Each phase independently testable.** Name how it will be proven — the
     test/command/output that becomes its `- Evidence:` ledger in Stage 4. A phase
     with no way to verify it is a planning bug. Its `Done when:` comes from the
     acceptance criteria in `spec.md` section 1b; between them, the phases must
     cover every criterion, and a criterion no phase delivers is a missing phase.
     Name the proof, not a test count: for a criterion a declaration or the
     type-checker already enforces, the honest plan says so instead of budgeting a
     test that can only restate it (see "One artifact per criterion is NOT one test
     per criterion" in Stage 4).
   - **Each phase has a rollback point.** Note where the checkpoint sits so a bad
     phase can be reverted cleanly (ties into the checkpoint/rollback machinery).
   - **Each phase has a `- Size:` — its diff budget.** Changed lines (added +
     deleted, tests included). The plan guard measures the phase's real diff at
     every Stop and refuses past 2× the estimate (min +40 lines) until the phase-log
     `- Over budget:` says why. An honest number matters more than a small one: it
     is the user's review load, stated before they agree to it.
   - **Decide the shape before the phases — fill `## Structure`.** Where each
     new file goes, the one responsibility each file has, the main flow from entry
     point to output, and — the part that matters most — the EXISTING feature it is
     shaped like, by path. Pick that exemplar from `project-map.md` "Existing
     features" and read it: the new code mirrors its layout, layering and naming.
     A coder given only "files to change" invents a layout per feature, and after
     a few features the codebase follows no pattern at all. If nothing in the
     project fits, name the pattern you chose and why; a departure from the
     exemplar goes on the `- Deviations:` line, where the user sees it.
   - **Prototype only when what the user will SEE is the uncertain part.** For a
     new screen or page whose layout nobody has pinned down, build a throwaway
     static mock (one HTML file, fake data, in the feature dir — never in the
     source tree) and show it before the plan checkpoint. It is a question to the
     user, not a first draft: it is deleted once the plan is approved, and no
     phase builds on it. Anything else — an endpoint, a job, a refactor — gets no
     prototype; `## Structure` on paper is enough.
   - **Reuse before rebuild.** Name, per phase, the existing building block or
     extension point from `project-map.md` it hooks into. If the plan adds
     something the project already has in another form, either use the existing
     one or state in `plan.md` why a second implementation is justified — that is
     a decision the user gets to see, not a silent one.
   - **Plan the change, not a project.** Only what the request and the chosen
     option require. Migrations, config, flags, docs, monitoring, refactors of code
     you happened to read — none of these get a phase unless the feature genuinely
     cannot work without them. Things that are merely a good idea go to the user as
     a suggestion, or into `spec.md` section 5 as a non-goal. They do not get
     planned in silently.
3. **Re-check the tier now.** The plan is the first point where the size is real
   rather than guessed. If it came out smaller than the Stage 0.8 estimate,
   collapse the phases and drop the machinery the lighter tier doesn't run — then
   tell the user you scaled it down. This is the cheapest correction available in
   the whole workflow, and it is the one most often skipped.
4. **Adversarial plan review** (standard + complex tiers; SKIP for trivial): spawn
   the `plan-reviewer` subagent on the drafted `plan.md`, handing it the
   existing-implementation survey, the map excerpts, and your diff estimate. It
   hunts in BOTH directions — missing phases, hidden dependencies, untestable
   phases, ordering mistakes, rollback gaps and duplicated work, but equally
   over-engineering, unnecessary phases, and a plan too heavy for the change it
   delivers. Fold its findings into `plan.md` (resequence, split, MERGE, add or
   DELETE phases) before showing the user — note what changed. Bounded like every
   other review loop: at most 2 rounds with the reviewer, then decide or take the
   disagreement to the user (see the review-round rules in Stage 4).
5. **CHECKPOINT: present the plan, stop, get approval or edits before any code.**
   Lead with the shape — tier, phase count, estimated files/lines — so the user can
   say "that's too much machinery for this" BEFORE paying for it. If you cut the
   plan down in step 3, say what you cut.

## Stage 4 — Phased implementation (loop per phase)
**Trivial tier: you write the code yourself — no `coder` spawn.** Use the tier as
it stands after Stage 3's re-check: a feature downgraded to trivial counts; a
standard one that merely ended with one phase does not. First Read
`${CLAUDE_SKILL_DIR}/../../agents/coder.md` once, from "While coding:" through its
"Tests" section, and follow it as the coder would: `conventions.md` and the
project's formatter/linter, scope, prefer what exists, the clean-code and
readability rules, the agreed `## Structure`, comments, tests, and run the
tests/build and report honestly. Then tick `[x] coded`,
fill `- Changed:` and pre-fill `- Evidence:`; anything extra goes to the user as
`Suggested, not built:`. Fix rounds are yours, scoped to the findings; reviewers stay
freshly spawned; `models.coder` does not apply to these phases.

**Standard/complex tiers: reuse ONE coder across the phases — don't respawn each
phase.** Spawn the `coder`
for Phase 1; for every later phase, CONTINUE that same coder (via SendMessage)
rather than a fresh Task. It keeps its warm context — the files it already opened,
the conventions, and what earlier phases did — so you pay the codebase-intake cost
ONCE instead of per phase. Respawn a fresh coder only when a phase moves to an
unrelated subsystem (its warm context stops helping and just bloats its window) or
after the user made large manual changes it hasn't seen — brief a reused coder on
any such changes. Reviewers are the opposite: ALWAYS freshly spawned per phase —
their value is objective fresh eyes on code they didn't write.

For each phase in `plan.md`, in order:
1. (standard/complex tiers) Give the coder THIS phase only — its scope + the chosen approach, quoted INLINE
   from the phase's `plan.md` block (including its `Done when:` — that is what the
   coder's Evidence has to prove) plus the one-line solution from `spec.md`, and
   the feature dir path. Hand it the EXACT files to touch as paths — and the
   function/symbol or line range when `plan.md`'s `Files:` names them — so it Reads
   those spots directly instead of Grep-walking the tree to locate them. Include
   the `project-map.md` lines that matter for THIS phase — the building block it
   should reuse, the extension point it hooks into, the gotcha in that module —
   quoted inline, a few lines, not the file. Quote `plan.md`'s `## Structure`
   too (its pattern + exemplar path, and this phase's files and flow steps): the
   coder mirrors the exemplar, and the code-reviewer gets the same block. A reused coder already knows most of
   this: send only what's NEW for this phase, and don't have it re-read the whole
   spec/plan.
2. When the code is done (the coder returns, or you finish it in trivial), spawn a
   fresh `code-reviewer` — hand it the changed files/diff and exact paths directly,
   never make it re-scan to find the change. Reviewers have no Bash and cannot run `git diff`: paste the diff inline,
   or for a long one, each changed file with the line ranges of its hunks. Add the
   phase's `Done when:` (the code-reviewer needs it to judge what
   is over-built) and `plan.md`'s `## Structure` (to judge whether the code
   follows the agreed shape). Ask the code-reviewer for its **review map** (see
   `agents/code-reviewer.md`) — on a re-review, for the fix diff only. If the coder returned `Suggested, not built:` items (or your
   own trivial work produced some), carry them to the user at this phase's checkpoint — never build them on your own call.
   Before the review, check the diff for files the phase should not leave behind:
   probe/smoke/e2e scripts, backups, `.diff` dumps, handoff notes — in `src/`,
   `scripts/` or the feature dir. Delete them unless the plan asked for them.
   The `code-reviewer` (logic/quality) runs ALWAYS, every phase, every tier. Ask for
   its **Security pass** ONLY when this phase touches a security-sensitive surface:
   auth/authz, input handling/parsing, crypto or secrets, data access (queries,
   serialization/deserialization), or external I/O (network, filesystem,
   subprocess). Gated by the phase's SURFACE, not the tier — a copy tweak or rename
   in a complex feature needs no security pass; a new endpoint in a trivial one
   does. When unsure, ask for it.
   Rationale: the per-phase security pass catches LOCAL, compounding bugs early
   (injection, hardcoded secrets, missing authz on a new endpoint) when they are
   cheap to fix. EMERGENT, cross-phase vulnerabilities are the Stage 5
   `security-audit`'s job, so skipping the pass on non-sensitive phases loses
   nothing there.
3. Summarize the review that ran for the user. Update `phase-log.md` — using the
   LITERAL checkbox strings from the table above, which the hooks parse. The coder
   (or you, in trivial) already ticked `[x] coded` and pre-filled `- Evidence:` with
   what it ran; your job here is the review boxes and evidence:
   - If the reviewer found issues, have `coder` fix them (fix them yourself in
     trivial), then re-review — **under the round budget below. Count the rounds; do
     not loop until they agree.**
   - Tick `[x] code-reviewed` once `code-reviewer`'s findings are resolved (plus
     `[x] security-scanned` when its report carries the `Security pass:` line).
     "Resolved" means fixed, rebutted with evidence you accepted (never your own
     rebuttal in a phase you coded), or decided by the user at escalation — never
     "we ran out of rounds".
   - Record the **`- Review map:`** in the phase's section: the first round's map,
     with each re-review's fix-diff entries merged in (a hunk changed by a fix is
     re-tiered, never left at a lower tier than the fix warrants). Replace the
     reviewer's line counts in the opening line with `git diff --numstat` totals.
     Keep the tier labels and one-line entries: the plan guard requires a MUST /
     SKIM / SKIP entry before you yield, and the dashboard renders them.
   - If the plan guard reported the diff **over its `- Size:` budget**, split the
     rest into a new phase or write why it lands together on `- Over budget:`.
   - Record `- Review rounds: N/2`, `- Unresolved:` and `- Deferred nits:` in the
     phase's section (prose lines, not parsed by the hooks — they exist so the user
     can see how contested the phase was, and what was consciously let go, before
     approving it).
   - **Augment the `- Evidence:` ledger** so it carries CITED proof it works:
     test/command output, `file:line` refs, concrete cases verified — one artifact
     per acceptance criterion this phase delivers (`spec.md` section 1b), no
     "looks fine". **An artifact is not the same thing as a new test** — see below.
     Ticking `[x] code-reviewed` arms the
     `Stop`-hook evidence gate: it will refuse to let you yield for approval while
     this line is still empty or a placeholder, and it will keep refusing.
4. **CHECKPOINT: the user reviews AFTER the AI. Stop and wait.** Lead with the
   review map, so the user reads 40 lines instead of 400: the totals line, any
   `- Over budget:` reason, the MUST entries in reading order with their questions,
   then every ASSUME. SKIM and SKIP go in one line each with counts. Do not paste the
   diff; the user opens the MUST ranges (or the dashboard shows them). Then the review
   summary and evidence. ONLY after the user
   has actually approved, tick `[x] USER APPROVED` in `phase-log.md` and move on.
   Never tick it yourself to advance; never advance unapproved.
5. If it's a git repo and the user wants per-phase commits, commit scoped to this
   phase (`Phase N: <title>`). Skip otherwise. Keeps the final-audit diff clean.

### One artifact per criterion is NOT one test per criterion
**Test budget.** Default is NO new test file per phase: extend the changed module's
existing spec. A test is written only for pure logic with real branching, a bug's
regression, or store-level behaviour proven against the real store. Never one per
defensive branch, never a wiring/DI test, never a test of vendored or generated
code. If a phase's diff has more test lines than code lines, that is a signal to
cut, not a sign of rigour.

The evidence rule above is the strongest incentive in this workflow: the gate will
not let the turn end without a citable artifact, and the cheapest artifact to
manufacture is a new test. Left alone, that turns "2–5 acceptance criteria" into
"2–5 new test files", whether or not the criteria have any logic worth testing —
and the tests it produces are shaped to be CITED, not to be able to fail. A ledger
reading `criterion 1 → x.spec.ts:123, criterion 2 → :135, criterion 3 → :160` is
that failure, not a sign of rigour.

**An artifact is anything that would have caught the criterion being wrong.** A
type-check or build that could not have passed otherwise, the command you ran
against the real thing and its output, a `file:line` where the constraint is now
enforced by construction, a log line from an actual run, one test that covers
several criteria at once. Cite the cheapest artifact that would actually fail.

**Some criteria must NOT get a test, and saying so is part of the job.** A
criterion satisfied by a declaration — a validator annotation, a schema field, a
config value, a type — is already checked by the linter, the type-checker or the
framework, and a test that asserts `@Max(100)` rejects 101 only restates the
annotation: it cannot fail unless someone edits the annotation, in which case it
changes with it. Cite the declaration and the type-check; do not write the test.
When you skip one, say which criterion and why in the ledger, so the user sees a
decision rather than a gap.

**A bug fix owes one artifact nothing else substitutes for: the before AND the
after.** The regression test or command must be shown FAILING on the unfixed code and
passing after — a test written after the fix and never seen red proves the code runs,
not that it fixes anything, and it is the single easiest thing to fool yourself with
here. You already captured the red half in Stage 0.5 step 1; the ledger cites that
output and the post-fix run, so this costs one extra paste, not one extra test run.
This is also the one place the "a declaration already enforces it" exemption above
does NOT apply: if the fix turns out to be a validator or a config value, the artifact
is still the repro, run twice.

**A test that mocks the thing it claims to prove is worse than no test**, because
it reports the risk as covered. Atomicity, uniqueness, index and transaction
behaviour live in the store: a fake counter that increments in one thread passes
"never yields a duplicate" forever, including after the real atomic operator is
deleted. If the criterion rests on the store, prove it against a real one — most
projects already ship a harness for this (check `package.json` before assuming
otherwise) — or narrow the claim to what a fake CAN prove: that the code sends the
right query. Faking a collaborator to INJECT a failure you cannot otherwise reach
is the legitimate case, and stays legitimate.

Two of these shapes are hook-enforced on write (`test_guard.py`: a provider built
from positional `as any` blanks, a test block that asserts nothing). The rest is
`code-reviewer`'s, and it is authorized to say a test should be DELETED.

### The review loop is BOUNDED — at most 2 fix rounds, then the user decides
A coder and a reviewer left alone will argue indefinitely: the reviewer keeps
finding things because finding things is its job, and each new round re-opens code
the last round already settled. Nothing in the loop ends it, so you end it.

**Budget: 2 fix rounds per phase.** The first review is round 0. Findings → coder
fixes → re-review is round 1. One more if needed is round 2. There is no round 3.

- **Re-reviews are DELTA-SCOPED.** Hand the fresh reviewer the previous round's
  findings AND the fix diff, and tell it to judge THOSE — did each finding get
  fixed, did the fix break anything — not to re-review the phase — and ask for the
  security pass again if round 0 had one. A new finding is
  admissible only if it is BLOCKING (correctness, security, data loss). New
  non-blocking nits go on the `- Deferred nits:` line and never justify a round;
  unscoped re-reviews are what turn a 2-round loop into a 6-round one.
- **The coder may DISSENT.** A finding can be wrong, or aimed at code outside the
  phase. The coder answers with evidence (`file:line`, the test that covers it)
  instead of editing. You adjudicate: if the rebuttal cites concrete code and the
  finding doesn't hold, mark it resolved-by-rebuttal and do NOT force the change.
  Deference to a reviewer that is mistaken damages the code — that is a real cost,
  not a diplomatic one. In a phase you coded you cannot accept your own rebuttal: a
  finding you disagree with goes to the user at once with `AskUserQuestion`, not
  after the round budget.
- **Never send the same finding back unchanged.** If round 2 would repeat round 1's
  argument, the loop has converged on disagreement, not on truth. Escalate now
  rather than spending the round.
- **When the budget runs out with blocking findings still open — or coder and
  reviewer still disagree — STOP and escalate** with `AskUserQuestion`. Give the
  user: the finding, the coder's rebuttal, your recommendation, and options — apply
  the reviewer's fix / accept the coder's position / ship it with the risk recorded
  in `- Unresolved:` / something else. This is a checkpoint like any other: you do
  not resolve a deadlock by ticking `[x] code-reviewed` yourself, and you do not
  quietly drop the finding.
- The budget bounds ARGUMENT, not correctness. A finding the coder agrees with and
  fixes cleanly isn't a round spent debating — but if fixing it keeps failing, that
  is exactly the signal the user should see. And a security finding is never
  "resolved" by exhausting rounds: unresolved ones go to the user, and to Stage 5.

The same budget applies to every review loop in this workflow: the plan review in
Stage 3, and the final review and audit in Stage 5.

## Stage 5 — Final review (whole feature)  (skip when the feature is ONE phase)
**Skip condition: a single-phase feature, in any tier** — there is nothing
"cross-phase" to review, and the per-phase review already was the whole review. A
trivial feature is single-phase by definition; a standard one often ends up there
after the Stage 3 re-check, and it skips this stage too.

**If you SKIP this stage, DELETE the `## Final review` section from `phase-log.md`.**
The template always scaffolds that section, but nothing ever ticks it when the stage
is skipped — and `status.py` reports the first unapproved section as the current one,
so the finished feature is reported as stuck on "Final review" forever. Removing the
section is what marks the feature done. Skipping the stage does NOT skip step 4
below: if the change added a capability or moved something, `project-map.md` still
gets its line at the phase's approval checkpoint — and since you are deleting the
Final review section that normally carries `- Project map updated:` and
`- Lessons:`, write both lines on the LAST PHASE instead, and run Stage 6 at that
phase's approval checkpoint. The plan guard requires them there.

1. Run over all phases together. Brief both reviewers with the feature's
   footprint so they don't re-discover it: every changed file grouped by phase,
   with the line ranges of its hunks, and which phases skipped the code-reviewer's security pass.
   - `code-reviewer` on CROSS-PHASE issues ONLY — inconsistencies, phase
     interactions, integration seams. Do NOT re-review files from scratch (done
     per phase).
   - `security-audit` (deep pass) — owns EMERGENT, cross-phase interaction
     vulnerabilities (auth flows spanning phases, data-flow and trust-boundary
     analysis). It must ALSO give a full pass to any security-sensitive surface
     whose per-phase security pass was gated out in Stage 4, so nothing
     ships unscanned. Do NOT re-review clean, non-sensitive phases from scratch.
2. Summarize findings; update `phase-log.md` final section and its `- Evidence:`
   line with feature-level proof (test-suite result, validation output, key
   end-to-end invariants checked), plus `- Review rounds:` and `- Unresolved:`.
3. If issues found, fix via `coder` and re-audit — **same 2-round budget, same
   escalation.** An unresolved security finding is never waved through on a round
   count: it goes to the user with your recommendation, explicitly.
4. **Update `project-map.md`** so the next feature starts from what this one
   built — this is how project knowledge accumulates instead of being re-derived:
   - Append a row to `Existing features`: what it does, key files, today's date.
   - Add/adjust `Module map` rows for anything new or newly re-scoped, and add any
     new `Shared building block` or `Extension point` this feature introduced.
   - Fix entries this feature proved stale, and drop entries for what it removed.
   - Keep entries to a couple of lines. If nothing structural changed, say so and
     write nothing — a map that grows a paragraph per feature stops being read.
5. **CHECKPOINT: present the final result, the `project-map.md` update AND the
   Stage 6 lesson proposals, then stop for sign-off.** The map is what future
   agents will treat as fact, so the user gets to correct it here.

## Stage 6 — Lessons  (every feature, every tier, at its final checkpoint)
The workflow does not get better on its own: a review finding, a correction the user
made, a suggestion they turned down all die with the feature's `phase-log.md`, and
the next feature makes the same mistake. This stage turns what recurred into a rule
in `conventions.md` — which every agent already reads on every phase — and only with
the user's approval. It runs at the final checkpoint: Stage 5's, or the last phase's
when Stage 5 is skipped. It is one question to the user, not a retrospective.

1. **Gather signal from this feature** — the phase-log you already have:
   - what the user asked to change at any checkpoint (`- User notes:`), and what
     they overrode at an escalation (`- Unresolved:`);
   - `Suggested, not built:` items the user declined — "don't propose X" is a rule;
   - review findings of the same KIND that came up in two or more phases, or that
     the coder kept needing a round to fix;
   - plus any rules from "Post-ship edits" below that are still pending.
2. **Keep only what generalises.** A rule is worth a line only if it would change
   what an agent does on a DIFFERENT feature of this project. Drop one-off facts
   and anything the linter could enforce (propose the lint rule instead). If
   `conventions.md` already has the rule and it was broken anyway, don't add a
   duplicate — tell the user the rule is being ignored. One line each, imperative, concrete, ending with where it
   came from: `- Scale token amounts with bigint, never Number() — user rewrote
   formatUnits (space-balance)`.
3. **Propose at most three**, via one `AskUserQuestion` with `multiSelect`, each
   option a rule with its evidence. Nothing worth proposing is the common, correct
   outcome — then say so in one line and ask nothing.
4. **Write the approved ones** to the `## Learned rules` section of `conventions.md`
   (create the section above "Domain-specific correctness rules" if it is missing).
   If it passes ~15 lines, propose merging or dropping the weakest in the same
   question rather than growing it. Record the outcome on the last section's
   `- Lessons:` line — the rules added, or "none". The plan guard requires the line.
5. **Record the ship point** (git repos only), after the user signs off:
   `python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py" ship <slug>`. It stores
   the tree as it was handed over, which is what "Post-ship edits" diffs against.
   If the approval gate is LOCKED, Bash is denied — ask the user to run it with a
   `!` prefix, or skip it and say so; never work around the gate.

### Post-ship edits — what the user changed after accepting the code
The strongest signal this workflow ever gets arrives AFTER the feature: the user
opens the code the agents wrote and rewrites part of it. Nobody tells the agents.
At Stage 0 of the next feature, for the most recently shipped feature(s) — at most
two, newest first from `git for-each-ref --sort=-creatordate
--format='%(refname:short)' refs/dev-workflow/shipped` — whose last phase-log
section has no `- Post-ship reviewed:` line:
1. Run `python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py" since-ship <slug>
   <files>`, passing the files from that feature's `- Changed:` lines. "never
   shipped" means no ship point was recorded — mark it reviewed and move on.
2. Read the diff for what the USER changed in agent-written code: rewritten logic,
   deleted comments or tests, renamed variables, removed handling. Ignore changes
   another feature's `- Changed:` explains, and formatting. Unsure whether an edit
   was the user's? Ask in the same question rather than guess.
3. Turn what generalises into rule proposals exactly as in steps 2–4 above, in one
   `AskUserQuestion` — or none, which is common. Keep it quick; the user came here
   to start a new feature.
4. Write `- Post-ship reviewed: <date> — <rules added | no user edits | none
   generalised>` on that feature's last section, so it is never asked about twice.

## Notes
- Subagents can't pause to ask mid-task; scope each delegated task tightly and
  resolve ambiguity with the user BEFORE delegating — that is what Stage 0.5 is
  for, and why the analyst role is yours and can never be delegated to a subagent.
- Reviewers are read-only with fresh context and always freshly spawned, so they
  judge code they didn't write — the `coder`'s, or yours in a trivial phase.
- For a hard-enforced approval gate, see the `.approval-gate` hook in the README.
