# Guards and hooks: how each one works

The details behind the table in the [README](../README.md#guards). Every hook fails open: one that errors never blocks your work.

## Approval gate

A `PreToolUse` hook (`hooks/gate.py`) blocks `Edit`/`Write`/`MultiEdit`/`NotebookEdit` on source code **and all of `Bash`** while a `.approval-gate` file at your project root says `LOCKED`. Opt-in — does nothing until the file exists.

- Working docs (`spec.md`, `plan.md`, `phase-log.md`, `conventions.md`, anything under `.dev-workflow/`) stay editable while locked, so the log can still be maintained.
- **Bash is denied outright while locked** — not filtered. `coder` has Bash, and a denylist of write constructs cannot be closed: `sed -i`, here-docs, `patch`, `git checkout` and any interpreter with `-c` all write files. Rather than pretend to catch them, the gate runs none of them. This costs nothing, because `LOCKED` means *"stop, the phase is waiting on you"* — the coder runs its tests and lint while unlocked.
- **Only you can unlock**, from your own shell — Claude can't. The edit tools can't write `.approval-gate`, and Bash referring to it is refused (quoting like `.approval-gat"e"` and globs like `rm .approval*` are caught too — though the Bash filename check is best-effort, not a hard barrier; what makes the lock hold is that **no** Bash runs while locked). A rollback can't flip it either: gate state is preserved and never snapshotted.

```shell
! echo LOCKED > .approval-gate      # activate + lock
! echo UNLOCKED > .approval-gate    # after approving a phase
```

The `!` prefix runs in *your* shell, so it isn't a Claude tool call the hook can intercept.

## Checkpoints & rollback

In a git repo, a `PreToolUse` hook (`hooks/checkpoint.py`) snapshots the working tree before every mutating tool call to a shadow ref `refs/dev-workflow/checkpoints/<ts>` — via git plumbing on a temp index, so it **never touches your index / HEAD / branch / worktree**. Fail-open, with a timeout.

- `/dev-workflow:rollback list` — list snapshots (newest first).
- `/dev-workflow:rollback [ref]` — restore to a checkpoint (default: latest). It first saves current state as a reversible `pre-rollback` checkpoint (`undo` reverses it); never moves your branch, never hard-deletes.

Rollback restores tracked *content*; files created since are left in place (they show in `git status`).

**Limits:** git only · refs are local (not pushed) · snapshots respect `.gitignore`, so keep secrets ignored.

**Retention:** each new snapshot deletes checkpoints older than 14 days. Set `DEV_WORKFLOW_CHECKPOINT_KEEP_DAYS` to another number of days, or `0` to keep everything; `checkpoint.py prune [days]` prunes on demand. Ship points (`refs/dev-workflow/shipped/`) are never pruned.

## Evidence gate

Completion checkpoints ask for *cited proof*. Each phase's `phase-log.md` has an `- Evidence:` ledger to fill with concrete artifacts — test/command output, `file:line` references, the cases verified — one per acceptance criterion. Review subagents back every verdict with what they actually checked.

A `Stop` hook (`hooks/evidence_guard.py`) enforces it: end a turn with the current phase marked `[x] code-reviewed` but its Evidence ledger empty, and it blocks and asks for proof — and it keeps blocking if you stop again without filling it. Fail-open, silent unless a phase-log is active.

**What the hook can and cannot check.** It verifies the ledger *exists and is not a placeholder or a scrap* — it cannot judge whether what you wrote is true. "Everything looks fine" is long enough to pass the hook; it is the `coder` and reviewer prompts, and your own eyes at the approval gate, that make the evidence real. The hook raises the floor; it is not a proof checker.

To stop it from hard-locking a turn, it gives up after 3 consecutive blocks — and says so loudly in the message, so a phase never slips through an empty ledger *silently*.

## Plan guard

The two levers that decide how long a feature *takes* are numbers the model picks for itself: how many phases the plan has, and how many rounds a phase spends arguing with its reviewer. Prompt text alone kept losing to the instinct to split work and keep reviewing — which is how a twenty-line change grows a three-phase plan.

A `Stop` hook (`hooks/plan_guard.py`) refuses to end a turn when:

- `plan.md` has been drafted but its **`## Size estimate`** is still the placeholder — the size is what makes an over-built plan visible at the approval checkpoint.
- a plan has more than one phase and some phase after the first has no **`- Why separate:`** reason. Splitting stays allowed; splitting *silently* does not.
- a `phase-log.md` phase records more than 2 **review rounds** with an empty `- Unresolved:` — the budget was blown and nothing was escalated to you.
- a **finished** feature has no **`- Lessons:`** line — the step that turns its review findings and your corrections into rules was skipped. `"none"` is a complete answer.
- a **finished** feature never said what it did to **`project-map.md`** (only when the project has one). Stage 5 is what maintains the map, and single-phase features skip Stage 5 — which, now that phases have to earn themselves, is most of them, so the map would rot fastest on the commonest path. `"no structural change"` is a complete answer; silence is not.
- the current phase is reviewed but has no **`- Review map:`**. The code-reviewer sorts every changed hunk into `MUST` (with the question you have to answer), `SKIM` or `SKIP`, and lists every `ASSUME` (a decision the spec never made). Security surface, new branches, data writes and untested code can never go below `MUST`. The approval checkpoint opens with the map, so you read the 40 lines that matter instead of all 400. The dashboard shows the map with the code of each `MUST` range.
- the current phase's real diff is over **2× its plan `- Size:`** (minimum +40 lines) and `- Over budget:` gives no reason. The baseline is the working tree at the last turn before the phase was coded, so it works without per-phase commits.
- the phases' `- Size:` estimates add up to more than one **PR's worth** (`pr_cap` in `.dev-workflow/plan-guard.json`, default 300 lines, `0` = off) and the plan is neither cut into `## PRs` (stacked, every phase in one PR, each PR at or under the cap) nor gives an `- Over cap:` reason. While the cap is on, every phase needs a `- Size:`.

**What it can and cannot check.** No hook can judge whether four phases were warranted; that is a design opinion, and one that tried would block good plans. It checks that the justification EXISTS — "because it is a separate step" passes the hook. What it removes is the silent case, which nobody can review. You are still the one who reads the reason at the plan checkpoint and says "no, merge them".

Silent until a phase has a real `- Scope:` (the scaffolded plan is not a plan), and bounded like the evidence gate: it gives up loudly after 3 refusals rather than trap a turn.

## Workflow state & approval

Each feature's progress is a `state.json` in `.dev-workflow/features/<slug>/`. `phase-log.md` is rendered from it after every change, in the same layout as before, so you read it as you always did.

Every change goes through one command, `.dev-workflow/dw` (a launcher the plugin writes into the project):

```
dw coded 1 --changed "src/orders/list.ts"     evidence on stdin
dw round 1                                     a fix round starts
dw reviewed 1 --security                       review map on stdin
dw set 1 unresolved                            text on stdin
dw approve                                     yours: run it in your own shell
dw status · dw check
```

The command validates the step and refuses with the reason: a phase cannot be reviewed before it is coded, approved without evidence and a review map, or started before the previous one is approved. Review rounds are counted by `dw round`, not self-reported. The edit tools are refused on `state.json` and on the rendered log, with a message naming the command.

**Approval** arrives one of two ways, and the state records which:

- **Direct** — you type `/dev-workflow:approve`, run `! .dev-workflow/dw approve`, or press Mark done on the dashboard. A hook records the typed command; Claude calling the command does not reach that hook.
- **Relayed** — you approve in plain words and Claude records it with your words quoted. It is refused unless you have sent a message since the phase was reviewed, so a phase cannot be approved in the turn that reviewed it.

`/dev-workflow:config set approval.mode direct` accepts direct approvals only. That is the strict setting: Claude Code raises the same prompt event for turns it starts itself (a background agent reporting back), and the hook can only skip the ones it recognises.

**What it can and cannot do.** This is a guard, not a security boundary: Claude has a shell and can write any file you can. What it removes is the easy path, where approving meant ticking a box.

**Features started on an older version** have no `state.json` and keep working as before. `dw import <slug>` converts one that is in flight and keeps its hand-written log as `phase-log.legacy.md`. The launcher is a `sh` script, so on Windows call `python3 <plugin>/hooks/dw.py` instead.

## Learning across features

A plugin that makes the same mistake on every feature is one you end up correcting by hand. So each feature ends with a **lessons** step: the orchestrator reads what the reviews kept flagging, what you asked to change at checkpoints, and which `Suggested, not built` extras you declined, and proposes **at most three** one-line rules — each with where it came from. You tick the ones you want; they go into a `## Learned rules` section of `conventions.md`, which every agent already reads on every phase. Nothing is written without your pick, and "nothing worth a rule" is the usual outcome.

The strongest signal comes later: **what you rewrite after accepting the code**. When a feature is signed off, `checkpoint.py ship <slug>` records the tree as handed over (`refs/dev-workflow/shipped/<slug>`, never your branch). At the start of the next feature, `since-ship` diffs that against the code now; your edits to agent-written code become rule proposals the same way, and the feature is marked so it is never asked about twice.

The plan guard requires a `- Lessons:` line on a finished feature, so the step cannot be skipped silently.

## Comment guard

**Comments say WHY, in one line, where the logic is hard — nothing else.** The code is the documentation: when a line needs explaining, the fix is nearly always a clearer name, a smaller function or a named constant, and reaching for a comment instead leaves both the confusing code and a line that goes stale. On top of that, agents write comments *at the reviewer*: which acceptance criterion the line satisfies, what the code used to do, why it's correct. All of it is true on the day of the review and dead weight the moment the PR merges. The rule against it shipped in four documents and still drifted, because prose is the one enforcement layer a model can talk itself past.

A `PreToolUse` hook (`hooks/comment_guard.py`) denies the edit on three deterministic checks, all applied **only to comment lines the edit adds** — a comment merely carried through an edit's context is never blamed for it:

- **Noise patterns** — workflow artifacts (`AC-2`, `plan.md`, `Phase 3:`), diff narration (`we now…`, `Added a helper…`, `Previously this…`), reviewer-facing talk (`as requested`, `this ensures…`). Deliberately narrow: `# phase 2 of the TLS handshake` passes, `# Phase 2: wire the parser` does not.
- **Density** — an edit gets **one** comment line, or about **one per twenty** lines of code it adds, whichever is more: room for the why on hard logic, none for commenting everything. A file that already comments more grants its *own* comments-per-code ratio, so a codebase that documents heavily still gets to. The budget is never borrowed from sibling files: that is how agent-written comments used to compound, each commented file raising the allowance for the next.
- **Block length** — no added comment block may carry more than **two** lines of text, whatever the density. A paragraph is a design argument, and that belongs in the commit message.

Tool directives (`eslint-disable`, `@ts-expect-error`, `noqa`, `type: ignore`, shebangs, licence lines…) are not comments and are never counted. Python docstrings count. `.md` / `.json` / `.yaml` and everything under `.dev-workflow/` are out of scope.

**What it can and cannot check.** It catches *mechanical* shapes only — it cannot tell whether a comment earns its line, and one that tried would delete good comments. That judgement stays with `code-reviewer` and with you. Denial is safe in a way a `Stop` hook's refusal is not: deleting the comment is always an available move, so it can't trap a turn and needs no give-up bound.

Off with `DEV_WORKFLOW_COMMENT_GUARD=off`, or per-project via `.dev-workflow/comment-guard.json`. Defaults are `floor: 1`, `min_ratio: 0.05`, `max_block: 2`. A comment matching an `allow` pattern is exempt from both the noise check and the budget. To forbid comments entirely, or to lift the block cap:

```json
{ "allow": ["phase \\d of the handshake"], "density": { "floor": 0, "min_ratio": 0 }, "max_block": 0 }
```

## Test guard

The evidence gate above is the strongest incentive in the workflow: a turn cannot end without a citable artifact per acceptance criterion, and the cheapest artifact to manufacture is a new test. So criteria become tests one-for-one — including criteria that are pure declarations — and the tests come out shaped to be *cited*, not to be able to *fail*. A ledger reading `criterion 1 → x.spec.ts:123, criterion 2 → :135` is that failure mode, not rigour.

Most of the fix is prompt-side (Stage 4's "one artifact per criterion is NOT one test per criterion", the `coder`'s testing rules, `code-reviewer`'s mandate to recommend DELETING a test). A `PreToolUse` hook (`hooks/test_guard.py`) backs the two shapes that need no judgement, applied **only to test files and only to what the edit adds**:

- **Positional empty fakes** — `new Service({} as any, {} as any, model, {} as any…)`. A provider assembled by position out of blanks stops testing the code the moment a constructor parameter moves, and stays green while it does. Three or more placeholders in one call is the line; one or two is how a focused unit test stays short.
- **A test with no assertion** — it cannot fail except by throwing, so it reports a behaviour as covered while covering nothing. Named assertion helpers (`expectNetwork(…)`, or any local helper whose own body asserts) count as asserting.

**What it deliberately does NOT check:** *the test mocks the risk it claims to prove* — a `jest.fn()` counter standing in for an atomic `$inc` — which is the most damaging shape of all. Two designs were built and measured against 93 real test files: block-scoped detection missed every true positive (the fake lives in a factory outside the block), and file-scoped detection ran at roughly half false positives, because the claim lives in English — "a unique payer+amount candidate" is an in-process statement wearing a store guarantee's words, and a fake that *throws* is the only way to reach a driver error like E11000 at all. That judgement needs the subject read next to the test, so it belongs to `code-reviewer` and to the Testing contract in `conventions.md`.

Off with `DEV_WORKFLOW_TEST_GUARD=off`, or per-project via `.dev-workflow/test-guard.json`:

```json
{ "enabled": true, "checks": { "fakes": true, "assertions": true }, "max_empty_args": 3, "allow": ["legacy fixture"] }
```

## Config readout

Every guard here fails *quietly* by design: `comment_guard`, `test_guard` and the feature skill's read of `models.json` all swallow a parse error and carry on with defaults, because a malformed preference must never crash an edit or trap a turn. The cost is that a stray comma disables nothing, warns nobody, and leaves the project believing it configured something.

`/dev-workflow:config` is the readout that closes that hole. It reports every knob's **effective** value and, next to it, **where the value came from** — `default`, `file`, `env <VAR>`, or `file, IGNORED` for a key that was written and changed nothing (a wrong type, a regex that will not compile). A `PROBLEMS` block leads when a file is being ignored in full, when a key is misspelled past recognition, or when `DEV_WORKFLOW_*_GUARD` is set and no file can override it.

It never restates a default: `hooks/config.py` imports the guards and reads their own constants and their own `load_config`, and scrapes agent names and default models from `agents/*.md` frontmatter — so a report that disagrees with the running hook is not constructible.

`config set <key> <value>` writes one key and prunes anything equal to its default, keeping each file a diff against the plugin rather than a frozen copy of it. It refuses to write over a file it cannot parse.

```
/dev-workflow:config
/dev-workflow:config set comment-guard.density.floor 4
/dev-workflow:config set models.coder sonnet
/dev-workflow:config set test-guard.checks.fakes default
```

`.approval-gate` and `.dev-workflow/active` show up under *workflow state*, not configuration — the gate is yours alone, and no tool call here can move it.

## Context re-injection

A `SessionStart` hook (`hooks/status.py`) re-surfaces the active feature, phase progress, and gate state at every session start — **including after `/compact` or auto-compaction** (it fires with `source: "compact"` and adds a "context was just compacted — re-read the files" reminder). This keeps the file-based source of truth (`spec.md` / `plan.md` / `phase-log.md`) from being lost to context rot.
