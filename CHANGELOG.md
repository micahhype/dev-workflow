# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`subagent_traces.py` shows where the time goes.** Each run is split into turns, one per
  task the agent was given (a kept-alive `coder` gets one per phase and one per review round),
  so the wait between phases counts nowhere. Each turn records model time and tool time by kind
  (test, lint, read, edit, other); `traces.jsonl` rows gain `active_ms`, `model_ms`, `tool_ms`,
  `tool_calls` and `turns`. The report adds the median turn per agent and the slowest turns
  (`--slowest N`, default 5).
- **`subagent_traces.py --since YYYY-MM-DD`** keeps only runs started on or after that date (UTC),
  to compare the workflow before and after a change.

### Changed
- **`coder` runs checks cheaply:** only the changed spec while iterating, the broad suite once
  at the end in the background (failures read from its saved output, then only the failing files
  rerun), and one linter invocation over all touched files.

## [0.19.0] - 2026-10-27

### Added
- **`scripts/subagent_traces.py`** reads your Claude Code subagent transcripts (default
  `~/.claude/projects`) into `traces.jsonl`, one row per run: feature trace id, agent, start,
  duration, tokens counted once per API request, model. No prompt text is written. Prints tokens
  and time per agent type plus the agents that run together in one feature. Field names match
  single-agent-loop-kit's `coupling_map.py`.

### Changed
- **Trivial phases are coded by the orchestrator itself**, with no `coder` spawn, following the
  coder's rules from `agents/coder.md`. A freshly spawned `code-reviewer` still reviews every
  phase, and in a phase the orchestrator coded it cannot accept its own rebuttal: a finding it
  disagrees with goes to you at once. Standard and complex tiers keep the `coder`.
- **`code-reviewer` runs the per-phase security pass**, asked for only when the phase touches a
  sensitive surface (same gating as before). Critical/High findings always block. Its
  `Security pass:` line is what ticks `[x] security-scanned`.

### Removed
- **`security-scan-fast` agent**, folded into `code-reviewer`. A `security-scan-fast` key left in
  `.dev-workflow/models.json` now does nothing; `/dev-workflow:config` lists it as unknown.

## [0.18.0] - 2026-10-19

### Added
- **Review map at every phase checkpoint.** The `code-reviewer` sorts each changed hunk into
  `MUST` (with the concrete question the user must answer), `SKIM` or `SKIP`, and lists every
  `ASSUME`: a rule or default the code settles that the spec did not. Security surface, new
  branches, data writes, changed error handling, public signatures and untested code can never go
  below `MUST`. The orchestrator records it as `- Review map:` and opens the approval checkpoint
  with it instead of the diff. The plan guard refuses to end a turn on a reviewed phase without one.
- **Per-phase diff budget.** Plan phases state `- Size: ~N lines`. `hooks/diff_budget.py` records
  each phase's baseline tree at Stop (no per-phase commits needed), and the plan guard refuses
  past 2× the estimate (minimum +40 lines) until the phase-log `- Over budget:` gives a reason.
- **Dashboard shows the review map**: totals, the diff against its budget, `MUST` entries with
  their code (read from the working file, only inside the project), assumptions, then skim/skip.
- **Mark done from the dashboard.** A feature finished outside the workflow no longer waits
  forever: the drawer's Mark done button (inline confirm) ticks its open phases through one
  guarded `POST /api/mark-done` (own Host and Origin, JSON body, per-launch token). GET stays
  write-free. `hooks/mark_done.py` does the same from your own terminal.

## [0.17.2] - 2026-10-07

### Changed
- **Subagents spend fewer tool calls finding code.** Every agent prompt gains a short "Read
  efficiently" block: start from the brief's paths, check `project-map.md` before Glob-walking,
  batch independent Reads/Greps in one turn, Grep then Read only the range, never re-read.
