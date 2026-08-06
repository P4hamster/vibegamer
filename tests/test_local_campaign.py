import argparse
import json
import sys

from tower_referee.decision_log import export_decision_log
from tower_referee.local_campaign import (
    EventTailer,
    build_referee_command,
    discover_artifact,
    format_event,
)


def test_event_tailer_only_returns_new_records(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"event_type": "campaign_stage_started", "stage": 1}) + "\n",
        encoding="utf-8",
    )
    tailer = EventTailer()

    assert len(tailer.read(events)) == 1
    assert tailer.read(events) == []

    with events.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event_type": "campaign_stage_complete"}) + "\n")
    assert [item["event_type"] for item in tailer.read(events)] == [
        "campaign_stage_complete"
    ]


def test_format_event_keeps_milestones_and_drops_noisy_events():
    assert format_event({"event_type": "monitor_trigger"}) is None
    assert format_event(
        {
            "event_type": "campaign_stage_complete",
            "stage": 2,
            "map_id": "1",
            "won": True,
            "base_hp": 8,
        }
    ) == "[STAGE 2] map=1 WON hp=8"
    assert "model_request_failed" in format_event(
        {"event_type": "model_request_failed", "error": "timeout"}
    )


def test_discover_artifact_ignores_existing_directories(tmp_path):
    old = tmp_path / "experiment-campaign-kimi-old"
    old.mkdir()
    existing = {old}
    new = tmp_path / "experiment-campaign-kimi-new"
    new.mkdir()

    assert discover_artifact(
        tmp_path, "experiment-campaign-kimi-", existing
    ) == new


def test_build_referee_command_forwards_resume_artifact():
    args = argparse.Namespace(
        config="recording.json",
        model="Kimi",
        output="artifacts",
        resume_artifact="artifacts/old",
    )

    assert build_referee_command(args) == [
        sys.executable,
        "-m",
        "tower_referee.cli",
        "campaign-smoke",
        "--config",
        "recording.json",
        "--model",
        "Kimi",
        "--output",
        "artifacts",
        "--resume-artifact",
        "artifacts/old",
    ]


def test_decision_log_pairs_same_wave_requests_and_exports_reasoning(tmp_path):
    base = {"round_id": 1, "run_index": 1, "wave": 2, "model_id": "m"}
    records = [
        {
            **base,
            "event_type": "decision_received",
            "parse_status": "valid",
            "request_trace": [
                {
                    "phase": "planning",
                    "reasoning_content": "first reasoning",
                    "reasoning_content_chars": 15,
                    "reasoning_content_complete": True,
                }
            ],
        },
        {
            **base,
            "event_type": "decision",
            "analysis_summary": "first",
            "raw_response": '{"actions":[{"type":"noop"}]}',
        },
        {
            **base,
            "event_type": "decision",
            "analysis_summary": "local",
            "raw_response": '{"source":"local_plan_queue"}',
        },
        {
            **base,
            "event_type": "decision_received",
            "parse_status": "valid",
            "request_trace": [
                {
                    "phase": "planning",
                    "reasoning_content": "second reasoning",
                    "reasoning_content_chars": 16,
                    "reasoning_content_complete": False,
                }
            ],
        },
        {
            **base,
            "event_type": "decision",
            "analysis_summary": "second",
            "raw_response": '{"actions":[{"type":"noop"}]}',
        },
    ]
    events = tmp_path / "events.jsonl"
    events.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )

    output = export_decision_log(events, tmp_path / "decisions.md")
    markdown = output.read_text(encoding="utf-8")

    assert markdown.index("first reasoning") < markdown.index("second reasoning")
    assert markdown.count("first reasoning") == 1
    assert markdown.count("second reasoning") == 1
    assert "### Planning Reasoning" in markdown
    assert "- Complete: `False`" in markdown
