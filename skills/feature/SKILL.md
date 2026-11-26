---
name: feature
allowed-tools: Bash(.dev-workflow/dw *), Bash(python3 "${CLAUDE_SKILL_DIR}/../../hooks/dw.py" *)
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
  re-read if unsure. Progress itself lives in `state.json` beside them and changes
  only through the `dw` command; `phase-log.md` is rendered from it.
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

## Progress changes through `dw` — never by editing `phase-log.md`

A feature's progress is `state.json`; `phase-log.md` is rendered from it after every
change, and the hooks refuse an Edit to either. Every change is one command:
`.dev-workflow/dw <command>`. It validates the step and refuses with the reason — a
phase cannot be reviewed before it is coded, or approved without evidence and a review
map. Long text goes on stdin (`<<'EOF' … EOF`) or `--file <path>`.

**Wherever this skill names a line of the phase log — `[x] coded`, `- Evidence:`,
`- Review map:`, `- Lessons:` — it means the field below, written with its command.**

| What | Command | Who runs it |
|---|---|---|
| The phase list, once the plan is approved | `dw phases "<title>" ["<title>" …]`; a phase added later: `dw add-phase "<title>"` | you |
| `[x] coded`, `- Changed:`, first `- Evidence:` | `dw --by coder coded N --changed "<files + key decisions>"`, evidence on stdin | the `coder`; you in a trivial phase (without `--by coder`) |
| A fix round starts | `dw round N` — before you send BLOCKING findings back; this is what counts `- Review rounds:` | you |
| `[x] code-reviewed`, `[x] security-scanned`, `- Review map:` | `dw reviewed N --security`, the review map on stdin: the totals line, then one `MUST` / `SKIM` / `SKIP` / `ASSUME` entry per line | you, once the findings are resolved |
| `- Evidence:` (the full ledger, rewritten), `- Code review result:`, `- Unresolved:`, `- Deferred nits:`, `- Over budget:`, `- User notes:` | `dw set N evidence` / `review_result` / `unresolved` / `deferred_nits` / `over_budget` / `user_notes`, text on stdin | you |
| `- Project map updated:`, `- Lessons:`, `- Post-ship reviewed:` | `dw set feature project_map` / `lessons` / `post_ship_reviewed` | you |
| `[x] USER APPROVED` | the user types `/dev-workflow:approve`; or, when they approve in plain words, `dw approve N --said "<their words>"` | **the user** — you only relay |
| The user wants changes after the review | `dw reopen N`, then fix, review and `dw reviewed N` again | you |
| The phase's diff, as a file for the reviewer | `dw diff N`; the fix diff of a re-review: `dw diff N --since-review` | you |
| What is still missing / where things stand | `dw check` · `dw status` | anyone |

The final review of a multi-phase feature is phase `final` in every command.

**You never approve.** A bare `dw approve` refuses inside Claude Code, and a relayed
one is refused unless the user has sent a message since the phase was reviewed — so
present the review, stop, and wait. If you are unsure whether they approved, they did
not: ask. A project set to `direct` approvals accepts only `/dev-workflow:approve`.

The `coder` owns `coded` and the first draft of the evidence because it ran the code.
Everything a REVIEW attests to is yours. Run each command as its step completes, not
in a batch at the end: the guards can only protect a phase they know has been reviewed.

**A feature without `state.json`** was started on an older version. Before continuing
it, run `.dev-workflow/dw import <slug>`; its hand-written log is kept beside the new
one as `phase-log.legacy.md`.


The plan guard (`hooks/plan_guard.py`, a `Stop` hook) refuses to let a turn end
while any of these is missing. It cannot judge whether a reason is GOOD — that is
the user's call at the plan checkpoint — only whether you made the choice silently.

| Field | Where | Why it is enforced |
|---|---|---|
| `## Size estimate` | `plan.md`, once any phase's `- Scope:` is filled | It is what makes an over-built plan visible at the checkpoint. A plan that hides its size hides the thing the user needs to reject it. |
| `- Size:` | every drafted phase, while the PR cap is on | The sizes are what show whether the feature fits in one PR; a plan without them would skip the cap. |
| `## PRs` or `- Over cap:` | `plan.md`, when the phases' `- Size:` total is over the PR cap (`pr_cap` in `.dev-workflow/plan-guard.json`, default 300, `0` = off) | A diff past the cap gets skimmed, not reviewed. Each `### PR N` lists its `- Phases:`; every phase sits in one PR, and a PR over the cap carries its own `- Over cap:` reason. |
| `- Why separate:` | every phase AFTER the first | Each extra phase costs the user an implement-review-approve round-trip. Splitting stays allowed; splitting without naming why does not. |
| `unresolved` | any phase that took more than 2 review rounds — `dw reviewed` refuses without it | Going past the budget means coder and reviewer did not converge — that is a decision for the USER, and the extra rounds must not pass silently. |
| `project_map` | a finished feature, when the project has a `project-map.md` | Stage 5 is what maintains the map — and single-phase features skip Stage 5, which is now most of them. `"no structural change"` is a complete answer; saying nothing is not. |
| `lessons` | a finished feature | Stage 6 is where the workflow learns, and it runs when everyone wants to be done. `"none"` is a complete answer; skipping the step is not. |