- **Reviewer briefs carry the change itself.** Reviewers have no Bash, so the orchestrator pastes
  the phase diff (or each file's hunk ranges for a long one). The final `code-reviewer` and
  `security-audit` get every changed file by phase plus which phases skipped the fast scan.

## [0.17.1] - 2026-09-29

### Changed
- **Dashboard board grouped by project.** One block per project, features waiting for your
  approval first, Done folded behind "N done", fully finished projects on one "All done" line.
  Fixed-width phase track and one-line rows, so 50+ features stay readable.
- **Resume button** on every feature waiting for approval: copies
  `cd <project> && claude --continue`, to jump back into the session that is waiting.
- **Plan, Spec and Evidence render as formatted text** in the detail panel (headings, lists,
  tables, code) instead of raw Markdown. Hand-rolled subset, text-only DOM, no dependency.

## [0.17.0] - 2026-09-29

### Added
- **`/dev-workflow:dashboard` — a local, read-only board of every project.** One page on
  `127.0.0.1` shows every project using the plugin: features waiting for your approval first,
  then one row per feature with a phase track and a short status. Spec, plan, evidence,
  checkpoints (with copyable `!` rollback commands) and config open in a side panel on click.
  Refreshes itself every 2s. Stdlib only, GET only, Host-checked, no write route; `--detach`
  returns at once and the server stops after 30 min idle.
- **Project registry.** The SessionStart hook records each project that has `.dev-workflow/` in
  `~/.claude/dev-workflow/projects.json` — the plugin's first per-user file. Silent on any error.
  A project shows up on the board after its first session on this version.

## [0.16.0] - 2026-09-29

### Added
- **`plan.md` decides the shape of the code, not just the files.** `## Files
  expected to change` becomes `## Structure`: the existing feature the new one is
  shaped like (by path), each file's one responsibility, the main flow, and any
  deviations. The coder had only a file list, so it invented a layout per feature
  and the codebase drifted away from any pattern. The coder now mirrors the named
  exemplar, the plan-reviewer blocks a plan without one, and the code-reviewer
  flags structure drift. The solution architect names the exemplar its option
  would follow.
- **Throwaway UI prototype, only when the screen is the open question.** A new
  page whose layout is not pinned down gets a static HTML mock in the feature dir
  before the plan checkpoint, deleted once the plan is approved. Nothing else gets
  a prototype.

## [0.15.0] - 2026-09-25

### Changed
- **Opus for every agent that judges.** `solution-architect` and
  `domain-researcher` ran on Haiku, `code-reviewer` and `security-audit` on Sonnet.
  Since 0.13 a standard feature usually gets ONE simplicity-first architect, the
  codebase survey is what stops a feature rebuilding what exists (a Haiku survey
  once reported an existing `getSeqno` as missing), and the reviewer now decides
  what is over-built, unreadable or a test to delete. All four default to `opus`
  now. `security-scan-fast` moves from `fable` to `sonnet`: it is a quick filter
  that `security-audit` backs up. Cheaper defaults are one line each in
  `.dev-workflow/models.json`.

## [0.14.1] - 2026-09-25

### Changed
- **Agent models are aliases now, not pinned IDs.** `coder` was pinned to Opus 4.8
  and `security-scan-fast` to Fable 5 while newer models shipped, so the agent that
  writes the code ran a generation behind the session. Every agent's default is now
  its family alias (`opus`, `sonnet`, `haiku`, `fable`), which tracks the newest
  model without a plugin update. To pin a version, set a full model ID for that
  agent in `.dev-workflow/models.json`.

## [0.14.0] - 2026-09-25

### Added
- **The workflow learns across features.** A review finding, a correction you made
  at a checkpoint, a suggestion you turned down all died with the feature's
  `phase-log.md`, and the next feature repeated the mistake. A new **Stage 6 —
  Lessons** runs at every feature's final checkpoint: it proposes at most three
  one-line rules, each with its evidence, and writes the ones you pick to a new
  `## Learned rules` section of `conventions.md`, which every agent already reads.
- **Post-ship edits become lessons.** `checkpoint.py ship <slug>` records the tree
  a feature was handed over in (`refs/dev-workflow/shipped/<slug>`); `since-ship
  <slug> [path...]` diffs it against the working tree. At the start of the next
  feature the orchestrator reads what you rewrote in agent code and proposes rules
  from it, once per feature (`- Post-ship reviewed:`).
- **Plan guard: `- Lessons:` line.** A finished feature must record what it
  learned — `"none"` is a complete answer — so the step cannot be skipped silently.

### Changed
- **Comments: a one-line WHY is back.** 0.13's zero-comment default overshot —
  genuinely hard logic lost the one line that said why. Defaults are now
  `floor: 1`, `min_ratio: 0.05` (one line per edit, about one per twenty lines of
  code); the two-line block cap and the no-sibling-inheritance rule stay, so the
  design essays 0.13 stopped stay stopped. `coder` and `code-reviewer` now ask for
  WHY on hard logic and forbid WHAT, history and paragraphs. `{"density":
  {"floor": 0, "min_ratio": 0}}` restores zero.

## [0.13.0] - 2026-09-25

### Changed
- **Simpler code, by default.** Agents kept adding what nobody asked for: caches
  with env-configured TTLs, caps against abuse nobody reported, "partial" flags,
  try/catch that logs and returns a default. Two sources fed it. The orchestrator
  invented business rules while writing acceptance criteria, and `code-reviewer`
  asked for handling of every empty/null/overflow case, reachable or not.
  - Every acceptance criterion must now trace to something the user said. Extras
    go to a `Suggested, not built:` line in `spec.md` and are built only on the
    user's word. `coder` gets an explicit don't-add list and a trim pass over its
    own diff before returning.
  - `code-reviewer` flags an edge case only when a real caller can reach it, and
    treats over-building as a first-class finding whose fix is deletion (BLOCKING
    when it adds surface). `plan-reviewer` blocks invented business rules.
  - `security-scan-fast` asks for validation only of untrusted input at a trust
    boundary.
  - The architect panel always runs simplicity-first. Performance-first and
    risk-first run only on a named signal.
- **Readable code, not decodable code.** Agent code was correct but had to be
  decoded: string-glued map keys, `out`/`rows`/`base` names (one reused for two
  things), a 0/1 sort trick, meaning carried by `null` vs `undefined`, five
  positional parameters, loops nesting `await Promise.all` → `map`. With comments
  now at zero, the code is the only explanation, so this matters more. `coder`
  gets concrete readability rules, a before/after from a real diff, and a
  "could a teammate explain this cold?" self-check. `code-reviewer` treats a
  broken rule as BLOCKING. New **Readability contract** section in
  `conventions.md`, copied verbatim by `init`.
- **Fewer tests.** The "one artifact per criterion" rule was being met with one new
  spec file per criterion and one test per defensive branch. The default is now no
  new test file per phase: extend the module's existing spec. Tests are written for
  real branching logic, bug regressions and store-level behaviour only. Wiring
  tests, tests of vendored or generated code, and committed probe/smoke scripts are
  out, and `code-reviewer` recommends deleting them.
- **Comment guard: zero by default.** A comment-free or new file now grants no
  comment lines (was one). New files no longer inherit their siblings' density,
  which let agent-written comments compound across a directory. New `max_block`
  (default 2) caps any added comment block, whatever the density, which ends the
  design-essay comment. Tool directives (`eslint-disable`, `noqa`,
  `@ts-expect-error`, shebangs, licence lines) are never counted. `allow` patterns
  now exempt a comment from the budget too. A new file's header docstring is no
  longer free. Restore the old behaviour with `{"density": {"floor": 1},
  "max_block": 0}`.

## [0.12.0] - 2026-08-26

### Added
- **`--bug`: a bug-shaped front end for `/dev-workflow:feature`.** The workflow had
  one entry path, and it assumed you already knew what you wanted built — Stage 0.5
  turns a request into acceptance criteria. A bug report's unknown is not what to
  build, it is where the cause is, and nothing downstream could recover from getting
  that wrong: reviewers check the code against the plan, so a patch aimed at the
  symptom passes every review in the workflow when the plan says "stop the 500".

  `--bug` (or a request that plainly reports something broken) swaps that stage for
  reproduce → root cause → regression, then rejoins the existing tiers, phases,
  reviews, gates and hooks unchanged — it is a branch in one stage, not a second
  workflow with a second state model the hooks would have to learn to parse.
  It reproduces BEFORE diagnosing and **stops to ask when it cannot**, because an
  unreproducible bug leaves Stage 4's evidence gate measuring nothing; it names the
  cause at `file:line` and separates it from the symptom, deliberately, out loud;
  it states the blast radius, including **data the bug already wrote** — repairing
  that is a phase with its own rollback and its own approval, never a silent extra
  in the fix; and it stops if the diagnosis finds no bug rather than building the
  change that would make the report true.

  The first acceptance criterion is always the regression, and the Evidence ledger
  must cite the repro **failing before and passing after**. The red half is captured
  during diagnosis, so this costs one paste rather than one more test run — and it
  closes the gap where a test written after a fix, never seen fail, is cited as
  proof it works. The "a declaration already enforces it" exemption does not apply
  to it. Tier is set by the ROOT CAUSE, not the severity of the symptom: a
  production outage caused by a one-line off-by-one stays trivial and stays one
  reviewable diff. `templates/spec.md` gained an optional (commented-out) section
  `1a. Bug: reproduction & root cause` so the cause is reviewable at the plan
  checkpoint instead of living only in the conversation.

## [0.11.0] - 2026-08-20

### Fixed
- **The approval gate denied any Bash command containing a regex like `(.*?)`.** Its
  glob sweep ran on a quote-STRIPPED copy of the command and split on shell
  separators including parentheses, so an ordinary `re.search(r'<t>(.*?)</t>', s)`
  produced the bare token `.*?` — which `fnmatch` happily matches against
  `.approval-gate`. Regexes containing `.*` are everywhere, so this fired on
  read-only greps, `sed` one-liners and `python3 -c` snippets that had nothing to do
  with the gate, which is exactly how a guard earns being switched off.

  Globs do not expand inside quotes, so the sweep now removes quoted spans instead
  of unquoting them. A quote closed early to split the name (`rm '.approval-gat'?`)
  would slip past that, so the stripped form is still swept — but only for patterns
  that spell out at least six literal characters of the name, which no incidental
  regex does. Every previously-blocked evasion stays blocked; verified against 11
  evasion shapes and 12 ordinary commands.

### Added
- **`/dev-workflow:config` — the effective configuration, and where each value came
  from.** The plugin's knobs were spread over three JSON files, two environment
  variables and a gate file, documented only inside collapsed README sections and
  hook docstrings, and every one of them fails silently: `comment_guard`,
  `test_guard` and the feature skill's read of `models.json` all swallow a parse
  error and carry on with defaults. That is right — a malformed preference must
  never crash an edit or trap a turn — but it means a stray comma disables nothing,
  warns nobody, and leaves a project believing it configured something.

  The new skill reports each knob's effective value beside its provenance:
  `default`, `file`, `env <VAR>`, or `file, IGNORED` for a key that was written and
  changed nothing. A `PROBLEMS` block leads when a file is being ignored in full,
  when a key is misspelled past recognition, when an `allow` pattern will not
  compile, when `"enabled": "false"` was written as a string (only the literal JSON
  `false` disables a guard), or when a `DEV_WORKFLOW_*_GUARD` switch is set and no
  file can override it.

  `hooks/config.py` never restates a default: it imports the guards and reads their
  own constants and their own `load_config`, and scrapes agent names and default
  models from `agents/*.md` frontmatter — so a report that disagrees with the
  running hook is not constructible. `config set <key> <value>` writes a single key
  and prunes anything equal to its default, keeping each file a diff against the
  plugin rather than a frozen copy of it, and refuses to write over a file it
  cannot parse.

## [0.10.1] - 2026-08-20

### Fixed
- **`pytest` at the repo root collected a shipped hook and died before running a
  single test**, taking CI red on the 0.10.0 tag. `hooks/test_guard.py` matches
  pytest's default `test_*.py` glob, so collection imported it as a test module and
  choked on its `test_blocks()` generator. A `pytest.ini` now declares what was
  always true — the suite is in `tests/` — with `norecursedirs` covering an
  explicit `pytest .` as well. Local runs used `pytest tests/` and never saw it.

## [0.10.0] - 2026-08-20

### Changed
- **The comment rule's default is now NO comment.** It previously read "comment
  only what the code cannot say itself, and match the file's density", which still
  granted every edit a free paragraph: the guard's floor was 4 comment lines
  regardless of ratio, and a comment-free file still granted 25%. Between them,
  four lines of commentary landed in a bare file on every edit and never reached
  the density check at all. The floor is now **1** and the comment-free allowance
  **0**, so a file with no comments grants exactly one line per edit however large
  the edit — the caveat that genuinely cannot be said any other way — and anything
  beyond that has to be earned from the file's own density, which keeps the rule
  from being wrong on a codebase that documents heavily.

  The prose moved with it in all four places (`references/clean-code.md`,
  `agents/coder.md`, `agents/code-reviewer.md`, `templates/conventions.md`): the
  first move when a line needs explaining is to fix the CODE — a clearer name, a
  smaller function, a named constant — and a comment is an exception that earns its
  line only by stating a constraint the code cannot, a reason the obvious approach
  is wrong here, or a caveat with real consequences. `code-reviewer` now treats
  every comment in a diff as a finding that must justify itself, and when a comment
  explains confusing code the finding is the code, not the comment.

  Projects that want the old behaviour back:
  `.dev-workflow/comment-guard.json` -> `{"density": {"floor": 4, "min_ratio": 0.25}}`.

### Added
- **The workflow no longer converts acceptance criteria into tests one-for-one.**
  The evidence gate is the strongest incentive in the plugin — a turn cannot end
  until `- Evidence:` cites an artifact per criterion — and the cheapest artifact
  to manufacture is a new test. So criteria became tests one-for-one regardless of
  whether they had logic worth testing, and the tests came out shaped to be CITED
  rather than able to FAIL. Stage 4 now says plainly that an artifact is not the
  same thing as a new test (a type-check, a command run against the real thing, a
  `file:line` where the constraint holds by construction, one test covering several
  criteria all qualify), that a criterion satisfied by a declaration — a validator
  annotation, a schema field, a config constant, a type — must NOT get a test that
  can only restate it, and that skipping one is recorded in the ledger as a
  decision. Stage 3 asks the plan to name the proof rather than budget a test.
- **`coder` has testing rules for the first time.** It previously had none: the
  agent was told to run existing tests and nothing about when a test is worth
  writing or how to build one. Three rules, applied in order — prove store and
  external behaviour against the real thing (checking the manifest for a harness
  first, since one is usually already installed); pure logic gets a plain unit test
  with no DI and no mocks; everything else gets no test. Dependencies are bound by
  NAME, never positionally out of `{} as any` blanks.
- **`code-reviewer` reviews the tests.** The agent definition did not contain the
  word "test". It now owns the judgement no hook can make — a test that mocks the
  risk it claims to prove, a test that restates a declaration, a test that cannot
  fail — and is explicitly authorized to recommend DELETING a test, while still
  flagging the opposite failure of a criterion with no artifact behind it.
- **`conventions.md` gained a Testing section and a verbatim Testing contract**,
  and `/dev-workflow:init` now detects the testing setup — including a real-store
  harness that is installed but unused, which is the common case and the reason an
  agent mocks the database instead of using it.
- **`hooks/test_guard.py`** (`PreToolUse`) backs the two shapes that need no
  judgement, on test files only and only on what an edit adds: a provider built
  from three or more positional `as any` blanks, and a test block with no assertion
  (named assertion helpers count as asserting). Off with
  `DEV_WORKFLOW_TEST_GUARD=off` or `.dev-workflow/test-guard.json`.

  Deliberately NOT hooked: "the test mocks the risk it claims to prove". Two
  designs were measured against 93 real test files — block-scoped detection missed
  every true positive because the fake is built in a factory outside the block, and
  file-scoped detection reached roughly half false positives because the claim
  lives in English ("a unique payer+amount candidate" is in-process wording, and a
  fake that throws is the only way to reach a driver duplicate-key error at all).
  That call needs the subject read beside the test, so it stays with
  `code-reviewer`.

## [0.9.1] - 2026-08-13

### Fixed
- **The comment guard's refusal pointed outside-workflow agents at files that do
  not exist.** It denied with "belongs in your return message to the orchestrator
  and in `phase-log.md`" on every edit — but the guard runs always, not only
  inside a feature, so most of the time it is read by an agent chatting directly
  with the user, where there is no orchestrator and no phase log. The refusal now
  names `phase-log.md` only when `.dev-workflow/active` resolves to a real feature
  directory, and otherwise says the change-talk belongs in the message to the user
  or in the commit message. A dangling `active` slug (feature deleted or renamed)
  counts as outside. The density refusal's "say so in your return message" lost
  the same assumption.

## [0.9.0] - 2026-08-13

### Added
- **Comment discipline now has a hook behind it.** 0.7.0 made the rule explicit in
  four documents and it still drifted — comments citing acceptance criteria,
  quoting `plan.md`, narrating the diff and arguing correctness at the reviewer
  kept shipping, because prose is the one enforcement layer a model can talk itself
  past. Every other load-bearing rule here has a hook (`gate.py`,
  `evidence_guard.py`, `plan_guard.py`); this one now does too.
  `hooks/comment_guard.py` runs `PreToolUse` on every edit tool and denies the
  write on two deterministic checks, both applied ONLY to comment lines the edit
  ADDS — a comment merely carried through an edit's context is never blamed, since
  the coder has no compliant move there:
  - **Noise patterns** — workflow artifacts (`AC-2`, `plan.md`, `Phase 3:`), diff
    narration (`we now...`, `Added a helper...`, `Previously this...`), and
    reviewer-facing talk (`as requested`, `this ensures...`, `addresses the review
    finding`). Deliberately narrow: it catches the mechanical shapes and leaves
    every judgement call to `code-reviewer`, because a guard that cries wolf gets
    configured off. `# phase 2 of the TLS handshake` passes; `# Phase 2: wire the
    parser` does not.
  - **Density** — comment lines added are capped by the file's OWN comments-per-code
    ratio, which is the only way to enforce "match the file's existing comment
    density" at all. It self-calibrates: the same block lands in a heavily
    commented file and is refused in a terse one. A new file is measured against
    its siblings; a module docstring or licence header is not charged.
  Python docstrings count (a file whose functions all grew one is the noise this
  exists to stop), `.md`/`.json`/`.yaml` and everything under `.dev-workflow/` are
  out of scope, and an unterminated triple quote is treated as code so a multi-line
  SQL string cannot make the rest of the file read as comments. Escape hatches:
  `DEV_WORKFLOW_COMMENT_GUARD=off`, or `.dev-workflow/comment-guard.json` with
  `enabled`, an `allow` regex list, and `density` overrides — a malformed config
  falls back to the defaults rather than failing open. Denial is safe here in a way
  a Stop hook's refusal is not: deleting the comment is always available, so it
  cannot trap a turn and needs no refusal budget.

## [0.8.1] - 2026-07-22

Three hook gaps, each found by running the hooks exactly as Claude Code runs them
(JSON payload on stdin, `CLAUDE_PROJECT_DIR` set) and each closed with a red-first
test that fails on 0.8.0.

### Fixed
- **`NotebookEdit` bypassed both the approval gate and the checkpoint engine.** It
  was missing from `hooks.json`'s `PreToolUse` matcher and from `checkpoint.py`'s
  `MUTATING_TOOLS`, so while the gate said `LOCKED` a phase could still advance
  through an `.ipynb` file — and notebook edits got no pre-edit snapshot, making
  them the one kind of change rollback could not recover. Now routed to both hooks;
  `gate.py` reads its `notebook_path` (it does not use `file_path`) for the
  gate-file protection and the working-doc carve-out alike. A new
  `tests/test_hooks_json.py` pins the matchers to `MUTATING_TOOLS` itself, so the
  wiring and the tool list cannot silently disagree again.
- **Shell globs could name the gate file without spelling it.** The Bash filename
  check stripped quotes but not globs: `rm .approval-gat?` and
  `echo UNLOCKED > .approval*` were allowed while UNLOCKED, letting the model
  delete its own gate and disarm it for every phase after. Glob-carrying tokens are
  now `fnmatch`ed against the gate name — only tokens starting with a literal dot,
  mirroring the shell's own dotfile rule, so everyday globs like `rm *.pyc` are not
  denied for it. (The check stays best-effort by nature; what makes the lock hold
  is still that no Bash runs while LOCKED.)
- **Evidence opening with `<` was refused as the template placeholder.** `<200ms
  p99 measured via wrk` is real cited proof, but `is_unfilled()` treated any value
  starting with `<` as the blank — a false block at the exact moment the turn tried
  to yield for approval. A placeholder is now a value still ENTIRELY wrapped in
  `<...>`; the template's own blanks (including the long Evidence one, whose prose
  contains a `->`) still block.

