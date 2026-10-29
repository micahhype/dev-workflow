"""subagent_traces.py: traces.jsonl + usage report from subagent transcripts."""
import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "subagent_traces.py")
CWD = "/data/projects/shop/.dev-workflow/features/topup"
FEATURE_PROMPT = "Implement Phase 1. Feature dir: /data/projects/shop/.dev-workflow/features/topup/"


def run(root, out, *args):
    return subprocess.run([sys.executable, SCRIPT, str(root), "-o", str(out), *args],
                          capture_output=True, text=True)


def make_run(transcript, agent_type, lines):
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(
        "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n")
    meta_path(transcript).write_text(json.dumps({"agentType": agent_type}))


def meta_path(transcript):
    return transcript.with_name(transcript.stem + ".meta.json")


def user(content, ts="2026-10-20T04:00:00.000Z"):
    return {"type": "user", "timestamp": ts, "cwd": CWD, "message": {"content": content}}


def assistant(ts, output_tokens, request_id="req_1"):
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 100,
             "cache_read_input_tokens": 1000, "output_tokens": output_tokens}
    return {"type": "assistant", "timestamp": ts, "requestId": request_id,
            "message": {"model": "claude-opus-5-5", "id": "msg_1", "usage": usage}}


def read_rows(out):
    return [json.loads(line) for line in out.read_text().splitlines()]


def test_runs_become_traces_with_per_request_usage_and_pairs(tmp_path):
    root, out = tmp_path / "projects", tmp_path / "out" / "traces.jsonl"
    session_1 = root / "-data-projects-shop" / "s1" / "subagents"
    session_2 = root / "-data-projects-shop" / "s2" / "subagents"
    synthetic = {"type": "assistant", "timestamp": "2026-10-20T04:00:02.500Z",
                 "message": {"model": "<synthetic>"}}
    make_run(session_1 / "agent-a1.jsonl", "dev-workflow:implementer", [
        user(FEATURE_PROMPT),
        assistant("2026-10-20T04:00:01.000Z", 16),
        assistant("2026-10-20T04:00:02.500Z", 155),
        synthetic,
    ])
    make_run(session_1 / "agent-a2.jsonl", "dev-workflow:code-reviewer",
             [user([{"type": "text", "text": "Review .dev-workflow/features/topup."}])])
    make_run(session_2 / "agent-a3.jsonl", "dev-workflow:planner",
             [user("Write .dev-workflow/features/<slug>/plan.md")])
    make_run(session_2 / "agent-a4.jsonl", "Explore", [user("look around")])

    result = run(root, out)

    assert result.returncode == 0, result.stderr
    rows = {row["agent"]: row for row in read_rows(out)}
    assert set(rows) == {"dev-workflow:implementer", "dev-workflow:code-reviewer",
                         "dev-workflow:planner"}
    implementer = rows["dev-workflow:implementer"]
    assert implementer == {
        "trace_id": "shop:topup", "project": "shop", "session_id": "s1",
        "agent": "dev-workflow:implementer", "ts": "2026-10-20T04:00:00.000Z",
        "duration_ms": 2500, "input_tokens": 2, "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 1000, "output_tokens": 155, "model": "claude-opus-5-5",
        "active_ms": 2500, "model_ms": 1000, "tool_calls": 0,
        "tool_ms": {"test": 0, "lint": 0, "read": 0, "edit": 0, "other": 0},
        "turns": [{"ts": "2026-10-20T04:00:00.000Z", "duration_ms": 2500, "model_ms": 1000,
                   "tool_calls": 0,
                   "tool_ms": {"test": 0, "lint": 0, "read": 0, "edit": 0, "other": 0}}],
    }
    assert rows["dev-workflow:code-reviewer"]["trace_id"] == "shop:topup"
    assert rows["dev-workflow:planner"]["trace_id"] == "shop:session:s2"
    assert "1  dev-workflow:code-reviewer + dev-workflow:implementer" in result.stdout
    assert "1 filtered (non-plugin agents)" in result.stdout
    assert "2 runs with no usage" in result.stdout


def tool_use(ts, tool_id, name, tool_input):
    content = [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]
    return {"type": "assistant", "timestamp": ts, "message": {"content": content}}


def tool_result(ts, tool_id):
    content = [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}]
    return {"type": "user", "timestamp": ts, "message": {"content": content}}


