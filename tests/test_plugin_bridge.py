from __future__ import annotations

import json
import pytest
from types import MethodType, SimpleNamespace
from unittest.mock import patch

from tower_referee.game.towermind import TowerMindAdapter
from tower_referee.plugin_bridge import PluginBridge
from tower_referee.schema import Action, Enemy, GameState, HeroState, Tower


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_plugin_bridge_reads_health_and_publishes_decision():
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.endswith("/health"):
            return FakeResponse({"ok": True, "version": "0.1.0"})
        assert request.full_url.endswith("/decision")
        assert json.loads(request.data)["model"] == "DeepSeek"
        return FakeResponse({"ok": True})

    bridge = PluginBridge(timeout=0.25)
    with patch("tower_referee.plugin_bridge.urlopen", side_effect=fake_urlopen):
        assert bridge.health()["ok"] is True
        assert bridge.publish_decision("DeepSeek", "守住中段", "建造魔法塔")[
            "ok"
        ]
    assert [item[0].method for item in requests] == ["GET", "POST"]


def test_towermind_observer_port_is_read_from_plugin_url():
    assert TowerMindAdapter._resolve_observer_port("http://127.0.0.1:19001") == 19001
    assert TowerMindAdapter._resolve_observer_port(None) == 17871
    with pytest.raises(ValueError):
        TowerMindAdapter._resolve_observer_port("http://127.0.0.1:80")


def test_plugin_bridge_publishes_transition_and_reads_choice():
    payloads = []

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/decision"):
            payloads.append(json.loads(request.data))
            return FakeResponse({"ok": True})
        assert request.full_url.endswith("/transition-action")
        return FakeResponse({"ok": True, "action": "retry"})

    bridge = PluginBridge(timeout=0.25)
    with patch("tower_referee.plugin_bridge.urlopen", side_effect=fake_urlopen):
        bridge.publish_transition(
            "failure",
            "YOU FAILED",
            "止步第 3 关",
            can_retry=True,
        )
        assert bridge.transition_action() == "retry"

    assert payloads[0]["view"] == "transition"
    assert payloads[0]["can_retry"] is True


def test_plugin_bridge_reads_current_decision():
    def fake_urlopen(request, timeout):
        assert request.full_url.endswith("/decision")
        assert request.method == "GET"
        return FakeResponse(
            {
                "view": "transition",
                "analysis_summary": "YOU DID IT!",
            }
        )

    bridge = PluginBridge(timeout=0.25)
    with patch("tower_referee.plugin_bridge.urlopen", side_effect=fake_urlopen):
        assert bridge.decision()["view"] == "transition"


def test_towermind_initial_state_gate_rejects_advanced_or_wrong_economy():
    adapter = object.__new__(TowerMindAdapter)
    adapter._active_level_config = {
        "InitialMoney": 120,
        "TotalLife": 20,
        "Waves": [15, 16, 18, 0, 1],
    }
    state = GameState(
        wave=5,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=500,
        build_sites=[(0.0, 0.0)],
        enemy_paths=[[(0.0, 0.0), (1.0, 1.0)]],
        game_step=0,
    )

    errors = adapter._initial_state_errors(state)

    assert "wave=5, expected 0" in errors
    assert "gold=500, expected 120" in errors


def test_towermind_map_fingerprint_detects_cross_map_geometry_reuse():
    adapter = object.__new__(TowerMindAdapter)
    adapter._map_fingerprints = {"0": "abc123"}
    adapter._fingerprint_maps = {"abc123": "0"}

    assert (
        adapter._fingerprint_identity_error("1", "abc123")
        == "map 1 reused geometry fingerprint from map 0"
    )


def test_towermind_cleanup_terminates_spawned_unity_process():
    class FakeProcess:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            del timeout
            self.waited = True

    adapter = object.__new__(TowerMindAdapter)
    adapter._unity_process = FakeProcess()
    adapter._unity_pid = 12345

    adapter._terminate_spawned_unity()

    assert adapter._unity_process is None
    assert adapter._unity_pid is None