Until a phase has a real `- Scope:`, the plan is still the untouched scaffold and
the guard stays silent — Stages 0.5–2 legitimately end turns with no plan written.

## Setup — feature workspace
1. Derive a short kebab-case `slug` (e.g. `wallet-topup`).
2. Run `python3 "${CLAUDE_SKILL_DIR}/../../hooks/dw.py" new <slug> "<feature title>"`.
   It creates `.dev-workflow/features/<slug>/` with `state.json` and the rendered
   `phase-log.md`, makes the feature active (`.dev-workflow/active`; several can
   coexist, switch by rewriting that file), and writes the `.dev-workflow/dw` launcher
   every later command uses.
3. Scaffold `spec.md` and `plan.md` in that directory — copy from the plugin's
   `templates/` if reachable, else create them with the standard sections.
4. Once the tier is known (Stage 0.8) nothing more is needed here; once the plan is
   approved (Stage 3), record its phases with `dw phases`.

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
`conventions.md` is already in your context when `CLAUDE.md` imports it (`init`
sets that up) — then don't Read it again.

- If `project-map.md` is missing, say so and offer `/dev-workflow:init` — it
  drafts both files. If the user declines, DON'T guess the project's shape:
  Stage 1's researcher surveys the relevant part of the codebase instead, and you
  work from that survey.
- If it exists, treat it as a map, not as gospel: it can be stale. When something
  you read in the code contradicts it, the CODE wins — fix the entry in
  `project-map.md` as you go, and tell the user what you corrected.
- From the map, pull the entries this feature plausibly touches (modules,
  existing features that overlap, building blocks to reuse, the extension point
  to hook into, the gotchas in those modules) and carry THOSE forward. Every
  entry carries its path, so grepping the map for a module's path collects them. You hand agents excerpts, never "go read
  project-map.md" — the point of the file is that they don't each pay for it.
- **Read what the user changed after the last feature shipped** — "Post-ship
  edits" in `${CLAUDE_SKILL_DIR}/references/lessons.md`. Do it before Stage 0.5, so an approved rule already binds
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
exists and is behaving wrong. If it is genuinely unclear which it is, ask in one line.
**Read `${CLAUDE_SKILL_DIR}/references/bug-mode.md` now and follow it instead of steps
1–5**: reproduce first (cannot reproduce → stop and ask the user), root cause at
`file:line`, blast radius, then acceptance criteria whose first item is the
regression. The same file sets a bug's tier and what its Evidence ledger owes. Then
continue at Stage 0.8.

## Stage 0.8 — Size it: the machinery must be proportional to the change
**The user pays for this workflow in wall-clock time and approval round-trips.** A
20-line change that runs a research agent, two architects, three phases and five
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
| **trivial** | *(default)* one subsystem, one reviewable diff, no new interface, no new dependency, no new persistent state — a validation rule, an added field, a config value, a bug fix, a new parameter with a default | the **Trivial path** below: survey → one inline proposal the user approves → **1 phase**, coded by you (no `coder`) → `code-reviewer` (logic + security pass) → your approval. **No researcher, no architect, no plan-reviewer, no Stage 5.** |
| **standard** | a new interface others will call (endpoint, command, screen, public function), OR new persistent state/schema, OR several files across one subsystem | survey, plus external research **only if there is a real external question** → one fit-first architect → plan + `plan-reviewer` → phases → Stage 5 only if the plan ended up with more than one phase |
| **complex** | crosses a subsystem or trust boundary, OR changes a data model other code depends on, OR the design itself is security-sensitive, OR wide blast radius | full machinery — two independent fit-first architects, full final audit |

**For a bug, the root cause sets the tier, not the severity of the symptom** — see
`bug-mode.md`.

**Re-check the tier after the plan is drafted, and DOWNGRADE without ceremony.** This
estimate is a guess; the plan is when you actually know. If the work turned out to be
one small diff, collapse it: drop the remaining phases into one, skip Stage 5, and
tell the user you scaled it down and why. Downgrading needs no permission. Upgrading
does: name the signal and tell the user before you spend their time on it.

