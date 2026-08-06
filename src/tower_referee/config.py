from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelConfig:
    name: str
    provider: str
    model: str
    api_base: str | None = None
    api_key_env: str | None = None
    omit_temperature: bool = False
    reasoning_effort: str | None = None
    provider_seed_mode: str = "best_effort"
    request_timeout_seconds: float | None = None
    request_params: dict[str, Any] = field(default_factory=dict)
    decision_pipeline: str = "single"
    planning_max_tokens: int | None = None
    action_max_tokens: int | None = None
    planning_request_params: dict[str, Any] = field(default_factory=dict)
    action_request_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    experiment_id: str
    backend: str
    runs_per_round: int
    seed: int
    fixed_map: str
    unseen_map: str
    max_waves: int
    models: tuple[ModelConfig, ...]
    temperature: float = 0.0
    provider_seed: int | None = None
    max_tokens: int = 900
    model_request_timeout_seconds: float = 30.0
    model_request_retries: int = 0
    towermind_executable: str | None = None
    towermind_time_scale: float = 20.0
    towermind_screen_width: int = 1600
    towermind_screen_height: int = 900
    towermind_quality_level: int = 2
    towermind_fullscreen: bool = False
    towermind_plugin_url: str | None = None
    towermind_plugin_required: bool = False
    hold_after_run_seconds: float = 0.0
    event_driven: bool = False
    max_decisions_per_run: int = 25
    monitor_max_steps: int = 600
    low_priority_event_debounce_seconds: float = 3.0
    # Map 0's fixed-script A/B reaches a native terminal at step 4999.
    # 12000 is deliberately >2x that measured run and also well beyond the
    # known premature wave-5 artifact at step 3776.
    watchdog_max_game_steps: int = 12000
    campaign_maps: tuple[str, ...] = ()
    campaign_transition_seconds: float = 0.0
    campaign_max_retries: int = 0
    level_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    evaluation_suite: str = "competition_v1"
    harness_version: str = "2.0"
    observation_mode: str = "semantic_structured"
    scaffold_id: str = "direct_action_v1"
    score_profile: str = "research_v2"

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentConfig":
        data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        models = tuple(ModelConfig(**item) for item in data.pop("models"))
        if "campaign_maps" in data:
            data["campaign_maps"] = tuple(str(item) for item in data["campaign_maps"])
        if len(models) != 6:
            raise ValueError(f"Exactly six models are required, got {len(models)}")
        config = cls(models=models, **data)
        if config.runs_per_round < 1:
            raise ValueError("runs_per_round must be >= 1")
        if config.backend not in {"sim", "towermind"}:
            raise ValueError("backend must be 'sim' or 'towermind'")
        if config.towermind_screen_width < 320:
            raise ValueError("towermind_screen_width must be >= 320")
        if config.towermind_screen_height < 240:
            raise ValueError("towermind_screen_height must be >= 240")
        if config.campaign_transition_seconds < 0:
            raise ValueError("campaign_transition_seconds must be >= 0")
        if config.campaign_max_retries < 0:
            raise ValueError("campaign_max_retries must be >= 0")
        if config.watchdog_max_game_steps < 1:
            raise ValueError("watchdog_max_game_steps must be >= 1")
        if config.model_request_timeout_seconds <= 0:
            raise ValueError("model_request_timeout_seconds must be > 0")
        invalid_timeouts = [
            item.name
            for item in config.models
            if item.request_timeout_seconds is not None
            and item.request_timeout_seconds <= 0
        ]
        if invalid_timeouts:
            raise ValueError(
                "request_timeout_seconds must be > 0 "
                f"(invalid models: {', '.join(invalid_timeouts)})"
            )
        if config.model_request_retries < 0:
            raise ValueError("model_request_retries must be >= 0")
        if config.low_priority_event_debounce_seconds < 0:
            raise ValueError("low_priority_event_debounce_seconds must be >= 0")
        invalid_pipelines = [
            item.name
            for item in config.models
            if item.decision_pipeline not in {"single", "plan_then_action"}
        ]
        if invalid_pipelines:
            raise ValueError(
                "decision_pipeline must be 'single' or 'plan_then_action' "
                f"(invalid models: {', '.join(invalid_pipelines)})"
            )
        invalid_phase_budgets = [
            item.name
            for item in config.models
            if (
                item.planning_max_tokens is not None
                and item.planning_max_tokens < 1
            )
            or (
                item.action_max_tokens is not None
                and item.action_max_tokens < 1
            )
        ]
        if invalid_phase_budgets:
            raise ValueError(
                "planning_max_tokens and action_max_tokens must be >= 1 "
                f"(invalid models: {', '.join(invalid_phase_budgets)})"
            )
        invalid_seed_modes = [
            item.name
            for item in config.models
            if item.provider_seed_mode not in {"off", "best_effort", "required"}
        ]
        if invalid_seed_modes:
            raise ValueError(
                "provider_seed_mode must be 'off', 'best_effort' or 'required' "
                f"(invalid models: {', '.join(invalid_seed_modes)})"
            )
        return config
