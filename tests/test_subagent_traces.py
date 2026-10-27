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
    }
    assert rows["dev-workflow:code-reviewer"]["trace_id"] == "shop:topup"
    assert rows["dev-workflow:planner"]["trace_id"] == "shop:session:s2"
    assert "1  dev-workflow:code-reviewer + dev-workflow:implementer" in result.stdout
    assert "1 filtered (non-plugin agents)" in result.stdout
    assert "2 runs with no usage" in result.stdout


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
    assert "6 found, 0 filtered (non-plugin agents), 2 read, 4 skipped" in result.stdout
    assert "2 lines skipped" in result.stdout


def test_missing_root_exits_2(tmp_path):
    result = run(tmp_path / "nope", tmp_path / "traces.jsonl")

    assert result.returncode == 2
    assert not (tmp_path / "traces.jsonl").exists()