## [0.8.0] - 2026-07-22

Two complaints from running 0.7.0: the designs came back over-built, and small
changes ran the machinery of large ones. Same root cause — every role in the
workflow was rewarded for adding, and nobody was paid to cut.

### Added
- **Plan guard (`hooks/plan_guard.py`) — the anti-bloat rules are now ENFORCED, not
  just advised.** Everything above is prompt text, and prompt text kept losing to the
  model's instinct to split work and keep reviewing. A `Stop` hook now refuses to end
  a turn when a drafted `plan.md` leaves `## Size estimate` at the placeholder, when a
  phase after the first carries no `- Why separate:` reason, or when a phase-log
  records more than 2 review rounds with an empty `- Unresolved:`.
  No hook can judge whether four phases were warranted — a hook that tried would block
  good plans. It checks that the justification EXISTS: "because it is a separate step"
  passes. What it removes is the SILENT split and the silently-blown budget, which
  nobody can review. Silent until a phase has a real `- Scope:` (a scaffolded plan is
  not a plan, and Stages 0.5–2 legitimately write none), fail-open, and bounded like
  the evidence gate — it gives up loudly after 3 refusals rather than trap a turn.
- **The guard also keeps `project-map.md` alive.** Nothing forced the map to be
  updated — and the anti-bloat work above made that worse, not better: single-phase
  features skip Stage 5, Stage 5 is the only stage that maintains the map, and phases
  now have to earn themselves, so single-phase is the common case. The map would have
  rotted fastest on the commonest path. A finished feature (every section approved),
  in a project that has a map, must now carry a `- Project map updated:` line on its
  LAST section — anywhere else and an early phase could answer "no structural change"
  for work a later phase did. `"no structural change"` is a complete answer; silence
  is not. 25 tests, including the shipped templates passing their own guard both
  empty and filled.