def test_transition_frame_resets_terminal_gym_episode_before_pumping():
    class FakeEnv:
        def __init__(self):
            self.reset_calls = 0
            self.step_calls = 0

        def reset(self):
            self.reset_calls += 1
            return "reset-observation"

        def step(self, action):
            self.step_calls += 1
            assert action == [0.0, 0.0, 6]
            return "step-observation", 0.0, False, {}

    adapter = object.__new__(TowerMindAdapter)
    adapter.env = FakeEnv()
    adapter.state = GameState(
        wave=5,
        max_waves=5,
        base_hp=1,
        max_base_hp=20,
        gold=0,
        done=True,
        won=True,
    )
    adapter._episode_done = True
    adapter._translate = MethodType(
        lambda self, _obs, max_waves: GameState(
            wave=0,
            max_waves=max_waves,
            base_hp=20,
            max_base_hp=20,
            gold=500,
        ),
        adapter,
    )
    adapter._refresh_plugin_state = MethodType(lambda self: None, adapter)

    adapter.pump_transition_frame()

    assert adapter.env.reset_calls == 1
    assert adapter.env.step_calls == 1
    assert adapter._episode_done is False


def test_plugin_snapshot_filters_non_official_sites_and_enriches_enemy():
    adapter = object.__new__(TowerMindAdapter)
    adapter._plugin_mechanics = {"objective": {"victory": "survive"}}
    adapter._plugin_required = False
    state = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=500,
        build_sites=[(-0.23, 0.22), (1.35, 0.39)],
        visible_enemies=[
            Enemy(
                id="enemy_000",
                kind="Outlaw",
                hp=400,
                progress=0.1,
                position=(-1.0, 0.8),
            )
        ],
    )
    snapshot = {
        "ready": True,
        "plugin_version": "0.1.0",
        "scene": "map",
        "build_sites": [
            {"site_id": "site_00", "position": [-0.23, 0.22]},
            {"site_id": "fog_marker", "position": [-0.12, 2.62]},
        ],
        "enemies": [
            {
                "enemy_id": "enemy_-42",
                "enemy_type": "Outlaw",
                "position": [-0.95, 0.8],
                "max_health": 400,
                "path_progress": 0.35,
                "movement_type": "Ground",
                "path_distance_to_base": 4.5,
                "estimated_seconds_to_base": 9.0,
            }
        ],
        "telemetry": {"enemy_damage": 123, "leaks": 2},
    }

    adapter._merge_plugin_snapshot(state, snapshot)

    assert [site["site_id"] for site in state.site_insights] == ["site_00"]
    assert state.visible_enemies[0].id == "enemy_-42"
    assert state.visible_enemies[0].estimated_seconds_to_base == 9.0
    assert state.combat_telemetry["enemy_damage"] == 123
    assert state.game_rules["public_mechanics"]["objective"]["victory"] == "survive"


def test_fresh_map_ignores_stale_plugin_tower_from_previous_episode():
    adapter = object.__new__(TowerMindAdapter)
    adapter._plugin_mechanics = {}
    adapter._plugin_required = False
    adapter._tower_catalog = []
    state = GameState(
        wave=0,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=500,
        game_step=0,
        build_sites=[(0.0, 0.0)],
    )
    snapshot = {
        "ready": True,
        "plugin_version": "0.2.0",
        "build_sites": [
            {
                "site_id": "current_site",
                "known_legal": True,
                "position": [0.0, 0.0],
                "built": True,
                "tower_type": "archer",
                "tower_level": 3,
            },
            {
                "site_id": "old_map_site",
                "known_legal": True,
                "position": [9.0, 9.0],
                "built": True,
                "tower_type": "magician",
                "tower_level": 2,
            },
        ],
        "enemies": [],
        "telemetry": {"enemy_damage": 9999, "leaks": 20},
    }

    adapter._merge_plugin_snapshot(state, snapshot)

    assert state.towers == []
    assert [item["site_id"] for item in state.site_insights] == ["current_site"]
    assert state.site_insights[0]["built"] is False
    assert "tower_type" not in state.site_insights[0]
    assert state.combat_telemetry == {}


