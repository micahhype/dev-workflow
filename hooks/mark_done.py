#!/usr/bin/env python3
"""Tick `[x] USER APPROVED` on every open section of a feature the user already finished.

The CLI refuses under CLAUDECODE: the tick is the user's approval (a guard, not a security
boundary, as gate.py). The dashboard's POST route calls apply(), never main().
"""
import datetime
import os
import re
import stat
import sys
import tempfile

import _workflow

UNTICKED = "[ ] USER APPROVED"
TICKED = "[x] USER APPROVED"
NOTE = "- Marked done from the dashboard: %s"
USAGE = "usage: mark_done.py <project root> <feature slug>"
CHECKLIST_ITEM = re.compile(r"^\s*- \[ \] USER APPROVED")
REPORT_LINES = {
    "ticked": "ticked: %s",
    "skipped": "skipped: %s (no '" + UNTICKED + "' checkbox on its Status line or as a '- "
               + UNTICKED + "' item)",
}


class Refused(Exception):
    pass


class NotAFeature(Refused):
    pass


def apply(root, slug, today):
    """Tick the feature's open sections and write the log. -> report lines; raises Refused."""
    if slug not in feature_slugs(root):
        raise NotAFeature("%r is not a feature of %s (no .dev-workflow/features/%s/)."
                          % (slug, root, slug))
    path = phase_log_path(root, slug)
    expected_dir = os.path.join(os.path.realpath(root), _workflow.STATE_DIR, "features", slug)
    if os.path.islink(path) or os.path.realpath(os.path.dirname(path)) != expected_dir:
        raise Refused("%s or its phase-log.md is a symlink, so the write could land "
                      "outside this project." % slug)
    if not os.path.isfile(path):
        raise Refused("%s has no phase-log.md." % slug)
    new_log, report = mark_done(root, slug, today)
    if not report:
        return ["No open sections in %s. Nothing written." % slug]
    if new_log != read_log(path):
        write_atomically(path, new_log)
    return report


def mark_done(root, slug, today):
    log = read_log(phase_log_path(root, slug))
    preamble, sections = split_sections(log)
    marked_sections = []
    report = []
    for title, section in sections:
        marked_section, outcome = mark_section(section, today)
        marked_sections.append(marked_section)
        if outcome:
            report.append(REPORT_LINES[outcome] % title)
    return preamble + "".join(marked_sections), report


def phase_log_path(root, slug):
    return os.path.join(root, _workflow.STATE_DIR, "features", slug, "phase-log.md")


def read_log(path):
    # newline="" keeps a CRLF file CRLF when it is written back.
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def split_sections(log):
    headings = list(_workflow.PHASE_HEADING.finditer(log))
    if not headings:
        return log, []
    starts = [heading.start() for heading in headings] + [len(log)]
    sections = [(heading.group(1).strip(), log[starts[index]:starts[index + 1]])
                for index, heading in enumerate(headings)]
    return log[:starts[0]], sections


def mark_section(section, today):
    if _workflow.APPROVED.search(section):
        return section, None
    lines = section.splitlines(keepends=True)
    checkbox_index = next((index for index, line in enumerate(lines) if is_approval_checkbox(line)), None)
    if checkbox_index is None:
        return section, "skipped"
    newline = "\r\n" if "\r\n" in section else "\n"
    lines[checkbox_index] = lines[checkbox_index].replace(UNTICKED, TICKED, 1)
    insert_at = end_of_fields(lines)
    if not lines[insert_at - 1].endswith("\n"):
        lines[insert_at - 1] += newline
    lines.insert(insert_at, NOTE % today + newline)
    return "".join(lines), "ticked"


def is_approval_checkbox(line):
    is_on_status_line = line.startswith("- Status:") and UNTICKED in line
    return is_on_status_line or bool(CHECKLIST_ITEM.match(line))


def end_of_fields(lines):
    last_field = max(index for index, line in enumerate(lines) if line.startswith("- "))
    end = last_field + 1
    while end < len(lines) and lines[end][:1] in (" ", "\t") and lines[end].strip():
        end += 1
    return end


def feature_slugs(root):
    features_dir = os.path.join(root, _workflow.STATE_DIR, "features")
    if not os.path.isdir(features_dir):
        return []
    return [slug for slug in os.listdir(features_dir)
            if os.path.isdir(os.path.join(features_dir, slug))]


def write_atomically(path, text):
    mode = stat.S_IMODE(os.stat(path).st_mode)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".phase-log-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def main(argv):
    if os.environ.get("CLAUDECODE"):
        print("Refusing: this ticks YOUR approval, so Claude must not run it. "
              "Run the same command in your own terminal.", file=sys.stderr)
        return 1
    if len(argv) != 3:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        report = apply(argv[1], argv[2], datetime.date.today().isoformat())
    except Refused as refusal:
        print("Refusing: %s" % refusal, file=sys.stderr)
        return 1
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