- **Stage 0.5 — the requirements conversation, before anything is delegated.** The
  orchestrator now plays analyst: restate the request concretely, write acceptance
  criteria, surface conflicts with what the code already does, and ask — in ONE
  batched round — only the questions whose answers fork the design, stating
  assumptions in writing for everything else. Deliberately not a subagent: a
  subagent cannot stop to ask, so it would pick a reading silently, and a plan built
  on a wrong reading passes every review in this workflow, because reviewers check
  the code against the plan and never the plan against what was wanted.
- **Acceptance criteria actually exist now** (`spec.md` section 1b), plus a section
  1c recording what was asked, answered, and assumed. The evidence ledger already
  demanded "one artifact per acceptance criterion" and `plan.md` had a per-phase
  `Done when:` — but nothing in the workflow ever wrote the criteria down, so both
  pointed at nothing. They now flow from 1b into each phase's `Done when:`, into
  `plan-reviewer`'s new coverage check (a criterion no phase delivers is a missing
  phase; a phase serving no criterion is scope creep), and into the ledger.

### Changed
- **The machinery is now sized to the diff, not to the description.** The
  orchestrator estimates files and rough lines BEFORE picking a tier and says the
  estimate out loud; **a feature is trivial by default** and moving up a tier
  requires naming the signal that puts it there (a new interface, new persistent
  state, a boundary crossed). Each tier now states exactly what runs, so "standard"
  can't quietly mean "everything".
