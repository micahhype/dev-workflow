# Project conventions

*Keep this file lean — every research/coding/review subagent re-reads it in full,
every phase, so each line is paid for many times over. Aim for under ~50 lines;
push long detail into dedicated files (a `references/` doc, an ADR) that agents
open only when a task needs them. (This note stays; the guidance blockquotes go.)*

> This is the domain + engineering context for THIS project. It is the source of
> truth the workflow reads before researching, coding, and reviewing.
>
> Fill it in one of two ways:
> - Run `/dev-workflow:init` — it inspects the project (stack, structure, existing
>   patterns) and drafts this file for you to review.
> - Or leave it; each feature will infer the relevant domain from your feature
>   description and the surrounding code.
>
> Delete the guidance blockquotes once filled.

## Domain
> What kind of software is this (e.g. fintech payments, healthcare records,
> e-commerce, dev tooling, gaming)? What domain rules/regulations apply?

## Tech stack
> Languages, frameworks, datastores, key libraries, runtime/target.

## Architecture & structure
> The shape of the system in a few lines: the layers/services and how they talk.
> Keep it to what every agent needs on every phase. The detailed map — module
> table, existing features, shared building blocks, extension points — lives in
> `project-map.md`, which is read only when a task needs it; point there instead
> of inlining it here.

## Coding conventions
> Style, naming, error-handling patterns, testing approach, things reviewers
> should enforce. Name the linter/formatter and the EXACT command to run them
> (e.g. `ruff check` / `npm run lint` / `gofmt -l`) and the test command — the
> coder runs these and the reviewer enforces them. Objective tooling beats prose.
> (Greenfield with no conventions yet? Start from `references/clean-code.md`.)

## Testing
> The EXACT test command, and the harness for proving store/external behaviour for
> real (an in-memory server, a container, a fixture DB) — name it even if nothing
> uses it yet, because an agent that cannot see it will mock instead. Then how a
> subject is built in a test (a testing module, a named factory — never positional
> `as any` blanks). Anything else this project wants enforced.

## Testing contract (always applies)
*This section stays verbatim — it is not project-specific and is not a fallback.*
- Test at the boundary where the risk lives. Correctness that depends on the store
  or an external system — atomicity, uniqueness, indexes, transactions, real filter
  semantics — is proven against the real thing, not a mock of it. A fake that
  stands in for the risky call proves nothing about it and reports it as covered.
  Faking a collaborator to INJECT an otherwise unreachable failure is fine.
- Pure logic gets a plain unit test: no DI, no mocks.
- Behaviour a user or caller can observe — an acceptance criterion about what an
  endpoint, a command, a screen or a public function does — is held by a durable
  test at that boundary. One test may hold several criteria. A command run by hand
  proves the behaviour today and guards nothing tomorrow, so it does not replace
  the test.
- Every new test is seen failing once, with the behaviour it guards broken, before
  it counts. A test nobody has seen fail may be unable to.
- Nothing else gets a test. A behaviour that is a declaration — a validator
  annotation, a schema field, a config constant, a type — is already enforced by
  the type-checker, the linter or the framework; a test restating it cannot fail.
- Few tests: extend the module's existing spec rather than add a file; never a
  test per defensive branch, a wiring/DI test, or a test of generated code.
  Probe/smoke scripts are scratch — run them, paste the output, don't commit them.
- Build the subject by NAME, never positionally out of empty placeholders.
  (The last two shapes are enforced by a hook. Turn it off for this project with
  `.dev-workflow/test-guard.json` -> `{"enabled": false}`.)

## Simplicity contract (always applies)
*This section stays verbatim — it is not project-specific and is not a
fallback. It applies on top of the conventions above, in every project.*
- Build only what the task requires — no speculative options, config, or
  abstraction for imagined future needs.
- No new abstraction until a real third use; prefer a function over a class,
  a literal over a config system, straight-line code over a framework.
- Match existing patterns; don't add libraries or layers the codebase doesn't
  already use.
- No business rule the request did not state — no extra limit, quota, status,
  permission, cache or abuse guard. Suggest it; don't build it.
- Handle only errors that can actually occur here; validate only untrusted input,
  at the boundary. No checks for cases the types or callers rule out.
- Comments: a one-line WHY where the logic is genuinely hard — a non-obvious
  constraint, the idea behind a formula, an order that matters, a workaround.
  Never WHAT the code does (fix the name instead), never the history of the
  change, never a paragraph; longer reasoning goes in the commit message.
  (Enforced by a hook, which denies the edit: about one comment line per edit and
  one per twenty lines of code, more only where the file already comments more,
  and no added block past two lines. Tool directives like `eslint-disable` are
  exempt. Tune it in `.dev-workflow/comment-guard.json`: `{"density": {"floor": 0,
  "min_ratio": 0}}` forbids comments entirely, `{"allow": ["<regex>"]}` exempts a
  phrase, `{"enabled": false}` turns it off.)
- Before adding anything beyond the literal request, STOP and ask — default to less.

## Readability contract (always applies)
*This section stays verbatim — it is not project-specific and is not a fallback.*
- Code is written for a teammate reading it cold, without the spec or comments.
  Correct code that has to be decoded is a defect.
- Names in full words that say what the value is; never one name for two things;
  booleans read as questions.
- One idea per line: named intermediates over dense chains; no nested ternaries,
  no arithmetic on booleans, no clever tricks.
- No hidden encodings: no string-glued keys, never `null` and `undefined` meaning
  two different things, no magic numbers, no empty `catch`.
- At most three parameters on a function you define (injected constructors and
  framework-dictated signatures are exempt); control flow nested at most two
  levels; the entry function reads top to bottom, details below it in private
  functions that name each step.

## Learned rules
> Rules this project learned from past features — each one approved by the user at
> a feature's final checkpoint, added by `/dev-workflow:feature`, never invented.
> One line each, ending with where it came from. Keep it under ~15 lines: when it
> grows past that, merge or drop the weakest rather than append.
> e.g. `- Scale token amounts with bigint, never Number() — user rewrote formatUnits (space-balance)`

## Domain-specific correctness rules
> Invariants that MUST hold for this domain. Examples by domain:
> - Fintech: money as integer minor units / decimal (never float); idempotency
>   keys on money writes; audit logging; atomic balance updates.
> - Healthcare: PHI handling, access control, audit trails.
> - E-commerce: inventory consistency, price/tax rounding rules.
> Replace with YOUR project's rules.

## Security focus for this project
> Beyond the generic checklist (injection, auth bypass, secrets, insecure crypto,
> unsafe deserialization, SSRF), what are the high-value risks specific to this
> domain? These are what the security reviewers prioritize.

## Workflow files
Per-feature `spec.md` / `plan.md` / `phase-log.md` live under
`.dev-workflow/features/<slug>/` (active slug in `.dev-workflow/active`); this file
and `project-map.md` (what exists and where) are project-wide at the repo root. All
survive `/compact` and `/clear`.
