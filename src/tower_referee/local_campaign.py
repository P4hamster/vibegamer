from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from tower_referee.config import ExperimentConfig
from tower_referee.decision_log import export_decision_log


MILESTONE_EVENTS = {
    "campaign_stage_started",
    "campaign_stage_complete",
    "campaign_stage_invalid",
    "model_request_failed",
    "model_json_parse_failed",
    "decision_budget_exhausted",
    "native_step_watchdog_timeout",
}


class EventTailer:
    """Read newly appended JSONL records without loading the full audit log."""

    def __init__(self) -> None:
        self.offset = 0

    def read(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            while True:
                line_start = handle.tell()
                line = handle.readline()
                if not line:
                    break
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    # The recorder may still be appending this line. Retry it
                    # on the next poll instead of silently losing the event.
                    handle.seek(line_start)
                    break
            self.offset = handle.tell()
        return records


def format_event(record: dict[str, Any]) -> str | None:
    event = record.get("event_type")
    if event == "campaign_stage_started":
        return (
            f"[STAGE {record.get('stage')}] map={record.get('map_id')} "
            f"attempt={record.get('attempt')} started"
        )
    if event == "run_started":
        state = record.get("initial_state") or {}
        observer = state.get("observer_meta") or {}
        return (
            f"[GATE] map={record.get('map_id')} wave={state.get('wave')} "
            f"gold={state.get('gold')} hp={state.get('base_hp')} "
            f"towers={len(state.get('towers') or [])} "
            f"validated={observer.get('initial_state_validated')} "
            f"reset_attempt={observer.get('reset_attempt')} "
            f"unity_reopened={observer.get('unity_reopened')}"
        )
    if event == "decision_received" and record.get("parse_status") != "valid":
        return (
            f"[MODEL] wave={record.get('wave')} "
            f"parse_status={record.get('parse_status')}"
        )
    if event == "campaign_stage_complete":
        result = "WON" if record.get("won") else "LOST"
        return (
            f"[STAGE {record.get('stage')}] map={record.get('map_id')} "
            f"{result} hp={record.get('base_hp')}"
        )
    if event in MILESTONE_EVENTS:
        reason = record.get("reason") or record.get("error") or event
        return f"[ERROR] {event}: {str(reason)[:300]}"
    return None


def discover_artifact(
    output_root: Path,
    prefix: str,
    existing: set[Path],
) -> Path | None:
    candidates = [
        path
        for path in output_root.glob(f"{prefix}*")
        if path.is_dir() and path not in existing
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a TowerMind campaign with local, zero-LLM monitoring"
    )
    parser.add_argument(
        "--config",
        default="configs/experiment.official-six.recording.json",
    )
    parser.add_argument("--model", required=True, help="Model display name")
    parser.add_argument("--output", default="artifacts")
    parser.add_argument("--resume-artifact", default=None)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    return parser


def build_referee_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "tower_referee.cli",
        "campaign-smoke",
        "--config",
        args.config,
        "--model",
        args.model,
        "--output",
        args.output,
    ]
    if args.resume_artifact:
        command.extend(["--resume-artifact", args.resume_artifact])
    return command


def print_final_summary(artifact: Path) -> None:
    events_path = artifact / "events.jsonl"
    if events_path.is_file():
        decision_log = export_decision_log(events_path, artifact / "model_decisions.md")
        print(f"[DECISIONS] {decision_log.resolve()}", flush=True)
    campaign_path = artifact / "campaign_summary.json"
    validity_path = artifact / "validity.json"
    if validity_path.is_file():
        validity = json.loads(validity_path.read_text(encoding="utf-8"))
        print(
            f"[VALIDITY] status={validity.get('status')} "
            f"reason={validity.get('reason') or '-'}",
            flush=True,
        )
    if campaign_path.is_file():
        campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
        print(
            f"[RESULT] reached={campaign.get('reached_stages')}/"
            f"{campaign.get('total_stages')} "
            f"cleared={campaign.get('cleared_stages')}/"
            f"{campaign.get('total_stages')} "
            f"score={campaign.get('campaign_score')}",
            flush=True,
        )
    print(f"[ARTIFACT] {artifact.resolve()}", flush=True)


def main() -> None:
    args = build_parser().parse_args()
    config = ExperimentConfig.load(args.config)
    selected = [item for item in config.models if item.name == args.model]
    if len(selected) != 1:
        available = ", ".join(item.name for item in config.models)
        raise ValueError(f"Unknown model {args.model!r}; choose: {available}")

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    prefix = f"{config.experiment_id}-campaign-{args.model.lower()}-"
    existing = set(output_root.glob(f"{prefix}*"))
    poll_seconds = max(0.2, float(args.poll_seconds))
    log_fd, temporary_log = tempfile.mkstemp(
        prefix="tower-campaign-", suffix=".log", dir=output_root
    )
    artifact: Path | None = None
    process: subprocess.Popen[bytes] | None = None
    tailer = EventTailer()

    print(
        "[LOCAL MONITOR] No extra LLM is used. Keep recording and do not "
        "operate the game window.",
        flush=True,
    )
    try:
        with os.fdopen(log_fd, "wb") as runtime_log:
            process = subprocess.Popen(
                build_referee_command(args),
                stdout=runtime_log,
                stderr=subprocess.STDOUT,
            )
            while process.poll() is None:
                artifact = artifact or discover_artifact(
                    output_root, prefix, existing
                )
                if artifact is not None:
                    for record in tailer.read(artifact / "events.jsonl"):
                        message = format_event(record)
                        if message:
                            print(message, flush=True)
                time.sleep(poll_seconds)
        if artifact is not None:
            for record in tailer.read(artifact / "events.jsonl"):
                message = format_event(record)
                if message:
                    print(message, flush=True)
    except KeyboardInterrupt:
        print("[STOP] Forwarding interrupt to the referee...", flush=True)
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait()
    finally:
        artifact = artifact or discover_artifact(output_root, prefix, existing)
        log_path = Path(temporary_log)
        if artifact is not None and log_path.exists():
            shutil.move(str(log_path), artifact / "runtime.log")

    return_code = process.returncode if process is not None else 1
    if artifact is not None:
        print_final_summary(artifact)
        if return_code != 0:
            print(
                f"[FAILED] referee exit={return_code}; inspect "
                f"{artifact / 'runtime.log'}",
                file=sys.stderr,
            )
    else:
        print(
            f"[FAILED] No artifact was created; runtime log: {temporary_log}",
            file=sys.stderr,
        )
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
