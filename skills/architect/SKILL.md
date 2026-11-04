---
name: architect
description: System-level design before /dev-workflow:feature — for a new project or a big cross-module feature, draft docs/architecture/<name>.md (numeric NFRs, patterns picked from the plugin's catalog, components, data flow, mermaid diagram, tradeoffs, risks, PR slices). `adr <title>` records one decision as docs/adr/NNNN-<title>.md. Writes only after user approval.
---

# Architect — design from the pattern catalog, record decisions as ADRs

The argument picks the mode: `adr <title>` runs **adr mode**; anything else runs
**design mode**, with the argument as the goal. An empty argument, or a bare
`adr` with no title, means ask the user for the goal or the title first.

Every pattern comes from the catalog at
`${CLAUDE_SKILL_DIR}/../../references/architecture-patterns.md` or the project's
`docs/architecture/catalog-additions.md`. The catalog's `## Rules` header holds
the pick rules and the briefing rule — follow them from there. An ADR is accepted
when its Status line reads `accepted`.

## Design mode
1. Read, in one turn: `conventions.md`, `project-map.md` if present, every
   accepted ADR in `docs/adr/`, the catalog, and
   `docs/architecture/catalog-additions.md` if present. Then survey what the
   codebase already has for the goal (modules, building blocks, extension points).
   A pick that contradicts an accepted ADR names the ADR it supersedes.
2. Ask the user for the non-functional requirements in ONE batched question
   round, as numbers: load (requests/s, peak), latency budget (p95), data size and
   growth, availability target, team size, compliance. An NFR the user does not
   give stays `TBD` — never invent one.
3. Pick catalog ids per the catalog's Rules. Only when the user asks for competing
   options, spawn one `solution-architect` per angle in parallel — simplicity-first
   always, performance-first or risk-first only on a signal for it — each given the
   goal and the NFRs in place of acceptance criteria, plus a brief per the
   catalog's briefing rule.
4. If no entry fits, say so and draft a new entry in the catalog's format.
   **CHECKPOINT: show the draft entry; wait for the user to approve it.** On
   approval, append it to `docs/architecture/catalog-additions.md` (create
   `docs/architecture/` if needed), then continue picking. Never use an
   unapproved entry.
5. Draft the design doc from this template, reusing what exists:

   ```markdown
   # <Name> — architecture
   ## Context & goal
   ## Non-functional requirements   <!-- each: number or TBD, and its source -->
   ## Chosen patterns               <!-- each: `id` — matched signal — why the cheaper entry its Not when names (if any) lost -->
   ## Components                    <!-- each: name — responsibility -->
   ## Data flow
   ## Diagram                       <!-- mermaid; only components named above -->
   ## Tradeoffs                     <!-- include each pick's Cost line -->
   ## Risks & mitigations
   ## PR slices                     <!-- each a one-line /dev-workflow:feature request under the plan guard's `pr_cap` (`.dev-workflow/plan-guard.json`, default 300 lines); prep → core → wiring -->
   ## Open questions
   ```

6. **CHECKPOINT: show the draft and stop. Write `docs/architecture/<name>.md`
   only after the user approves it.** `catalog-additions` is a reserved name; if
   `docs/architecture/<name>.md` already exists, say at the checkpoint that it
   will be overwritten.
7. Offer to record the key decisions as ADRs (adr mode below).

## ADR mode
1. Next number = the highest `docs/adr/NNNN-*.md` + 1, four digits, never reused;
   `0001` if there is none (create `docs/adr/`).
2. Draft from this template:

   ```markdown
   # NNNN. <Title>
   - Status: accepted
   - Date: YYYY-MM-DD
   - Supersedes: NNNN      <!-- omit when none -->
   ## Context
   ## Decision drivers       <!-- the NFRs -->
   ## Considered options     <!-- catalog ids where they apply -->
   ## Decision
   ## Consequences
   ```

3. **CHECKPOINT: show the draft; write `docs/adr/NNNN-<title>.md` only after the
   user approves it.**
4. A superseded ADR's Status line becomes `superseded by <new NNNN>`, in the same
   approved write as the new ADR. That is the only edit an accepted ADR ever gets.

## Rules
- No pattern stacking — a pattern needs its own matched Signals line, not a
  partner's. Reuse what the codebase already has before adding a component.
- Write nothing but `docs/architecture/<name>.md`,
  `docs/architecture/catalog-additions.md` and `docs/adr/NNNN-<title>.md`, each
  after its checkpoint — plus the Status line of the ONE existing
  `docs/adr/<NNNN>-*.md` matched by the Supersedes number, a regular file inside
  `docs/adr/`; on zero or several matches, stop and ask. `<name>` and `<title>`
  are lowercase kebab-case slugs (`[a-z0-9-]`) derived from the goal and the ADR
  title.
