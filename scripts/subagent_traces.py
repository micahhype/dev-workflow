#!/usr/bin/env python3
"""Subagent traces from Claude Code transcripts, in coupling_map.py's field names.

Same-basename projects merge into one; no prompt text is written (secrets).

Usage: python scripts/subagent_traces.py [ROOT] [-o OUT] [--all-agents] [--top N] [--slowest N] [--since DATE]
Exit code 0 = done (malformed input skipped and counted), 2 = ROOT does not exist.
"""
import argparse
import glob
import itertools
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

PLUGIN_AGENT_PREFIX = "dev-workflow:"
FEATURE_SLUG = re.compile(r"\.dev-workflow/features/([A-Za-z0-9._-]+)")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
TOKEN_FIELDS = ("input_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens", "output_tokens")
TIME_KINDS = ("test", "lint", "read", "edit", "other")
READ_TOOLS = {"Read", "Grep", "Glob", "LS"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
TEST_COMMAND = re.compile(
    r"\b(jest|vitest|pytest|mocha|phpunit|rspec|go test|cargo test|forge test|bun test"
    r"|(npm|yarn|pnpm)( run)? (-s )?test)\b")
LINT_COMMAND = re.compile(
    r"\b(eslint|tsc|ruff|flake8|pylint|mypy|prettier|biome|golangci-lint|cargo clippy|stylelint)\b")
READ_COMMAND = re.compile(r"^\s*(cd [^;&|]+(&&|;)\s*)?(cat|sed -n|head|tail|grep|rg|ls|find|wc|nl)\b")


def main(argv=None):
    args = parse_args(argv)
    root = os.path.expanduser(args.root)
    if not os.path.isdir(root):
        print(f"ROOT does not exist: {root}", file=sys.stderr)
        return 2

    stats = Counter()
    rows = []
    for project_dir, session_id, transcript in iter_runs(root):
        stats["files_found"] += 1
        agent = read_meta(transcript)
        if agent is None:
            stats["files_skipped"] += 1
            continue
        if not args.all_agents and not agent.startswith(PLUGIN_AGENT_PREFIX):
            stats["files_filtered"] += 1
            continue
        run = parse_run(transcript, stats)
        if run is None:
            stats["files_skipped"] += 1
            continue
        if args.since and run["start"] < args.since:
            stats["files_before_since"] += 1
            continue
        stats["files_read"] += 1
        run["agent"] = agent
        rows.append(trace_row(run, project_dir, session_id))

    write_rows(rows, args.output)
    print_report(build_report(rows, args.top), stats)
    print_slowest(rows, args.slowest)
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Subagent traces from Claude Code transcripts.")
    parser.add_argument("root", nargs="?", default="~/.claude/projects", metavar="ROOT")
    parser.add_argument("-o", "--output", default="./traces.jsonl")
    parser.add_argument("--all-agents", action="store_true",
                        help="include agents from outside the dev-workflow plugin")
    parser.add_argument("--top", type=int, default=10, help="co-occurring pairs to list")
    parser.add_argument("--slowest", type=int, default=5, help="slowest turns to break down")
    parser.add_argument("--since", type=since_date, metavar="DATE",
                        help="only runs started on or after DATE (YYYY-MM-DD, UTC)")
    return parser.parse_args(argv)


def since_date(text):
    try:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text}")


def iter_runs(root):
    for transcript in sorted(glob.glob(os.path.join(root, "*", "*", "subagents", "agent-*.jsonl"))):
        session_dir = os.path.dirname(os.path.dirname(transcript))
        project_dir = os.path.dirname(session_dir)
        yield os.path.basename(project_dir), os.path.basename(session_dir), transcript


def read_meta(transcript):
    meta_path = transcript[:-len(".jsonl")] + ".meta.json"
    try:
        with open(meta_path, encoding="utf-8") as meta_file:
            meta = json.load(meta_file)
    except (OSError, ValueError, RecursionError):
        return None
    agent = meta.get("agentType") if isinstance(meta, dict) else None
    return agent if isinstance(agent, str) and agent else None


