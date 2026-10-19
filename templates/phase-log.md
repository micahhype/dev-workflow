# Phase log: <feature name>

> Append-only record of each phase. Survives /compact and /clear — re-read this
> instead of trusting conversation memory. ONE section per phase in `plan.md` —
> copy the block below for a second phase only if `plan.md` has one.
>
> **This file is machine-parsed.** Keep the `## Phase N — ...` headings and the
> `- Status:` / `- Evidence:` lines in the shape below: the hooks find a phase by
> its `## Phase`/`## Final review` heading, arm the evidence gate on the literal
> `[x] code-reviewed` (or `[x] full code review` in the Final review section), and
> read progress from the literal `[x] USER APPROVED`. Reworded into prose, the
> safety hooks go silent — without saying so.
> `[x] USER APPROVED` means the USER approved. Claude never ticks it unprompted.
>
> More lines are machine-checked, by the plan guard: `- Review rounds:` above 2
> requires a filled `- Unresolved:`, and the LAST section of a finished feature needs
> a `- Project map updated:` line and a `- Lessons:` line (both scaffolded in Final
> review below — when Stage 5 is skipped, add them to the last phase instead). A reviewed
> phase needs a `- Review map:` with `MUST` / `SKIM` / `SKIP` entries, and a phase whose
> diff outgrew its plan `- Size:` needs a filled `- Over budget:`. The dashboard renders
> the map, so keep each entry one line: `- TIER `path:start-end` — what it does → what to
> check`, plus `- ASSUME <decision the spec did not make>`. The rest is prose for you and
> the user; no hook reads it.

## Phase 1 — <title>
- Status: [ ] coded  [ ] code-reviewed  [ ] security-scanned  [ ] USER APPROVED
- Changed: <files + key decisions>
- Review map: <N must-read / N skim / N skip of N changed lines>
  - MUST `<path:start-end>` — <what it does> → <the question the user must answer>
  - SKIM `<path:start-end>` — <what it does>
  - SKIP `<path>` — <why it needs no reading>
  - ASSUME <a decision the code makes that the spec did not>
- Over budget: <only when the plan guard flags the diff as over its `- Size:`: why it
  lands as one phase. Leave the placeholder otherwise.>
- Code review result: <summary of findings + how resolved>
- Security scan result: <summary>
- Review rounds: <N/2 — how many fix→re-review rounds this phase took>
- Unresolved: <blocking findings closed by escalation + the user's call, or "none">
- Deferred nits: <non-blocking findings not worth a round, or "none">
- Evidence: <cited PROOF this phase works — concrete artifacts only, no "looks
  fine". e.g. `pytest -q` -> 12 passed; snapshot ref created + `git rev-parse
  HEAD` unchanged; hooks/x.py:42 handles the empty case. Required before you ask
  the user to approve; one artifact per acceptance criterion this phase delivers
  (the `Done when:` of its phase in plan.md, from `spec.md` section 1b).>
- User notes: <what the user said / requested changes>

---
<!-- DELETE this whole section if Stage 5 is skipped — i.e. whenever the feature
     ended up a SINGLE phase, in any tier: an unticked section is reported as the
     current one forever. -->
## Final review (all phases)
- Status: [ ] full code review  [ ] security-audit  [ ] USER APPROVED
- Cross-phase findings:
- Resolution:
- Review rounds:
- Unresolved:
- Project map updated: <what was appended/corrected in project-map.md, or "no
  structural change">
- Lessons: <rules the user approved into conventions.md "Learned rules", or "none">
- Evidence: <cited proof for the whole feature — test suite result, validation
  command output, the key invariants checked end-to-end.>
