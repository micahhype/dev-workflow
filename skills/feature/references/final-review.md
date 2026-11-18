# Stage 5 — Final review of a multi-phase feature

Read by `/dev-workflow:feature` once every phase of a feature with MORE than one phase is approved. Review-round budget and escalation are the feature skill's (Stage 4).

1. Run over all phases together. Brief both reviewers with the feature's
   footprint so they don't re-discover it: every changed file grouped by phase,
   with the line ranges of its hunks.
   - `code-reviewer` on CROSS-PHASE issues ONLY — inconsistencies, phase
     interactions, integration seams. Do NOT re-review files from scratch (done
     per phase).
   - `security-audit` (deep pass) — owns EMERGENT, cross-phase interaction
     vulnerabilities (auth flows spanning phases, data-flow and trust-boundary
     analysis). Do NOT re-review single phases from scratch; each already had its
     security pass.
2. Summarize findings; update `phase-log.md` final section and its `- Evidence:`
   line with feature-level proof (test-suite result, validation output, key
   end-to-end invariants checked), plus `- Review rounds:` and `- Unresolved:`.
3. If issues found, fix via `coder` and re-audit — **same 2-round budget, same
   escalation.** An unresolved security finding is never waved through on a round
   count: it goes to the user with your recommendation, explicitly.
4. **Update `project-map.md`** as the feature skill's Stage 5 says.
5. **CHECKPOINT: present the final result, the `project-map.md` update AND the
   Stage 6 lesson proposals, then stop for sign-off.** The map is what future
   agents will treat as fact, so the user gets to correct it here.