def parse_run(transcript, stats):
    run = {"start_ts": None, "start": None, "end": None,
           "prompt": None, "cwd": None, "model": None}
    usage_by_request = {}
    clock = {"waiting_since": None, "open": {}, "turns": []}
    lines = read_lines(transcript)
    if lines is None:
        return None
    for line_number, entry in read_entries(lines, stats):
        note_timestamp(run, entry.get("timestamp"))
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        if run["prompt"] is None and entry.get("type") == "user":
            run["prompt"] = prompt_text(message.get("content"))
        if not run["cwd"] and isinstance(entry.get("cwd"), str):
            run["cwd"] = entry["cwd"]
        if entry.get("type") == "assistant":
            run["model"] = message_model(message) or run["model"]
            record_usage(usage_by_request, message, request_key(entry, message, line_number))
        time_entry(clock, entry, message)

    if run["start"] is None:
        return None
    if not usage_by_request:
        stats["runs_without_usage"] += 1
    run["tokens"] = {field: sum(token_count(usage, field) for usage in usage_by_request.values())
                     for field in TOKEN_FIELDS}
    run["turns"] = [finished_turn(turn) for turn in clock["turns"]]
    run["active_ms"] = sum(turn["duration_ms"] for turn in run["turns"])
    run["model_ms"] = sum(turn["model_ms"] for turn in run["turns"])
    run["tool_ms"] = {kind: sum(turn["tool_ms"][kind] for turn in run["turns"]) for kind in TIME_KINDS}
    run["tool_calls"] = sum(turn["tool_calls"] for turn in run["turns"])
    return run


