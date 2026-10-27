---
name: init
description: Inspect the current project and draft conventions.md (domain, stack, conventions, security focus) plus project-map.md (module map, existing features, shared building blocks, extension points) so the feature workflow has accurate project context. Read-heavy; after user review, writes both files and imports conventions.md from CLAUDE.md.
---

# Init — learn this project, draft conventions.md + project-map.md

Your job is to produce TWO files at the project root for `/dev-workflow:feature`
to rely on. They split by *kind of knowledge*, and the split is what keeps the
workflow affordable:

| File | Holds | Read by |
|---|---|---|
| `conventions.md` | the RULES — domain, stack, conventions, correctness rules, security focus | every subagent, in full, every phase — so it stays under ~50 lines |
| `project-map.md` | what EXISTS and WHERE — module map, existing features, shared building blocks, extension points, gotchas | lazily: the orchestrator when researching/planning, the coder for the modules it touches |

When you learn something, ask which it is: a rule to follow goes in
`conventions.md`, a location or a capability that already exists goes in
`project-map.md`. Never put the module table or the feature list in
`conventions.md` — it is re-read on every phase by every agent, and that is what
the lean budget is protecting.

## Steps
1. Inspect the project (read-only first):
   - Detect the tech stack from manifests (`package.json`, `go.mod`,
     `pyproject.toml`/`requirements.txt`, `Cargo.toml`, `pom.xml`, `Gemfile`,
     etc.), framework imports, and the directory layout.
   - Infer the DOMAIN from names, models/entities, routes, and any existing docs
     (README, docs/). Examples: fintech, healthcare, e-commerce, dev tooling.
   - Note existing coding conventions and architecture/module boundaries. In
     particular, detect the linter/formatter and record the EXACT command to run
     them (e.g. `ruff check`, `npm run lint`, `gofmt -l`, `cargo fmt`) plus the
     test command, and any naming/error-handling patterns the code already
     follows. These are what the coder runs and the reviewer enforces.
   - **Detect the testing setup, including what is installed but unused.** The
     runner and its exact command; how existing tests build a subject (a testing
     module, a factory, positional constructor calls); and — the part that gets
     missed — whether a harness for proving store/external behaviour FOR REAL is
     already a dependency (an in-memory server such as `mongodb-memory-server`,
     Testcontainers, a fixture DB, a fake HTTP server). Grep the manifest, not just
     the test files: these are routinely installed and then used in one file out of
     fifty, and an agent that cannot see the harness mocks the database instead and
     writes a test that cannot fail. Record it by name in `conventions.md` even
     when nothing currently uses it. If there is none, say that too — "no real-store
     harness; add one before claiming store behaviour in a test" is a useful line.
   - **Survey what the project already DOES**, not just how it is written — this
     is the part agents are missing today, and it is why they propose rebuilding
     something that exists. Enumerate the capabilities from the surfaces that
     declare them: routes/endpoints, CLI commands, event/queue handlers,
     scheduled jobs, exported modules, UI screens, public API. For each, note
     what it does and the file that owns it. Then find the SHARED building blocks
     a new feature is expected to reuse (base classes, middleware, validators,
     error types, HTTP/DB clients, auth helpers, config access, test fixtures)
     and the EXTENSION POINTS ("to add a route, touch X"; "migrations live in Y").
   - If a `CLAUDE.md` already exists, read it and reuse its content — do not
     duplicate or overwrite it; complement it.
2. Draft `conventions.md` using the section structure from the plugin template
   (Domain / Tech stack / Architecture / Coding conventions / Testing / Testing
   contract / Simplicity contract / Readability contract / Learned rules /
   Domain-specific correctness rules / Security focus / Workflow files). Leave
   Learned rules empty — the feature workflow fills it, and a re-run of `init` must
   carry any existing entries over unchanged. Fill each section from what
   you observed; mark anything uncertain as an assumption. Copy the **Simplicity
   contract**, **Readability contract** and **Testing contract** sections verbatim
   from the template in BOTH paths (observed project conventions and greenfield
   default) — they are standing constraints, not fallback baselines. Never
   rephrase, soften, or drop them.
