---
description: Approve the phase that is waiting for you. Typing this command yourself is what records the approval; Claude cannot record it by calling the command.
disable-model-invocation: true
---

The user typed `/dev-workflow:approve`, optionally followed by a phase number or `final`.

A hook has already tried to record the approval, and its result is in a
`[dev-workflow]` line in your context for this turn. Do not run `dw approve` yourself.

- **"The user's approval is recorded …"**: say so in one line and carry on with the
  workflow from that phase's approval (next phase, or the final steps).
- **"No approval recorded: …"**: tell the user the reason as given. If the phase is not
  reviewed yet, finish the review first; do not approve it another way.
- **The line says the feature has no state.json**: it is a hand-written log. Tick
  `[x] USER APPROVED` for the current phase in `phase-log.md`, as the feature skill says.
- **No `[dev-workflow]` line at all**: the hook did not run. Say the approval was not
  recorded and that the user can run `! .dev-workflow/dw approve` in their own shell.