def test_plugin_preserves_a_remembered_own_tower_under_fog():
    adapter = object.__new__(TowerMindAdapter)
    adapter._plugin_mechanics = {}
    adapter._plugin_required = False
    adapter._tower_catalog = []
    state = GameState(
        wave=4,
        max_waves=5,
        base_hp=5,
        max_base_hp=20,
        gold=100,
        build_sites=[(-0.23, 0.22)],
        towers=[
            Tower(
                "unstable_raw_id",
                "archer",
                (1.35, 0.39),
                level=3,
            )
        ],
    )
    snapshot = {
        "ready": True,
        "plugin_version": "0.2.0",
        "build_sites": [
            {
                "site_id": "site_01",
                "known_legal": True,
                "position": [1.35, 0.39],
                "built": True,
                "tower_type": "archer",
                "tower_level": 3,
                "frozen": False,
                "under_fog": True,
                "operational": False,
            }
        ],
        "enemies": [],
        "telemetry": {},
    }

    adapter._merge_plugin_snapshot(state, snapshot)

    assert len(state.towers) == 1
    assert state.towers[0].id == "tower_site_01"
    assert state.towers[0].under_fog is True
    assert state.towers[0].operational is False
    public = state.public_dict()
    assert public["threat_summary"]["anti_air"]["archer_tower_count"] == 1
    assert (
        public["threat_summary"]["anti_air"]["operational_archer_tower_count"]
        == 0
    )


def test_public_state_never_exposes_unspawned_wave_roster():
    state = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=500,
        current_wave_enemy_types=["Outlaw", "Demon Bat", "Pirate Captain"],
        visible_enemies=[
            Enemy(id="enemy_1", kind="Outlaw", hp=400, progress=0.2)
        ],
    )

    assert state.public_dict()["current_wave_enemy_types"] == ["Outlaw"]


def test_public_state_summarizes_only_visible_air_threats():
    state = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=500,
        towers=[Tower("tower_1", "archer", (0, 0), level=2)],
        hero=HeroState(hp=1600, max_hp=1600),
        visible_enemies=[
            Enemy(
                id="bat_near",
                kind="Demon Bat",
                hp=500,
                progress=0.8,
                flying=True,
                movement_type="Flying",
                estimated_seconds_to_base=2.5,
            ),
            Enemy(
                id="bat_hidden",
                kind="Demon Bat",
                hp=550,
                progress=0.1,
                flying=True,
                movement_type="Flying",
                estimated_seconds_to_base=12,
            ),
        ],
    )

    normal = state.public_dict()
    fogged = state.public_dict(fog_of_war=True)

    assert normal["threat_summary"]["visible_flying_count"] == 2
    assert normal["threat_summary"]["visible_flying_total_hp"] == 1050
    assert normal["threat_summary"]["anti_air"]["archer_tower_count"] == 1
    assert normal["threat_summary"]["anti_air"]["archer_total_levels"] == 2
    assert fogged["threat_summary"]["visible_flying_count"] == 1
    assert fogged["threat_summary"]["visible_flying_total_hp"] == 500


def test_completed_plugin_telemetry_survives_unity_auto_reset():
    adapter = object.__new__(TowerMindAdapter)
    adapter._plugin_mechanics = {}
    adapter._plugin_required = False
    adapter._episode_done = True
    adapter._last_plugin_telemetry = {
        "latest_seq": 90,
        "enemy_damage": 9000,
    }
    state = GameState(
        wave=4,
        max_waves=5,
        base_hp=0,
        max_base_hp=20,
        gold=10,
    )
    snapshot = {
        "ready": True,
        "plugin_version": "0.1.0",
        "build_sites": [],
        "enemies": [],
        "telemetry": {
            "latest_seq": 1,
            "enemy_damage": 0,
            "last_completed": {
                "enemy_damage": 12345,
                "leaks": 20,
                "leaks_by_type": {"Demon Bat": 9, "Outlaw": 11},
                "enemy_kills": 50,
            },
        },
    }

    adapter._merge_plugin_snapshot(state, snapshot)

    assert state.combat_telemetry["enemy_damage"] == 12345
    assert state.combat_telemetry["leaks"] == 20
    assert state.combat_telemetry["leaks_by_type"]["Demon Bat"] == 9
    assert state.combat_telemetry["source"] == "last_completed"


def test_plugin_damage_is_preferred_over_unstable_enemy_index_estimate():
    before = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=100,
        combat_telemetry={"enemy_damage": 1000},
        observer_meta={"connected": True},
    )
    after = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=100,
        combat_telemetry={"enemy_damage": 1250},
        observer_meta={"connected": True},
    )

    assert TowerMindAdapter._result_damage(before, after, 9999, 8888) == 250


