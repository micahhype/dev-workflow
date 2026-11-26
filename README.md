# 🛠️ dev-workflow

A Claude Code plugin for spec-driven development. It clarifies the request, plans the change, then builds it in small phases. Every phase gets an AI code review with a security pass, and nothing moves on until you approve.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/micahhype/dev-workflow/main/assets/flow-dark.svg">
    <img alt="The feature line: clarify → research → design (you pick) → plan (you approve) → per-phase loop of build → review (you approve) → final audit (you approve) → ship" src="https://raw.githubusercontent.com/micahhype/dev-workflow/main/assets/flow-light.svg" width="830">
  </picture>
</p>

- **You approve every step.** The plan before any code, then each phase after the AI reviewers have been through it.
- **The machinery scales with the change.** A small change is one proposal and one phase. Research, a solution architect and a final audit are added only when the change needs them.
- **Files are the source of truth.** `spec.md`, `plan.md` and `state.json` survive `/compact` and `/clear`.
- **Review loops are bounded.** After two fix rounds, you decide.
- **It works in any domain.** Project context comes from your `conventions.md`, or is inferred from the code.

## Install

```shell
/plugin marketplace add micahhype/dev-workflow
/plugin install dev-workflow@dev-workflow-marketplace
```

You need:

- **`python3` on PATH.** The hooks run as `python3`. If it is missing they cannot start, and because hooks fail open you get **no approval gate, no checkpoints and no evidence gate, silently**. On Windows with a python.org install you may only have `python` and `py`; add a `python3` shim.
- **Git**, for checkpoints and rollback. Everything else works without it.
- **`.dev-workflow/` in your `.gitignore`.** The working docs live there.

To update, run `/plugin marketplace update dev-workflow-marketplace`, then `/plugin update dev-workflow@dev-workflow-marketplace`. The [changelog](CHANGELOG.md) lists what is new.

## Use

```shell
/dev-workflow:init                       # optional: learn the repo → conventions.md + project-map.md
/dev-workflow:feature add pagination to the orders endpoint
/dev-workflow:feature --bug the orders endpoint 500s on an empty cart
/dev-workflow:approve                    # approve the phase that is waiting for you
```

Each feature keeps its docs in `.dev-workflow/features/<slug>/`. Several features can run at once; `.dev-workflow/active` names the current one.

| Command | What it does |
|---------|--------------|
| `/dev-workflow:init` | Inspects the project and drafts `conventions.md` and `project-map.md` |
| `/dev-workflow:feature` | Runs the whole workflow for one feature. `--bug` starts with reproduce → root cause → regression |
| `/dev-workflow:approve` | Approves the phase waiting for you (or a phase number, or `final`) |
| `/dev-workflow:status` | Shows the active feature, phase and gate. Also injected at the start of each session |
| `/dev-workflow:architect` | System design before a big feature: NFRs, patterns from the [catalog](references/architecture-patterns.md), diagram, PR slices. `adr <title>` records one decision |
| `/dev-workflow:rollback` | Restores a checkpoint, reversibly. `rollback list` only lists them |
| `/dev-workflow:config` | Shows the effective settings and where each came from, and sets a value |
| `/dev-workflow:dashboard` | Opens a local web board of every project's features, the ones waiting for you first |

## Guards

Hooks hold the workflow to its rules. They all fail open: a hook that errors never blocks your work.

| Guard | What it does |
|-------|--------------|
| [Approval gate](docs/guards.md#approval-gate) | A `LOCKED` gate only you can flip. While locked, Claude cannot edit source or run Bash |
| [Checkpoints and rollback](docs/guards.md#checkpoints--rollback) | A git snapshot before every edit, and a safe, reversible restore |
| [Evidence gate](docs/guards.md#evidence-gate) | "Done" must cite proof. An empty ledger is refused |
| [Plan guard](docs/guards.md#plan-guard) | Extra phases and blown review budgets must be justified in writing |
| [Workflow state](docs/guards.md#workflow-state--approval) | Progress lives in `state.json`, changed by one command that validates each step and records how your approval arrived |
| [Context re-injection](docs/guards.md#context-re-injection) | Workflow state survives `/compact` |
| [Comment guard](docs/guards.md#comment-guard) | Refuses comments that narrate the diff or talk to the reviewer |
| [Test guard](docs/guards.md#test-guard) | Refuses tests with no assertion and providers built from empty fakes |

Checkpoints run in every git repo, whether or not a feature is active. They write only to their own shadow refs, never your index, HEAD, branch or worktree, and are deleted after 14 days. The other guards stay silent when no workflow is active.

## Agents and models

| Agent | Role |
|-------|------|
| `domain-researcher` | Domain and stack research, plus what the codebase already has |
| `solution-architect` | The option that fits, plus priced leaner and safer deltas |
| `plan-reviewer` | Adversarial plan review before coding |
| `coder` | Implements one phase |
| `code-reviewer` | Logic and quality review plus a security pass, every phase |
| `security-audit` | Deep final audit across all phases |

Every agent defaults to `opus`, an alias that follows the newest Opus without a plugin update. To change that:

- **One agent:** set it in `.dev-workflow/models.json`, for example `{ "coder": "sonnet" }`. Values are an alias (`opus`, `sonnet`, `haiku`, `fable`), a full model ID to pin a version, or `inherit` for the session's model. `templates/models.json` is a starting point.
- **All agents:** set `CLAUDE_CODE_SUBAGENT_MODEL=<model>` before launching.
- **Replace an agent, prompt included:** put `.claude/agents/<name>.md` in your project.

## More

- [docs/design.md](docs/design.md): why the workflow is built this way.
- [docs/guards.md](docs/guards.md): how each guard works, how the plugin [learns rules across features](docs/guards.md#learning-across-features), and the [config readout](docs/guards.md#config-readout).
- Two scripts to run from your own terminal:
  - `python3 <plugin>/hooks/mark_done.py <root> <slug>` marks every open phase of a feature you already finished as approved. It refuses inside Claude Code.
  - `python3 <plugin>/scripts/subagent_traces.py [ROOT]` reads your subagent transcripts and prints tokens and time per agent type.
