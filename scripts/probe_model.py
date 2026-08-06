"""Probe one configured model without starting TowerMind."""

from __future__ import annotations

import argparse
import time

from tower_referee.cli import load_local_env
from tower_referee.config import ExperimentConfig
from tower_referee.models import build_model
from tower_referee.schema import GameState, HeroState


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.official-six.json")
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    load_local_env()
    config = ExperimentConfig.load(args.config)
    selected = next(item for item in config.models if item.name == args.model)
    model = build_model(
        selected,
        config.seed,
        config.temperature,
        config.max_tokens,
        request_timeout=(
            selected.request_timeout_seconds
            if selected.request_timeout_seconds is not None
            else config.model_request_timeout_seconds
        ),
        request_retries=config.model_request_retries,
        provider_seed=config.provider_seed,
    )
    state = GameState(
        wave=0,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=240,
        build_sites=[(-0.23, 0.22), (1.35, 0.39), (2.48, -0.9)],
        available_actions=["build", "move_hero", "noop"],
        hero=HeroState(position=(0, 0), hp=1600, max_hp=1600),
        game_rules={
            "tower_costs": {"archer": 120, "magician": 110, "knight": 100}
        },
    )
    started = time.monotonic()
    decision = model.decide(state)
    elapsed = time.monotonic() - started
    trace = decision.request_trace[-1] if decision.request_trace else {}
    phases = [
        {
            "phase": item.get("phase"),
            "response_model": item.get("response_model"),
            "finish_reason": item.get("finish_reason"),
            "reasoning_effort": item.get("reasoning_effort"),
            "max_tokens": item.get("max_tokens"),
            "reasoning_content_chars": item.get("reasoning_content_chars", 0),
            "reasoning_content_complete": item.get(
                "reasoning_content_complete"
            ),
            "input_chars": item.get("input_chars"),
            "full_input_chars": item.get("full_input_chars"),
        }
        for item in decision.request_trace
    ]
    print(
        {
            "model": model.name,
            "configured_model": model.model_id,
            "response_model": trace.get("response_model"),
            "seconds": round(elapsed, 2),
            "finish_reason": trace.get("finish_reason"),
            "reasoning_content_chars": trace.get("reasoning_content_chars", 0),
            "reasoning_content_complete": trace.get("reasoning_content_complete"),
            "parse_status": decision.parse_status,
            "reason": decision.analysis_summary,
            "actions": [action.type for action in decision.actions],
            "standing_orders": (
                decision.standing_orders is not None
            ),
            "has_raw_output": bool(decision.raw_response),
            "request_phases": phases,
        }
    )


if __name__ == "__main__":
    main()
