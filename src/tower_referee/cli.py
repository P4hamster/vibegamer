from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from dataclasses import replace
from pathlib import Path

from tower_referee.config import ExperimentConfig
from tower_referee.runner import ExperimentRunner


def load_local_env(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE entries without overriding the shell environment."""
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)
    # Volcengine calls the credential ARK_API_KEY in its console, while some
    # LiteLLM releases look for VOLCENGINE_API_KEY.
    if os.environ.get("ARK_API_KEY"):
        os.environ.setdefault("VOLCENGINE_API_KEY", os.environ["ARK_API_KEY"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the vibegamer TowerMind referee")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run all three experiment rounds")
    run.add_argument("--config", default="configs/experiment.example.json")
    run.add_argument("--output", default="artifacts")
    smoke = subparsers.add_parser("smoke", help="Run one selected model once")
    smoke.add_argument("--config", default="configs/experiment.official-six.json")
    smoke.add_argument("--model", required=True, help="Model display name")
    smoke.add_argument("--map", default=None, dest="map_id")
    smoke.add_argument("--waves", type=int, default=1)
    smoke.add_argument("--time-scale", type=float, default=None)
    smoke.add_argument("--width", type=int, default=None)
    smoke.add_argument("--height", type=int, default=None)
    smoke.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    smoke.add_argument(
        "--max-decisions",
        type=int,
        default=None,
        help="Override the model decision budget for this run",
    )
    smoke.add_argument("--hold-seconds", type=float, default=0.0)
    smoke.add_argument("--output", default="artifacts")
    campaign = subparsers.add_parser(
        "campaign-smoke",
        help="Run one selected model through the configured map campaign",
    )
    campaign.add_argument("--config", default="configs/experiment.official-six.json")
    campaign.add_argument("--model", required=True, help="Model display name")
    campaign.add_argument("--time-scale", type=float, default=None)
    campaign.add_argument("--width", type=int, default=None)
    campaign.add_argument("--height", type=int, default=None)
    campaign.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    campaign.add_argument(
        "--max-decisions",
        type=int,
        default=None,
        help="Override the model decision budget for this run",
    )
    campaign.add_argument("--hold-seconds", type=float, default=0.0)
    campaign.add_argument("--output", default="artifacts")
    campaign.add_argument(
        "--resume-artifact",
        default=None,
        help=(
            "Import completed winning stages from an interrupted campaign "
            "artifact and continue from the next map"
        ),
    )
    verify = subparsers.add_parser("verify-config", help="Validate configuration")
    verify.add_argument("--config", default="configs/experiment.example.json")
    return parser


def main() -> None:
    load_local_env()
    args = build_parser().parse_args()
    config = ExperimentConfig.load(args.config)
    if args.command == "verify-config":
        print(
            json.dumps(
                {
                    "ok": True,
                    "experiment_id": config.experiment_id,
                    "backend": config.backend,
                    "models": [item.name for item in config.models],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.command in {"smoke", "campaign-smoke"}:
        selected = tuple(item for item in config.models if item.name == args.model)
        if len(selected) != 1:
            available = ", ".join(item.name for item in config.models)
            raise ValueError(f"Unknown or ambiguous model {args.model!r}; choose: {available}")
        config = replace(
            config,
            experiment_id=(
                f"{config.experiment_id}-"
                f"{'campaign' if args.command == 'campaign-smoke' else 'smoke'}-"
                f"{args.model.lower()}-"
                f"{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            ),
            models=selected,
            runs_per_round=1,
            max_waves=max(1, getattr(args, "waves", config.max_waves)),
            towermind_time_scale=(
                max(0.1, args.time_scale)
                if args.time_scale is not None
                else config.towermind_time_scale
            ),
            towermind_screen_width=(
                max(320, args.width)
                if args.width is not None
                else config.towermind_screen_width
            ),
            towermind_screen_height=(
                max(240, args.height)
                if args.height is not None
                else config.towermind_screen_height
            ),
            towermind_fullscreen=(
                args.fullscreen
                if args.fullscreen is not None
                else config.towermind_fullscreen
            ),
            max_decisions_per_run=(
                max(1, args.max_decisions)
                if args.max_decisions is not None
                else config.max_decisions_per_run
            ),
            hold_after_run_seconds=max(0.0, args.hold_seconds),
        )
        runner = ExperimentRunner(config, args.output)
        if args.command == "campaign-smoke":
            dashboard = runner.run_campaign_smoke(args.resume_artifact)
            print(f"Campaign smoke complete: {dashboard.resolve()}")
        else:
            dashboard = runner.run_smoke(args.map_id)
            print(f"Smoke run complete: {dashboard.resolve()}")
        return
    dashboard = ExperimentRunner(config, args.output).run()
    print(f"Experiment complete: {dashboard.resolve()}")


if __name__ == "__main__":
    main()
