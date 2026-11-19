# Bug mode — the request is a bug, not a feature

Read by `/dev-workflow:feature` Stage 0.5 when the request is a bug. "Steps 1–5" are that stage's feature steps; `spec.md`, tiers and stages are the feature skill's.

Enter this branch on `--bug`, or when the request describes something that already
exists and is behaving wrong ("the orders endpoint 500s on an empty cart", "the total
is off after a refund"). If it is genuinely unclear which it is, ask in one line — the
two front ends diverge immediately, and correcting the mode later costs a stage.

**The unknown is different, so the stage is different.** A feature request's risk is
building the wrong thing; steps 1–5 above exist to pin down WHAT. A bug report's risk
is fixing the wrong PLACE: the symptom is visible and the cause is not, and a patch
aimed at the symptom passes every review in this workflow — reviewers check the code
against the plan, and the plan would say "stop the 500". Nothing downstream can catch
it. So this branch buys the cause before anything is planned, and it is yours: a
subagent that cannot reproduce and cannot ask will hand you a plausible cause.

1. **Reproduce it first, and paste the proof.** The smallest command, test or request
   that makes the bug happen, plus its actual output. Reproduce BEFORE you diagnose —
   a cause you reasoned out from reading code is a hypothesis, and this workflow will
   spend an implementation, a review and a user approval on it.
   **If you cannot reproduce it, STOP and go to the user** with what you tried and
   what you need (the failing input, the env, the log line, the version). Do not
   proceed on a report alone: an unreproducible bug has no way to prove it was fixed,
   which means Stage 4 has no Evidence to cite and the gate is measuring nothing.
   The repro output you capture here is the "before" half of that evidence — keep it
   verbatim.
2. **Localize, then name the root cause with evidence.** Give the `file:line` and say
   in one or two sentences why THAT code produces THIS symptom. Distinguish the two
   out loud: a null check that would suppress the crash is the symptom; the write
   that left the field null is the cause. Fixing the symptom is sometimes the right
   call — under time pressure, or when the cause sits in someone else's code — but it
   is then a decision the user makes at step 4, recorded as one, not a diagnosis you
   quietly stopped short of.
3. **State the blast radius.** What else reaches that code path, what else the same
   cause is plausibly breaking that nobody reported yet, and — the one that gets
   missed — **whether bad data was already written.** Fixing the code does not repair
   rows the bug already corrupted; if any exist, say so here, because that is a
   separate piece of work with its own risk and its own approval, never a silent
   extra in the fix.
4. **CHECKPOINT — only when something actually forks.** Stop and use
   `AskUserQuestion` if the root cause is uncertain, if the honest fix reaches beyond
   the reported symptom, if cause and symptom fixes are both defensible, or if there
   is data to repair. Otherwise state the repro, the cause and where the fix belongs,
   and keep going — the fix itself gets proposed where it normally is (inline for
   trivial, the architect above trivial), not here.
   **If the diagnosis shows there is no bug** — the behaviour is intended, or the
   caller is wrong — say that and stop. Do not build the change that would make the
   report true; that is a feature request, and it goes back through steps 1–5.
5. **Turn it into acceptance criteria** in `spec.md` 1b, same as any feature. The
   first one is always the regression, and it names the repro verbatim: "`pytest
   tests/test_cart.py::test_empty` fails on the current commit and passes after the
   fix". Add one criterion per behaviour that must NOT change — the callers from
   step 3 — because a fix that breaks a neighbour is the second most common way this
   goes wrong.
6. **Write section 1a of `spec.md`** — repro, root cause with `file:line`, blast
   radius, and (if any) the data-repair question and its answer. This is what makes
   the cause reviewable at the plan checkpoint instead of living only in this
   conversation; the coder and the reviewers get it quoted inline like everything
   else.

Then continue at Stage 0.8 — a bug fix is TRIVIAL by default, and usually stays there.

## Tier
**For a bug, the ROOT CAUSE sets the tier — not the severity of the symptom.** A
production outage caused by a one-line off-by-one is still one reviewable diff and
still trivial; urgency is a reason to move fast, not a reason to run more machinery.
Move up only when the cause says so: it sits in shared code many callers depend on,
or the fix changes a contract others rely on (**standard**); the bug IS a
vulnerability, or the cause crosses a trust boundary or a data model (**complex**).
Data already corrupted by the bug is not a tier signal — it is its own phase, with
its own `- Why separate:`, its own rollback point and its own approval, and it is
never folded into the code fix.

## Evidence
**A bug fix owes one artifact nothing else substitutes for: the before AND the
after.** The regression test or command must be shown FAILING on the unfixed code and
passing after — a test written after the fix and never seen red proves the code runs,
not that it fixes anything, and it is the single easiest thing to fool yourself with
here. You already captured the red half in Stage 0.5 step 1; the ledger cites that
output and the post-fix run, so this costs one extra paste, not one extra test run.
This is also the one place the "a declaration already enforces it" exemption (feature
skill, Stage 4) does NOT apply: if the fix turns out to be a validator or a config value, the artifact
is still the repro, run twice.
