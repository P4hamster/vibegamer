from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from hashlib import sha256
from math import dist
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit

from tower_referee.game.base import GameAdapter, InvalidInitialStateError
from tower_referee.events import EventDetector, StrategicEventBatcher
from tower_referee.micro import LocalTacticsController
from tower_referee.plugin_bridge import PluginBridge, PluginUnavailable
from tower_referee.schema import (
    Action,
    ActionRejection,
    Decision,
    DroppedGold,
    Enemy,
    GameState,
    HeroState,
    KnightState,
    LastActionState,
    StandingOrders,
    Tower,
    WaveResult,
    GameEvent,
)

ACTION_INDEX = {
    ("build", "archer"): 0,
    ("build", "magician"): 1,
    ("build", "knight"): 2,
    ("upgrade", None): 3,
    ("sell", None): 4,
    ("show_range", None): 5,
    ("noop", None): 6,
    ("relocate_knights", None): 7,
    ("deploy_reinforcements", None): 8,
    ("move_hero", None): 9,
    ("hero_skill", None): 10,
    ("upgrade_hero", None): 11,
}

DEFAULT_OBSERVER_PORT = 17871
OBSERVER_PORT_ENV = "TOWERMIND_OBSERVER_PORT"


class TowerMindAdapter(GameAdapter):
    """Thin adapter over TowerMind's official Unity ML-Agents Gym interface.

    TowerMind is real-time. A "wave" here means advancing actions until the
    structured observation reports a new wave or the episode ends.
    """

    def __init__(
        self,
        executable: str | Path,
        repo_root: str | Path,
        time_scale: float = 20.0,
        screen_width: int = 1600,
        screen_height: int = 900,
        quality_level: int = 2,
        fullscreen: bool = False,
        level_overrides: dict[str, dict[str, Any]] | None = None,
        plugin_url: str | None = None,
        plugin_required: bool = False,
        low_priority_event_debounce_seconds: float = 3.0,
        worker_id: int = 0,
    ) -> None:
        self.executable = str(Path(executable).resolve())
        self.repo_root = Path(repo_root).resolve()
        self.time_scale = max(0.1, float(time_scale))
        self.screen_width = max(320, int(screen_width))
        self.screen_height = max(240, int(screen_height))
        self.quality_level = max(0, int(quality_level))
        self.fullscreen = bool(fullscreen)
        self.level_overrides = level_overrides or {}
        self.env: Any = None
        self._unity_process: Any = None
        self._unity_pid: int | None = None
        self.raw: dict[str, Any] = {}
        self.state: GameState | None = None
        self._last_obs: Any = None
        self._episode_done = False
        self._terminal_interrupted: bool | None = None
        self._gold_spent = 0
        self._config_backups: dict[Path, bytes] = {}
        self._active_level_config: dict[str, Any] = {}
        self._enemy_catalog = self._load_enemy_catalog()
        self._tower_catalog = self._load_catalog("TowerConfig.json", "Towers")
        self._hero_config = self._load_json_config("HeroConfig.json")
        self._event_detector = EventDetector()
        self._event_batcher = StrategicEventBatcher(
            low_priority_event_debounce_seconds
        )
        self._monitor_audit: list[dict[str, Any]] = []
        self._micro = LocalTacticsController()
        self._micro_actions: list[dict[str, Any]] = []
        self._plugin = PluginBridge(plugin_url) if plugin_url else None
        self._observer_port = self._resolve_observer_port(plugin_url)
        self._plugin_required = bool(plugin_required)
        self._plugin_mechanics: dict[str, Any] = {}
        self._last_plugin_telemetry: dict[str, Any] = {}
        self._map_fingerprints: dict[str, str] = {}
        self._fingerprint_maps: dict[str, str] = {}
        self.worker_id = max(0, int(worker_id))

    def reset(self, map_id: str, seed: int, max_waves: int) -> GameState:
        del seed  # TowerMind fixed levels are selected through their config.
        self._event_detector.reset()
        self._event_batcher.reset()
        self._monitor_audit = []
        self._micro = LocalTacticsController()
        self._micro_actions = []
        failures: list[dict[str, Any]] = []
        # A transition card has to pump a disposable episode so Unity can
        # repaint. At high time scales that episode may already be several
        # waves old. Try two explicit resets, then reopen Unity as a clean
        # recovery path. No model request happens until this gate passes.
        for attempt in range(1, 4):
            if attempt == 3 and self.env is not None:
                self.close()
            self._set_level(map_id)
            if self.env is None:
                self._open()
            obs = self.env.reset()
            self._last_obs = obs
            self._episode_done = False
            self._terminal_interrupted = None
            self._gold_spent = 0
            self._last_plugin_telemetry = {}
            self.state = self._translate(obs, max_waves)
            fingerprint = self._map_fingerprint(self.state)
            errors = self._initial_state_errors(self.state)
            identity_error = self._fingerprint_identity_error(map_id, fingerprint)
            if identity_error:
                errors.append(identity_error)
            if errors:
                failures.append(
                    {
                        "attempt": attempt,
                        "reopened_unity": attempt == 3,
                        "errors": errors,
                        "observed": self._initial_state_snapshot(
                            self.state, fingerprint
                        ),
                    }
                )
                continue
            self._map_fingerprints[map_id] = fingerprint
            self._fingerprint_maps[fingerprint] = map_id
            break
        else:
            raise InvalidInitialStateError(
                f"Map {map_id} failed the fresh-start gate",
                {
                    "requested_map_id": map_id,
                    "expected": self._expected_initial_state(),
                    "attempts": failures,
                },
            )

        self._refresh_plugin_state()
        initial_meta = {
            "requested_map_id": map_id,
            "map_fingerprint": fingerprint,
            "initial_state_validated": True,
            "reset_attempt": attempt,
            "unity_reopened": attempt == 3,
            "reset_recovery": failures,
        }
        self.state.observer_meta.update(initial_meta)
        if (
            self._plugin is not None
            and self._plugin_required
            and self.state.build_sites
            and not self.state.site_insights
        ):
            deadline = monotonic() + 1.0
            while monotonic() < deadline and not self.state.site_insights:
                sleep(0.05)
                self._refresh_plugin_state()
                self.state.observer_meta.update(initial_meta)
        return self.state

    def _initial_state_errors(self, state: GameState) -> list[str]:
        expected = self._expected_initial_state()
        errors = []
        if state.wave != 0:
            errors.append(f"wave={state.wave}, expected 0")
        if state.game_step != 0:
            errors.append(f"game_step={state.game_step}, expected 0")
        if state.base_hp != expected["base_hp"]:
            errors.append(
                f"base_hp={state.base_hp}, expected {expected['base_hp']}"
            )
        if state.max_base_hp != expected["base_hp"]:
            errors.append(
                f"max_base_hp={state.max_base_hp}, expected {expected['base_hp']}"
            )
        if state.gold != expected["gold"]:
            errors.append(f"gold={state.gold}, expected {expected['gold']}")
        if state.max_waves != expected["max_waves"]:
            errors.append(
                f"max_waves={state.max_waves}, expected {expected['max_waves']}"
            )
        if state.towers:
            errors.append(f"prebuilt_towers={len(state.towers)}, expected 0")
        if not state.build_sites:
            errors.append("build_sites is empty")
        if not state.enemy_paths:
            errors.append("enemy_paths is empty")
        if state.done or state.won:
            errors.append("episode is already terminal")
        return errors

    def _expected_initial_state(self) -> dict[str, int]:
        waves = self._active_level_config.get("Waves") or []
        return {
            "gold": int(self._active_level_config.get("InitialMoney", -1)),
            "base_hp": int(self._active_level_config.get("TotalLife", -1)),
            "max_waves": len(waves),
        }

    @staticmethod
    def _map_fingerprint(state: GameState) -> str:
        geometry = {
            "build_sites": [
                [round(float(x), 3), round(float(y), 3)]
                for x, y in state.build_sites
            ],
            "enemy_paths": [
                [
                    [round(float(x), 3), round(float(y), 3)]
                    for x, y in path
                ]
                for path in state.enemy_paths
            ],
        }
        payload = json.dumps(
            geometry,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(payload).hexdigest()[:16]

    def _fingerprint_identity_error(
        self, map_id: str, fingerprint: str
    ) -> str | None:
        previous_fingerprint = self._map_fingerprints.get(map_id)
        if previous_fingerprint and previous_fingerprint != fingerprint:
            return (
                f"map {map_id} geometry changed from "
                f"{previous_fingerprint} to {fingerprint}"
            )
        previous_map = self._fingerprint_maps.get(fingerprint)
        if previous_map is not None and previous_map != map_id:
            return (
                f"map {map_id} reused geometry fingerprint from map {previous_map}"
            )
        return None

    @staticmethod
    def _initial_state_snapshot(
        state: GameState, fingerprint: str
    ) -> dict[str, Any]:
        return {
            "wave": state.wave,
            "game_step": state.game_step,
            "game_time": state.game_time,
            "base_hp": state.base_hp,
            "max_base_hp": state.max_base_hp,
            "gold": state.gold,
            "max_waves": state.max_waves,
            "tower_count": len(state.towers),
            "build_site_count": len(state.build_sites),
            "enemy_path_count": len(state.enemy_paths),
            "map_fingerprint": fingerprint,
            "done": state.done,
            "won": state.won,
        }

    def pause(self) -> None:
        # Unity is stepped only when env.step is called, so model latency does
        # not advance simulation time.
        return None

    def resume(self) -> None:
        return None

    def set_standing_orders(self, orders: StandingOrders | None) -> None:
        self._micro.set_orders(orders)

    def drain_micro_actions(self) -> list[dict]:
        actions = self._micro_actions
        self._micro_actions = []
        return actions

    def publish_decision(
        self,
        model_name: str,
        decision: Decision,
        accepted: list[Action],
        rejected: list[ActionRejection],
    ) -> None:
        if self._plugin is None:
            return
        action_text = "；".join(self._format_action(action) for action in accepted)
        if decision.standing_orders is not None:
            orders = decision.standing_orders
            order_parts = []
            if orders.hero_anchor:
                order_parts.append(f"英雄驻守{orders.hero_anchor}")
            if orders.knight_block_point:
                order_parts.append(f"骑士拦截{orders.knight_block_point}")
            if orders.reinforcement_point:
                order_parts.append(f"援军投放{orders.reinforcement_point}")
            if order_parts:
                action_text = "；".join(
                    item for item in (action_text, "长期：" + "、".join(order_parts)) if item
                )
        if rejected:
            action_text = "；".join(
                item
                for item in (action_text, f"{len(rejected)} 个动作被裁判拒绝")
                if item
            )
        if not action_text:
            action_text = "等待局面变化"
        try:
            self._plugin.publish_decision(
                model_name,
                decision.analysis_summary or "正在执行当前策略",
                action_text,
            )
        except PluginUnavailable:
            if self._plugin_required:
                raise

    def publish_transition(
        self,
        outcome: str,
        title: str,
        detail: str,
        can_retry: bool = False,
    ) -> None:
        if self._plugin is None:
            return
        try:
            self._plugin.publish_transition(
                outcome,
                title,
                detail,
                can_retry=can_retry,
            )
        except PluginUnavailable:
            if self._plugin_required:
                raise

    def transition_action(self) -> str | None:
        if self._plugin is None:
            return None
        try:
            return self._plugin.transition_action()
        except PluginUnavailable:
            if self._plugin_required:
                raise
            return None

    def pump_transition_frame(self) -> None:
        if self.env is None or self.state is None:
            return
        if self._episode_done:
            # The legacy Gym wrapper forbids stepping a terminal episode.
            # Reset the same map only to give Unity a live frame loop behind
            # the opaque result card; the completed run has already been
            # summarized, and the campaign performs its own next-map reset.
            max_waves = self.state.max_waves
            obs = self.env.reset()
            self._last_obs = obs
            self._episode_done = False
            self._terminal_interrupted = None
            self.state = self._translate(obs, max_waves)
            self._refresh_plugin_state()
        # ML-Agents blocks Unity while Python is idle. Release one no-op
        # decision so OnGUI can repaint and process transition button clicks.
        # Campaign summaries are already finalized before this method runs.
        try:
            obs, _, done, info = self.env.step(
                [0.0, 0.0, ACTION_INDEX[("noop", None)]]
            )
        except (RuntimeError, ValueError):
            # Some ML-Agents wrappers reject a step on the terminal frame.
            # The visible terminal frame remains valid; the next campaign
            # stage will perform an explicit reset.
            return
        self._last_obs = obs
        self._record_terminal_step(done, info)
        self.state = self._translate(obs, self.state.max_waves)
        self._refresh_plugin_state()

    def apply_actions(self, actions: list[Action]) -> GameState:
        if self.env is None or self.state is None:
            raise RuntimeError("TowerMind must be reset before use")
        for action in actions:
            x, y, index = self._encode_action(action)
            before_gold = self.state.gold
            obs, _, done, info = self.env.step([x, y, index])
            self._record_terminal_step(done, info)
            self._last_obs = obs
            self.state = self._translate(obs, self.state.max_waves)
            self._gold_spent += max(0, before_gold - self.state.gold)
            # _translate() exposes TowerMind's transient list-index IDs. Restore
            # the plugin's stable site-based tower IDs before encoding the next
            # action in the same decision, otherwise an upgrade/sell following
            # a build can lose its target and fall back to coordinate (0, 0).
            self._refresh_plugin_state()
            if done:
                break
        return self.state

    def play_wave(self) -> tuple[GameState, WaveResult]:
        if self.env is None or self.state is None:
            raise RuntimeError("TowerMind must be reset before use")
        old = self.state
        target_wave = old.wave + 1
        damage_before = sum(t.damage for t in old.towers)
        steps = 0
        while not self._episode_done and self.state.wave < target_wave and steps < 3000:
            obs, _, done, info = self.env.step([0.0, 0.0, 6])
            self._record_terminal_step(done, info)
            self._last_obs = obs
            self.state = self._translate(obs, old.max_waves)
            steps += 1
        if steps >= 3000 and self.state.wave < target_wave:
            raise TimeoutError("TowerMind did not advance to the next wave in 3000 steps")
        damage_after = sum(t.damage for t in self.state.towers)
        leaked = max(0, old.base_hp - self.state.base_hp)
        self._refresh_plugin_state()
        result = WaveResult(
            wave=self.state.wave,
            base_hp_before=old.base_hp,
            base_hp_after=self.state.base_hp,
            gold_before=old.gold,
            gold_after=self.state.gold,
            enemies_defeated=0,
            enemies_leaked=leaked,
            damage_dealt=self._result_damage(
                old,
                self.state,
                observed=0.0,
                fallback=max(0.0, damage_after - damage_before),
            ),
        )
        return self.state, result

    def advance_until_event(
        self, max_steps: int = 600
    ) -> tuple[GameState, list[GameEvent], WaveResult]:
        if self.env is None or self.state is None:
            raise RuntimeError("TowerMind must be reset before use")
        # A few narrow test doubles construct the adapter without __init__.
        if not hasattr(self, "_event_batcher"):
            self._event_batcher = StrategicEventBatcher()
        if not hasattr(self, "_monitor_audit"):
            self._monitor_audit = []
        start = self.state
        previous = self.state
        damage_before = sum(t.damage for t in start.towers)
        observed_damage = 0.0
        events: list[GameEvent] = []
        steps = 0
        while not self._episode_done and steps < max_steps:
            micro_action = self._micro.decide(previous)
            encoded = (
                list(self._encode_action(micro_action))
                if micro_action is not None
                else [0.0, 0.0, 6]
            )
            obs, _, done, info = self.env.step(encoded)
            self._record_terminal_step(done, info)
            self._last_obs = obs
            current = self._translate(obs, start.max_waves)
            observed_damage += self._observed_enemy_damage(previous, current)
            detected = self._event_detector.detect(previous, current)
            events, audit = self._event_batcher.push(
                detected,
                current.game_time,
            )
            self._monitor_audit.extend(audit)
            self.state = current
            if micro_action is not None:
                self._micro_actions.append(
                    {
                        "game_step": current.game_step,
                        "type": micro_action.type,
                        "position": micro_action.position,
                    }
                )
            steps += 1
            if events:
                break
            previous = current
        if not events and not self._episode_done:
            events, audit = self._event_batcher.flush(
                self.state.game_time,
                "monitor_limit",
            )
            self._monitor_audit.extend(audit)
            if not events:
                events = [
                    GameEvent(
                        "monitor_interval",
                        {"steps": steps, "game_time": self.state.game_time},
                        10,
                    )
                ]
        self._refresh_plugin_state()
        damage_after = sum(t.damage for t in self.state.towers)
        result = WaveResult(
            wave=self.state.wave,
            base_hp_before=start.base_hp,
            base_hp_after=self.state.base_hp,
            gold_before=start.gold,
            gold_after=self.state.gold,
            enemies_defeated=max(
                0, len(start.visible_enemies) - len(self.state.visible_enemies)
            ),
            enemies_leaked=max(0, start.base_hp - self.state.base_hp),
            damage_dealt=self._result_damage(
                start,
                self.state,
                observed=observed_damage,
                fallback=max(0.0, damage_after - damage_before),
            ),
        )
        return self.state, events, result

    def drain_monitor_audit(self) -> list[dict]:
        audit = list(self._monitor_audit)
        self._monitor_audit.clear()
        return audit

    def close(self) -> None:
        try:
            if self.env is not None:
                self.env.close()
        except Exception as exc:
            # Cleanup must still terminate the exact Unity player that this
            # adapter launched; a close error must not leave the Observer
            # port occupied for the next run.
            del exc
        finally:
            self.env = None
            self._terminate_spawned_unity()
        for path, payload in self._config_backups.items():
            path.write_bytes(payload)
        self._config_backups.clear()

    @staticmethod
    def _resolve_observer_port(plugin_url: str | None) -> int:
        if not plugin_url:
            return DEFAULT_OBSERVER_PORT
        parsed = urlsplit(plugin_url)
        port = parsed.port or DEFAULT_OBSERVER_PORT
        if not 1024 <= port <= 65535:
            raise ValueError("Observer plugin port must be between 1024 and 65535")
        return port

    def _terminate_spawned_unity(self) -> None:
        """Best-effort cleanup for Unity players that outlive ML-Agents close()."""
        process = self._unity_process
        pid = self._unity_pid
        self._unity_process = None
        self._unity_pid = None
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            except OSError:
                pass
        if pid is None:
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            pass

    def _open(self) -> None:
        try:
            from mlagents_envs.environment import UnityEnvironment
            # ML-Agents 1.1 registers a remote demo manifest at import time.
            # TowerMind uses a local executable, so disable that unnecessary
            # network lookup before importing the legacy Gym wrapper.
            from mlagents_envs.registry import default_registry

            default_registry.clear()
            from mlagents_envs.envs.unity_gym_env import UnityToGymWrapper
            from mlagents_envs.side_channel.engine_configuration_channel import (
                EngineConfigurationChannel,
            )
        except ImportError as exc:
            raise RuntimeError(
                "ML-Agents is not installed. Use Python 3.10 and run "
                "pip install -e '.[towermind]'"
            ) from exc
        sys.path.insert(0, str(self.repo_root))
        from common.wrappers import Continuous2DiscreteActionWrapper

        channel = EngineConfigurationChannel()
        engine_config = {
            "quality_level": self.quality_level,
            "target_frame_rate": 60,
            "time_scale": self.time_scale,
            "capture_frame_rate": 60,
        }
        # ML-Agents applies width/height through Screen.SetResolution in
        # windowed mode. On macOS that can undo native fullscreen, so true
        # fullscreen uses Unity launch flags and leaves resolution to macOS.
        if not self.fullscreen:
            engine_config.update(
                width=self.screen_width,
                height=self.screen_height,
            )
        channel.set_configuration_parameters(**engine_config)
        launch_args = None
        if self.fullscreen:
            launch_args = [
                "-screen-fullscreen",
                "1",
                "-screen-width",
                str(self.screen_width),
                "-screen-height",
                str(self.screen_height),
            ]
        previous_port = os.environ.get(OBSERVER_PORT_ENV)
        os.environ[OBSERVER_PORT_ENV] = str(self._observer_port)
        try:
            unity = UnityEnvironment(
                self.executable,
                worker_id=self.worker_id,
                additional_args=launch_args,
                side_channels=[channel],
            )
        finally:
            if previous_port is None:
                os.environ.pop(OBSERVER_PORT_ENV, None)
            else:
                os.environ[OBSERVER_PORT_ENV] = previous_port
        self._unity_process = getattr(unity, "_process", None)
        self._unity_pid = getattr(self._unity_process, "pid", None)
        gym_env = UnityToGymWrapper(unity, uint8_visual=True, allow_multiple_obs=True)
        self.env = Continuous2DiscreteActionWrapper(gym_env)
        if self._plugin is not None:
            try:
                self._plugin.wait_until_ready()
                self._plugin_mechanics = self._plugin.mechanics()
            except PluginUnavailable:
                if self._plugin_required:
                    self.env.close()
                    self.env = None
                    raise

    def _translate(self, obs: Any, max_waves: int) -> GameState:
        sys.path.insert(0, str(self.repo_root))
        from common.wrappers import get_json_from_obs

        raw = get_json_from_obs(obs[1])
        self.raw = raw
        sites = self._tower_sites(raw)
        towers = []
        for index, item in enumerate(raw.get("Level_Towers_Realtime_Status") or []):
            if not item.get("Is_Built", True):
                continue
            position = item.get("Position") or {}
            tower_position = (
                float(position.get("X", 0)),
                float(position.get("Y", 0)),
            )
            kind = self._tower_kind(item.get("Tower_Name", ""))
            level = int(item.get("Tower_Level", 0)) + 1
            price = {
                self._tower_kind(str(config.get("Name", ""))): int(
                    config.get("Price", 0)
                )
                for config in self._tower_catalog
            }.get(kind, 0)
            towers.append(
                Tower(
                    id=self._stable_tower_id(tower_position, sites, index),
                    kind=kind,
                    position=tower_position,
                    # TowerMind exposes zero-based upgrade indices.
                    level=level,
                    spent=price * level,
                    frozen=bool(item.get("Is_Frozen", False)),
                    rally_position=self._position(
                        item.get("Knights_Assembly_Position")
                    ),
                )
            )
        enemies = []
        for index, item in enumerate(raw.get("Level_Enemies_Realtime_Status") or []):
            enemy_type = int(item.get("Type", -1))
            enemy_meta = self._enemy_catalog.get(enemy_type, {})
            position = self._position(item.get("Position"))
            enemies.append(
                Enemy(
                    id=f"enemy_{index:03}",
                    kind=str(enemy_meta.get("Name", enemy_type)),
                    hp=float(item.get("Current_Health", 0)),
                    progress=self._path_progress(position, raw),
                    position=position,
                    flying=not bool(enemy_meta.get("CanAttackGround", True))
                    if "CanAttackGround" in enemy_meta
                    else enemy_type == 2,
                    description=str(enemy_meta.get("Description", "")),
                )
            )
        total_waves = int(raw.get("Level_Total_Waves_Number", max_waves))
        hero_raw = raw.get("Level_Hero_Realtime_Status") or {}
        hero = HeroState(
            position=self._position(hero_raw.get("Hero_Position")),
            hp=float(hero_raw.get("Hero_Current_Health", 0)),
            max_hp=float(hero_raw.get("Hero_Maximum_Health", 1600)),
            dead=bool(hero_raw.get("Is_Hero_Dead", False)),
            revive_countdown=float(hero_raw.get("Hero_Revive_Countdown", 0)),
        )
        knights = [
            KnightState(
                id=f"knight_{index:03}",
                position=self._position(item.get("Position")) or (0.0, 0.0),
                hp=float(item.get("Current_Health", 0)),
            )
            for index, item in enumerate(
                raw.get("Level_Knights_Realtime_Status") or []
            )
        ]
        coin_raw = raw.get("Level_Dropped_Gold_Coins_Realtime_Status")
        dropped_gold = (
            DroppedGold(
                position=self._position(coin_raw.get("Position")) or (0.0, 0.0),
                remaining_lifetime=float(coin_raw.get("RemainingLifetime", 0)),
            )
            if coin_raw
            else None
        )
        last_raw = raw.get("Agent_Last_Action_Info") or {}
        last_action = LastActionState(
            action_index=int(last_raw.get("Action_Index", -1)),
            position=self._position(last_raw.get("Position")) or (0.0, 0.0),
            success=bool(last_raw.get("Is_Success", True)),
            error_code=last_raw.get("Error_Code"),
        )
        return GameState(
            wave=int(raw.get("Level_Current_Wave", 0)),
            # This is the native map's total.  The runner separately enforces
            # a requested smoke-wave budget; reporting a truncated value here
            # would make a partial smoke look like a completed level.
            max_waves=total_waves,
            base_hp=int(raw.get("Level_Current_Health", 0)),
            max_base_hp=int(raw.get("Level_Initial_Health", 1)),
            gold=int(raw.get("Level_Current_Gold_Coins", 0)),
            towers=towers,
            visible_enemies=enemies,
            available_actions=[
                "build",
                "upgrade",
                "sell",
                "show_range",
                "relocate_knights",
                "deploy_reinforcements",
                "move_hero",
                "hero_skill",
                "upgrade_hero",
                "noop",
            ],
            build_sites=sites,
            enemy_paths=[
                [
                    self._position(point) or (0.0, 0.0)
                    for point in path
                ]
                for path in (raw.get("Level_Enemy_Movement_Paths") or [])
            ],
            current_wave_enemy_types=[
                str(self._enemy_catalog.get(int(item), {}).get("Name", item))
                for item in (raw.get("Level_Current_Wave_Enemies") or [])
            ],
            hero=hero,
            knights=knights,
            dropped_gold=dropped_gold,
            reinforcement_countdown=float(
                raw.get("Level_Knight_Reinforcements_Countdown", 0)
            ),
            active_fire_zones=[
                self._position(item) or (0.0, 0.0)
                for item in (raw.get("Level_Hero_Fire_Of_Rage_Positions") or [])
            ],
            last_action=last_action,
            game_step=int(raw.get("Level_Current_Step", 0)),
            game_time=float(raw.get("Level_Current_Time", 0)),
            game_rules={
                "objective": "守住基地并尽可能高效使用金币",
                "future_waves_hidden": True,
                "sell_refund_ratio": float(
                    self._active_level_config.get("TowerSellingDiscount", 0)
                ),
                "tower_types": [
                    {
                        "name": item.get("Name"),
                        "price": item.get("Price"),
                        "upgrade_price": item.get("UpgradePrice"),
                        "attack_speed": item.get("AttackSpeed"),
                        "attack_damage": item.get("AttackDamage"),
                        "attack_range": item.get("AttackRange"),
                        "can_attack_air": item.get("CanAttackAir"),
                        "can_attack_ground": item.get("CanAttackGround"),
                        "description": item.get("Description"),
                    }
                    for item in self._tower_catalog
                ],
                "hero": {
                    key: self._hero_config.get(key)
                    for key in (
                        "Health",
                        "AttackDamage",
                        "AttackRange",
                        "UpgradeGoldCoinCost",
                        "ReviveTime",
                        "Description",
                        "SkillDescription",
                    )
                },
            },
            done=self._episode_done,
            won=(
                self._episode_done
                and self._terminal_interrupted is False
                and int(raw.get("Level_Current_Health", 0)) > 0
            ),
            terminal_interrupted=(
                self._terminal_interrupted if self._episode_done else None
            ),
        )

    def _record_terminal_step(self, done: bool, info: Any) -> None:
        """Preserve ML-Agents' native terminal certificate before any reset."""
        self._episode_done = bool(done)
        if not self._episode_done:
            self._terminal_interrupted = None
            return
        self._terminal_interrupted = None
        terminal_steps = info.get("step") if isinstance(info, dict) else None
        interrupted = getattr(terminal_steps, "interrupted", None)
        if interrupted is not None and len(interrupted) > 0:
            self._terminal_interrupted = bool(interrupted[0])

    def _refresh_plugin_state(self) -> None:
        if self._plugin is None or self.state is None:
            return
        try:
            snapshot = self._plugin.state()
        except PluginUnavailable as exc:
            self.state.observer_meta = {
                "connected": False,
                "error": str(exc),
            }
            if self._plugin_required:
                raise
            return
        self._merge_plugin_snapshot(self.state, snapshot)

    def _merge_plugin_snapshot(
        self, state: GameState, snapshot: dict[str, Any]
    ) -> None:
        if not snapshot.get("ready"):
            state.observer_meta = {
                "connected": False,
                "error": snapshot.get("error", "observer is not ready"),
            }
            if self._plugin_required:
                raise PluginUnavailable(str(state.observer_meta["error"]))
            return
        legal_sites = list(state.build_sites)
        fresh_empty_map = state.wave == 0 and state.game_step == 0 and not state.towers
        site_insights = []
        for item in snapshot.get("build_sites") or []:
            position_raw = item.get("position")
            if not isinstance(position_raw, list) or len(position_raw) != 2:
                continue
            position = (float(position_raw[0]), float(position_raw[1]))
            currently_official = any(
                dist(position, legal) <= 0.15 for legal in legal_sites
            )
            remembered_own_site = (
                not fresh_empty_map
                and bool(item.get("known_legal"))
                and (bool(item.get("built")) or bool(item.get("under_fog")))
            )
            if not currently_official and not remembered_own_site:
                continue
            normalized_item = dict(item)
            if fresh_empty_map:
                # Native ML-Agents state is authoritative at the freshly
                # validated boundary. The HTTP observer can lag one frame
                # behind a reset and must not resurrect a prior map's tower.
                normalized_item.update(
                    built=False,
                    under_fog=False,
                    operational=True,
                )
                normalized_item.pop("tower_type", None)
                normalized_item.pop("tower_level", None)
            if bool(item.get("built")) and not currently_official:
                # The in-game HTTP snapshot can lag one rendered frame behind
                # ML-Agents. Missing from the official list is already enough
                # to mark a remembered own tower as cloud-covered.
                normalized_item["under_fog"] = True
                normalized_item["operational"] = False
            site_insights.append(normalized_item)
        state.site_insights = site_insights
        if not fresh_empty_map:
            self._synchronize_plugin_towers(state, site_insights)
        incoming_telemetry = dict(snapshot.get("telemetry") or {})
        completed = incoming_telemetry.get("last_completed")
        episode_done = bool(getattr(self, "_episode_done", False))
        last_telemetry = dict(
            getattr(self, "_last_plugin_telemetry", {})
        )
        if fresh_empty_map:
            # Like towers, cumulative telemetry can be one observer frame
            # behind reset. A new model must never inherit the previous map's
            # kills, leaks, or damage.
            state.combat_telemetry = {}
        elif episode_done and isinstance(completed, dict):
            state.combat_telemetry = {
                **completed,
                "latest_seq": incoming_telemetry.get("latest_seq", 0),
                "source": "last_completed",
            }
        elif (
            episode_done
            and last_telemetry
            and int(incoming_telemetry.get("latest_seq", 0))
            < int(last_telemetry.get("latest_seq", 0))
        ):
            state.combat_telemetry = last_telemetry
        else:
            state.combat_telemetry = incoming_telemetry
        self._last_plugin_telemetry = dict(state.combat_telemetry)
        state.observer_meta = {
            "connected": True,
            "plugin_version": snapshot.get("plugin_version"),
            "scene": snapshot.get("scene"),
        }
        if self._plugin_mechanics:
            state.game_rules["public_mechanics"] = self._plugin_mechanics

        plugin_enemies = list(snapshot.get("enemies") or [])
        used: set[int] = set()
        for enemy in state.visible_enemies:
            candidates: list[tuple[float, int, dict[str, Any]]] = []
            for index, item in enumerate(plugin_enemies):
                if index in used or item.get("enemy_type") != enemy.kind:
                    continue
                raw_position = item.get("position")
                if (
                    enemy.position is None
                    or not isinstance(raw_position, list)
                    or len(raw_position) != 2
                ):
                    continue
                position = (float(raw_position[0]), float(raw_position[1]))
                candidates.append((dist(enemy.position, position), index, item))
            if not candidates:
                continue
            distance, index, match = min(candidates, key=lambda value: value[0])
            if distance > 0.35:
                continue
            used.add(index)
            enemy.id = str(match.get("enemy_id", enemy.id))
            enemy.max_hp = float(match.get("max_health", enemy.max_hp))
            enemy.progress = float(match.get("path_progress", enemy.progress))
            enemy.movement_type = str(match.get("movement_type", ""))
            enemy.distance_to_base = float(
                match.get("path_distance_to_base", 0.0)
            )
            enemy.estimated_seconds_to_base = float(
                match.get("estimated_seconds_to_base", 0.0)
            )

    def _synchronize_plugin_towers(
        self,
        state: GameState,
        site_insights: list[dict[str, Any]],
    ) -> None:
        existing = list(state.towers)
        prices = {
            self._tower_kind(str(item.get("Name", ""))): int(
                item.get("Price", 0)
            )
            for item in getattr(self, "_tower_catalog", [])
        }
        synchronized: list[Tower] = []
        for site in site_insights:
            if not bool(site.get("built")) or not site.get("tower_type"):
                continue
            raw_position = site.get("position")
            if not isinstance(raw_position, list) or len(raw_position) != 2:
                continue
            position = (float(raw_position[0]), float(raw_position[1]))
            kind = str(site.get("tower_type"))
            level = max(1, int(site.get("tower_level", 1)))
            previous = next(
                (
                    tower
                    for tower in existing
                    if dist(tower.position, position) <= 0.15
                ),
                None,
            )
            site_id = str(site.get("site_id", "unknown"))
            synchronized.append(
                Tower(
                    id=f"tower_{site_id}",
                    kind=kind,
                    position=position,
                    level=level,
                    spent=(
                        previous.spent
                        if previous is not None and previous.spent > 0
                        else prices.get(kind, 0) * level
                    ),
                    damage=previous.damage if previous is not None else 0.0,
                    frozen=bool(site.get("frozen", False)),
                    rally_position=self._list_position(
                        site.get("knight_assembly_position")
                    ),
                    under_fog=bool(site.get("under_fog", False)),
                    operational=bool(site.get("operational", True)),
                )
            )
        state.towers = synchronized

    @staticmethod
    def _telemetry_delta(before: GameState, after: GameState, key: str) -> float:
        return max(
            0.0,
            float(after.combat_telemetry.get(key, 0))
            - float(before.combat_telemetry.get(key, 0)),
        )

    @classmethod
    def _result_damage(
        cls,
        before: GameState,
        after: GameState,
        observed: float,
        fallback: float,
    ) -> float:
        if (
            before.observer_meta.get("connected")
            and after.observer_meta.get("connected")
            and before.combat_telemetry
            and after.combat_telemetry
        ):
            return cls._telemetry_delta(before, after, "enemy_damage")
        return max(0.0, observed, fallback)

    @staticmethod
    def _format_action(action: Action) -> str:
        tower_names = {
            "archer": "弓箭塔",
            "magician": "魔法塔",
            "knight": "骑士塔",
        }
        if action.type == "build":
            return f"建造{tower_names.get(action.tower or '', action.tower)} @{action.position}"
        if action.type == "upgrade":
            return f"升级 {action.tower_id}"
        if action.type == "sell":
            return f"出售 {action.tower_id}"
        labels = {
            "show_range": "显示射程",
            "relocate_knights": "调整骑士集结点",
            "deploy_reinforcements": "投放援军",
            "move_hero": "移动英雄",
            "hero_skill": "释放英雄技能",
            "upgrade_hero": "升级英雄",
            "noop": "暂不调整",
        }
        label = labels.get(action.type, action.type)
        return f"{label} @{action.position}" if action.position else label

    def _encode_action(self, action: Action) -> tuple[float, float, int]:
        x, y = action.position or (0.0, 0.0)
        key: tuple[str, str | None]
        if action.type == "build":
            key = ("build", action.tower)
        else:
            key = (action.type, None)
            if action.tower_id and self.state:
                tower = next(
                    (t for t in self.state.towers if t.id == action.tower_id), None
                )
                if tower:
                    x, y = tower.position
        if key not in ACTION_INDEX:
            raise ValueError(f"Action is not supported by TowerMind: {key}")
        return float(x), float(y), ACTION_INDEX[key]

    @staticmethod
    def _observed_enemy_damage(before: GameState, after: GameState) -> float:
        """Estimate combat damage from consecutive structured observations."""
        current = {enemy.id: enemy for enemy in after.visible_enemies}
        damage = 0.0
        for enemy in before.visible_enemies:
            if enemy.id in current:
                damage += max(0.0, enemy.hp - current[enemy.id].hp)
            elif after.base_hp >= before.base_hp:
                # The enemy vanished without damaging the base, so it was killed.
                damage += max(0.0, enemy.hp)
        return damage

    def _load_enemy_catalog(self) -> dict[int, dict[str, Any]]:
        payload = self._load_json_config("AllEnemiesConfig.json")
        return {index: item for index, item in enumerate(payload.get("Enemies", []))}

    def _config_dir(self) -> Path:
        app = Path(self.executable)
        data = (
            app / "Contents/Resources/Data"
            if app.suffix == ".app"
            else app.parent / "td_Data"
        )
        return data / "StreamingAssets/Config"

    def _load_json_config(self, name: str) -> dict[str, Any]:
        return json.loads(
            (self._config_dir() / name).read_text(encoding="utf-8-sig")
        )

    def _load_catalog(self, name: str, key: str) -> list[dict[str, Any]]:
        return list(self._load_json_config(name).get(key, []))

    @staticmethod
    def _position(value: Any) -> tuple[float, float] | None:
        if not isinstance(value, dict) or "X" not in value or "Y" not in value:
            return None
        return (round(float(value["X"]), 3), round(float(value["Y"]), 3))

    @staticmethod
    def _list_position(value: Any) -> tuple[float, float] | None:
        if not isinstance(value, list) or len(value) != 2:
            return None
        return (round(float(value[0]), 3), round(float(value[1]), 3))

    @classmethod
    def _path_progress(
        cls, position: tuple[float, float] | None, raw: dict[str, Any]
    ) -> float:
        if position is None:
            return 0.0
        points = [
            cls._position(point)
            for path in (raw.get("Level_Enemy_Movement_Paths") or [])
            for point in path
        ]
        points = [point for point in points if point is not None]
        if not points:
            return 0.0
        nearest = min(
            range(len(points)),
            key=lambda index: (points[index][0] - position[0]) ** 2
            + (points[index][1] - position[1]) ** 2,
        )
        return round(nearest / max(len(points) - 1, 1), 3)

    def _set_level(self, map_id: str) -> None:
        try:
            level = int(map_id)
        except ValueError as exc:
            raise ValueError("TowerMind map_id must be an integer from 0 to 8") from exc
        if not 0 <= level <= 4:
            raise ValueError("This TowerMind build provides benchmark map IDs 0 to 4")
        app = Path(self.executable)
        data = app / "Contents/Resources/Data" if app.suffix == ".app" else app.parent / "td_Data"
        config_path = data / "StreamingAssets/Config/FixedLevelsConfig.json"
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if isinstance(config, dict):
            if "CurrentLevel" in config:
                config["CurrentLevel"] = level
            elif "Current_Level" in config:
                config["Current_Level"] = level
            else:
                raise KeyError("CurrentLevel is missing from FixedLevelsConfig.json")
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        levels_path = self._config_dir() / "BenchmarkLevelsConfig.json"
        levels = json.loads(levels_path.read_text(encoding="utf-8-sig"))
        target = next(
            (
                item
                for item in levels.get("Levels", [])
                if int(item.get("ID", -1)) == level
            ),
            None,
        )
        if target is None:
            raise KeyError(f"Benchmark level {level} is missing")
        override = self.level_overrides.get(str(level))
        if override:
            if levels_path not in self._config_backups:
                self._config_backups[levels_path] = levels_path.read_bytes()
            allowed = {"InitialMoney", "TowerSellingDiscount"}
            unknown = set(override) - allowed
            if unknown:
                raise ValueError(
                    f"Unsupported level override fields: {sorted(unknown)}"
                )
            target.update(override)
            levels_path.write_text(
                json.dumps(levels, ensure_ascii=False),
                encoding="utf-8",
            )
        self._active_level_config = dict(target)

    @staticmethod
    def _tower_kind(name: str) -> str:
        lowered = name.lower()
        if "magician" in lowered:
            return "magician"
        if "knight" in lowered:
            return "knight"
        return "archer"

    @staticmethod
    def _tower_sites(raw: dict[str, Any]) -> list[tuple[float, float]]:
        candidates = (
            raw.get("Level_Tower_Points")
            or raw.get("Level_Tower_Positions")
            or raw.get("Tower_Points")
            or raw.get("Level_Towers_Realtime_Status")
            or []
        )
        sites = []
        for item in candidates:
            position = item.get("Position", item) if isinstance(item, dict) else {}
            if "X" in position and "Y" in position:
                sites.append((float(position["X"]), float(position["Y"])))
        return sites

    @staticmethod
    def _stable_tower_id(
        position: tuple[float, float],
        sites: list[tuple[float, float]],
        fallback_index: int,
    ) -> str:
        if sites:
            site_index = min(
                range(len(sites)),
                key=lambda index: dist(position, sites[index]),
            )
            if dist(position, sites[site_index]) <= 0.15:
                return f"tower_site_{site_index:02d}"
        return f"tower_{fallback_index:03d}"
