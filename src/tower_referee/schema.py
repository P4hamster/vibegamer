from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping

ActionType = Literal[
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
]
RunOutcome = Literal["won", "lost", "invalid", "partial"]


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(slots=True)
class Tower:
    id: str
    kind: str
    position: tuple[float, float]
    level: int = 1
    spent: int = 0
    damage: float = 0.0
    frozen: bool = False
    rally_position: tuple[float, float] | None = None
    under_fog: bool = False
    operational: bool = True


@dataclass(slots=True)
class Enemy:
    id: str
    kind: str
    hp: float
    progress: float
    max_hp: float = 0.0
    lane: str = "main"
    position: tuple[float, float] | None = None
    flying: bool = False
    movement_type: str = ""
    distance_to_base: float = 0.0
    estimated_seconds_to_base: float = 0.0
    description: str = ""


@dataclass(slots=True)
class HeroState:
    position: tuple[float, float] | None = None
    hp: float = 0.0
    max_hp: float = 0.0
    dead: bool = False
    revive_countdown: float = 0.0


@dataclass(slots=True)
class KnightState:
    id: str
    position: tuple[float, float]
    hp: float


@dataclass(slots=True)
class DroppedGold:
    position: tuple[float, float]
    remaining_lifetime: float


@dataclass(slots=True)
class LastActionState:
    action_index: int = -1
    position: tuple[float, float] = (0.0, 0.0)
    success: bool = True
    error_code: int | str | None = None


@dataclass(slots=True)
class Action:
    type: ActionType
    tower: str | None = None
    position: tuple[float, float] | None = None
    tower_id: str | None = None
    skill: str | None = None
    id: str | None = None
    after: list[str] = field(default_factory=list)
    wait: str | None = None


@dataclass(slots=True)
class StandingOrders:
    """Persistent tactics executed locally between expensive LLM turns."""

    hero_anchor: tuple[float, float] | None = None
    hero_retreat_position: tuple[float, float] | None = None
    hero_retreat_below_hp: float = 350
    collect_gold: bool = True
    collect_gold_radius_from_anchor: float = 1.25
    knight_block_point: tuple[float, float] | None = None
    reinforcement_point: tuple[float, float] | None = None
    use_hero_skill_when_enemy_count: int = 5
    hero_skill_min_hp: float = 700


