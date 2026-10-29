# 🛠️ dev-workflow

**A Claude Code plugin for spec-driven development — research, plan, then build each feature in reviewed phases, with AI code review every phase, a security scan on every phase that touches a sensitive surface, and a final cross-phase security audit. Domain-agnostic, review-gated, safe by default.**

Every feature runs the same disciplined gauntlet — and *you* are the final boss at every gate:

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/micahhype/dev-workflow/main/assets/flow-dark.svg">
    <img alt="The feature gauntlet: detect conventions → research → solution options panel → phased plan → per-phase loop (build → AI code review, plus a security scan when the phase touches a sensitive surface → you approve) → final cross-phase audit → ship it" src="https://raw.githubusercontent.com/micahhype/dev-workflow/main/assets/flow-light.svg" width="460">
  </picture>
</p>

> Pair programming, except your pair is six robots who *actually read the spec* — and you still hold the almighty **“nope.”**

The domain isn't hardcoded — it's read from your `conventions.md` (via `/dev-workflow:init`) or inferred per feature from the code.

## Install

```shell
/plugin marketplace add micahhype/dev-workflow
/plugin install dev-workflow@dev-workflow-marketplace
```

> Update later (two steps — refresh the catalog, then pull the new code):
> ```shell
> /plugin marketplace update dev-workflow-marketplace
> /plugin update dev-workflow@dev-workflow-marketplace
> ```
> See the [changelog](CHANGELOG.md) for what's new.

## Quick start

```shell
/dev-workflow:init                       # (optional) learn the repo → conventions.md + project-map.md
/dev-workflow:feature add pagination to the orders endpoint
/dev-workflow:feature --bug the orders endpoint 500s on an empty cart
/dev-workflow:status                     # where am I?  (also auto-injected each session)
```

Working docs scaffold automatically under `.dev-workflow/features/<slug>/`; multiple features can run at once (`.dev-workflow/active` names the current one).

## What's inside

**Commands & skills**

| Command | Purpose |
|---------|---------|
| `/dev-workflow:init` | Inspect the project, draft `conventions.md` + `project-map.md`, import conventions from `CLAUDE.md` |
| `/dev-workflow:feature` | Drive the whole feature workflow (orchestrator). `--bug` swaps the front end for reproduce → root cause → regression |
| `/dev-workflow:status` | Readout of the active feature / phase / gate |
| `/dev-workflow:config` | Effective settings, where each came from, and which config lines are silently doing nothing |
| `/dev-workflow:dashboard` | Local web board (127.0.0.1) of all projects: each feature's progress, the ones waiting for your approval first; phases, evidence, plan, spec, checkpoints and config on click; refreshes itself. Its only write: a guarded Mark done button |
| `python3 <plugin>/hooks/mark_done.py <root> <slug>` | Tick every open phase of a feature you already finished as approved — or use the **Mark done** button in the dashboard drawer. The CLI refuses inside Claude Code; run it in your own terminal |
| `python3 <plugin>/scripts/subagent_traces.py [ROOT]` | Read your Claude Code subagent transcripts (default `~/.claude/projects`) into `traces.jsonl` and print tokens and time per agent type, where each agent's time goes per task (model, test, lint, read, edit) and the slowest tasks, plus which agents run together in one feature |
| `/dev-workflow:checkpoints` | List auto-snapshots |
| `/dev-workflow:rollback` | Restore to a checkpoint (safe, reversible) |

**Subagents** — Opus wherever the job is judgement (designing, surveying what exists, writing and reviewing code, the final audit). These are **defaults you can override per agent** (see below).

| Agent | Default model | Role |
|-------|---------------|------|
| `domain-researcher` | `opus` | Domain/stack research (read-only + web) |
| `solution-architect` | `opus` | One solution option per angle (panel) |
| `plan-reviewer` | inherit | Adversarial plan review before coding |
| `coder` | `opus` | Implement one phase (standard/complex tiers) |
| `code-reviewer` | `opus` | Logic/quality review, plus a security pass on sensitive surfaces |
| `security-audit` | `opus` | Deep final cross-phase audit |