The tier scales research and the number of architects — NOT security coverage:
`code-reviewer` runs every phase in every tier, security pass included. Nor does it
scale approval: in every tier the user approves what will be built before any code
is written, and approves each phase after its review. The trivial tier only merges
the option and plan checkpoints into one proposal.

## Trivial path — one proposal, one checkpoint, one phase
The trivial tier does not run Stages 1–3. It does this instead, and it is the whole
front half of the workflow for a small change:

1. **Survey.** Read the `project-map.md` entries for the area and the files they
   name (no map: Grep the area), so the change doesn't quietly duplicate an
   existing helper. Two minutes of Reads, not a subagent.
2. **Propose inline**, in one short message: the files you will touch, the approach,
   the existing code it reuses or mirrors, the estimated lines, and what proves each
   acceptance criterion. Write the same into `plan.md` as its single phase (`##
   Size estimate`, and the phase's `- Scope:`, `- Files:`, `- Done when:`,
   `- Size:`, `- Verify:`) — a few lines; `## Structure` is its `- Pattern:` line,
   naming the code the change mirrors.
   There is no options table: a trivial change has one obvious way. If you find
   two ways the user would actually choose between, ask in this same message.
3. **CHECKPOINT: the user approves the proposal.** This one stop stands in for the
   option checkpoint and the plan checkpoint. Then `dw phases "<title>"` and go to
   Stage 4.

If writing the proposal turns up a signal from the tier table (a new interface, new
persistent state, a second subsystem), it is not trivial: tell the user, and run
Stages 1–3.

## Stages 1–3 — Research, option, plan  (standard and complex tiers)
**Read `${CLAUDE_SKILL_DIR}/references/design-stages.md` now and run it** — the
codebase survey and research (Stage 1), the fit-first solution option with its
checkpoint (Stage 2), then the plan, the tier re-check, the `plan-reviewer` and the
plan checkpoint (Stage 3). The files it names: `pr-slicing.md` and `ui-prototype.md`
are in `${CLAUDE_SKILL_DIR}/references/`; the pattern catalog is
`${CLAUDE_SKILL_DIR}/../../references/architecture-patterns.md`. When the plan is
approved and its phases recorded with `dw phases`, continue at Stage 4.

## Stage 4 — Phased implementation (loop per phase)
**Trivial tier: you write the code yourself — no `coder` spawn.** Use the tier as
it stands after Stage 3's re-check: a feature downgraded to trivial counts; a
standard one that merely ended with one phase does not. First Read
`${CLAUDE_SKILL_DIR}/../../agents/coder.md` once, from "While coding:" through its
"Tests" section, and follow it as the coder would: `conventions.md` and the
project's formatter/linter, scope, prefer what exists, the clean-code and
readability rules, the agreed `## Structure`, comments, tests, and run the
tests/build and report honestly. Then run `dw coded N` with what changed and the
evidence you ran; anything extra goes to the user as
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
   never make it re-scan to find the change. Reviewers have no Bash and cannot run
   `git diff`, so run `dw diff N`: it writes the phase's diff to
   `.dev-workflow/features/<slug>/phase-N.diff` and prints each changed file with
   its line counts. Put that path in the brief for the reviewer to Read. Do not paste
   the diff into the brief and do not Read the file yourself: a pasted diff is
   output you pay for, and it stays in your context for the rest of the feature.
   (Not a git repo: `dw diff` refuses — name each changed file with the line ranges
   of its hunks instead.) Add the
   phase's `Done when:` (the code-reviewer needs it to judge what
   is over-built) and `plan.md`'s `## Structure` (to judge whether the code
   follows the agreed shape). Ask the code-reviewer for its **review map** (see
   `agents/code-reviewer.md`) — on a re-review, for the fix diff only. If the coder returned `Suggested, not built:` items (or your
   own trivial work produced some), carry them to the user at this phase's checkpoint — never build them on your own call.
   Before the review, check the file list `dw diff` printed for files the phase
   should not leave behind: probe/smoke/e2e scripts, backups, `.diff` dumps, handoff
   notes — in `src/`, `scripts/` or the feature dir. Delete them unless the plan
   asked for them. (The `phase-N*.diff` files `dw diff` writes are its own, and
   each run overwrites them.)
   The `code-reviewer` runs ALWAYS, every phase, every tier, and its **Security
   pass** runs with it — there is no surface to judge first. On a phase that touches
   nothing sensitive the pass is one line naming what was checked. It catches LOCAL
   bugs while they are cheap to fix (injection, hardcoded secrets, missing authz on a
   new endpoint); EMERGENT, cross-phase vulnerabilities are Stage 5's `security-audit`.