- **The tier is re-checked after the plan is drafted** — the first point where the
  size is real rather than guessed — and downgrading needs no permission: collapse
  the phases, drop the stages the lighter tier doesn't run, tell the user. Upgrading
  does need a named reason. The plan checkpoint now leads with tier, phase count and
  estimated size, so the user can reject the shape before paying for it.
- **Phase counts start at ONE and every extra phase must be justified** — it crosses
  a subsystem boundary, it needs its own rollback point, or it is too big to review
  in one sitting. The old "typically 2–5 phases for standard" guidance was an anchor
  that produced three phases for twenty-line changes; there is deliberately no target
  count now, because a range reads as a quota to fill.
- **`plan-reviewer` reviews in both directions.** It hunted only for what was
  missing, which made it a force for more work in a workflow that already had one.
  Over-engineering is now a first-class finding alongside missing work — speculative
  abstraction, config nobody will change, unrelated refactors and docs that crept in
  — and "merge these phases" / "this phase doesn't need to exist" / "this plan is too
  heavy for what it delivers" are recommendations it is expected to make. It checks
  the plan against the Simplicity contract, which binds the plan and not just code.
- **Architects must stay proportional and report size.** An angle is a lens, not a
  licence to grow the change: an option that solves a problem this project doesn't
  have is a losing option even from its own angle, and an architect with nothing to
  add at this size should say so rather than manufacture a difference. Every option
  now reports files + rough lines and how much of it is NEW structure, and that lands
  as a **Size column in the comparison table**, so bloat is visible at the moment the
  user chooses instead of three phases later.