Defaults are **aliases**, so each agent runs the newest model of its family without a plugin update. Want a fixed version (reproducible cost and behaviour)? Pin a full model ID per agent in `.dev-workflow/models.json`, below.

**Pick your own models** — three ways, no plugin edits (which get overwritten on update):

1. **Per agent** (recommended) — drop a `.dev-workflow/models.json` mapping agent → model; the orchestrator applies it at spawn time. Omitted agents keep their default. Copy the plugin's `templates/models.json` to start:
   ```json
   { "coder": "sonnet", "security-audit": "opus" }
   ```
   Values take aliases (`opus`/`sonnet`/`haiku`/`fable`), full model IDs, or `inherit` (use your session's model). This keeps each agent's tuned prompt — only the model changes. (`.dev-workflow/` is gitignored, so this is per-developer; un-ignore the file if you want to commit a team-wide policy.)
2. **All agents at once** — set `CLAUDE_CODE_SUBAGENT_MODEL=<model>` before launching; every subagent uses it. Blunt but zero-config.
3. **Fully replace an agent** — put a `.claude/agents/<name>.md` in your project (it shadows the plugin's). Use this to change the *prompt* too, not just the model — you take over its whole definition.

## Safety & reliability

Five hooks make the workflow *trustworthy*, not just well-behaved. All fail open — a hook that errors never blocks your work.

| | Gives you |
|---|---|
| 🔒 **Approval gate** | A `LOCKED` gate only *you* can flip: while locked, Claude cannot edit source or run Bash |
| 💾 **Checkpoints + rollback** | Auto git snapshots before every edit; safe reversible restore |
| 🧾 **Evidence gate** | "Done" must cite proof — an empty ledger is refused |
| 📏 **Plan guard** | Extra phases and blown review budgets must be justified in writing, not chosen silently |
| ♻️ **Context re-injection** | Workflow state survives `/compact` |

Four of the five stay silent when no workflow is active. **Checkpoints are the exception**: in any git repo, the checkpoint hook snapshots before every `Edit`/`Write`/`MultiEdit`/`NotebookEdit`/`Bash` whether or not a dev-workflow feature is running. It writes only to its own shadow refs — never your index, HEAD, branch, or worktree — but it is not side-effect-free, and the refs are not pruned automatically (see the v1 limits below).

<details>
<summary><b>🔒 Approval gate</b> — how it works</summary>

<br>A `PreToolUse` hook (`hooks/gate.py`) blocks `Edit`/`Write`/`MultiEdit`/`NotebookEdit` on source code **and all of `Bash`** while a `.approval-gate` file at your project root says `LOCKED`. Opt-in — does nothing until the file exists.

- Working docs (`spec.md`, `plan.md`, `phase-log.md`, `conventions.md`, anything under `.dev-workflow/`) stay editable while locked, so the log can still be maintained.
- **Bash is denied outright while locked** — not filtered. `coder` has Bash, and a denylist of write constructs cannot be closed: `sed -i`, here-docs, `patch`, `git checkout` and any interpreter with `-c` all write files. Rather than pretend to catch them, the gate runs none of them. This costs nothing, because `LOCKED` means *"stop, the phase is waiting on you"* — the coder runs its tests and lint while unlocked.
- **Only you can unlock**, from your own shell — Claude can't. The edit tools can't write `.approval-gate`, and Bash referring to it is refused (quoting like `.approval-gat"e"` and globs like `rm .approval*` are caught too — though the Bash filename check is best-effort, not a hard barrier; what makes the lock hold is that **no** Bash runs while locked). A rollback can't flip it either: gate state is preserved and never snapshotted.

```shell
! echo LOCKED > .approval-gate      # activate + lock
! echo UNLOCKED > .approval-gate    # after approving a phase
```

The `!` prefix runs in *your* shell, so it isn't a Claude tool call the hook can intercept.
</details>

<details>
<summary><b>💾 Checkpoints & rollback</b> — how it works</summary>

<br>In a git repo, a `PreToolUse` hook (`hooks/checkpoint.py`) snapshots the working tree before every mutating tool call to a shadow ref `refs/dev-workflow/checkpoints/<ts>` — via git plumbing on a temp index, so it **never touches your index / HEAD / branch / worktree**. Fail-open, with a timeout.

- `/dev-workflow:checkpoints` — list snapshots (newest first).
- `/dev-workflow:rollback [ref]` — restore to a checkpoint (default: latest). It first saves current state as a reversible `pre-rollback` checkpoint (`undo` reverses it); never moves your branch, never hard-deletes.

Rollback restores tracked *content*; files created since are left in place (they show in `git status`).

**v1 limits:** git only · no auto-pruning — refs are local (not pushed); prune with
`git for-each-ref --format='delete %(refname)' refs/dev-workflow | git update-ref --stdin` · snapshots respect `.gitignore`, so keep secrets ignored.
</details>

<details>
<summary><b>🧾 Evidence gate</b> — how it works</summary>

<br>Completion checkpoints ask for *cited proof*. Each phase's `phase-log.md` has an `- Evidence:` ledger to fill with concrete artifacts — test/command output, `file:line` references, the cases verified — one per acceptance criterion. Review subagents back every verdict with what they actually checked.

A `Stop` hook (`hooks/evidence_guard.py`) enforces it: end a turn with the current phase marked `[x] code-reviewed` but its Evidence ledger empty, and it blocks and asks for proof — and it keeps blocking if you stop again without filling it. Fail-open, silent unless a phase-log is active.

**What the hook can and cannot check.** It verifies the ledger *exists and is not a placeholder or a scrap* — it cannot judge whether what you wrote is true. "Everything looks fine" is long enough to pass the hook; it is the `coder` and reviewer prompts, and your own eyes at the approval gate, that make the evidence real. The hook raises the floor; it is not a proof checker.

To stop it from hard-locking a turn, it gives up after 3 consecutive blocks — and says so loudly in the message, so a phase never slips through an empty ledger *silently*.
</details>

<details>
<summary><b>📏 Plan guard</b> — how it works</summary>

<br>The two levers that decide how long a feature *takes* are numbers the model picks for itself: how many phases the plan has, and how many rounds a phase spends arguing with its reviewer. Prompt text alone kept losing to the instinct to split work and keep reviewing — which is how a twenty-line change grows a three-phase plan.

A `Stop` hook (`hooks/plan_guard.py`) refuses to end a turn when:

- `plan.md` has been drafted but its **`## Size estimate`** is still the placeholder — the size is what makes an over-built plan visible at the approval checkpoint.
- a plan has more than one phase and some phase after the first has no **`- Why separate:`** reason. Splitting stays allowed; splitting *silently* does not.
- a `phase-log.md` phase records more than 2 **review rounds** with an empty `- Unresolved:` — the budget was blown and nothing was escalated to you.
- a **finished** feature has no **`- Lessons:`** line — the step that turns its review findings and your corrections into rules was skipped. `"none"` is a complete answer.
- a **finished** feature never said what it did to **`project-map.md`** (only when the project has one). Stage 5 is what maintains the map, and single-phase features skip Stage 5 — which, now that phases have to earn themselves, is most of them, so the map would rot fastest on the commonest path. `"no structural change"` is a complete answer; silence is not.
- the current phase is reviewed but has no **`- Review map:`**. The code-reviewer sorts every changed hunk into `MUST` (with the question you have to answer), `SKIM` or `SKIP`, and lists every `ASSUME` (a decision the spec never made). Security surface, new branches, data writes and untested code can never go below `MUST`. The approval checkpoint opens with the map, so you read the 40 lines that matter instead of all 400. The dashboard shows the map with the code of each `MUST` range.
- the current phase's real diff is over **2× its plan `- Size:`** (minimum +40 lines) and `- Over budget:` gives no reason. The baseline is the working tree at the last turn before the phase was coded, so it works without per-phase commits.

**What it can and cannot check.** No hook can judge whether four phases were warranted; that is a design opinion, and one that tried would block good plans. It checks that the justification EXISTS — "because it is a separate step" passes the hook. What it removes is the silent case, which nobody can review. You are still the one who reads the reason at the plan checkpoint and says "no, merge them".

Silent until a phase has a real `- Scope:` (the scaffolded plan is not a plan), and bounded like the evidence gate: it gives up loudly after 3 refusals rather than trap a turn.
</details>

<details>
<summary><b>📚 Learning across features</b> — how it works</summary>

<br>A plugin that makes the same mistake on every feature is one you end up correcting by hand. So each feature ends with a **lessons** step: the orchestrator reads what the reviews kept flagging, what you asked to change at checkpoints, and which `Suggested, not built` extras you declined, and proposes **at most three** one-line rules — each with where it came from. You tick the ones you want; they go into a `## Learned rules` section of `conventions.md`, which every agent already reads on every phase. Nothing is written without your pick, and "nothing worth a rule" is the usual outcome.

The strongest signal comes later: **what you rewrite after accepting the code**. When a feature is signed off, `checkpoint.py ship <slug>` records the tree as handed over (`refs/dev-workflow/shipped/<slug>`, never your branch). At the start of the next feature, `since-ship` diffs that against the code now; your edits to agent-written code become rule proposals the same way, and the feature is marked so it is never asked about twice.

The plan guard requires a `- Lessons:` line on a finished feature, so the step cannot be skipped silently.
</details>

<details>
<summary><b>💬 Comment guard</b> — how it works</summary>

<br>**Comments say WHY, in one line, where the logic is hard — nothing else.** The code is the documentation: when a line needs explaining, the fix is nearly always a clearer name, a smaller function or a named constant, and reaching for a comment instead leaves both the confusing code and a line that goes stale. On top of that, agents write comments *at the reviewer*: which acceptance criterion the line satisfies, what the code used to do, why it's correct. All of it is true on the day of the review and dead weight the moment the PR merges. The rule against it shipped in four documents and still drifted, because prose is the one enforcement layer a model can talk itself past.

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
</details>

<details>
<summary><b>🧪 Test guard</b> — how it works</summary>

<br>The evidence gate above is the strongest incentive in the workflow: a turn cannot end without a citable artifact per acceptance criterion, and the cheapest artifact to manufacture is a new test. So criteria become tests one-for-one — including criteria that are pure declarations — and the tests come out shaped to be *cited*, not to be able to *fail*. A ledger reading `criterion 1 → x.spec.ts:123, criterion 2 → :135` is that failure mode, not rigour.

Most of the fix is prompt-side (Stage 4's "one artifact per criterion is NOT one test per criterion", the `coder`'s testing rules, `code-reviewer`'s mandate to recommend DELETING a test). A `PreToolUse` hook (`hooks/test_guard.py`) backs the two shapes that need no judgement, applied **only to test files and only to what the edit adds**:

- **Positional empty fakes** — `new Service({} as any, {} as any, model, {} as any…)`. A provider assembled by position out of blanks stops testing the code the moment a constructor parameter moves, and stays green while it does. Three or more placeholders in one call is the line; one or two is how a focused unit test stays short.
- **A test with no assertion** — it cannot fail except by throwing, so it reports a behaviour as covered while covering nothing. Named assertion helpers (`expectNetwork(…)`, or any local helper whose own body asserts) count as asserting.

**What it deliberately does NOT check:** *the test mocks the risk it claims to prove* — a `jest.fn()` counter standing in for an atomic `$inc` — which is the most damaging shape of all. Two designs were built and measured against 93 real test files: block-scoped detection missed every true positive (the fake lives in a factory outside the block), and file-scoped detection ran at roughly half false positives, because the claim lives in English — "a unique payer+amount candidate" is an in-process statement wearing a store guarantee's words, and a fake that *throws* is the only way to reach a driver error like E11000 at all. That judgement needs the subject read next to the test, so it belongs to `code-reviewer` and to the Testing contract in `conventions.md`.

Off with `DEV_WORKFLOW_TEST_GUARD=off`, or per-project via `.dev-workflow/test-guard.json`:

```json
{ "enabled": true, "checks": { "fakes": true, "assertions": true }, "max_empty_args": 3, "allow": ["legacy fixture"] }
```
</details>

<details>
<summary><b>🎛️ Config readout</b> — how it works</summary>

<br>Every guard here fails *quietly* by design: `comment_guard`, `test_guard` and the feature skill's read of `models.json` all swallow a parse error and carry on with defaults, because a malformed preference must never crash an edit or trap a turn. The cost is that a stray comma disables nothing, warns nobody, and leaves the project believing it configured something.

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
</details>

<details>
<summary><b>♻️ Context re-injection</b> — how it works</summary>

<br>A `SessionStart` hook (`hooks/status.py`) re-surfaces the active feature, phase progress, and gate state at every session start — **including after `/compact` or auto-compaction** (it fires with `source: "compact"` and adds a "context was just compacted — re-read the files" reminder). This keeps the file-based source of truth (`spec.md` / `plan.md` / `phase-log.md`) from being lost to context rot.
</details>

## Under the hood

- **Files are the source of truth** — `spec.md` / `plan.md` / `phase-log.md` survive `/compact` and `/clear`. Re-read them, don't trust conversation memory.
- **You review AFTER the AI** reviewers at every phase; nothing advances unapproved.
- **Proportional machinery** — the `feature` skill estimates the diff first, then sizes the job (trivial / standard / complex) and scales the machinery to it: trivial skips research and the option panel and runs as **one** phase; the option panel always runs a simplicity-first architect and adds performance- or risk-first only on a named signal; complex adds a full final audit. **A feature is trivial by default** — moving up a tier means naming the signal that puts it there — and the tier is re-checked once the plan makes the real size visible, so a change that turned out small gets collapsed instead of running the plan it was guessed to need. Phase counts start at one and every extra phase has to earn itself, because each one costs you an implement-review-approve round-trip. **The tier never scales security coverage down**: `code-reviewer` runs on every phase in every tier, and its security pass is gated on the phase's *surface*, not the tier — a new endpoint in a trivial feature gets scanned; a copy tweak in a complex one does not. Trivial phases are coded by the orchestrator itself, with no `coder` spawn, and still reviewed by a freshly spawned `code-reviewer`.
- **Token discipline across phases** — the fresh-context re-reads that make multi-phase workflows expensive are attacked directly: **one `coder` is reused across a feature's phases** (continued, not respawned) so codebase intake is paid once, not per phase; the orchestrator hands coder and reviewers the **exact files/paths** from `plan.md` so they Read the spot instead of Grep-walking to find it; and `conventions.md` is kept lean because every subagent re-reads it in full. Reviewers stay freshly spawned per phase on purpose — objective fresh eyes are the point. (An MCP can *store* shared context but can't avoid this cost: each subagent still pulls it into its own window.)
- **Optional: semantic code retrieval** — on large codebases, a symbol-level retrieval MCP (e.g. [Serena](https://github.com/oraios/serena)) lets agents read *symbols* rather than whole files, shrinking read size. It's an opt-in per-project MCP, not bundled — add it to your own `.mcp.json` if the codebase is big enough to warrant it.
- **The agents know what the project already has** — two project-level files, split by what they cost. `conventions.md` holds the RULES and is re-read in full by every subagent every phase, so it stays lean; **`project-map.md`** holds what EXISTS — module map, shipped features, shared building blocks, extension points, gotchas — and is read lazily: the orchestrator when researching and planning, the coder as inline excerpts for the module it's touching. `init` drafts it, the researcher verifies it against the code (**the code wins when they disagree**), and Stage 5 appends each shipped feature — so knowledge accumulates instead of being re-derived per feature. Without it, agents cheerfully propose rebuilding what's already there.
- **The requirements conversation happens before anything is delegated.** Stage 0.5 has the orchestrator play analyst: restate the request concretely, write **acceptance criteria** into `spec.md`, surface conflicts with what the code already does, then ask — in ONE batched round — only the questions whose answers fork the design, stating assumptions in writing for everything else (vetoing an assumption costs the user one word; answering an interrogation costs an afternoon). This is deliberately *not* a subagent: a subagent cannot stop to ask, so it would silently pick a reading and build it — and a plan built on a wrong reading passes every review here, because reviewers check code against the plan, not the plan against what you wanted. The criteria then flow all the way down: each phase's `Done when:`, the plan reviewer's coverage check, and the Evidence ledger's one-artifact-per-criterion rule.
- **Bugs get a different front end, not a different workflow.** `--bug` (or a request that plainly reports something broken) swaps Stage 0.5's *restate → acceptance criteria* for *reproduce → root cause → regression*, then rejoins the same tiers, phases, reviews and gates. The reason it is a branch and not a second command: a bug's risk isn't building the wrong thing, it's fixing the wrong **place** — and a patch aimed at the symptom passes every review here, because reviewers check the code against the plan and the plan says "stop the 500". So the branch buys the cause first: reproduce before diagnosing (**can't reproduce → it stops and asks you**, because an unreproducible bug has no way to prove it was fixed), name the cause at `file:line` and distinguish it from the symptom, state the blast radius — including **data the bug already corrupted**, which becomes its own phase with its own approval rather than a silent extra. The first acceptance criterion is always the regression, and the Evidence ledger has to cite the repro **failing before and passing after** — the red half is captured during diagnosis, so a test that was never seen fail can't be passed off as proof. Tier is set by the root cause, not the severity of the symptom: a production outage from a one-line off-by-one is still one reviewable diff.
- **Someone is paid to cut.** Every other role in the workflow is rewarded for adding — the architect for a richer option, the reviewer for another finding, the planner for another phase — and nothing balanced that, which is how a fifteen-line change grew a three-phase plan. So `plan-reviewer` now reviews in *both* directions and treats over-engineering as a first-class finding ("merge these", "this phase doesn't need to exist", "the plan is too heavy for what it delivers"); architects are told their angle is a lens, not a licence to grow the change, and must report each option's **size in files and lines** so bloat is visible in the comparison table *before* you pick; and the Simplicity contract from `conventions.md` binds the plan, not just the code.
- **Review loops are bounded — 2 rounds, then you arbitrate.** A coder and a reviewer left alone argue indefinitely: the reviewer keeps finding things because finding things is its job, and each round re-opens what the last one settled. So re-reviews are delta-scoped (the previous findings + the fix diff, *not* the phase again), findings are labelled BLOCKING or NIT and only BLOCKING ones can spend a round, and **the coder is allowed to disagree** — answering with evidence instead of editing away a finding it believes is wrong, because complying with a mistaken review puts a real defect in the code. If the budget runs out with a blocking finding still open, the workflow stops and asks *you*; it never resolves a deadlock by ticking `code-reviewed` itself. Each phase records `Review rounds: N/2` and what stayed unresolved.
- **Domain context** ships per-project via `conventions.md` (plugins can't ship a project `CLAUDE.md`). The plugin's skills and subagents Read it directly; `init` also adds an `@conventions.md` import to your `CLAUDE.md` so plain chat sessions — not just `/dev-workflow:*` — carry the same project context. `project-map.md` gets a *pointer* in `CLAUDE.md` rather than an import, so ordinary chat knows the map exists and reads it when a task needs it, without paying for the whole map in every session. A minimal `references/clean-code.md` baseline applies in **every** project, greenfield or not — but it is strictly subordinate: on a genuine conflict, precedence is linter/formatter > `conventions.md` > surrounding style > baseline.

## Requirements

- **`python3` on PATH** — the hooks are invoked as `python3`. macOS and most Linux distros ship no binary named `python` at all, so that is the only name that reliably resolves. On Windows, the Microsoft Store build provides `python3`; if you installed from python.org you may only have `python` and `py`, in which case add a `python3` shim on PATH.
  Check with `python3 --version`. If it fails, the hooks fail to launch — and because hooks fail open, you get **no approval gate, no checkpoints and no evidence gate, silently**.
- **Git** for checkpoints/rollback (the other features work without it).
- Add **`.dev-workflow/`** to your project `.gitignore`.
