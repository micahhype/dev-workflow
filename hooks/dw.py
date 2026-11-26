#!/usr/bin/env python3
"""`dw`: the one command that changes a feature's workflow state (state.json)."""
import argparse
import json
import os
import re
import sys

import _workflow
import approval as approval_rules
import checkpoint
import diff_budget
import evidence_guard
import legacy
import plan_guard
import shim
import state as workflow_state
from state import Corrupt, Refused

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAP_LINE = re.compile(r"^(?:-[ \t]*)?(MUST|SKIM|SKIP|ASSUME)[ \t]+(\S.*)$")
ROOT_ENV = "DEV_WORKFLOW_ROOT"
LEGACY_BACKUP = "phase-log.legacy.md"
ACTORS = ("orchestrator", "coder", "user")


def project_root():
    return os.environ.get(ROOT_ENV) or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def feature_dir(root, slug):
    if not SLUG.match(slug or ""):
        raise Refused("Not a feature slug: %r (lowercase letters, digits, dashes)." % slug)
    return os.path.join(root, _workflow.STATE_DIR, "features", slug)


def chosen_dir(root, args):
    return feature_dir(root, args.feature) if args.feature else active_dir(root)


def active_dir(root):
    directory, slug = _workflow.docs_dir(root)
    if slug is None:
        raise Refused('No active feature. Start one with: dw new <slug> "<title>"')
    return directory


def target_of(word):
    if word == workflow_state.FINAL:
        return word
    if not word.isdigit():
        raise Refused("Not a phase: %r. Use a phase number or `final`." % word)
    return int(word)


def named(word):
    return "The final review" if word == workflow_state.FINAL else "Phase %s" % word


def given_text(args):
    if args.file:
        with open(args.file, "r", encoding="utf-8") as source:
            return source.read()
    return "" if sys.stdin.isatty() else sys.stdin.read()


def change(root, args, edit):
    event = {"by": args.by, "do": args.command, "phase": event_phase(args)}
    return workflow_state.update(chosen_dir(root, args), edit, event)


def event_phase(args):
    word = getattr(args, "phase", None)
    return word if word in (None, "feature") else target_of(word)


# --- commands ---------------------------------------------------------------

def new(root, args):
    directory = feature_dir(root, args.slug)
    workflow_state.create(directory, workflow_state.new_state(args.slug, args.title, args.tier))
    with open(os.path.join(root, _workflow.STATE_DIR, "active"), "w", encoding="utf-8") as active:
        active.write(args.slug + "\n")
    shim.write(root)
    return "Created %s and made it the active feature." % args.slug


def phases(root, args):
    change(root, args, lambda state: workflow_state.set_phases(state, args.titles))
    return "Phases set: %d." % len(args.titles)


def add_phase(root, args):
    state = change(root, args, lambda state: workflow_state.add_phase(state, args.title))
    return "Added phase %d." % len(state["phases"])


def coded(root, args):
    record = {"changed": args.changed, "evidence": given_text(args)}
    change(root, args, lambda state: workflow_state.mark_coded(state, target_of(args.phase), record))
    return "%s coded." % named(args.phase)


def start_round(root, args):
    state = change(root, args, lambda state: workflow_state.start_round(state, target_of(args.phase)))
    rounds = workflow_state.section(state, target_of(args.phase))["rounds"]
    return "Round %d of %d started." % (rounds, workflow_state.MAX_ROUNDS)


def reviewed(root, args):
    summary, entries = parsed_map(given_text(args))
    review = {"entries": entries, "security_scanned": args.security}

    def edit(state):
        target = target_of(args.phase)
        workflow_state.mark_reviewed(state, target, review)
        if summary:
            workflow_state.section(state, target)["review_summary"] = summary

    change(root, args, edit)
    return "%s reviewed; waiting for the user's approval." % named(args.phase)


