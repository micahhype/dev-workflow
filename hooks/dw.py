#!/usr/bin/env python3
"""`dw`: the one command that changes a feature's workflow state (state.json)."""
import argparse
import json
import os
import re
import sys

import _workflow
import legacy
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
    return workflow_state.update(active_dir(root), edit, event)


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
    approval = {"via": "relayed", "quote": args.said} if args.said else {"via": "user"}
    args.by = "orchestrator" if args.said else "user"

    if not args.phase:
        args.phase = str(current(loaded(root))["id"])
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


def loaded(root):
    state = workflow_state.load(active_dir(root))
    if state is None:
        raise Refused("The active feature has no state.json. Convert it with: dw import <slug>")
    return state


def status(root, args):
    state = loaded(root)
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
    command("status", status, (["--json"], {"action": "store_true"}))
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