- **External research is a separate switch from the codebase survey.** The survey is
  cheap and nearly always worth it; a web round-trip is only worth it when there is a
  real external question (unfamiliar protocol, domain rule with a standard answer,
  library choice, known-pitfall area). Adding a field to a response has none, and
  `domain-researcher` now returns survey-only when told to.
- **The templates stopped anchoring the plan up.** `plan.md` carried its own
  "typically 2–5 phases" line and scaffolded three empty phase blocks — the skill
  can say "start from one" all it likes while the file copied into every feature
  hands the model three slots to fill. It now scaffolds ONE phase, states the
  earn-your-phase rule, and carries a `Size estimate` section so an over-built plan
  is visible before approval. `phase-log.md` likewise scaffolds one phase section,
  not two.

### Fixed
- **Stage 5 was skipped on the wrong condition.** Its header said "trivial +
  single-phase" while the tier table said a standard feature that ends up one phase
  skips it too. A standard single-phase feature therefore either ran a cross-phase
  review with no cross-phase to review, or left an unticked `## Final review`
  section — which `status.py` reports as the current phase forever, so the feature
  never reads as done. One rule now, in the skill, the tier table and the template:
  **skip when the feature is a single phase, in any tier.**
- The sizing rules sat physically before the stage they depend on (you cannot size a
  request you have not pinned down), and are now Stage 0.8, after the clarify stage.
- Stage 4 now records `- Deferred nits:` — the field existed in the template with no
  instruction that ever filled it.
- `security-scan-fast` says whether each finding BLOCKS the phase, so its
  Critical/High/Medium/Low severities map onto the BLOCKING/NIT vocabulary the review
  round budget is actually spent on.
- **Plans cover the change, not a project.** Migrations, config, flags, docs,
  monitoring and refactors of code that happened to be read do not get a phase unless
  the feature cannot work without them — they go to the user as a suggestion or into
  `spec.md` non-goals.

## [0.7.0] - 2026-07-22

Two gaps that showed up in real runs: agents that didn't know what the project
already contained, and a review loop with no way to end.

### Added
- **`project-map.md` — the project's own knowledge file.** `conventions.md` says
  how code is written here; the map says what already EXISTS and where: module map,
  shipped features, shared building blocks, extension points, known gotchas,
  glossary. `/dev-workflow:init` drafts it alongside `conventions.md` (both go to
  the user for confirmation), `domain-researcher` verifies it against the code and
  reports stale entries — **the code wins when they disagree** — and Stage 5 appends
  each shipped feature, so project knowledge accumulates instead of being re-derived
  every feature. It is read LAZILY (orchestrator while researching/planning; the
  coder as inline excerpts for the module it touches), which is what keeps
  `conventions.md` free to stay under its ~50-line budget.
- **The existing-implementation survey.** `domain-researcher` now returns what this
  codebase already has for the requested feature — closest implementations at
  `path:line`, what to reuse, what would be duplicated — into `spec.md` section 2b.
  The architect panel, the plan and `plan-reviewer` all work from it, so "we already
  have this" surfaces before code is written, not in review. The trivial tier skips
  the researcher but not the survey.
- **`project-map.md` is a workflow doc to the approval gate**, so Stage 5's knowledge
  update isn't blocked at the one moment it is written — the final checkpoint, with
  the gate `LOCKED`.
- **Ordinary chat sees the map too.** `init` adds a pointer to `project-map.md` in
  `CLAUDE.md` — deliberately a pointer, not an `@`-import: importing it would load
  the whole map into every session (the standing cost the lazy-read design avoids)
  to answer a question most turns never ask. `conventions.md` stays `@`-imported,
  because rules apply to every turn and a map does not.