3. Draft `project-map.md` using the plugin template's sections (Module map /
   Existing features / Shared building blocks / Extension points / Known gotchas
   / Glossary). Fill it from the survey in step 1.
   - Entries are POINTERS: path, what it owns, entry point. Do not restate what
     the code says or paste signatures — one to three lines per entry.
   - Only write what you actually verified by reading the code. An invented or
     guessed entry is worse than a missing one, because agents trust this file
     and will build against it. Mark anything inferred as an assumption for the
     user to confirm.
   - For `Existing features`, leave the `Shipped` column blank for pre-existing
     work you can't date — the feature workflow fills it for features it ships.
   - If the project is small enough that the map would just re-list five files,
     say so and keep it to the Module map + Extension points; don't pad it.
4. **CHECKPOINT: show BOTH drafts to the user and ask them to confirm or correct
   them before writing.** Call out your assumptions explicitly — the map is the
   thing later agents will treat as fact. Only write the files after they approve.
5. Make both files visible to ordinary chat, not just this plugin. The plugin's own
   skills and subagents Read them directly, but a plain Claude Code session only
   auto-loads `CLAUDE.md` and the files it `@`-imports — so without a line in
   `CLAUDE.md`, everything you wrote is invisible outside `/dev-workflow:*`.
   The two files get DIFFERENT treatment, and the difference is deliberate:

   ```markdown
   Project domain and conventions:
   @conventions.md

   What already exists in this project — module map, shipped features, shared
   building blocks, extension points — is in `project-map.md`. Read it before
   proposing to build something, to check whether it exists already and where it
   would go. (Not imported: it is a lookup file, read it when a task needs it.)
   ```

   - `conventions.md` is `@`-imported: it is the RULES, and they apply to every
     turn, so they belong in context from the start.
   - `project-map.md` is POINTED AT, not imported. Importing it would load the whole
     map into every session — the standing cost the lazy-read design exists to
     avoid — to answer a question most turns never ask. A pointer costs three lines
     and still gets the file read when it matters.
   - If `CLAUDE.md` already has both, leave the file alone; if it has the import but
     no pointer (written by an older init), append just the pointer. Otherwise
     append what's missing — do not touch anything else in the file.
   - If there is no `CLAUDE.md`, ask the user whether to create a minimal one
     holding just those lines. If they decline, tell them plain chat sessions won't
     see either file and move on.

   Then tell the user that a session already running must be restarted to pick the
   import up — `CLAUDE.md` is loaded once at session start, not re-read each turn.
   (Subagents Read the files live, so they always see the latest.)
6. After writing, point the user to **model routing** (optional, one line each) so
   they can tune cost/quality before running a feature:
   - **Per-agent (recommended):** copy the plugin's `templates/models.json` to
     `.dev-workflow/models.json` and map any of the six agents
     (`domain-researcher`, `solution-architect`, `plan-reviewer`, `coder`,
     `code-reviewer`, `security-audit`) to a model — an alias
     (`opus`/`sonnet`/`haiku`/`fable`), a full model ID, or `inherit`. Omitted
     agents keep their default; prompts are untouched.
   - **All agents at once:** set `CLAUDE_CODE_SUBAGENT_MODEL=<model>` before launching.
   - **Replace an agent entirely:** add `.claude/agents/<name>.md` to shadow the
     plugin's (changes the prompt too, not just the model).
   Mention it and move on — do NOT create `models.json` yourself; init writes
   `conventions.md`, `project-map.md` and the `CLAUDE.md` import line, nothing else.

## Rules
- Be concrete and specific to THIS project — no generic filler.
- Do not modify source code. The only files you create/update are
  `conventions.md`, `project-map.md` and — for the import line alone —
  `CLAUDE.md`.
- Re-running init on a project that already has these files REFRESHES them:
  re-verify every existing entry against the code, correct what drifted, drop
  what no longer exists, and show the user a diff of what changed rather than
  silently overwriting their edits.
- The clean-code baseline (`references/clean-code.md`) applies to EVERY project,
  not just greenfield — the coder and reviewer enforce it always, subordinate to
  the project's own linter/conventions/style on a genuine conflict. So the Coding
  conventions section should capture what is SPECIFIC to this project (linter/test
  commands, real naming/error patterns); don't re-list the generic baseline.
- If the project is empty/greenfield, ask the user a few targeted questions about
  the intended domain and stack, then draft from their answers. For the Coding
  conventions section, if there's nothing project-specific yet, point to the
  baseline as the starting default to refine — do not leave it blank.