3. Summarize the review that ran for the user, and record it with `dw`. The coder
   (or you, in trivial) already ran `dw coded` with what it ran; your job here is the
   review and the evidence:
   - If the reviewer found BLOCKING issues, run `dw round N`, have `coder` fix them
     (fix them yourself in trivial), then re-review — **under the round budget below. Count the rounds; do
     not loop until they agree.**
   - Run `dw reviewed N --security` once `code-reviewer`'s findings, its
     `Security pass:` ones included, are resolved.
     "Resolved" means fixed, rebutted with evidence you accepted (never your own
     rebuttal in a phase you coded), or decided by the user at escalation — never
     "we ran out of rounds".
   - Give `dw reviewed` the **review map** on stdin: the first round's map,
     with each re-review's fix-diff entries merged in (a hunk changed by a fix is
     re-tiered, never left at a lower tier than the fix warrants). Replace the
     reviewer's line counts in the opening line with the totals `dw diff N` prints
     (run it again after a fix round, for the phase as it now stands).
     Keep the tier labels and one-line entries: `dw reviewed` refuses a map with no
     MUST / SKIM / SKIP entry, and the dashboard renders them.
   - If the plan guard reported the diff **over its `- Size:` budget**, split the
     rest into a new phase (`dw add-phase`) or say why it lands together
     (`dw set N over_budget`).
   - Record `review_result`, `unresolved` and `deferred_nits` with `dw set N` — they
     let the user see how contested the phase was, and what was consciously let go,
     before approving it. The round count is kept by `dw round`.
   - **Augment the evidence ledger** (`dw set N evidence`, the whole ledger again) so
     it carries CITED proof it works:
     test/command output, `file:line` refs, concrete cases verified — one artifact
     per acceptance criterion this phase delivers (`spec.md` section 1b), no
     "looks fine". **An artifact is not the same thing as a new test** — see below.
     A reviewed phase with an empty ledger cannot be approved, and the `Stop`-hook
     evidence gate refuses to let you yield for approval while it is empty.
4. **CHECKPOINT: the user reviews AFTER the AI. Stop and wait.** Lead with the
   review map, so the user reads 40 lines instead of 400: the totals line, any
   `- Over budget:` reason, the MUST entries in reading order with their questions,
   then every ASSUME. SKIM and SKIP go in one line each with counts. Do not paste the
   diff; the user opens the MUST ranges (or the dashboard shows them). Then the review
   summary and evidence. Tell the user they can approve with
   `/dev-workflow:approve` or in their own words. When they approve in words, relay it:
   `dw approve N --said "<their words>"`. If they ask for changes, record them with
   `dw set N user_notes` and `dw reopen N`. Never advance unapproved.
5. **Commit.** With a `## PRs` section, follow `pr-slicing.md`: commit per PR on
   `<slug>/pr-<N>` once its last phase is approved; never push. Without `## PRs`: if
   it's a git repo and the user wants per-phase commits, commit scoped to this phase
   (`Phase N: <title>`). Skip otherwise.

### One artifact per criterion is NOT one test per criterion
The gate will not let the turn end without a citable artifact, and the cheapest one
to manufacture is a new test — so, left alone, criteria turn into tests one-for-one,
shaped to be CITED rather than to be able to fail. A ledger reading `criterion 1 →
x.spec.ts:123, criterion 2 → :135` is that failure, not rigour.

- **An artifact is anything that would have caught the criterion being wrong**: a
  type-check or build that could not have passed otherwise, a command run against
  the real thing with its output, a `file:line` where the constraint now holds by
  construction, a log line from a real run, one test covering several criteria.
  Cite the cheapest one that would actually fail.
- **Test budget.** Default is NO new test file per phase: extend the changed
  module's existing spec. A test is written only for pure logic with real branching,
  a bug's regression, or store-level behaviour proven against the real store. More
  test lines than code lines in a phase is a signal to cut.
- **A criterion satisfied by a declaration** (a validator annotation, a schema field,
  a config value, a type) gets NO test — one would only restate it. Cite the
  declaration and the type-check, and say in the ledger which criterion you skipped
  and why, so the user sees a decision rather than a gap.
- **A test that mocks the thing it claims to prove is worse than no test.**
  Atomicity, uniqueness, index and transaction behaviour live in the store: prove
  them against a real one, or narrow the claim to what a fake CAN prove. Faking a
  collaborator to INJECT a failure you cannot otherwise reach stays legitimate.