def parsed_map(text):
    """-> (summary, entries). An opening line that is not an entry is the totals summary."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = lines.pop(0) if lines and not MAP_LINE.match(lines[0]) else None
    entries = []
    for line in lines:
        entry = MAP_LINE.match(line)
        if not entry:
            raise Refused("Not a review-map line: %r. Start it with MUST, SKIM, SKIP or ASSUME." % line)
        entries.append({"tier": entry.group(1), "text": entry.group(2)})
    return summary, entries


def set_text(root, args):
    text = given_text(args).strip()

    def edit(state):
        if args.phase == "feature":
            workflow_state.set_feature_text(state, args.field, text)
        else:
            phase = workflow_state.section(state, target_of(args.phase))
            workflow_state.set_phase_text(phase, args.field, text)

    change(root, args, edit)
    return "Set %s on %s." % (args.field, args.phase)


def approve(root, args):
    if not args.said and os.environ.get("CLAUDECODE"):
        raise Refused("This records YOUR approval, so Claude must not run it bare. Run it in "
                      'your own shell, or relay the user\'s words: dw approve --said "<quote>"')
    if args.said and approval_rules.load_config(root)["mode"] == "direct":
        raise Refused("This project accepts direct approvals only: the user types "
                      "/dev-workflow:approve, or runs `! .dev-workflow/dw approve`.")
    approval = {"via": "user"}
    if args.said:
        approval = {"via": "relayed", "quote": args.said,
                    "prompted_at": approval_rules.prompted_at(root)}
    args.by = "orchestrator" if args.said else "user"

    if not args.phase:
        args.phase = str(current(loaded(root, args))["id"])
    change(root, args, lambda state: workflow_state.approve(state, target_of(args.phase), approval))
    return "%s approved (via %s)." % (named(args.phase), approval["via"])


def current(state):
    waiting = [phase for phase in workflow_state.sections(state) if phase["status"] != "approved"]
    if not waiting:
        raise Refused("Every phase of this feature is already approved.")
    return waiting[0]


def reopen(root, args):
    change(root, args, lambda state: workflow_state.reopen(state, target_of(args.phase)))
    return "%s reopened." % named(args.phase)


def diff(root, args):
    """Write the phase's diff where a reviewer without Bash can Read it."""
    number = target_of(args.phase)
    if number == workflow_state.FINAL:
        raise Refused("`dw diff` covers one phase. Brief the final review with the "
                      "changed files grouped by phase.")
    workflow_state.section(loaded(root, args), number)
    if not checkpoint.is_git_repo(root):
        raise Refused("Not a git repository, so there is no diff to write. Hand the "
                      "reviewer the changed files and line ranges instead.")
    directory = chosen_dir(root, args)
    slug = os.path.basename(directory)
    head, now = checkpoint.working_tree(root)
    base, since = diff_base(root, slug, number, head, args.since_review)
    text, files = diff_budget.patch(root, base, now)
    if not files:
        raise Refused("Nothing has changed since %s." % since)
    name = "phase-%d%s.diff" % (number, ".fix" if args.since_review else "")
    with open(os.path.join(directory, name), "w", encoding="utf-8") as out:
        out.write(text + "\n")
    diff_budget.remember_reviewed(root, slug, number, now)
    return diff_summary(os.path.join(_workflow.STATE_DIR, "features", slug, name), files, since)


def diff_base(root, slug, number, head, since_review):
    """-> (tree, what it is, in words)."""
    if since_review:
        tree = diff_budget.last_reviewed(root, slug, number)
        if not tree:
            raise Refused("No earlier `dw diff %d` to compare with. Run it without "
                          "--since-review." % number)
        return tree, "the last `dw diff %d`" % number
    tree = diff_budget.phase_base(root, slug, number)
    if tree:
        return tree, "the phase started"
    return (head or diff_budget.EMPTY_TREE,
            "HEAD (no phase baseline was recorded, so any earlier uncommitted work is included)")


def diff_summary(path, files, since):
    counted = [(int(a), int(d)) for a, d, _path in files if a.isdigit() and d.isdigit()]
    lines = ["Wrote %s: %d files, +%d -%d since %s." % (
        path, len(files), sum(a for a, _d in counted), sum(d for _a, d in counted), since)]
    lines += ["  +%s -%s  %s" % row for row in files]
    return "\n".join(lines)


