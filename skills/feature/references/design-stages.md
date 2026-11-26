# Stages 1–3 — Research, option, plan  (standard and complex tiers)

Read by `/dev-workflow:feature` once Stage 0.8 has put the feature in the standard or complex tier. The trivial tier does not run these stages: it takes the feature skill's "Trivial path". The feature skill gives the full path of every plugin file named here.

## Stage 1 — Research
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
3. Summarize for the user in a few lines, leading with what already exists (that
   is the part that changes what we build), and go straight on to Stage 2 — the
   user steers at the options checkpoint. Stop here only if the research
   contradicts the request or an acceptance criterion: that is a Stage 0.5
   question, and it goes to the user before any option is drawn up.

## Stage 2 — Solution option (fit-first)
1. Spawn ONE `solution-architect`. Its brief is **fit-first**:
   the smallest design that satisfies the acceptance criteria and covers the risks
   this change's surface actually has. It returns one core option plus priced
   **deltas** — what a leaner variant drops and loses, what a safer variant adds and
   covers. **Complex tier: spawn TWO in parallel, with the same brief and no word of
   each other** — a second independent design is worth its cost only where a wrong one
   is expensive, and independent context is what reduces single-thread bias. Give the
   architect the description + the acceptance criteria from `spec.md` 1b (an option is
   only valid if it satisfies them) + research summary + the existing-implementation
   survey and the building blocks / extension points from the map — an architect
   blind to what already exists designs a parallel copy of it. **Tell it your diff
   estimate and that the option must be proportional to it.** Name a load signal in
   the brief only if there is a real one (a hot path, a large data set, a latency
   budget); without one, performance is not a design goal, and an unanchored architect
   will invent a cache for a fifteen-line fix.
   **Brief each architect on patterns per the briefing rule** in the `## Rules`
   header of the plugin's `references/architecture-patterns.md`.
2. Write it into `spec.md` section 3: the core option (**size — files and rough
   lines** / complexity / security risk / effort, and the risks it covers) and a
   deltas table — delta / size / what it buys or loses. The sizes are the point: they
   make an over-built choice visible to the user at the checkpoint instead of three
   phases later. With two architects, put both cores side by side, merge what is
   the same, and say where they disagree — the disagreement is the finding. Present
   what the architects ACTUALLY returned. Do NOT add an option or a delta of your
   own: one you wrote yourself carries the single-thread bias the second opinion
   exists to remove. If you think something was missed, say so to the user and offer
   to spawn another architect; don't quietly fill the gap. Check every catalog id an
   architect cites that you did not expand against its full entry (Signals, Not
   when) before it reaches the table. Each PROPOSED entry an architect returns gets
   its own yes/no item at the checkpoint below, showing the full entry text; picking
   an option never approves its PROPOSED entry. On yes, append the entry without the
   PROPOSED mark to the project's `docs/architecture/catalog-additions.md`
   (create `docs/architecture/` if missing).
3. Give your recommendation first, but don't decide for the user: the core as
   returned, plus or minus the deltas you would take, and why. A delta that covers a
   risk nobody can point to in the code is a cost, not a feature — "handles 100× the
   traffic we have" is the same. The Simplicity contract in `conventions.md` binds
   this stage: no speculative options, config, or abstraction for imagined future
   needs.
4. **CHECKPOINT: use AskUserQuestion so the user picks — the core (which one, when
   there are two) and, with `multiSelect`, the deltas to apply. Stop and wait.**
   Record the choice + rationale in `spec.md` sections 4–5.

## Stage 3 — Plan
1. Write nothing but the working docs until the plan is approved. Map the files to change; split the work into phases. Write `plan.md`, following
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
     direction is just as real: a diff too big to review in one sitting hides bugs,
     and it is what takes control of the change away from the user.
   - **Over the PR cap → cut the plan into PRs.** When the phases' `- Size:` total
     is over the PR cap, read `pr-slicing.md` (beside this file) and add
     the `## PRs` section it describes, or an `- Over cap:` reason for landing as one.
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
     test that can only restate it; for a criterion about behaviour a user or
     caller can observe, the proof is a durable test at the boundary they use it
     through (see "One artifact per criterion is NOT one test per criterion" in the
     feature skill's Stage 4).
   - **Each phase has a rollback point.** Note where the checkpoint sits so a bad
     phase can be reverted cleanly (ties into the checkpoint/rollback machinery).
   - **Each phase has a `- Size:` — its diff budget.** Changed lines (added +
     deleted, tests included). The plan guard measures the phase's real diff at
     every Stop and refuses past 2× the estimate (min +40 lines) until the phase-log
     `- Over budget:` says why. Lockfiles and generated files do not count toward
     `- Size:`, but the diff budget still measures them, so name them on
     `- Over budget:`. An honest number matters more than a small one: it is the
     user's review load, stated before they agree to it.
   - **Decide the shape before the phases — fill `## Structure`.** Where each
     new file goes, the one responsibility each file has, the main flow from entry
     point to output, and — the part that matters most — the EXISTING feature it is
     shaped like, by path. Pick that exemplar from `project-map.md` "Existing
     features" and read it: the new code mirrors its layout, layering and naming.
     A coder given only "files to change" invents a layout per feature, and after
     a few features the codebase follows no pattern at all. If nothing in the
     project fits, name the pattern you chose and why; a departure from the
     exemplar goes on the `- Deviations:` line, where the user sees it.
   - **A new screen whose layout nobody has pinned down** gets a throwaway mock
     before the plan checkpoint — read `ui-prototype.md` (beside this file).
     Nothing else gets a prototype; `## Structure` on paper is enough.
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
2. **Re-check the tier now.** The plan is the first point where the size is real
   rather than guessed. If it came out smaller than the Stage 0.8 estimate,
   collapse the phases and drop the machinery the lighter tier doesn't run — then
   tell the user you scaled it down. This is the cheapest correction available in
   the whole workflow, and it is the one most often skipped.
3. **Adversarial plan review**: spawn
   the `plan-reviewer` subagent on the drafted `plan.md`, handing it the
   existing-implementation survey, the map excerpts, and your diff estimate. It
   hunts in BOTH directions — missing phases, hidden dependencies, untestable
   phases, ordering mistakes, rollback gaps and duplicated work, but equally
   over-engineering, unnecessary phases, and a plan too heavy for the change it
   delivers. Fold its findings into `plan.md` (resequence, split, MERGE, add or
   DELETE phases) before showing the user — note what changed. Bounded like every
   other review loop: at most 2 rounds with the reviewer, then decide or take the
   disagreement to the user (see the review-round rules in the feature skill's Stage 4).
4. **CHECKPOINT: present the plan, stop, get approval or edits before any code.**
   When it is approved, record the phases: `dw phases "<title>" ["<title>" …]`.
   Lead with the shape — tier, PR count, phase count, estimated files/lines — so the
   user can say "that's too much machinery for this" BEFORE paying for it. If you
   cut the plan down in step 2, say what you cut.