def test_each_task_is_a_turn_with_model_and_tool_time_by_kind(tmp_path):
    root, out = tmp_path / "projects", tmp_path / "traces.jsonl"
    reminder = {**user("<system-reminder>hand back</system-reminder>", ts="2026-10-20T04:00:00Z"),
                "isMeta": True}
    review_round = {**user("Fix these", ts="2026-10-20T05:20:00Z"), "isMeta": True,
                    "origin": {"kind": "coordinator"}}
    make_run(root / "proj" / "s1" / "subagents" / "agent-c.jsonl", "dev-workflow:coder", [
        user(FEATURE_PROMPT, ts="2026-10-20T04:00:00Z"),
        reminder,
        tool_use("2026-10-20T04:00:10Z", "t1", "Read", {"file_path": "a.ts"}),
        tool_result("2026-10-20T04:00:11Z", "t1"),
        tool_use("2026-10-20T04:00:20Z", "t2", "Bash", {"command": "cd /p && yarn -s jest src/a"}),
        tool_result("2026-10-20T04:02:20Z", "t2"),
        tool_use("2026-10-20T04:02:30Z", "t3", "Bash", {"command": "npx eslint src/a.ts"}),
        tool_result("2026-10-20T04:03:30Z", "t3"),
        assistant("2026-10-20T04:03:40Z", 9),
        user("Implement Phase 2", ts="2026-10-20T05:00:00Z"),
        tool_use("2026-10-20T05:00:30Z", "t4", "Edit", {"file_path": "a.ts"}),
        tool_result("2026-10-20T05:00:31Z", "t4"),
        tool_use("2026-10-20T05:00:40Z", "t5", "Bash", {"command": "sed -n 1,20p a.ts"}),
        tool_result("2026-10-20T05:00:42Z", "t5"),
        review_round,
        tool_use("2026-10-20T05:20:05Z", "t6", "Bash", {"command": "make deploy"}),
        tool_result("2026-10-20T05:20:08Z", "t6"),
    ])

    result = run(root, out, "--slowest", "1")

    assert result.returncode == 0, result.stderr
    [row] = read_rows(out)
    phase_1, phase_2, review = row["turns"]
    assert phase_1["duration_ms"] == 220_000
    assert phase_1["model_ms"] == 39_000
    assert phase_1["tool_ms"] == {"test": 120_000, "lint": 60_000, "read": 1000, "edit": 0, "other": 0}
    assert phase_2["tool_ms"]["edit"] == 1000 and phase_2["tool_ms"]["read"] == 2000
    assert review["ts"] == "2026-10-20T05:20:00Z" and review["tool_ms"]["other"] == 3000
    assert row["active_ms"] == 220_000 + 42_000 + 8_000
    assert row["tool_calls"] == 6
    slowest = result.stdout.split("Slowest turns")[1].splitlines()[2].split()
    assert slowest[0] == "3.7" and slowest[2] == "2.0" and slowest[-3:-1] == ["dev-workflow:coder,", "shop:topup,"]


def test_malformed_input_is_skipped_and_counted(tmp_path):
    root, out = tmp_path / "projects", tmp_path / "traces.jsonl"
    session = root / "proj" / "s1" / "subagents"
    odd_request_id = assistant("2026-10-20T04:00:01Z", 5, request_id={"not": "a string"})
    make_run(session / "agent-good.jsonl", "dev-workflow:implementer",
             [user("hi", ts="2026-10-20T04:00:00"), "{not json", "[1, 2]", odd_request_id])
    make_run(session / "agent-badmeta.jsonl", "dev-workflow:implementer", [user("hi")])
    meta_path(session / "agent-badmeta.jsonl").write_text("{oops")
    make_run(session / "agent-nots.jsonl", "dev-workflow:implementer",
             [{"type": "user", "timestamp": "yesterday", "message": {"content": "hi"}}])
    make_run(session / "agent-other.jsonl", "Explore", [user("hi")])
    (session / "agent-nometa.jsonl").write_text(json.dumps(user("x")))
    (session / "agent-dir.jsonl").mkdir()
    meta_path(session / "agent-dir.jsonl").write_text(json.dumps({"agentType": "dev-workflow:coder"}))

    result = run(root, out, "--all-agents")

    assert result.returncode == 0, result.stderr
    rows = {row["agent"]: row for row in read_rows(out)}
    assert sorted(rows) == ["Explore", "dev-workflow:implementer"]
    assert rows["dev-workflow:implementer"]["ts"] == "2026-10-20T04:00:01Z"
    assert rows["dev-workflow:implementer"]["output_tokens"] == 5
    assert "6 found, 0 filtered (non-plugin agents), 0 before --since, 2 read, 4 skipped" in result.stdout
    assert "2 lines skipped" in result.stdout


def test_since_keeps_only_runs_started_on_or_after_the_date(tmp_path):
    root, out = tmp_path / "projects", tmp_path / "traces.jsonl"
    session = root / "proj" / "s1" / "subagents"
    make_run(session / "agent-old.jsonl", "dev-workflow:coder", [user("a", ts="2026-10-28T23:59:59Z")])
    make_run(session / "agent-new.jsonl", "dev-workflow:coder", [user("b", ts="2026-10-29T00:00:00Z")])

    result = run(root, out, "--since", "2026-10-29")

    assert result.returncode == 0, result.stderr
    assert [row["ts"] for row in read_rows(out)] == ["2026-10-29T00:00:00Z"]
    assert "1 before --since, 1 read" in result.stdout
    assert run(root, out, "--since", "yesterday").returncode == 2


def test_missing_root_exits_2(tmp_path):
    result = run(tmp_path / "nope", tmp_path / "traces.jsonl")

    assert result.returncode == 2
    assert not (tmp_path / "traces.jsonl").exists()