# A kept-alive agent (the coder across phases) gets each task as a user message; a
# turn runs from it to the turn's last line, so idle waits between phases count nowhere.
def time_entry(clock, entry, message):
    moment = parse_timestamp(entry.get("timestamp"))
    if moment is None:
        return
    content = message.get("content")
    blocks = [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []
    results = [block for block in blocks if block.get("type") == "tool_result"]
    if entry.get("type") == "user" and not results and is_new_task(entry):
        clock["turns"].append({"ts": entry["timestamp"], "start": moment, "end": moment,
                               "model_ms": 0, "tool_ms": Counter(), "tool_calls": 0})
    if not clock["turns"]:
        return
    turn = clock["turns"][-1]
    turn["end"] = moment
    if entry.get("type") == "assistant":
        if clock["waiting_since"] is not None:
            turn["model_ms"] += elapsed_ms(clock["waiting_since"], moment)
            clock["waiting_since"] = None
        for block in blocks:
            if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                clock["open"][block["id"]] = (moment, time_kind(block.get("name"), block.get("input")))
                turn["tool_calls"] += 1
    elif entry.get("type") == "user":
        clock["waiting_since"] = moment
        for block in results:
            started = clock["open"].pop(block.get("tool_use_id"), None)
            if started:
                turn["tool_ms"][started[1]] += elapsed_ms(started[0], moment)


def is_new_task(entry):
    # Meta lines are system reminders, save a message the coordinator sends mid-run.
    return not entry.get("isMeta") or isinstance(entry.get("origin"), dict)


def finished_turn(turn):
    return {"ts": turn["ts"], "duration_ms": elapsed_ms(turn["start"], turn["end"]),
            "model_ms": turn["model_ms"],
            "tool_ms": {kind: turn["tool_ms"][kind] for kind in TIME_KINDS},
            "tool_calls": turn["tool_calls"]}


def elapsed_ms(start, end):
    return max(0, round((end - start).total_seconds() * 1000))


def time_kind(tool, tool_input):
    if tool in READ_TOOLS:
        return "read"
    if tool in EDIT_TOOLS:
        return "edit"
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if tool != "Bash" or not isinstance(command, str):
        return "other"
    if TEST_COMMAND.search(command):
        return "test"
    if LINT_COMMAND.search(command):
        return "lint"
    if READ_COMMAND.search(command):
        return "read"
    return "other"


def read_lines(transcript):
    try:
        with open(transcript, encoding="utf-8", errors="replace") as transcript_file:
            return transcript_file.readlines()
    except OSError:
        return None


def read_entries(lines, stats):
    for line_number, line in enumerate(lines):
        entry = json_object(line)
        if entry is None:
            stats["bad_lines"] += 1
            continue
        yield line_number, entry


def json_object(line):
    try:
        entry = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return entry if isinstance(entry, dict) else None


def note_timestamp(run, timestamp):
    moment = parse_timestamp(timestamp)
    if moment is None:
        return
    if run["start"] is None:
        run["start_ts"], run["start"] = timestamp, moment
    run["end"] = moment


def parse_timestamp(timestamp):
    if not isinstance(timestamp, str):
        return None
    # fromisoformat only accepts a trailing "Z" from Python 3.11 on.
    try:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A naive time cannot be subtracted from an aware one.
    return moment if moment.tzinfo is not None else None


def prompt_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts = [block.get("text") for block in content
             if isinstance(block, dict) and block.get("type") == "text"]
    return "\n".join(text for text in texts if isinstance(text, str))


def message_model(message):
    model = message.get("model")
    # Claude Code logs error and interrupt lines as model "<synthetic>".
    is_real_model = isinstance(model, str) and not model.startswith("<")
    return model if is_real_model else None


def request_key(entry, message, line_number):
    for candidate in (entry.get("requestId"), message.get("id")):
        if isinstance(candidate, str) and candidate:
            return candidate
    return line_number


def record_usage(usage_by_request, message, request_key):
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return
    # A streamed request logs several lines with growing output_tokens; the last is final.
    usage_by_request[request_key] = usage


def token_count(usage, field):
    value = usage.get(field)
    is_count = isinstance(value, int) and not isinstance(value, bool)
    return value if is_count else 0


def trace_row(run, project_dir, session_id):
    project = project_name(run["cwd"], project_dir)
    duration = run["end"] - run["start"]
    return {
        "trace_id": trace_id(project, session_id, run["prompt"]),
        "project": project,
        "session_id": session_id,
        "agent": run["agent"],
        "ts": run["start_ts"],
        "duration_ms": round(duration.total_seconds() * 1000),
        **run["tokens"],
        "model": run["model"],
        "active_ms": run["active_ms"],
        "model_ms": run["model_ms"],
        "tool_ms": run["tool_ms"],
        "tool_calls": run["tool_calls"],
        "turns": run["turns"],
    }


def project_name(cwd, project_dir):
    if not cwd:
        return project_dir
    project_path = cwd.split("/.dev-workflow/")[0]
    return os.path.basename(project_path.rstrip("/")) or project_dir


def trace_id(project, session_id, prompt):
    match = FEATURE_SLUG.search(prompt or "")
    slug = match.group(1).rstrip(".") if match else ""
    if slug:
        return f"{project}:{slug}"
    return f"{project}:session:{session_id}"


def write_rows(rows, output):
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row) + "\n")


def build_report(rows, top):
    agents_by_trace = defaultdict(set)
    rows_by_agent = defaultdict(list)
    for row in rows:
        agents_by_trace[row["trace_id"]].add(row["agent"])
        rows_by_agent[row["agent"]].append(row)

    agents = [agent_summary(agent, agent_rows, agents_by_trace)
              for agent, agent_rows in rows_by_agent.items()]
    agents.sort(key=lambda summary: summary["runs"], reverse=True)

    pairs = Counter()
    for trace_agents in agents_by_trace.values():
        pairs.update(itertools.combinations(sorted(trace_agents), 2))
    return {"runs": len(rows), "traces": len(agents_by_trace), "agents": agents,
            "pairs": pairs.most_common(top)}


