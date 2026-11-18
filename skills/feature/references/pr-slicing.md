# Cutting a plan into stacked PRs

Read by `/dev-workflow:feature` when the phases' `- Size:` total is over the PR cap (`pr_cap` in `.dev-workflow/plan-guard.json`, default 300, `0` = off). The plan guard checks the result.

## In the plan (Stage 3)
**Cut the plan into PRs when it is over the cap.** When the phases' `- Size:`
total is over the PR cap, add a `## PRs` section: stacked PRs, each one
independently mergeable, ordered prep/refactor → core + tests → wiring/UI.
Pieces that are not finished yet stay dormant or behind a flag until the PR
that wires them. A PR holds whole phases, and a phase never spans two PRs.
A plan that
must land as one PR anyway says why on an `- Over cap:` line instead.

## At each PR's last approval (Stage 4)
**With a `## PRs` section, commit per PR.** When the LAST phase of PR N is
approved, create or switch to branch `<slug>/pr-<N>` (PR 1 branches from the
current branch, PR N from `<slug>/pr-<N-1>`), commit that PR's changes, and write
`.dev-workflow/features/<slug>/pr-<N>.md`: What / Why / How to review (the
reading order, from the MUST entries of its phases' review maps) / Stacked on.
Never push and never run `gh pr create`; tell the user the branch and the file.
Once a PR is committed, that branch and commit are its rollback unit.
