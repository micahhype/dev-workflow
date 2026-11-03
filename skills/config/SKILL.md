---
name: config
description: Show the dev-workflow plugin's effective configuration for this project — every guard knob, where its value came from (default, file, or environment), and which config lines are silently doing nothing. Can also set a value.
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/../../hooks/config.py" show), Bash(python3 "${CLAUDE_SKILL_DIR}/../../hooks/config.py" set:*)
---

Report — and optionally change — how this project has configured the plugin.

The CLI is `python3 "${CLAUDE_SKILL_DIR}/../../hooks/config.py" <cmd>` (this resolves
to the plugin's `hooks/config.py`). It imports the guards themselves rather than
restating their defaults, so its report cannot drift from the hooks that are actually
running. Never answer this from memory or by reading the JSON files yourself: the
whole point is the gap between what a file SAYS and what the guards DO, and only the
CLI computes that.

## Showing

Run exactly:
```
python3 "${CLAUDE_SKILL_DIR}/../../hooks/config.py" show
```

Present the output as a short table per section. Two things carry the value here, so
do not flatten them away:

- **The `PROBLEMS` block, if there is one — lead with it.** Every guard falls back to
  its defaults when a config file will not parse, and says nothing; a `!` line means
  the project believes it configured something that is not happening. Quote the line
  and say plainly what is running instead.
- **The source column.** `default` / `file` / `env <VAR>` / `file, IGNORED`. That last
  one is the interesting case: the key was written, the guard read it, and the value
  is the default anyway — a wrong type, or a regex that will not compile.

If nothing is overridden and there are no problems, say so in one line rather than
reprinting a wall of defaults: the project is on stock settings.

## Setting

Only when the user asks for a change. Run:
```
python3 "${CLAUDE_SKILL_DIR}/../../hooks/config.py" set <key> <value>
```

Keys: `comment-guard.enabled`, `comment-guard.density.floor`,
`comment-guard.density.min_ratio`, `comment-guard.max_block`, `test-guard.enabled`, `test-guard.checks.fakes`,
`test-guard.checks.assertions`, `test-guard.max_empty_args`, `plan-guard.pr_cap` (`0` = off),
`models.<agent>`.
Values: `on` / `off`, a number, a model alias (`opus`, `sonnet`, `haiku`, `fable`,
`inherit`) or a `claude-*` id, or `default` to drop the key.

The file is a diff against the defaults, so a value equal to its default is removed
rather than written — that is intended, not a failure. The command refuses to write
over a file it cannot parse; when it does, tell the user to fix or delete that file
rather than trying to repair it yourself.

`allow` patterns are not settable here — a regex needs to be read before it is
trusted. Edit the JSON directly and re-run `show` to confirm the pattern compiled.

## What this cannot change

`.approval-gate` and `.dev-workflow/active` appear in the report under *workflow
state*, not configuration. The gate especially: a hook denies any attempt to write it
from a Claude tool call, and while it says `LOCKED` no Bash runs at all. Only the user
can move it, from their own shell:
```
! echo UNLOCKED > .approval-gate
```

Do not edit any config file directly in this skill — use the CLI, so the written file
and the reported state cannot disagree.
