from dataclasses import replace
import json

from tower_referee.config import ExperimentConfig, ModelConfig
from tower_referee.game.base import GameAdapter, InvalidInitialStateError
from tower_referee.game.sim import SimulatedTowerDefense
from tower_referee.runner import ExperimentRunner
from tower_referee.schema import (
    Action,
    Decision,
    GameEvent,
    GameState,
    RunSummary,
    WaveResult,
)


class ScriptedTerminalGame(GameAdapter):
    """Small native-terminal test double; each frame is one monitor segment."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.state = None
        self.reset_maps = []
        self.transition_resets = 0

    def reset(self, map_id, seed, max_waves):
        del seed, max_waves
        self.reset_maps.append(map_id)
        self.state = GameState(
            wave=0,
            max_waves=5,
            base_hp=20,
            max_base_hp=20,
            gold=500,
            available_actions=["noop"],
            build_sites=[(0.0, 0.0)],
        )
        return self.state

    def pause(self):
        return None

    def resume(self):
        return None

    def apply_actions(self, actions):
        del actions
        return self.state

    def play_wave(self):
        frame = self.frames.pop(0) if self.frames else {}
        before_hp = self.state.base_hp
        before_gold = self.state.gold
        for key, value in frame.items():
            setattr(self.state, key, value)
        result = WaveResult(
            wave=self.state.wave,
            base_hp_before=before_hp,
            base_hp_after=self.state.base_hp,
            gold_before=before_gold,
            gold_after=self.state.gold,
            enemies_defeated=0,
            enemies_leaked=max(0, before_hp - self.state.base_hp),
            damage_dealt=0.0,
        )
        return self.state, result

    def advance_until_event(self, max_steps=600):
        del max_steps
        state, result = self.play_wave()
        event = (
            GameEvent("game_over", {"won": state.won}, 100)
            if state.done
            else GameEvent("monitor_interval", {"steps": 1}, 10)
        )
        return state, [event], result

    def pump_transition_frame(self):
        self.transition_resets += 1
        self.state.wave = 0
        self.state.base_hp = 20
        self.state.gold = 500
        self.state.done = False
        self.state.won = False
        self.state.terminal_interrupted = None

    def close(self):
        return None


def test_smoke_runs_only_one_model_and_one_round(tmp_path):
    config = ExperimentConfig(
        experiment_id="smoke-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=1,
        models=(
            ModelConfig(name="Only", provider="rule", model="balanced"),
        ),
    )

    dashboard = ExperimentRunner(config, tmp_path).run_smoke()

    assert dashboard.exists()
    summary = (tmp_path / "smoke-test" / "summary.json").read_text(encoding="utf-8")
    assert '"model_name": "Only"' in summary
    assert '"round_id": 1' in summary


def test_event_driven_smoke_stops_at_requested_wave_budget(tmp_path):
    class NativeFiveWaveSim(SimulatedTowerDefense):
        def reset(self, map_id, seed, max_waves):
            state = super().reset(map_id, seed, max_waves)
            state.max_waves = 5
            return state

    config = ExperimentConfig(
        experiment_id="event-budget-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=1,
        event_driven=True,
        models=(ModelConfig(name="Only", provider="rule", model="balanced"),),
    )

    ExperimentRunner(
        config, tmp_path, game_factory=NativeFiveWaveSim
    ).run_smoke()

    root = tmp_path / "event-budget-test"
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))[0]
    events = (root / "events.jsonl").read_text(encoding="utf-8")
    assert summary["waves_survived"] == 1
    assert summary["max_waves"] == 5
    assert summary["won"] is False
    assert summary["outcome"] == "partial"
    assert summary["partial"] is True
    assert summary["terminal_confirmed"] is False
    assert summary["score_eligible"] is False
    validity = json.loads((root / "validity.json").read_text(encoding="utf-8"))
    assert validity["status"] == "partial"
    assert events.count('"event_type": "wave_complete"') == 1


def test_full_native_map_is_won_when_terminal_signal_arrives_late(tmp_path):
    config = ExperimentConfig(
        experiment_id="late-terminal-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=5,
        event_driven=True,
        models=(ModelConfig(name="Only", provider="rule", model="balanced"),),
    )
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "game_step": 3776,
                "done": False,
                "won": False,
                "terminal_interrupted": None,
            },
            {
                "wave": 5,
                "game_step": 4999,
                "done": True,
                "won": True,
                "terminal_interrupted": False,
            },
        ]
    )

    ExperimentRunner(
        config, tmp_path, game_factory=lambda: game
    ).run_smoke()

    summary = json.loads(
        (tmp_path / "late-terminal-test" / "summary.json").read_text(
            encoding="utf-8"
        )
    )[0]
    assert summary["waves_survived"] == 5
    assert summary["max_waves"] == 5
    assert summary["won"] is True
    assert summary["terminal_confirmed"] is True
    assert summary["terminal_interrupted"] is False
    assert summary["terminal_snapshot"]["game_step"] == 4999
    assert summary["decision_count"] == 2


def scripted_config(experiment_id, **overrides):
    values = {
        "experiment_id": experiment_id,
        "backend": "sim",
        "runs_per_round": 1,
        "seed": 7,
        "fixed_map": "river_gate",
        "unseen_map": "fog_crossroads",
        "max_waves": 5,
        "event_driven": True,
        "models": (
            ModelConfig(name="Only", provider="rule", model="balanced"),
        ),
    }
    values.update(overrides)
    return ExperimentConfig(**values)


def read_only_summary(tmp_path, experiment_id):
    return json.loads(
        (tmp_path / experiment_id / "summary.json").read_text(encoding="utf-8")
    )[0]


def test_native_terminal_with_zero_hp_is_a_confirmed_loss(tmp_path):
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "base_hp": 0,
                "game_step": 4900,
                "done": True,
                "won": False,
                "terminal_interrupted": False,
            }
        ]
    )
    config = scripted_config("terminal-loss-test")

    ExperimentRunner(config, tmp_path, game_factory=lambda: game).run_smoke()

    summary = read_only_summary(tmp_path, "terminal-loss-test")
    assert summary["outcome"] == "lost"
    assert summary["outcome_valid"] is True
    assert summary["won"] is False
    assert summary["score_eligible"] is True


def test_interrupted_terminal_is_invalid_not_win_or_loss(tmp_path):
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "base_hp": 20,
                "game_step": 4900,
                "done": True,
                "won": False,
                "terminal_interrupted": True,
            }
        ]
    )
    config = scripted_config("interrupted-test")

    ExperimentRunner(config, tmp_path, game_factory=lambda: game).run_smoke()

    summary = read_only_summary(tmp_path, "interrupted-test")
    assert summary["outcome"] == "invalid"
    assert summary["outcome_valid"] is False
    assert summary["terminal_interrupted"] is True
    assert summary["won"] is False
    assert summary["score_eligible"] is False
    assert summary["invalid_reason"] == "native_terminal_interrupted"


def test_native_step_watchdog_without_terminal_is_invalid(tmp_path):
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "base_hp": 20,
                "game_step": 120,
                "done": False,
                "won": False,
            }
        ]
    )
    config = scripted_config(
        "watchdog-test",
        watchdog_max_game_steps=100,
    )

    ExperimentRunner(config, tmp_path, game_factory=lambda: game).run_smoke()

    summary = read_only_summary(tmp_path, "watchdog-test")
    assert summary["outcome"] == "invalid"
    assert summary["watchdog_timed_out"] is True
    assert summary["won"] is False
    assert summary["score_eligible"] is False
    assert summary["invalid_reason"] == "native_step_watchdog_timeout"


def test_decision_budget_before_terminal_is_invalid(tmp_path):
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "base_hp": 20,
                "game_step": 1,
                "done": False,
                "won": False,
            }
        ]
    )
    config = scripted_config(
        "budget-test",
        max_decisions_per_run=1,
    )

    ExperimentRunner(config, tmp_path, game_factory=lambda: game).run_smoke()

    summary = read_only_summary(tmp_path, "budget-test")
    assert summary["outcome"] == "invalid"
    assert summary["decision_budget_exhausted"] is True
    assert summary["won"] is False
    assert summary["score_eligible"] is False
    assert (
        summary["invalid_reason"]
        == "decision_budget_exhausted_before_terminal"
    )


def test_model_request_failure_is_recorded_as_invalid(tmp_path):
    class FailingModel:
        name = "Only"
        model_id = "test/failing-model"
        last_request_metadata = {
            "request_index": 0,
            "reasoning_content": "中断前的思考",
            "reasoning_content_complete": False,
        }

        def decide(self, state, memory=None, fog_of_war=False):
            del state, memory, fog_of_war
            raise TimeoutError("test model timeout")

    config = scripted_config("model-request-failure-test")
    runner = ExperimentRunner(config, tmp_path)
    runner.models[0] = FailingModel()

    runner.run_smoke()

    root = tmp_path / "model-request-failure-test"
    summary = read_only_summary(tmp_path, "model-request-failure-test")
    events = (root / "events.jsonl").read_text(encoding="utf-8")
    assert summary["outcome"] == "invalid"
    assert summary["invalid_reason"] == "model_request_failed"
    assert summary["model_request_failed"] is True
    assert '"event_type": "model_request_failed"' in events
    failure = next(
        item for item in map(json.loads, events.splitlines())
        if item["event_type"] == "model_request_failed"
    )
    assert failure["request_trace"][0]["reasoning_content"] == "中断前的思考"


def test_model_json_parse_failure_is_invalid_not_noop(tmp_path):
    class MalformedModel:
        name = "Only"
        model_id = "test/malformed-model"

        def decide(self, state, memory=None, fog_of_war=False):
            del state, memory, fog_of_war
            return Decision(
                analysis_summary="模型连续两次未返回合法 JSON，本局判为无效",
                actions=[Action(type="noop")],
                parse_status="repair_failed",
                parse_error_type="JSONDecodeError",
                repair_attempted=True,
                request_trace=[{"request_index": 0}, {"request_index": 1}],
            )

    config = scripted_config("model-json-failure-test")
    runner = ExperimentRunner(config, tmp_path)
    runner.models[0] = MalformedModel()

    runner.run_smoke()

    root = tmp_path / "model-json-failure-test"
    summary = read_only_summary(tmp_path, "model-json-failure-test")
    events = (root / "events.jsonl").read_text(encoding="utf-8")
    assert summary["outcome"] == "invalid"
    assert summary["invalid_reason"] == "model_json_parse_failed"
    assert summary["model_parse_failures"] == 1
    assert summary["model_repair_count"] == 1
    assert '"event_type": "model_json_parse_failed"' in events
    assert '"event_type": "decision"' not in events


def test_terminal_snapshot_survives_transition_reset(tmp_path):
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "base_hp": 7,
                "gold": 33,
                "game_step": 4999,
                "done": True,
                "won": True,
                "terminal_interrupted": False,
            }
        ]
    )
    config = scripted_config("snapshot-freeze-test")
    runner = ExperimentRunner(config, tmp_path, game_factory=lambda: game)

    summary = runner._run_one(
        runner.models[0],
        round_id=1,
        run_index=1,
        map_id="river_gate",
        game=game,
        completion_mode="full",
    )
    frozen = dict(summary.terminal_snapshot)
    game.pump_transition_frame()

    assert game.transition_resets == 1
    assert game.state.wave == 0
    assert summary.base_hp == 7
    assert summary.gold_remaining == 33
    assert summary.waves_survived == 5
    assert summary.terminal_snapshot == frozen
    assert summary.terminal_snapshot["terminal"] is True


def test_missing_telemetry_keeps_native_outcome_but_marks_metrics_provisional(
    tmp_path,
):
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "base_hp": 11,
                "game_step": 4999,
                "done": True,
                "won": True,
                "terminal_interrupted": False,
                "combat_telemetry": {},
            }
        ]
    )
    config = scripted_config("missing-telemetry-test")

    ExperimentRunner(config, tmp_path, game_factory=lambda: game).run_smoke()

    summary = read_only_summary(tmp_path, "missing-telemetry-test")
    assert summary["outcome"] == "won"
    assert summary["outcome_valid"] is True
    assert summary["telemetry_valid"] is False
    assert summary["score_eligible"] is True
    assert set(summary["provisional_metrics"]) == {
        "damage_dealt",
        "enemies_defeated",
    }


def test_campaign_invalid_stage_stops_later_maps_and_skips_scoring(tmp_path):
    game = ScriptedTerminalGame(
        [
            {
                "wave": 5,
                "base_hp": 20,
                "game_step": 4999,
                "done": True,
                "won": False,
                "terminal_interrupted": True,
            }
        ]
    )
    config = scripted_config(
        "campaign-invalid-runtime-test",
        campaign_maps=("river_gate", "fog_crossroads"),
    )

    ExperimentRunner(config, tmp_path, game_factory=lambda: game).run_campaign_smoke()

    root = tmp_path / "campaign-invalid-runtime-test"
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    events = (root / "events.jsonl").read_text(encoding="utf-8")
    validity = json.loads((root / "validity.json").read_text(encoding="utf-8"))
    assert game.reset_maps == ["river_gate"]
    assert len(summary) == 1
    assert summary[0]["score"] == 0
    assert summary[0]["score_eligible"] is False
    assert validity["status"] == "invalid"
    assert '"event_type": "campaign_scoring_skipped"' in events
    assert "fog_crossroads" not in game.reset_maps


def test_summary_reconciles_monitor_gaps_with_cumulative_telemetry_and_hp(tmp_path):
    class CumulativeTelemetrySim(SimulatedTowerDefense):
        def play_wave(self):
            state, result = super().play_wave()
            state.combat_telemetry = {
                "enemy_damage": 4242,
                "enemy_kills": 17,
                # Deliberately wrong: native HP must remain authoritative.
                "leaks": 99,
            }
            return state, result

    config = ExperimentConfig(
        experiment_id="metric-reconciliation-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=1,
        event_driven=True,
        models=(ModelConfig(name="Only", provider="rule", model="balanced"),),
    )

    ExperimentRunner(
        config, tmp_path, game_factory=CumulativeTelemetrySim
    ).run_smoke()

    root = tmp_path / "metric-reconciliation-test"
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))[0]
    events = (root / "events.jsonl").read_text(encoding="utf-8")
    assert summary["damage_dealt"] == 4242
    assert summary["enemies_defeated"] == 17
    assert summary["enemies_leaked"] == summary["max_base_hp"] - summary["base_hp"]
    assert '"event_type": "metric_reconciliation"' in events


def test_campaign_stops_after_first_failed_map(tmp_path):
    config = ExperimentConfig(
        experiment_id="campaign-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=1,
        models=(
            ModelConfig(name="Only", provider="rule", model="balanced"),
        ),
        campaign_maps=("river_gate", "fog_crossroads"),
    )
    runner = ExperimentRunner(config, tmp_path)
    calls = []

    original = runner._run_one

    def controlled(
        model,
        round_id,
        run_index,
        map_id,
        fog_of_war=None,
        game=None,
        completion_mode="requested_waves",
    ):
        result = original(
            model,
            round_id,
            run_index,
            map_id,
            fog_of_war,
            game,
            completion_mode,
        )
        calls.append(map_id)
        result.won = False
        return result

    runner._run_one = controlled
    dashboard = runner.run_campaign_smoke()

    assert calls == ["river_gate"]
    assert dashboard.name == "campaign.html"
    campaign_summary = json.loads(
        (tmp_path / "campaign-test" / "campaign_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert campaign_summary["total_stages"] == 2
    assert campaign_summary["reached_stages"] == 1
    assert campaign_summary["campaign_score"] >= 0


def test_campaign_resume_imports_wins_and_starts_at_next_map(tmp_path):
    source = tmp_path / "interrupted-campaign"
    source.mkdir()
    (source / "manifest.json").write_text(
        json.dumps({"harness_version": "2.0"}), encoding="utf-8"
    )

    def completed_summary(stage, map_id):
        return RunSummary(
            experiment_id="interrupted-campaign",
            model_name="Only",
            model_id="rule/balanced/Only",
            round_id=stage,
            run_index=1,
            map_id=map_id,
            seed=7,
            waves_survived=5,
            max_waves=5,
            base_hp=10,
            max_base_hp=20,
            gold_remaining=100,
            gold_spent=400,
            damage_dealt=1000,
            invalid_actions=0,
            total_actions=3,
            won=True,
            outcome="won",
            outcome_valid=True,
            terminal_confirmed=True,
            terminal_interrupted=False,
            telemetry_valid=True,
            score_eligible=True,
            trial_id=f"old-stage-{stage}",
        )

    source_events = []
    for stage, map_id in ((1, "0"), (2, "1")):
        source_events.extend(
            [
                {
                    "event_type": "run_complete",
                    "summary": completed_summary(stage, map_id).to_dict(),
                },
                {
                    "event_type": "campaign_stage_complete",
                    "stage": stage,
                    "map_id": map_id,
                    "won": True,
                },
                {
                    "event_type": "campaign_review",
                    "stage": stage,
                    "map_id": map_id,
                    "model_id": "rule/balanced/Only",
                    "review": f"review-{stage}",
                },
            ]
        )
    source_events.extend(
        [
            {"event_type": "campaign_stage_started", "stage": 3, "map_id": "3"},
            {
                "event_type": "decision_received",
                "request_trace": [{"request_index": 11}],
            },
        ]
    )
    (source / "events.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in source_events),
        encoding="utf-8",
    )

    config = scripted_config(
        "resumed-campaign",
        campaign_maps=("0", "1", "3"),
    )
    runner = ExperimentRunner(config, tmp_path)
    calls = []

    def controlled(
        model,
        round_id,
        run_index,
        map_id,
        fog_of_war=None,
        game=None,
        completion_mode="requested_waves",
    ):
        del fog_of_war, game, completion_mode
        calls.append(map_id)
        assert runner.memories[model.model_id] == "review-2"
        return RunSummary(
            experiment_id=config.experiment_id,
            model_name=model.name,
            model_id=model.model_id,
            round_id=round_id,
            run_index=run_index,
            map_id=map_id,
            seed=config.seed,
            waves_survived=2,
            max_waves=5,
            base_hp=0,
            max_base_hp=20,
            gold_remaining=0,
            gold_spent=500,
            damage_dealt=500,
            invalid_actions=0,
            total_actions=2,
            won=False,
            outcome="lost",
            outcome_valid=True,
            terminal_confirmed=True,
            terminal_interrupted=False,
            telemetry_valid=True,
            score_eligible=True,
        )

    runner._run_one = controlled
    runner.run_campaign_smoke(resume_artifact=source)

    root = tmp_path / "resumed-campaign"
    summaries = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    resumed_event = next(
        json.loads(line)
        for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if '"event_type": "campaign_resumed"' in line
    )
    assert calls == ["3"]
    assert [item["map_id"] for item in summaries] == ["0", "1", "3"]
    assert resumed_event["imported_maps"] == ["0", "1"]
    assert resumed_event["source_incomplete_stages"] == [3]
    assert resumed_event["next_request_index"] == 12
    assert resumed_event["restored_review"] is True


def test_campaign_invalid_initial_state_fuses_before_any_decision(tmp_path):
    class InvalidStartGame(SimulatedTowerDefense):
        def reset(self, map_id, seed, max_waves):
            raise InvalidInitialStateError(
                "fresh-start gate failed",
                {"requested_map_id": map_id, "observed_wave": 5},
            )

    config = ExperimentConfig(
        experiment_id="invalid-start-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=1,
        models=(ModelConfig(name="Only", provider="rule", model="balanced"),),
        campaign_maps=("river_gate", "fog_crossroads"),
    )

    dashboard = ExperimentRunner(
        config, tmp_path, game_factory=InvalidStartGame
    ).run_campaign_smoke()

    root = tmp_path / "invalid-start-test"
    events = (root / "events.jsonl").read_text(encoding="utf-8")
    validity = json.loads((root / "validity.json").read_text(encoding="utf-8"))
    assert dashboard.exists()
    assert validity["status"] == "invalid"
    assert validity["details"]["observed_wave"] == 5
    assert '"event_type": "campaign_stage_invalid"' in events
    assert '"model_called": false' in events
    assert '"event_type": "decision_requested"' not in events
    assert json.loads((root / "summary.json").read_text(encoding="utf-8")) == []


def test_recording_config_uses_real_time_and_official_map_order():
    path = (
        __import__("pathlib").Path(__file__).parents[1]
        / "configs"
        / "experiment.official-six.recording.json"
    )

    config = ExperimentConfig.load(path)

    assert config.towermind_time_scale == 1.0
    assert config.hold_after_run_seconds == 0.0
    assert config.watchdog_max_game_steps == 12000
    assert config.campaign_maps == ("0", "1", "3", "2", "4")
    assert config.provider_seed == 20260724
    assert config.campaign_max_retries == 0
    assert config.harness_version == "2.5"
    assert config.observation_mode == "semantic_structured_compact"
    assert config.scaffold_id == "two_phase_high_plan_action_v3"
    assert config.low_priority_event_debounce_seconds == 3.0
    assert config.max_tokens == 8192
    deepseek = next(item for item in config.models if item.name == "DeepSeek")
    assert deepseek.omit_temperature is True
    assert deepseek.reasoning_effort == "high"
    assert deepseek.request_timeout_seconds == 60
    assert deepseek.decision_pipeline == "plan_then_action"
    assert deepseek.planning_max_tokens == 8192
    assert deepseek.action_max_tokens == 2048
    assert deepseek.planning_request_params["extra_body"] == {
        "thinking": {"type": "enabled"}
    }
    assert deepseek.action_request_params["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert deepseek.request_params["allowed_openai_params"] == ["reasoning_effort"]
    assert deepseek.request_params["stream"] is True
    assert deepseek.request_params["response_format"] == {"type": "json_object"}
    assert deepseek.request_params["extra_body"] == {
        "thinking": {"type": "enabled"}
    }
    kimi = next(item for item in config.models if item.name == "Kimi")
    assert kimi.reasoning_effort == "high"
    assert kimi.request_timeout_seconds == 60
    assert kimi.request_params["stream"] is True
    doubao = next(item for item in config.models if item.name == "豆包")
    assert doubao.reasoning_effort == "medium"
    assert doubao.request_timeout_seconds == 60
    assert doubao.request_params["stream"] is True


def test_official_request_profiles_and_token_limits_match():
    config_dir = __import__("pathlib").Path(__file__).parents[1] / "configs"
    profiles = []
    for filename in (
        "experiment.official-six.json",
        "experiment.official-six.recording.json",
    ):
        config = ExperimentConfig.load(config_dir / filename)
        assert config.max_tokens == 8192
        profiles.append(next(item for item in config.models if item.name == "DeepSeek"))

    assert profiles[0] == profiles[1]


def test_model_specific_timeout_overrides_experiment_default(tmp_path):
    config = ExperimentConfig(
        experiment_id="model-timeout-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=1,
        models=(
            ModelConfig(
                name="Kimi K3",
                provider="litellm",
                model="moonshot/kimi-k3",
                request_timeout_seconds=60,
            ),
        ),
    )

    runner = ExperimentRunner(config, tmp_path)

    assert runner.models[0].request_timeout == 60
def test_transition_wait_pumps_frames_until_spectator_choice(tmp_path):
    config = ExperimentConfig(
        experiment_id="transition-test",
        backend="sim",
        runs_per_round=1,
        seed=7,
        fixed_map="river_gate",
        unseen_map="fog_crossroads",
        max_waves=1,
        models=(
            ModelConfig(name="Only", provider="rule", model="balanced"),
        ),
        campaign_transition_seconds=0.5,
    )
    runner = ExperimentRunner(config, tmp_path)

    class TransitionGame:
        def __init__(self):
            self.frames = 0

        def pump_transition_frame(self):
            self.frames += 1

        def transition_action(self):
            return "retry" if self.frames >= 2 else None

    game = TransitionGame()

    assert runner._wait_for_transition(game, default="stop") == "retry"
    assert game.frames == 2