def agent_summary(agent, agent_rows, agents_by_trace):
    traces_with_agent = sum(1 for trace_agents in agents_by_trace.values() if agent in trace_agents)
    run_tokens = [sum(row[field] for field in TOKEN_FIELDS) for row in agent_rows]
    return {
        "agent": agent,
        "runs": len(agent_rows),
        "trace_share": traces_with_agent / len(agents_by_trace),
        "total_tokens": sum(run_tokens),
        "median_tokens": statistics.median(run_tokens),
        "median_duration_ms": statistics.median(row["duration_ms"] for row in agent_rows),
        **turn_medians([turn for row in agent_rows for turn in row["turns"]]),
    }


def turn_medians(turns):
    turns = turns or [{"duration_ms": 0, "model_ms": 0, "tool_calls": 0,
                       "tool_ms": dict.fromkeys(TIME_KINDS, 0)}]
    return {
        "median_turn_ms": statistics.median(turn["duration_ms"] for turn in turns),
        "median_model_ms": statistics.median(turn["model_ms"] for turn in turns),
        "median_tool_ms": {kind: statistics.median(turn["tool_ms"][kind] for turn in turns)
                           for kind in TIME_KINDS},
        "median_tool_calls": statistics.median(turn["tool_calls"] for turn in turns),
    }


def print_report(report, stats):
    print(f"{report['runs']} subagent runs in {report['traces']} traces\n")
    print(f"{'agent':<40} {'runs':>6} {'traces':>7} {'total tok':>13} {'median tok':>11} {'median s':>9}")
    for summary in report["agents"]:
        print(f"{printable(summary['agent']):<40} {summary['runs']:>6} {summary['trace_share']:>7.0%} "
              f"{summary['total_tokens']:>13,} {round(summary['median_tokens']):>11,} "
              f"{summary['median_duration_ms'] / 1000:>9.1f}")

    print(f"\nWhere the time goes, median minutes per turn\n{'agent':<40} {'turn':>6} {'model':>6} "
          + " ".join(f"{kind:>6}" for kind in TIME_KINDS) + f" {'calls':>6}")
    for summary in report["agents"]:
        tool_ms = summary["median_tool_ms"]
        print(f"{printable(summary['agent']):<40} {minutes(summary['median_turn_ms']):>6} "
              f"{minutes(summary['median_model_ms']):>6} "
              + " ".join(f"{minutes(tool_ms[kind]):>6}" for kind in TIME_KINDS)
              + f" {round(summary['median_tool_calls']):>6}")

    print("\nMost common pairs in one trace")
    for (first, second), count in report["pairs"]:
        print(f"{count:>6}  {printable(first)} + {printable(second)}")

    print(f"\nTranscripts: {stats['files_found']} found, "
          f"{stats['files_filtered']} filtered (non-plugin agents), "
          f"{stats['files_before_since']} before --since, {stats['files_read']} read, "
          f"{stats['files_skipped']} skipped (unreadable meta or transcript, or no timestamp); "
          f"{stats['bad_lines']} lines skipped; "
          f"{stats['runs_without_usage']} runs with no usage (format drift?)")


def print_slowest(rows, count):
    turns = [(turn, row) for row in rows for turn in row["turns"]]
    if count <= 0 or not turns:
        return
    print(f"\nSlowest turns (one task or phase each), minutes; tool time sums parallel calls\n"
          f"{'wall':>6} {'model':>6} " + " ".join(f"{kind:>6}" for kind in TIME_KINDS)
          + f" {'calls':>6}  agent, trace, start")
    for turn, row in sorted(turns, key=lambda pair: pair[0]["duration_ms"], reverse=True)[:count]:
        print(f"{minutes(turn['duration_ms']):>6} {minutes(turn['model_ms']):>6} "
              + " ".join(f"{minutes(turn['tool_ms'][kind]):>6}" for kind in TIME_KINDS)
              + f" {turn['tool_calls']:>6}  {printable(row['agent'])}, "
              f"{printable(row['trace_id'])}, {printable(str(turn['ts']))}")


def minutes(ms):
    return f"{ms / 60000:.1f}"


def printable(text):
    return CONTROL_CHARS.sub("?", text)


if __name__ == "__main__":
    sys.exit(main())