### Changed
- **Review loops are bounded at 2 fix rounds, then the user arbitrates.** The loop
  was "if reviewers found issues, have coder fix them, then re-review" — no exit
  condition, so coder and reviewer could argue until the context ran out. Now:
  re-reviews are delta-scoped to the previous findings plus the fix diff (not the
  phase again); findings are labelled BLOCKING or NIT and only BLOCKING ones can
  spend a round; the same finding is never sent back unchanged. Applies to the phase
  review, the Stage 3 plan review, and the Stage 5 audit.
- **The coder may dissent.** It answers a finding it believes is wrong with evidence
  (`file:line`, the covering test) instead of editing to make it go away, and returns
  FIXED / DISAGREE / NEEDS-DECISION per finding. Complying with a mistaken review
  puts a real defect in the code — that is the cost the round budget was hiding.
- **Deadlocks escalate to the user instead of being ticked away.** Budget exhausted
  with a blocking finding open → stop, present the finding, the rebuttal and a
  recommendation via `AskUserQuestion`. `[x] code-reviewed` now means resolved — by
  fix, by an accepted rebuttal, or by the user's explicit call — never "we ran out of
  rounds". An unresolved security finding always goes to the user, and to Stage 5.
- **`phase-log.md` records the argument**: `- Review rounds: N/2`, `- Unresolved:`,
  `- Deferred nits:`, and `- Project map updated:` in the final section. Prose lines,
  not parsed by the hooks — they exist so you can see how contested a phase was
  before approving it.

## [0.6.2] - 2026-07-14

Closes an independent audit of 0.6.1. Every finding was reproduced by running the
hooks (not by reading them) and each fix was reviewed by a fresh agent; the fixes
carry red-first tests. No behavior a correct 0.6.1 workflow relied on is removed.

### Fixed
- **The approval gate now blocks Bash while `LOCKED`.** `coder` has Bash, and a
  here-doc / `sed -i` / `python -c` wrote source behind the lock — the gate only
  covered the edit tools. A denylist of write constructs cannot be closed, so while
  `LOCKED` **all** Bash is denied (the coder runs tests/lint while `UNLOCKED`). Shell
  quoting like `.approval-gat"e"` can no longer smuggle the gate file past the check.
- **`rollback` no longer destroys `.dev-workflow/`.** A repo that commits its workflow
  docs lost its phase log — and the Evidence ledger written that phase — because
  `git read-tree --reset` deletes tracked paths absent from the snapshot, and
  snapshots exclude `.dev-workflow/`. It is now preserved across a rollback exactly as
  `.approval-gate` already was; `undo` recovers cleanly.
- **The evidence gate blocks more than once.** It trusted `stop_hook_active`, so
  block once → change nothing → stop again let an empty ledger through. It now refuses
  up to three times per phase, then yields **loudly** (never silently) so it can't trap
  a turn. The give-up bound survives a read-only `.dev-workflow/`, and the counter is
  per phase so concurrent features don't reset each other.
- **`## Final Review` (any capitalization) is parsed as a section.** The heading match
  was case-sensitive, so a capital `R` absorbed the section into the phase above it and
  marked the wrong phase approved. `USER APPROVED` stays case-sensitive on purpose, so
  incidental lowercase prose can't wave an unproven phase through.
- **Evidence written as sub-bullets counts.** The empty-ledger check mistook the
  ledger's own indented bullets for its terminator, so real cited proof read as empty.
- **Hooks invoke `python3`, not `python`.** On a stock Linux/macOS box there is no
  `python`, so every hook silently failed to launch — no gate, no checkpoints, no
  evidence gate. The plugin validator now fails if a hook ever names `python` again.
- The per-phase security scan is stated honestly as **surface-gated** (auth, input
  handling, crypto/secrets, data access, external I/O), not tier-gated; the README,
  `plugin.json`, and flow diagram no longer claim "security review at every step". The
  evidence gate is described as raising a floor, not verifying that the proof is true.
- The `code-reviewer` now carries the clean-code baseline inline instead of pointing at
  a plugin-relative path it cannot open from the user's project, so it and `coder`
  enforce the same baseline.
- `rollback`'s `undo` is no longer pre-approved in `allowed-tools` — it is itself a
  rollback that rewrites the working tree, so it gets the same confirmation.

### Changed
- The phase-log checkboxes are machine-parsed, so the feature skill, `coder`, and the
  template now state which literal strings the hooks read, who ticks each, and when —
  and that `coder` must never tick a review box or `USER APPROVED`.

**Updating** takes two steps — the first refreshes the catalog, the second pulls the
new code (the catalog refresh alone leaves your installed copy on 0.6.1):
```
/plugin marketplace update dev-workflow-marketplace
/plugin update dev-workflow@dev-workflow-marketplace
```

## [0.6.1] - 2026-07-14

### Removed
- **0.6.0 is withdrawn. This release reverts it to 0.5.0's behavior.** Do not run
  0.6.0. It added a Stop-hook "verify" check that executed the lint/test commands
  declared in the project's `conventions.md`, plus a "scope" check comparing the
  changed files against `plan.md`'s `- Files:`. An audit found three defects, two
  of them serious:
  - **Privilege escalation.** `hooks/gate.py` deliberately keeps `conventions.md`
    writable by the model even while the approval gate says `LOCKED`. The verify
    check shell-executed that same file's ```verify``` block — so the model could
    write `test: echo UNLOCKED > .approval-gate` and have another hook unlock the
    approval gate for it, with no tool call and no permission prompt. The same path
    gave arbitrary command execution outside Bash permissioning. The gate that only
    the user is supposed to be able to flip was flippable by the model.
  - **False blocks from Phase 2 onward.** The scope check diffed against `HEAD`,
    which is cumulative since the last commit — and per-phase commits are optional.
    So a phase that touched exactly the files it declared was still blocked over the
    previous, already-approved phase's uncommitted files, and the block message told
    the orchestrator to revert them. The test suite asserted this behavior as correct.
  - `lstrip("./")` is a character-set strip, so any dotfile declared in `- Files:`
    (`.github/workflows/ci.yml`, `.eslintrc.json`) lost its leading dot and was
    reported as scope creep.

  A verify gate is still the right idea — the evidence ledger is only a length check,
  so "ran tests, all pass" passes it today without anything having run. It will
  return reading its commands from a file the model cannot write.

