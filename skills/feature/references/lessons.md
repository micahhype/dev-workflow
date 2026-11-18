# Stage 6 — Lessons, and post-ship edits

Read by `/dev-workflow:feature` at every feature's final checkpoint, and at Stage 0 for "Post-ship edits". `<checkpoint.py>` below is the plugin's `hooks/checkpoint.py`; the feature skill's Stage 6 gives its full path.

The workflow does not get better on its own: a review finding, a correction the user
made, a suggestion they turned down all die with the feature's `phase-log.md`, and
the next feature makes the same mistake. This stage turns what recurred into a rule
in `conventions.md` — which every agent already reads on every phase — and only with
the user's approval. It runs at the final checkpoint: Stage 5's, or the last phase's
when Stage 5 is skipped. It is one question to the user, not a retrospective.

1. **Gather signal from this feature** — the phase-log you already have:
   - what the user asked to change at any checkpoint (`- User notes:`), and what
     they overrode at an escalation (`- Unresolved:`);
   - `Suggested, not built:` items the user declined — "don't propose X" is a rule;
   - review findings of the same KIND that came up in two or more phases, or that
     the coder kept needing a round to fix;
   - plus any rules from "Post-ship edits" below that are still pending.
2. **Keep only what generalises.** A rule is worth a line only if it would change
   what an agent does on a DIFFERENT feature of this project. Drop one-off facts
   and anything the linter could enforce (propose the lint rule instead). If
   `conventions.md` already has the rule and it was broken anyway, don't add a
   duplicate — tell the user the rule is being ignored. One line each, imperative, concrete, ending with where it
   came from: `- Scale token amounts with bigint, never Number() — user rewrote
   formatUnits (space-balance)`.
3. **Propose at most three**, via one `AskUserQuestion` with `multiSelect`, each
   option a rule with its evidence. Nothing worth proposing is the common, correct
   outcome — then say so in one line and ask nothing.
4. **Write the approved ones** to the `## Learned rules` section of `conventions.md`
   (create the section above "Domain-specific correctness rules" if it is missing).
   If it passes ~15 lines, propose merging or dropping the weakest in the same
   question rather than growing it. Record the outcome on the last section's
   `- Lessons:` line — the rules added, or "none". The plan guard requires the line.
5. **Record the ship point** (git repos only), after the user signs off:
   `python3 <checkpoint.py> ship <slug>`. It stores
   the tree as it was handed over, which is what "Post-ship edits" diffs against.
   If the approval gate is LOCKED, Bash is denied — ask the user to run it with a
   `!` prefix, or skip it and say so; never work around the gate.

## Post-ship edits — what the user changed after accepting the code
The strongest signal this workflow ever gets arrives AFTER the feature: the user
opens the code the agents wrote and rewrites part of it. Nobody tells the agents.
At Stage 0 of the next feature, for the most recently shipped feature(s) — at most
two, newest first from `git for-each-ref --sort=-creatordate
--format='%(refname:short)' refs/dev-workflow/shipped` — whose last phase-log
section has no `- Post-ship reviewed:` line:
1. Run `python3 <checkpoint.py> since-ship <slug>
   <files>`, passing the files from that feature's `- Changed:` lines. "never
   shipped" means no ship point was recorded — mark it reviewed and move on.
2. Read the diff for what the USER changed in agent-written code: rewritten logic,
   deleted comments or tests, renamed variables, removed handling. Ignore changes
   another feature's `- Changed:` explains, and formatting. Unsure whether an edit
   was the user's? Ask in the same question rather than guess.
3. Turn what generalises into rule proposals exactly as in steps 2–4 above, in one
   `AskUserQuestion` — or none, which is common. Keep it quick; the user came here
   to start a new feature.
4. Write `- Post-ship reviewed: <date> — <rules added | no user edits | none
   generalised>` on that feature's last section, so it is never asked about twice.