def loaded(root, args):
    state = workflow_state.load(chosen_dir(root, args))
    if state is None:
        raise Refused("This feature has no state.json. Convert it with: dw import <slug>")
    return state


def status(root, args):
    state = loaded(root, args)
    if args.json:
        return json.dumps(state, indent=2)
    lines = ["%s (%s)" % (state["title"], state["slug"])]
    waiting = next((phase for phase in workflow_state.sections(state)
                    if phase["status"] != "approved"), None)
    for phase in workflow_state.sections(state):
        name = phase["title"] if workflow_state.is_final(phase) else (
            "Phase %s — %s" % (phase["id"], phase["title"]))
        lines.append("  [%-8s] %s%s" % (phase["status"], name, "  <- current" if phase is waiting else ""))
    return "\n".join(lines)


def check(root, args):
    """What the Stop hooks would refuse the turn for, without waiting for them to."""
    directory = chosen_dir(root, args)
    log = workflow_state.log_text(directory) or ""
    plan = _workflow.read(os.path.join(directory, "plan.md"))
    findings = plan_guard.document_findings(root, plan, log)
    waiting = evidence_guard.current_section(log)
    if waiting and evidence_guard.unproven(waiting[1]):
        findings.append("'%s' is reviewed but its evidence is empty." % waiting[0])
    if not findings:
        return "Nothing missing."
    return "Missing:\n" + "\n".join("- " + finding for finding in findings)


def import_legacy(root, args):
    directory = feature_dir(root, args.slug)
    log_path = os.path.join(directory, workflow_state.LOG_FILE)
    backup_path = os.path.join(directory, LEGACY_BACKUP)
    if workflow_state.load(directory) is not None:
        raise Refused("%s already has a state.json." % args.slug)
    log = _workflow.read(log_path)
    if log is None:
        raise Refused("%s has no phase-log.md to import." % args.slug)
    if os.path.exists(backup_path):
        raise Refused("%s already exists; move it away first." % backup_path)
    os.rename(log_path, backup_path)
    try:
        workflow_state.create(directory, legacy.state_from_log(log, args.slug))
    except Exception:
        os.rename(backup_path, log_path)
        raise
    return "Imported %s. The hand-written log is kept as %s." % (args.slug, LEGACY_BACKUP)


# --- parsing ----------------------------------------------------------------

def parser():
    top = argparse.ArgumentParser(prog="dw", description=__doc__)
    top.add_argument("--by", choices=ACTORS, default="orchestrator", help="who is acting")
    top.add_argument("--feature", help="a feature other than the active one, by slug")
    commands = top.add_subparsers(dest="command", required=True)

    def command(name, handler, *arguments, text=False):
        sub = commands.add_parser(name)
        for flags, options in arguments:
            sub.add_argument(*flags, **options)
        if text:
            sub.add_argument("--file", help="read the text from this file instead of stdin")
        sub.set_defaults(handler=handler)

    phase = (["phase"], {"help": "phase number, or `final`"})
    command("new", new, (["slug"], {}), (["title"], {}), (["--tier"], {"default": "trivial"}))
    command("phases", phases, (["titles"], {"nargs": "+"}))
    command("add-phase", add_phase, (["title"], {}))
    command("coded", coded, phase, (["--changed"], {"default": ""}), text=True)
    command("round", start_round, phase)
    command("reviewed", reviewed, phase, (["--security"], {"action": "store_true"}), text=True)
    command("set", set_text, (["phase"], {"help": "phase number, `final` or `feature`"}),
            (["field"], {}), text=True)
    command("approve", approve, (["phase"], {"nargs": "?"}), (["--said"], {}))
    command("reopen", reopen, phase)
    command("diff", diff, phase, (["--since-review"], {"action": "store_true"}))
    command("status", status, (["--json"], {"action": "store_true"}))
    command("check", check)
    command("import", import_legacy, (["slug"], {}))
    return top


def main(argv):
    args = parser().parse_args(argv)
    try:
        print(args.handler(project_root(), args))
    except (Refused, Corrupt) as problem:
        print("Refused: %s" % problem, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