- **A bug fix** cites its repro failing before the fix and passing after
  (`bug-mode.md`); the declaration exemption does not apply to it.

The full rules are the "Tests" section of `agents/coder.md` — which you follow in a
trivial phase — and `code-reviewer`'s test checks. `test_guard.py` denies two shapes
on write (a provider built from positional `as any` blanks, a test block that
asserts nothing); the rest is the reviewer's, and it may say a test should be DELETED.

### The review loop is BOUNDED — at most 2 fix rounds, then the user decides
A coder and a reviewer left alone will argue indefinitely: the reviewer keeps
finding things because finding things is its job, and each new round re-opens code
the last round already settled. Nothing in the loop ends it, so you end it.

**A round is spent only on a BLOCKING finding.** Round 0 with no BLOCKING finding
is zero rounds: run `dw reviewed N`, put the nits in `deferred_nits` and show
them at the checkpoint. The user picks which to apply; a nit fix of a line or two (a
rename, a wording change) needs no re-review and no `dw round`.
When a round does run for a BLOCKING finding, the nits may ride along in the same
fix. There are two labels, BLOCKING and NIT — a reviewer's "should-fix" is BLOCKING
if it changes behaviour a real caller can reach, otherwise a NIT.

**Budget: 2 fix rounds per phase.** The first review is round 0. Findings → coder
fixes → re-review is round 1. One more if needed is round 2. There is no round 3.

- **Re-reviews are DELTA-SCOPED.** Hand the fresh reviewer the previous round's
  findings AND the fix diff (`dw diff N --since-review` writes what changed since
  the last `dw diff N` to `phase-N.fix.diff`), and tell it to judge THOSE — did each finding get
  fixed, did the fix break anything — not to re-review the phase; the
  security pass re-runs on the fix diff. A new finding is
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
  not resolve a deadlock by running `dw reviewed` yourself, and you do not
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

A single-phase feature has no final review in its state, so there is nothing to
remove. Skipping the stage does NOT skip the map update below or Stage 6: both run at
the phase's approval checkpoint, and the plan guard requires `project_map` (when the
project has a map) and `lessons` on a finished feature.

**More than one phase:** read `${CLAUDE_SKILL_DIR}/references/final-review.md` and run
it — cross-phase `code-reviewer` plus `security-audit`, the same 2-round budget, then a
sign-off checkpoint that presents the result, the map update and the Stage 6 proposals.

**Every feature, at its final checkpoint, update `project-map.md`** so the next feature starts from what this one
built. The `Rules for this file` at the top of the map bind the edit. A map drafted
by an older version has none: copy them from
`${CLAUDE_SKILL_DIR}/../../templates/project-map.md` first and bring the map in line
with them in this same update — rename `Shipped` to `Verified`, merge the per-change
rows of `Existing features` into one row per capability — and tell the user you did.
The map describes what
exists NOW, so most features edit an entry and few add one:
- `Existing features`: update the row of the capability this feature extended and
  set its `Verified` to today, or add a row for a capability the project did not
  have.
- Add/adjust `Module map` rows for anything new or newly re-scoped, and add any new
  `Shared building block`, `Extension point` or `Known gotcha` this feature
  introduced.
- Fix entries this feature proved stale, and drop entries for what it removed.
- If none of these applies — nothing a future agent would need to find — write
  nothing and record "no structural change". For a small change that is the usual
  answer.

## Stage 6 — Lessons  (every feature, every tier, at its final checkpoint)
At the final checkpoint — Stage 5's, or the last phase's when Stage 5 is skipped —
read `${CLAUDE_SKILL_DIR}/references/lessons.md` and run it: at most three rule
proposals for `conventions.md` in ONE `AskUserQuestion` (nothing worth proposing is
the common outcome — then say so and ask nothing), the result recorded with
`dw set feature lessons` (the plan guard requires it; `"none"` is a complete answer), then
the ship point. The same file holds **Post-ship edits**, which Stage 0 runs. Its
commands use `python3 "${CLAUDE_SKILL_DIR}/../../hooks/checkpoint.py"`.

## Notes
- Subagents can't pause to ask mid-task; scope each delegated task tightly and
  resolve ambiguity with the user BEFORE delegating — that is what Stage 0.5 is
  for, and why the analyst role is yours and can never be delegated to a subagent.
- Reviewers are read-only with fresh context and always freshly spawned, so they
  judge code they didn't write — the `coder`'s, or yours in a trivial phase.
- For a hard-enforced approval gate, see the `.approval-gate` hook in `docs/guards.md`.
