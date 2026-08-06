from __future__ import annotations

import math
import random
from dataclasses import replace

from tower_referee.game.base import GameAdapter
from tower_referee.schema import Action, Enemy, GameState, HeroState, Tower, WaveResult

TOWER_COSTS = {"archer": 120, "magician": 110, "knight": 100}
TOWER_POWER = {"archer": 50.0, "magician": 82.0, "knight": 60.0}
MAP_SITES = {
    "river_gate": [(0, 1), (1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2), (4, 2)],
    "fog_crossroads": [(0, 0), (2, 0), (4, 0), (1, 2), (2, 2), (3, 2), (2, 4), (4, 4)],
}


class SimulatedTowerDefense(GameAdapter):
    """Deterministic test double for developing the referee without Unity."""

    def __init__(self) -> None:
        self.state: GameState | None = None
        self.rng = random.Random()
        self.map_id = ""
        self.initial_gold = 650
        self.gold_spent = 0
        self._paused = False
        self._tower_counter = 0

    def reset(self, map_id: str, seed: int, max_waves: int) -> GameState:
        if map_id not in MAP_SITES:
            raise ValueError(f"Unknown simulated map: {map_id}")
        self.rng.seed(f"{seed}:{map_id}")
        self.map_id = map_id
        self.gold_spent = 0
        self._tower_counter = 0
        self.state = GameState(
            wave=0,
            max_waves=max_waves,
            base_hp=100,
            max_base_hp=100,
            gold=self.initial_gold,
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
            build_sites=list(MAP_SITES[map_id]),
            hero=HeroState(position=(0, 0), hp=100, max_hp=100),
            game_rules={
                "tower_costs": TOWER_COSTS,
                "sell_refund_ratio": 0.6,
                "backend": "simulation_for_engineering_only",
            },
        )
        return self.state

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def apply_actions(self, actions: list[Action]) -> GameState:
        state = self._require_state()
        for action in actions:
            if action.type == "noop":
                continue
            if action.type == "build":
                cost = TOWER_COSTS[action.tower or ""]
                self._tower_counter += 1
                tower = Tower(
                    id=f"tower_{self._tower_counter:03}",
                    kind=action.tower or "archer",
                    position=action.position or (0, 0),
                    spent=cost,
                )
                state.towers.append(tower)
                state.gold -= cost
                self.gold_spent += cost
            elif action.type == "upgrade":
                tower = next(t for t in state.towers if t.id == action.tower_id)
                cost = self.upgrade_cost(tower)
                tower.level += 1
                tower.spent += cost
                state.gold -= cost
                self.gold_spent += cost
            elif action.type == "sell":
                tower = next(t for t in state.towers if t.id == action.tower_id)
                state.gold += int(tower.spent * 0.6)
                state.towers.remove(tower)
            elif action.type == "hero_skill":
                state.previous_wave_summary["skill_armed"] = "hero_skill"
            elif action.type == "upgrade_hero":
                state.gold -= 500
                state.hero.max_hp += 50
                state.hero.hp += 50
            elif action.type == "move_hero" and state.hero:
                state.hero.position = action.position
        return state

    @staticmethod
    def upgrade_cost(tower: Tower) -> int:
        return TOWER_COSTS[tower.kind]

    def play_wave(self) -> tuple[GameState, WaveResult]:
        state = self._require_state()
        before_hp, before_gold = state.base_hp, state.gold
        next_wave = state.wave + 1
        enemy_count = 6 + next_wave * 2
        health_each = 34 + next_wave * 11
        map_factor = 1.12 if self.map_id == "fog_crossroads" else 1.0
        total_health = enemy_count * health_each * map_factor
        tower_damage: dict[str, float] = {}
        damage = 0.0
        for tower in state.towers:
            positional = 1.15 if tower.position in {(2, 1), (2, 2), (2, 4)} else 1.0
            dealt = TOWER_POWER[tower.kind] * (1 + 0.62 * (tower.level - 1)) * positional
            dealt *= 1 + self.rng.uniform(-0.04, 0.04)
            tower.damage += dealt
            tower_damage[tower.id] = round(dealt, 2)
            damage += dealt
        if state.previous_wave_summary.pop("skill_armed", None):
            damage += 190
        defeated = min(enemy_count, math.floor(enemy_count * damage / max(total_health, 1)))
        leaked = enemy_count - defeated
        hp_loss = leaked * (2 + next_wave // 4)
        state.base_hp = max(0, state.base_hp - hp_loss)
        reward = defeated * (10 + next_wave)
        state.gold += reward
        state.wave = next_wave
        state.game_step += 1
        state.game_time += 1.0
        state.visible_enemies = [
            Enemy(f"enemy_{next_wave}_{i}", "grunt", health_each, i / max(enemy_count, 1))
            for i in range(max(0, leaked))
        ]
        state.previous_wave_summary = {
            "enemies_defeated": defeated,
            "enemies_leaked": leaked,
            "base_hp_lost": before_hp - state.base_hp,
            "gold_earned": reward,
            "future_enemy_hint": f"wave {next_wave + 1} is stronger",
        }
        state.done = state.base_hp <= 0 or state.wave >= state.max_waves
        state.won = state.base_hp > 0 and state.wave >= state.max_waves
        state.terminal_interrupted = False if state.done else None
        result = WaveResult(
            wave=next_wave,
            base_hp_before=before_hp,
            base_hp_after=state.base_hp,
            gold_before=before_gold,
            gold_after=state.gold,
            enemies_defeated=defeated,
            enemies_leaked=leaked,
            damage_dealt=round(damage, 2),
            tower_damage=tower_damage,
        )
        return replace(state), result

    def close(self) -> None:
        self.state = None

    def _require_state(self) -> GameState:
        if self.state is None:
            raise RuntimeError("Game must be reset before use")
        return self.state