def test_multi_action_decision_restores_stable_tower_ids_between_steps():
    class FakeEnv:
        def __init__(self) -> None:
            self.actions = []

        def step(self, action):
            self.actions.append(action)
            return object(), 0.0, False, {}

    adapter = object.__new__(TowerMindAdapter)
    adapter.env = FakeEnv()
    adapter.state = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=500,
        towers=[Tower("tower_site_01", "archer", (1.35, 0.39))],
    )
    adapter._episode_done = False
    adapter._last_obs = None
    adapter._gold_spent = 0

    def fake_translate(self, _obs, max_waves):
        return GameState(
            wave=1,
            max_waves=max_waves,
            base_hp=20,
            max_base_hp=20,
            gold=500,
            towers=[Tower("tower_000", "archer", (1.35, 0.39))],
        )

    def restore_stable_ids(self):
        self.state.towers = [
            Tower("tower_site_01", "archer", (1.35, 0.39))
        ]

    adapter._translate = MethodType(fake_translate, adapter)
    adapter._refresh_plugin_state = MethodType(restore_stable_ids, adapter)

    adapter.apply_actions(
        [
            Action(type="noop"),
            Action(type="upgrade", tower_id="tower_site_01"),
        ]
    )

    assert adapter.env.actions[1] == [1.35, 0.39, 3]


def test_play_wave_entering_final_wave_without_terminal_is_not_a_win():
    class FakeEnv:
        def step(self, action):
            assert action == [0.0, 0.0, 6]
            return object(), 0.0, False, {"step": object()}

    adapter = object.__new__(TowerMindAdapter)
    adapter.env = FakeEnv()
    adapter.state = GameState(
        wave=4,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=100,
    )
    adapter._episode_done = False
    adapter._terminal_interrupted = None
    adapter._last_obs = None
    adapter._translate = MethodType(
        lambda self, _obs, max_waves: GameState(
            wave=5,
            max_waves=max_waves,
            base_hp=20,
            max_base_hp=20,
            gold=100,
            done=self._episode_done,
            won=False,
            terminal_interrupted=self._terminal_interrupted,
        ),
        adapter,
    )
    adapter._refresh_plugin_state = MethodType(lambda self: None, adapter)

    state, _ = adapter.play_wave()

    assert state.wave == 5
    assert state.done is False
    assert state.won is False
    assert state.terminal_interrupted is None


def test_advance_until_event_entering_final_wave_without_terminal_is_not_a_win():
    class FakeEnv:
        def step(self, _action):
            return object(), 0.0, False, {"step": object()}

    class NoMicro:
        def decide(self, _state):
            return None

    class WaveEvent:
        def detect(self, before, after):
            if before.wave != after.wave:
                return [
                    SimpleNamespace(
                        type="wave_changed",
                        detail={"from": before.wave, "to": after.wave},
                        priority=90,
                    )
                ]
            return []

    adapter = object.__new__(TowerMindAdapter)
    adapter.env = FakeEnv()
    adapter.state = GameState(
        wave=4,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=100,
    )
    adapter._episode_done = False
    adapter._terminal_interrupted = None
    adapter._last_obs = None
    adapter._micro = NoMicro()
    adapter._micro_actions = []
    adapter._event_detector = WaveEvent()
    adapter._translate = MethodType(
        lambda self, _obs, max_waves: GameState(
            wave=5,
            max_waves=max_waves,
            base_hp=20,
            max_base_hp=20,
            gold=100,
            done=self._episode_done,
            won=False,
            terminal_interrupted=self._terminal_interrupted,
        ),
        adapter,
    )
    adapter._refresh_plugin_state = MethodType(lambda self: None, adapter)

    state, _, _ = adapter.advance_until_event(max_steps=1)

    assert state.wave == 5
    assert state.done is False
    assert state.won is False


def test_towermind_reads_native_terminal_interrupted_flag():
    adapter = object.__new__(TowerMindAdapter)
    adapter._episode_done = False
    adapter._terminal_interrupted = None
    terminal_steps = SimpleNamespace(interrupted=[True])

    adapter._record_terminal_step(True, {"step": terminal_steps})

    assert adapter._episode_done is True
    assert adapter._terminal_interrupted is True