@dataclass(slots=True)
class Decision:
    analysis_summary: str
    actions: list[Action]
    reserve_gold: int = 0
    raw_response: str | None = None
    standing_orders: StandingOrders | None = None
    cancel_pending_plans: bool = False
    parse_status: str = "valid"
    parse_error_type: str = ""
    repair_attempted: bool = False
    request_trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class GameState:
    wave: int
    max_waves: int
    base_hp: int
    max_base_hp: int
    gold: int
    towers: list[Tower] = field(default_factory=list)
    visible_enemies: list[Enemy] = field(default_factory=list)
    available_actions: list[str] = field(default_factory=list)
    build_sites: list[tuple[float, float]] = field(default_factory=list)
    previous_wave_summary: dict[str, Any] = field(default_factory=dict)
    enemy_paths: list[list[tuple[float, float]]] = field(default_factory=list)
    current_wave_enemy_types: list[str] = field(default_factory=list)
    hero: HeroState | None = None
    knights: list[KnightState] = field(default_factory=list)
    dropped_gold: DroppedGold | None = None
    reinforcement_countdown: float = 0.0
    active_fire_zones: list[tuple[float, float]] = field(default_factory=list)
    last_action: LastActionState | None = None
    game_step: int = 0
    game_time: float = 0.0
    game_rules: dict[str, Any] = field(default_factory=dict)
    site_insights: list[dict[str, Any]] = field(default_factory=list)
    threat_summary: dict[str, Any] = field(default_factory=dict)
    combat_telemetry: dict[str, Any] = field(default_factory=dict)
    observer_meta: dict[str, Any] = field(default_factory=dict)
    done: bool = False
    won: bool = False
    terminal_interrupted: bool | None = None

    def public_dict(self, fog_of_war: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data.pop("done", None)
        data.pop("won", None)
        data.pop("terminal_interrupted", None)
        # TowerMind's internal field contains every not-yet-spawned enemy in
        # the active wave. Replacing it with actually visible types preserves
        # the published rule that future composition and spawn order are hidden.
        data["current_wave_enemy_types"] = sorted(
            {enemy["kind"] for enemy in data["visible_enemies"]}
        )
        if fog_of_war:
            data["visible_enemies"] = [
                enemy for enemy in data["visible_enemies"] if enemy["progress"] >= 0.18
            ]
            data["current_wave_enemy_types"] = sorted(
                {enemy["kind"] for enemy in data["visible_enemies"]}
            )
            data["previous_wave_summary"].pop("future_enemy_hint", None)
        # Always derive this from the exact enemy list sent to the model. This
        # keeps the summary useful without leaking enemies hidden by fog of war.
        data["threat_summary"] = self._build_threat_summary(data)
        return data

    @staticmethod
    def _build_threat_summary(data: dict[str, Any]) -> dict[str, Any]:
        enemies = list(data.get("visible_enemies") or [])
        flying = [
            enemy
            for enemy in enemies
            if bool(enemy.get("flying"))
            or str(enemy.get("movement_type", "")).lower() in {"air", "flying"}
        ]
        type_counts: dict[str, int] = {}
        for enemy in flying:
            kind = str(enemy.get("kind", "unknown"))
            type_counts[kind] = type_counts.get(kind, 0) + 1
        archer_towers = [
            tower
            for tower in (data.get("towers") or [])
            if str(tower.get("kind", "")).lower() == "archer"
        ]
        operational_archers = [
            tower
            for tower in archer_towers
            if bool(tower.get("operational", True))
            and not bool(tower.get("under_fog", False))
            and not bool(tower.get("frozen", False))
        ]
        hero = data.get("hero") or {}
        eta_values = [
            float(enemy.get("estimated_seconds_to_base", 0))
            for enemy in flying
            if float(enemy.get("estimated_seconds_to_base", 0)) > 0
        ]
        return {
            "visible_enemy_count": len(enemies),
            "visible_flying_count": len(flying),
            "visible_flying_types": type_counts,
            "visible_flying_total_hp": round(
                sum(max(0.0, float(enemy.get("hp", 0))) for enemy in flying), 3
            ),
            "closest_flying_path_progress": round(
                max(
                    (float(enemy.get("progress", 0)) for enemy in flying),
                    default=0.0,
                ),
                3,
            ),
            "closest_flying_seconds_to_base": (
                round(min(eta_values), 3) if eta_values else None
            ),
            "anti_air": {
                "archer_tower_count": len(archer_towers),
                "operational_archer_tower_count": len(operational_archers),
                "fogged_archer_tower_count": sum(
                    bool(tower.get("under_fog", False))
                    for tower in archer_towers
                ),
                "archer_total_levels": sum(
                    max(1, int(tower.get("level", 1))) for tower in archer_towers
                ),
                "operational_archer_total_levels": sum(
                    max(1, int(tower.get("level", 1)))
                    for tower in operational_archers
                ),
                "hero_alive": bool(hero) and not bool(hero.get("dead", False)),
                "hero_air_attack_condition": (
                    "Hero auto-attacks air only while stationary, not pathing, "
                    "and not occupied by a ground target."
                ),
            },
        }


@dataclass(frozen=True, slots=True)
class TerminalSnapshot:
    """Immutable evidence captured before any transition/reset can mutate state."""

    map_id: str
    final_hp: int
    max_base_hp: int
    native_current_wave: int
    max_waves: int
    terminal: bool
    interrupted: bool | None
    game_step: int
    game_time: float
    gold: int
    telemetry: Mapping[str, Any]
    outcome: RunOutcome

    @classmethod
    def capture(
        cls,
        map_id: str,
        state: GameState,
        outcome: RunOutcome,
    ) -> "TerminalSnapshot":
        # A JSON round-trip first detaches the evidence from plugin/state-owned
        # dictionaries; MappingProxyType and tuples then make it deeply immutable.
        telemetry = json.loads(
            json.dumps(state.combat_telemetry or {}, ensure_ascii=False)
        )
        return cls(
            map_id=map_id,
            final_hp=state.base_hp,
            max_base_hp=state.max_base_hp,
            native_current_wave=state.wave,
            max_waves=state.max_waves,
            terminal=state.done,
            interrupted=state.terminal_interrupted,
            game_step=state.game_step,
            game_time=state.game_time,
            gold=state.gold,
            telemetry=_freeze_json(telemetry),
            outcome=outcome,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "map_id": self.map_id,
            "final_hp": self.final_hp,
            "max_base_hp": self.max_base_hp,
            "native_current_wave": self.native_current_wave,
            "max_waves": self.max_waves,
            "terminal": self.terminal,
            "interrupted": self.interrupted,
            "game_step": self.game_step,
            "game_time": self.game_time,
            "gold": self.gold,
            "telemetry": _thaw_json(self.telemetry),
            "outcome": self.outcome,
        }


@dataclass(slots=True)
class GameEvent:
    type: str
    detail: dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass(slots=True)
class ActionRejection:
    action: dict[str, Any]
    reason: str


@dataclass(slots=True)
class WaveResult:
    wave: int
    base_hp_before: int
    base_hp_after: int
    gold_before: int
    gold_after: int
    enemies_defeated: int
    enemies_leaked: int
    damage_dealt: float
    tower_damage: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RunSummary:
    experiment_id: str
    model_name: str
    model_id: str
    round_id: int
    run_index: int
    map_id: str
    seed: int
    waves_survived: int
    max_waves: int
    base_hp: int
    max_base_hp: int
    gold_remaining: int
    gold_spent: int
    damage_dealt: float
    invalid_actions: int
    total_actions: int
    won: bool
    score: float = 0.0
    improvement: float = 0.0
    personality: str = ""
    task_id: str = ""
    trial_id: str = ""
    harness_version: str = ""
    observation_mode: str = ""
    scaffold_id: str = ""
    decision_count: int = 0
    accepted_actions: int = 0
    enemies_defeated: int = 0
    enemies_leaked: int = 0
    local_micro_actions: int = 0
    decision_budget_exhausted: bool = False
    model_request_failed: bool = False
    model_parse_failures: int = 0
    model_repair_count: int = 0
    watchdog_timed_out: bool = False
    outcome: RunOutcome = "invalid"
    partial: bool = False
    outcome_valid: bool = False
    terminal_confirmed: bool = False
    terminal_interrupted: bool | None = None
    telemetry_valid: bool = False
    score_eligible: bool = False
    invalid_reason: str = ""
    provisional_metrics: list[str] = field(default_factory=list)
    terminal_snapshot: dict[str, Any] = field(default_factory=dict)
    completion_ratio: float = 0.0
    base_hp_ratio: float = 0.0
    action_validity_rate: float = 0.0
    damage_per_gold: float = 0.0
    unspent_gold_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