## [0.5.0] - 2026-07-14

### Added
- **`conventions.md` now reaches ordinary chat, not just `/dev-workflow:*`.**
  Claude Code auto-loads only `CLAUDE.md` and its `@`-imports, so a plain chat
  session never saw `conventions.md` — only the plugin's skills and subagents,
  which Read it explicitly, did. `/dev-workflow:init` now also ensures
  `CLAUDE.md` imports it via an `@conventions.md` line (appending to an existing
  `CLAUDE.md`, or offering to create a minimal one), and tells you to restart any
  running session, since `CLAUDE.md` is loaded once at session start.

### Changed
- **Comment discipline is now enforceable, not just implied.** The baseline said
  only "comments explain WHY, not WHAT", which caught the wrong failure mode: it
  never stopped comments that narrate the diff, justify the change to the
  reviewer, or docstring every function in a file that has none. The
  `references/clean-code.md` rule now names those cases and requires matching the
  surrounding file's comment density; the same line ships verbatim in every
  project's Simplicity contract; and `code-reviewer` gained comment noise as an
  explicit focus area, so it actually gets flagged instead of falling through the
  generic "judge against the baseline" instruction.

## [0.4.0] - 2026-07-08

### Added
- **Simplicity contract in every project's `conventions.md`.** `/dev-workflow:init`
  now writes a fixed, always-on section of anti-over-engineering rules — build only
  what the task requires, no abstraction until a real third use, match existing
  patterns, handle only errors that can actually occur, and stop-and-ask before
  adding anything beyond the literal request. It ships verbatim in both the
  observed-project and greenfield paths and is never rephrased or softened.
- **`/dev-workflow:init` now surfaces model routing.** After writing
  `conventions.md`, init points you to the three ways to tune models — per-agent
  `.dev-workflow/models.json` (recommended), the `CLAUDE_CODE_SUBAGENT_MODEL` env
  var, or a full `.claude/agents/<name>.md` override — so routing is discoverable
  during setup, not just in the README. Init still writes only `conventions.md`.

### Changed
- **Clean-code principles now apply to every project, not just greenfield.** The
  `references/clean-code.md` baseline was reframed from a greenfield-only tie-breaker
  into an always-on engineering floor that the `coder` and `code-reviewer` enforce in
  every project. Precedence (linter/formatter > `conventions.md` > surrounding style >
  baseline) now resolves genuine conflicts rather than gating the baseline off
  entirely, so a project's established style still wins on the style-sensitive
  principles (function size, nesting) while universal hygiene applies everywhere.

## [0.3.0] - 2026-07-07

### Added
- **Per-agent model configuration.** Drop a `.dev-workflow/models.json` mapping each
  subagent to a model (`opus`/`sonnet`/`haiku`/`fable`, a full model ID, or
  `inherit`) and the orchestrator applies it at spawn time; omitted agents keep
  their default. `CLAUDE_CODE_SUBAGENT_MODEL` (all agents) and a `.claude/agents/`
  shadow (full replace) are documented as alternatives. See `templates/models.json`.
- **Adversarial plan review.** A `plan-reviewer` subagent breaks the drafted
  `plan.md` on paper before any code — hunting missing phases, hidden dependencies,
  oversized or untestable phases, ordering mistakes, and rollback gaps.
- **Automated hook test suite in CI.** 35 tests exercise the approval gate, evidence
  gate, checkpoint/rollback engine, and status readout exactly as Claude Code runs
  them, so the reliability backbone is regression-guarded.

### Changed
- **Lower token usage across the feature workflow.** One `coder` is reused across a
  feature's phases (continued, not respawned) so codebase intake is paid once, not
  per phase; the orchestrator hands the coder and reviewers the exact files/paths to
  touch instead of making them re-scan; and `conventions.md` is kept lean because
  every subagent re-reads it in full.
- **Per-phase security scan is gated by surface, not tier.** `security-scan-fast`
  runs whenever a phase touches a security-sensitive surface (auth/authz, input
  handling, crypto/secrets, data access, external I/O) in any tier — and is skipped
  for non-sensitive phases even in complex features.
- **Tighter Stage 3 planning.** Phases are right-sized (coherent, independently
  reviewable units), ordered by dependency then risk, and each names its evidence
  and a rollback point.
- README redesigned with a Mermaid flowchart, and the intro keyword-optimized for
  discoverability.
- _Internal:_ phase-log parsing consolidated into a single shared module so the
  SessionStart status hook and the Stop evidence gate can no longer drift apart.

### Fixed
- Checkpoints now work in a repository with no configured git identity (a fresh
  `git init` or a CI runner). Previously `git commit-tree` failed and the snapshot
  silently no-opped; the shadow-ref commits now carry a stable internal identity.

## [0.2.0] - 2026-07-02

### Added
- Checkpoint + rollback via git shadow refs (never touches your index/HEAD/branch),
  an evidence gate that requires cited proof before a phase is marked done, and
  workflow-state re-injection so the active feature/phase/gate survive `/compact`.
