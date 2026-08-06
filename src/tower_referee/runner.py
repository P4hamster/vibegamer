from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

from tower_referee.config import ExperimentConfig
from tower_referee.dashboard import write_campaign_dashboard, write_dashboard
from tower_referee.game.base import GameAdapter, InvalidInitialStateError
from tower_referee.game.sim import SimulatedTowerDefense
from tower_referee.game.towermind import TowerMindAdapter
from tower_referee.models import ModelAdapter, build_model
from tower_referee.plan_queue import ActionPlanQueue
from tower_referee.recorder import Recorder
from tower_referee.schema import (
    ActionRejection,
    Decision,
    GameState,
    RunOutcome,
    RunSummary,
    TerminalSnapshot,
)
from tower_referee.scoring import score_all, score_campaign
from tower_referee.validator import ActionValidator


class ExperimentRunner:
    def __init__(
        self,
        config: ExperimentConfig,
        output_root: str | Path = "artifacts",
        game_factory: Callable[[], GameAdapter] | None = None,
    ) -> None:
        self.config = config
        self.output_root = Path(output_root)
        self.recorder = Recorder(self.output_root, config.experiment_id)
        self.validator = ActionValidator()
        self.game_factory = game_factory or self._default_game_factory
        self.models = [
            build_model(
                item,
                config.seed,
                config.temperature,
                config.max_tokens,
                request_timeout=(
                    item.request_timeout_seconds
                    if item.request_timeout_seconds is not None
                    else config.model_request_timeout_seconds
                ),
                request_retries=config.model_request_retries,
                provider_seed=config.provider_seed,
            )
            for item in config.models
        ]
        self.memories: dict[str, str] = {}
        self.recorder.write_manifest(
            {
                "experiment_id": config.experiment_id,
                "evaluation_suite": config.evaluation_suite,
                "harness_version": config.harness_version,
                "observation_mode": config.observation_mode,
                "scaffold_id": config.scaffold_id,
                "score_profile": config.score_profile,
                "config": asdict(config),
                "metric_policy": {
                    "research_metrics": [
                        "won",
                        "completion_ratio",
                        "base_hp_ratio",
                        "enemies_leaked",
                        "damage_per_gold",
                        "unspent_gold_ratio",
                        "action_validity_rate",
                        "decision_count",
                    ],
                    "score": (
                        "节目展示指数：60%关卡进度 + 20%基地生命 "
                        "+ 10%动作合法率 + 10%通关；不作为单一研究结论"
                    ),
                },
                "control_attribution": {
                    "strategic_decisions": "configured model adapter",
                    "conditional_plan_execution": "local approved plan queue",
                    "hero_knight_reinforcement_micro": (
                        "local deterministic tactics controller, only after "
                        "the model supplies standing_orders"
                    ),
                },
                "native_step_watchdog": {
                    "max_game_steps": config.watchdog_max_game_steps,
                    "basis": (
                        "Map 0 fixed-script A/B native terminal: step 4999; "
                        "known premature wave-5 artifact: step 3776. The 12000 "
                        "default is >2x the confirmed terminal and uses native "
                        "game steps, never wall-clock time."
                    ),
                    "timeout_outcome": "invalid",
                },
            }
        )

    def run(self) -> Path:
        for round_id in (1, 2, 3):
            map_id = self.config.fixed_map if round_id < 3 else self.config.unseen_map
            for run_index in range(1, self.config.runs_per_round + 1):
                for model in self.models:
                    summary = self._run_one(
                        model,
                        round_id,
                        run_index,
                        map_id,
                        completion_mode="full",
                    )
                    self.recorder.add_summary(summary)
            if round_id == 1:
                self._create_private_reviews()
        score_all(self.recorder.summaries)
        self.recorder.write_summaries()
        return write_dashboard(self.recorder.root, self.recorder.summaries)

    def run_smoke(self, map_id: str | None = None) -> Path:
        """Run one model once without review/generalization rounds."""
        if len(self.models) != 1:
            raise ValueError("Smoke runs require exactly one selected model")
        summary = self._run_one(
            self.models[0],
            round_id=1,
            run_index=1,
            map_id=map_id or self.config.fixed_map,
            completion_mode="requested_waves",
        )
        self.recorder.add_summary(summary)
        score_all(self.recorder.summaries)
        self._write_single_run_validity(summary)
        self.recorder.write_summaries()
        return write_dashboard(self.recorder.root, self.recorder.summaries)

    def run_campaign_smoke(
        self, resume_artifact: str | Path | None = None
    ) -> Path:
        """Run one model through ordered maps, stopping at its first failed map."""
        if len(self.models) != 1:
            raise ValueError("Campaign smoke runs require exactly one selected model")
        if not self.config.campaign_maps:
            raise ValueError("campaign_maps must contain at least one map")
        model = self.models[0]
        stage = 1
        if resume_artifact is not None:
            stage = self._restore_campaign_resume(resume_artifact, model)
        game = self.game_factory()
        retries: dict[int, int] = {}
        campaign_invalid_reason: str | None = None
        try:
            while stage <= len(self.config.campaign_maps):
                map_id = self.config.campaign_maps[stage - 1]
                attempt = retries.get(stage, 0) + 1
                self.recorder.event(
                    "campaign_stage_started",
                    model=model.name,
                    model_id=model.model_id,
                    stage=stage,
                    map_id=map_id,
                    attempt=attempt,
                )
                try:
                    summary = self._run_one(
                        model,
                        round_id=stage,
                        run_index=attempt,
                        map_id=map_id,
                        fog_of_war=False,
                        game=game,
                        completion_mode="full",
                    )
                except InvalidInitialStateError as exc:
                    campaign_invalid_reason = exc.reason
                    self.recorder.event(
                        "campaign_stage_invalid",
                        model=model.name,
                        model_id=model.model_id,
                        stage=stage,
                        map_id=map_id,
                        attempt=attempt,
                        reason=exc.reason,
                        details=exc.details,
                        model_called=False,
                    )
                    self.recorder.write_validity(
                        "invalid",
                        reason=exc.reason,
                        details={
                            "stage": stage,
                            "map_id": map_id,
                            **exc.details,
                        },
                    )
                    break
                self.recorder.add_summary(summary)
                if not summary.outcome_valid:
                    campaign_invalid_reason = (
                        summary.invalid_reason or f"stage outcome is {summary.outcome}"
                    )
                    self.recorder.event(
                        "campaign_stage_invalid",
                        model=model.name,
                        model_id=model.model_id,
                        stage=stage,
                        map_id=map_id,
                        attempt=attempt,
                        reason=campaign_invalid_reason,
                        terminal_confirmed=summary.terminal_confirmed,
                        terminal_interrupted=summary.terminal_interrupted,
                        score_eligible=summary.score_eligible,
                    )
                    self.recorder.write_validity(
                        "invalid",
                        reason=campaign_invalid_reason,
                        details={
                            "stage": stage,
                            "map_id": map_id,
                            "outcome": summary.outcome,
                            "outcome_valid": summary.outcome_valid,
                            "terminal_confirmed": summary.terminal_confirmed,
                            "terminal_interrupted": summary.terminal_interrupted,
                            "telemetry_valid": summary.telemetry_valid,
                            "score_eligible": summary.score_eligible,
                        },
                    )
                    break
                self.recorder.event(
                    "campaign_stage_complete",
                    model=model.name,
                    model_id=model.model_id,
                    stage=stage,
                    map_id=map_id,
                    attempt=attempt,
                    won=summary.won,
                    base_hp=summary.base_hp,
                )
                if summary.won:
                    next_label = (
                        f"第 {stage + 1} 关 · 地图 "
                        f"{self.config.campaign_maps[stage]}"
                        if stage < len(self.config.campaign_maps)
                        else "五张地图全部通关"
                    )
                    game.publish_transition(
                        "success",
                        "YOU DID IT!",
                        f"第 {stage} 关通关 · {next_label}",
                    )
                    if stage < len(self.config.campaign_maps):
                        metrics = self._review_metrics([summary])
                        review = model.review(metrics)
                        self.memories[model.model_id] = review
                        self.recorder.event(
                            "campaign_review",
                            model=model.name,
                            model_id=model.model_id,
                            stage=stage,
                            map_id=map_id,
                            metrics=metrics,
                            review=review,
                            request_trace=self._latest_request_trace(model),
                        )
                    self._wait_for_transition(game, default="next")
                    stage += 1
                    continue

                used_retries = retries.get(stage, 0)
                can_retry = used_retries < self.config.campaign_max_retries
                game.publish_transition(
                    "failure",
                    "YOU FAILED",
                    (
                        f"止步第 {stage} 关 · 可选择再试一次或停止"
                        if can_retry
                        else f"止步第 {stage} 关 · 本轮结束"
                    ),
                    can_retry=can_retry,
                )
                action = self._wait_for_transition(game, default="stop")
                if action == "retry" and can_retry:
                    retries[stage] = used_retries + 1
                    self.recorder.event(
                        "campaign_retry_selected",
                        model=model.name,
                        model_id=model.model_id,
                        stage=stage,
                        map_id=map_id,
                        next_attempt=retries[stage] + 1,
                    )
                    continue
                break
        finally:
            game.close()
        if campaign_invalid_reason is None:
            self.recorder.write_validity(
                "valid",
                details={
                    "recorded_attempts": len(self.recorder.summaries),
                    "last_stage_won": (
                        self.recorder.summaries[-1].won
                        if self.recorder.summaries
                        else False
                    ),
                    "campaign_maps": list(self.config.campaign_maps),
                    "stages": [
                        {
                            "map_id": item.map_id,
                            "outcome": item.outcome,
                            "outcome_valid": item.outcome_valid,
                            "terminal_confirmed": item.terminal_confirmed,
                            "terminal_interrupted": item.terminal_interrupted,
                            "telemetry_valid": item.telemetry_valid,
                            "score_eligible": item.score_eligible,
                        }
                        for item in self.recorder.summaries
                    ],
                },
            )
        if campaign_invalid_reason is None:
            campaign_summary = score_campaign(
                self.recorder.summaries,
                total_stages=len(self.config.campaign_maps),
            )
            campaign_summary["status"] = "valid"
            self.recorder.write_campaign_summary(campaign_summary)
        else:
            self.recorder.event(
                "campaign_scoring_skipped",
                reason=campaign_invalid_reason,
                recorded_attempts=len(self.recorder.summaries),
            )
            campaign_summary = {
                "status": "invalid",
                "reason": campaign_invalid_reason,
                "total_stages": len(self.config.campaign_maps),
                "reached_stages": len(self.recorder.summaries),
                "cleared_stages": 0,
                "campaign_score": None,
            }
            self.recorder.write_campaign_summary(campaign_summary)
        self.recorder.write_summaries()
        return write_campaign_dashboard(
            self.recorder.root,
            self.recorder.summaries,
            campaign_summary=campaign_summary,
        )

    def _restore_campaign_resume(
        self, source_root: str | Path, model: ModelAdapter
    ) -> int:
        source = Path(source_root).expanduser().resolve()
        if source == self.recorder.root.resolve():
            raise ValueError("Resume artifact must differ from the new output artifact")
        events_path = source / "events.jsonl"
        manifest_path = source / "manifest.json"
        if not events_path.is_file() or not manifest_path.is_file():
            raise ValueError(
                "Resume artifact must contain events.jsonl and manifest.json"
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("harness_version") != self.config.harness_version:
            raise ValueError(
                "Resume artifact harness_version does not match current config"
            )
        records = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        summaries: list[RunSummary] = []
        imported_trials: list[str] = []
        for record in records:
            if record.get("event_type") != "run_complete":
                continue
            data = record.get("summary")
            if not isinstance(data, dict) or data.get("model_id") != model.model_id:
                continue
            if not data.get("outcome_valid") or not data.get("won"):
                continue
            summary = RunSummary(**data)
            summaries.append(summary)
            imported_trials.append(summary.trial_id)

        if not summaries:
            raise ValueError("Resume artifact has no completed winning stages")
        imported_maps = [item.map_id for item in summaries]
        expected_prefix = list(self.config.campaign_maps[: len(imported_maps)])
        if imported_maps != expected_prefix:
            raise ValueError(
                "Resume artifact completed maps are not the configured campaign prefix"
            )
        if len(summaries) >= len(self.config.campaign_maps):
            raise ValueError("Resume artifact already completed the full campaign")

        completed_events = {
            (int(record.get("stage", 0)), str(record.get("map_id", "")))
            for record in records
            if record.get("event_type") == "campaign_stage_complete"
            and record.get("won") is True
        }
        for stage_number, summary in enumerate(summaries, start=1):
            if (stage_number, summary.map_id) not in completed_events:
                raise ValueError(
                    "Resume artifact winning summary lacks campaign_stage_complete"
                )

        reviews = [
            record
            for record in records
            if record.get("event_type") == "campaign_review"
            and record.get("model_id") == model.model_id
            and isinstance(record.get("review"), str)
        ]
        if reviews:
            self.memories[model.model_id] = reviews[-1]["review"]

        request_indices = [
            int(trace["request_index"])
            for record in records
            if record.get("event_type") == "decision_received"
            for trace in record.get("request_trace", [])
            if isinstance(trace, dict)
            and isinstance(trace.get("request_index"), int)
        ]
        next_request_index = max(request_indices, default=-1) + 1
        restore_index = getattr(model, "restore_request_index", None)
        if callable(restore_index):
            restore_index(next_request_index)

        self.recorder.summaries.extend(summaries)
        next_stage = len(summaries) + 1
        incomplete_stages = sorted(
            {
                int(record["stage"])
                for record in records
                if record.get("event_type") == "campaign_stage_started"
                and isinstance(record.get("stage"), int)
                and int(record["stage"]) >= next_stage
            }
        )
        self.recorder.event(
            "campaign_resumed",
            model=model.name,
            model_id=model.model_id,
            source_artifact=str(source),
            imported_maps=imported_maps,
            imported_trials=imported_trials,
            next_stage=next_stage,
            next_map_id=self.config.campaign_maps[next_stage - 1],
            source_incomplete_stages=incomplete_stages,
            next_request_index=next_request_index,
            restored_review=bool(reviews),
        )
        return next_stage

    def _run_one(
        self,
        model: ModelAdapter,
        round_id: int,
        run_index: int,
        map_id: str,
        fog_of_war: bool | None = None,
        game: GameAdapter | None = None,
        completion_mode: str = "requested_waves",
    ) -> RunSummary:
        if completion_mode not in {"full", "requested_waves"}:
            raise ValueError(f"Unknown completion mode: {completion_mode}")
        owns_game = game is None
        game = game or self.game_factory()
        seed = self.config.seed + run_index - 1
        invalid_count = 0
        total_actions = 0
        total_damage = 0.0
        total_defeated = 0
        total_leaked = 0
        gold_spent = 0
        decision_count = 0
        accepted_count = 0
        local_micro_action_count = 0
        budget_exhausted = False
        watchdog_timed_out = False
        model_request_failed = False
        model_parse_failures = 0
        model_repair_count = 0
        invalid_reason = ""
        partial_completed = False
        trigger_events = [{"type": "game_started", "detail": {}}]
        plan_queue = ActionPlanQueue()
        plan_wait_cycles = 0
        hide_early_enemies = round_id == 3 if fog_of_war is None else fog_of_war
        state = game.reset(map_id, seed, self.config.max_waves)
        # Full completion is an explicit mode. A smoke requesting fewer waves
        # gets an explicit partial boundary; reaching the final wave is never
        # itself treated as completion.
        full_completion = (
            completion_mode == "full"
            or self.config.max_waves >= state.max_waves
        )
        partial_wave_limit = (
            None
            if full_completion
            else min(state.max_waves, state.wave + self.config.max_waves)
        )
        initial_gold = state.gold
        initial_base_hp = state.base_hp
        initial_game_step = state.game_step
        self.recorder.event(
            "run_started",
            model=model.name,
            model_id=model.model_id,
            round_id=round_id,
            run_index=run_index,
            map_id=map_id,
            seed=seed,
            requested_wave_count=self.config.max_waves,
            completion_mode=(
                "full_native_terminal" if full_completion else "partial_smoke"
            ),
            partial_wave_limit=partial_wave_limit,
            watchdog_max_game_steps=self.config.watchdog_max_game_steps,
            initial_state=state.public_dict(hide_early_enemies),
        )
        try:
            while True:
                if state.done:
                    break
                if (
                    partial_wave_limit is not None
                    and state.wave >= partial_wave_limit
                ):
                    partial_completed = True
                    break
                if state.base_hp <= 0:
                    invalid_reason = "base_hp_zero_without_native_terminal"
                    break
                native_steps_elapsed = state.game_step - initial_game_step
                if native_steps_elapsed >= self.config.watchdog_max_game_steps:
                    watchdog_timed_out = True
                    invalid_reason = "native_step_watchdog_timeout"
                    self.recorder.event(
                        "native_step_watchdog_timeout",
                        model=model.name,
                        model_id=model.model_id,
                        round_id=round_id,
                        run_index=run_index,
                        map_id=map_id,
                        game_step=state.game_step,
                        native_steps_elapsed=native_steps_elapsed,
                        limit=self.config.watchdog_max_game_steps,
                    )
                    break
                if decision_count >= self.config.max_decisions_per_run:
                    budget_exhausted = True
                    invalid_reason = "decision_budget_exhausted_before_terminal"
                    self.recorder.event(
                        "decision_budget_exhausted",
                        model=model.name,
                        model_id=model.model_id,
                        round_id=round_id,
                        run_index=run_index,
                        max_decisions=self.config.max_decisions_per_run,
                    )
                    break
                bad_waits = []
                state.previous_wave_summary["trigger_events"] = trigger_events
                state.previous_wave_summary["pending_plans"] = [
                    asdict(action) for action in plan_queue.pending
                ]
                game.pause()
                memory = self.memories.get(model.model_id) if round_id >= 2 else None
                event_types = {item["type"] for item in trigger_events}
                strategic_events = event_types - {"monitor_interval"}
                planned = plan_queue.pop_ready(state, event_types)
                if planned:
                    plan_wait_cycles = 0
                    decision = Decision(
                        analysis_summary="执行此前已批准的条件计划",
                        actions=planned,
                        raw_response='{"source":"local_plan_queue"}',
                    )
                elif (
                    plan_queue.pending
                    and not strategic_events
                    and plan_wait_cycles < 3
                ):
                    plan_wait_cycles += 1
                    decision = Decision(
                        analysis_summary="等待条件计划触发",
                        actions=[],
                        raw_response='{"source":"local_plan_wait"}',
                    )
                else:
                    if plan_queue.pending:
                        self.recorder.event(
                            "plan_queue_reviewed",
                            model=model.name,
                            pending=len(plan_queue.pending),
                            trigger_events=sorted(strategic_events),
                        )
                    plan_wait_cycles = 0
                    self.recorder.event(
                        "decision_requested",
                        model=model.name,
                        model_id=model.model_id,
                        round_id=round_id,
                        run_index=run_index,
                        wave=state.wave,
                    )
                    try:
                        decision = model.decide(
                            state, memory=memory, fog_of_war=hide_early_enemies
                        )
                    except Exception as exc:
                        model_request_failed = True
                        invalid_reason = "model_request_failed"
                        self.recorder.event(
                            "model_request_failed",
                            model=model.name,
                            model_id=model.model_id,
                            round_id=round_id,
                            run_index=run_index,
                            map_id=map_id,
                            wave=state.wave,
                            error_type=type(exc).__name__,
                            error=str(exc)[:300],
                            request_trace=self._latest_request_trace(model),
                        )
                        break
                    decision_count += 1
                    model_repair_count += int(
                        getattr(decision, "repair_attempted", False)
                    )
                    self.recorder.event(
                        "decision_received",
                        model=model.name,
                        model_id=model.model_id,
                        round_id=round_id,
                        run_index=run_index,
                        wave=state.wave,
                        action_count=len(decision.actions),
                        parse_status=getattr(decision, "parse_status", "valid"),
                        request_trace=getattr(decision, "request_trace", []),
                    )
                    if getattr(decision, "parse_status", "valid") == "repair_failed":
                        model_parse_failures += 1
                        invalid_reason = "model_json_parse_failed"
                        self.recorder.event(
                            "model_json_parse_failed",
                            model=model.name,
                            model_id=model.model_id,
                            round_id=round_id,
                            run_index=run_index,
                            map_id=map_id,
                            wave=state.wave,
                            error_type=getattr(
                                decision, "parse_error_type", "unknown"
                            ),
                            request_trace=getattr(decision, "request_trace", []),
                        )
                        break
                    if decision.cancel_pending_plans and plan_queue.pending:
                        self.recorder.event(
                            "plan_queue_cancelled",
                            model=model.name,
                            model_id=model.model_id,
                            round_id=round_id,
                            run_index=run_index,
                            pending=len(plan_queue.pending),
                        )
                        plan_queue.pending.clear()
                    _, bad_waits = plan_queue.enqueue(decision.actions)
                    planned = plan_queue.pop_ready(state, event_types)
                    decision.actions = planned
                accepted, rejected = self.validator.validate(
                    state, decision.actions, decision.reserve_gold
                )
                if bad_waits:
                    rejected.extend(
                        ActionRejection(
                            self.validator._action_dict(action),
                            "unsupported wait condition",
                        )
                        for action in bad_waits
                    )
                invalid_count += len(rejected)
                total_actions += len(decision.actions)
                accepted_count += len(accepted)
                before_gold = state.gold
                game.publish_decision(model.name, decision, accepted, rejected)
                self.recorder.event(
                    "decision",
                    model=model.name,
                    model_id=model.model_id,
                    round_id=round_id,
                    run_index=run_index,
                    wave=state.wave,
                    observation=state.public_dict(hide_early_enemies),
                    analysis_summary=decision.analysis_summary,
                    raw_response=decision.raw_response,
                    accepted=accepted,
                    rejected=rejected,
                    standing_orders=decision.standing_orders,
                )
                if decision.standing_orders is not None:
                    game.set_standing_orders(decision.standing_orders)
                state = game.apply_actions(accepted)
                plan_queue.mark_completed(accepted)
                gold_spent += max(0, before_gold - state.gold)
                game.resume()
                if state.done:
                    trigger_events = [
                        {
                            "type": "game_over",
                            "detail": {
                                "terminal": True,
                                "interrupted": state.terminal_interrupted,
                            },
                        }
                    ]
                    continue
                if self.config.event_driven:
                    remaining_watchdog_steps = max(
                        1,
                        self.config.watchdog_max_game_steps
                        - (state.game_step - initial_game_step),
                    )
                    state, events, wave_result = game.advance_until_event(
                        min(
                            self.config.monitor_max_steps,
                            remaining_watchdog_steps,
                        )
                    )
                    trigger_events = [
                        {"type": event.type, "detail": event.detail}
                        for event in events
                    ]
                    for audit in game.drain_monitor_audit():
                        audit_record = dict(audit)
                        audit_type = audit_record.pop(
                            "event_type", "monitor_trigger_deferred"
                        )
                        self.recorder.event(
                            audit_type,
                            model=model.name,
                            model_id=model.model_id,
                            round_id=round_id,
                            run_index=run_index,
                            wave=state.wave,
                            **audit_record,
                        )
                    self.recorder.event(
                        "monitor_trigger",
                        model=model.name,
                        model_id=model.model_id,
                        round_id=round_id,
                        run_index=run_index,
                        wave=state.wave,
                        events=trigger_events,
                    )
                    micro_actions = game.drain_micro_actions()
                    if micro_actions:
                        local_micro_action_count += len(micro_actions)
                        self.recorder.event(
                            "micro_actions",
                            model=model.name,
                            model_id=model.model_id,
                            round_id=round_id,
                            run_index=run_index,
                            wave=state.wave,
                            actions=micro_actions,
                        )
                else:
                    state, wave_result = game.play_wave()
                    trigger_events = [
                        {"type": "wave_changed", "detail": {"wave": state.wave}}
                    ]
                total_damage += wave_result.damage_dealt
                total_defeated += wave_result.enemies_defeated
                total_leaked += wave_result.enemies_leaked
                self.recorder.event(
                    "wave_complete",
                    model=model.name,
                    model_id=model.model_id,
                    round_id=round_id,
                    run_index=run_index,
                    result=wave_result,
                    state=state.public_dict(hide_early_enemies),
                )
            outcome, outcome_valid, invalid_reason = self._resolve_outcome(
                state=state,
                partial_completed=partial_completed,
                invalid_reason=invalid_reason,
            )
            terminal_snapshot = TerminalSnapshot.capture(map_id, state, outcome)
            self.recorder.event(
                "terminal_snapshot_created",
                model=model.name,
                model_id=model.model_id,
                round_id=round_id,
                run_index=run_index,
                snapshot=terminal_snapshot.to_dict(),
            )
        finally:
            if self.config.hold_after_run_seconds > 0:
                sleep(self.config.hold_after_run_seconds)
            if owns_game:
                game.close()

        snapshot_data = terminal_snapshot.to_dict()
        telemetry = snapshot_data["telemetry"]
        telemetry_valid = all(
            key in telemetry for key in ("enemy_damage", "enemy_kills")
        )
        exact_damage = float(telemetry.get("enemy_damage", total_damage))
        exact_defeated = int(telemetry.get("enemy_kills", total_defeated))
        # TowerMind's public rule is one base HP per leak. HP is native state
        # and remains authoritative even if a leak occurs during an action
        # step outside advance_until_event's monitoring window.
        exact_leaked = max(0, initial_base_hp - terminal_snapshot.final_hp)
        if (
            exact_damage != total_damage
            or exact_defeated != total_defeated
            or exact_leaked != total_leaked
        ):
            self.recorder.event(
                "metric_reconciliation",
                model=model.name,
                model_id=model.model_id,
                round_id=round_id,
                run_index=run_index,
                map_id=map_id,
                monitor_window_totals={
                    "damage_dealt": round(total_damage, 2),
                    "enemies_defeated": total_defeated,
                    "enemies_leaked": total_leaked,
                },
                authoritative_totals={
                    "damage_dealt": round(exact_damage, 2),
                    "enemies_defeated": exact_defeated,
                    "enemies_leaked": exact_leaked,
                },
                sources={
                    "damage_dealt": (
                        "plugin cumulative enemy_damage"
                        if "enemy_damage" in telemetry
                        else "monitor windows"
                    ),
                    "enemies_defeated": (
                        "plugin cumulative enemy_kills"
                        if "enemy_kills" in telemetry
                        else "monitor windows"
                    ),
                    "enemies_leaked": "native initial_hp - final_hp",
                },
            )
        return RunSummary(
            experiment_id=self.config.experiment_id,
            model_name=model.name,
            model_id=model.model_id,
            round_id=round_id,
            run_index=run_index,
            map_id=map_id,
            seed=seed,
            waves_survived=terminal_snapshot.native_current_wave,
            max_waves=terminal_snapshot.max_waves,
            base_hp=terminal_snapshot.final_hp,
            max_base_hp=terminal_snapshot.max_base_hp,
            gold_remaining=terminal_snapshot.gold,
            gold_spent=max(
                gold_spent,
                initial_gold - terminal_snapshot.gold,
            ),
            damage_dealt=round(exact_damage, 2),
            invalid_actions=invalid_count,
            total_actions=total_actions,
            won=outcome == "won",
            task_id=f"map:{map_id}:round:{round_id}",
            trial_id=(
                f"{self.config.experiment_id}:{model.model_id}:"
                f"r{round_id}:n{run_index}:seed{seed}"
            ),
            harness_version=self.config.harness_version,
            observation_mode=self.config.observation_mode,
            scaffold_id=self.config.scaffold_id,
            decision_count=decision_count,
            accepted_actions=accepted_count,
            enemies_defeated=exact_defeated,
            enemies_leaked=exact_leaked,
            local_micro_actions=local_micro_action_count,
            decision_budget_exhausted=budget_exhausted,
            model_request_failed=model_request_failed,
            model_parse_failures=model_parse_failures,
            model_repair_count=model_repair_count,
            watchdog_timed_out=watchdog_timed_out,
            outcome=outcome,
            partial=outcome == "partial",
            outcome_valid=outcome_valid,
            terminal_confirmed=terminal_snapshot.terminal,
            terminal_interrupted=terminal_snapshot.interrupted,
            telemetry_valid=telemetry_valid,
            # The current showcase score depends on native outcome/HP/wave and
            # action validation, not plugin damage/kill telemetry.
            score_eligible=outcome_valid,
            invalid_reason=invalid_reason,
            provisional_metrics=(
                [] if telemetry_valid else ["damage_dealt", "enemies_defeated"]
            ),
            terminal_snapshot=snapshot_data,
        )

    @staticmethod
    def _resolve_outcome(
        state: GameState,
        partial_completed: bool,
        invalid_reason: str,
    ) -> tuple[RunOutcome, bool, str]:
        if state.done:
            if state.terminal_interrupted is True:
                return "invalid", False, "native_terminal_interrupted"
            if state.terminal_interrupted is None:
                return "invalid", False, "terminal_interrupted_flag_unavailable"
            return ("won" if state.base_hp > 0 else "lost"), True, ""
        if partial_completed:
            return "partial", False, ""
        return "invalid", False, invalid_reason or "native_terminal_not_observed"

    def _write_single_run_validity(self, summary: RunSummary) -> None:
        if summary.outcome == "partial":
            status = "partial"
            reason = "requested partial smoke boundary reached"
        elif summary.outcome_valid:
            status = "valid"
            reason = ""
        else:
            status = "invalid"
            reason = summary.invalid_reason
        self.recorder.write_validity(
            status,
            reason=reason,
            details={
                "map_id": summary.map_id,
                "outcome": summary.outcome,
                "outcome_valid": summary.outcome_valid,
                "terminal_confirmed": summary.terminal_confirmed,
                "terminal_interrupted": summary.terminal_interrupted,
                "telemetry_valid": summary.telemetry_valid,
                "score_eligible": summary.score_eligible,
                "provisional_metrics": list(summary.provisional_metrics),
            },
        )

    def _wait_for_transition(
        self,
        game: GameAdapter,
        default: str,
    ) -> str:
        duration = self.config.campaign_transition_seconds
        if duration <= 0:
            return default
        deadline = monotonic() + duration
        while monotonic() < deadline:
            game.pump_transition_frame()
            action = game.transition_action()
            if action in {"next", "retry", "stop"}:
                return action
            sleep(min(0.1, max(0.0, deadline - monotonic())))
        return default

    def _create_private_reviews(self) -> None:
        for model in self.models:
            own = [
                item
                for item in self.recorder.summaries
                if item.round_id == 1 and item.model_id == model.model_id
            ]
            metrics = self._review_metrics(own)
            review = model.review(metrics)
            self.memories[model.model_id] = review
            self.recorder.event(
                "private_review",
                model=model.name,
                model_id=model.model_id,
                metrics=metrics,
                review=review,
                request_trace=self._latest_request_trace(model),
            )

    @staticmethod
    def _latest_request_trace(model: ModelAdapter) -> list[dict]:
        metadata = getattr(model, "last_request_metadata", None)
        if not isinstance(metadata, dict) or not metadata:
            return []
        return [dict(metadata)]

    @staticmethod
    def _review_metrics(summaries: list[RunSummary]) -> dict[str, float | int]:
        return {
            "waves_survived": round(
                sum(item.waves_survived for item in summaries) / len(summaries), 2
            ),
            "base_hp": round(
                sum(item.base_hp for item in summaries) / len(summaries), 2
            ),
            "gold_spent": round(
                sum(item.gold_spent for item in summaries) / len(summaries), 2
            ),
            "gold_remaining": round(
                sum(item.gold_remaining for item in summaries) / len(summaries), 2
            ),
            "invalid_actions": sum(item.invalid_actions for item in summaries),
            "damage_dealt": round(
                sum(item.damage_dealt for item in summaries) / len(summaries), 2
            ),
        }

    def _default_game_factory(self) -> GameAdapter:
        if self.config.backend == "sim":
            return SimulatedTowerDefense()
        if not self.config.towermind_executable:
            raise ValueError(
                "towermind_executable is required when backend is 'towermind'"
            )
        repo_root = Path("vendor/TowerMind")
        return TowerMindAdapter(
            self.config.towermind_executable,
            repo_root,
            time_scale=self.config.towermind_time_scale,
            screen_width=self.config.towermind_screen_width,
            screen_height=self.config.towermind_screen_height,
            quality_level=self.config.towermind_quality_level,
            fullscreen=self.config.towermind_fullscreen,
            level_overrides=self.config.level_overrides,
            plugin_url=self.config.towermind_plugin_url,
            plugin_required=self.config.towermind_plugin_required,
            low_priority_event_debounce_seconds=(
                self.config.low_priority_event_debounce_seconds
            ),
        )
