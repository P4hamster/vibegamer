from __future__ import annotations

from dataclasses import dataclass, field

from tower_referee.schema import Action, GameState


SUPPORTED_WAITS = (
    "wave_changed",
    "gold_at_least:",
    "base_hp_below:",
    "hero_hp_below:",
    "enemy_progress_at_least:",
    "reinforcements_ready",
    "tower_frozen",
)


@dataclass(slots=True)
class ActionPlanQueue:
    pending: list[Action] = field(default_factory=list)
    completed_ids: set[str] = field(default_factory=set)

    def enqueue(self, actions: list[Action]) -> tuple[list[Action], list[Action]]:
        accepted: list[Action] = []
        rejected: list[Action] = []
        for action in actions:
            if action.wait and not any(
                action.wait == prefix or action.wait.startswith(prefix)
                for prefix in SUPPORTED_WAITS
            ):
                rejected.append(action)
            else:
                if action.id:
                    self.pending = [
                        pending
                        for pending in self.pending
                        if pending.id != action.id
                    ]
                self.pending.append(action)
                accepted.append(action)
        return accepted, rejected

    def pop_ready(
        self, state: GameState, event_types: set[str]
    ) -> list[Action]:
        ready: list[Action] = []
        remaining: list[Action] = []
        for action in self.pending:
            if any(dep not in self.completed_ids for dep in action.after):
                remaining.append(action)
                continue
            if not self._wait_satisfied(action.wait, state, event_types):
                remaining.append(action)
                continue
            ready.append(action)
        self.pending = remaining
        return ready

    def mark_completed(self, actions: list[Action]) -> None:
        self.completed_ids.update(action.id for action in actions if action.id)

    @staticmethod
    def _wait_satisfied(
        wait: str | None, state: GameState, event_types: set[str]
    ) -> bool:
        if not wait:
            return True
        if wait == "wave_changed":
            return "wave_changed" in event_types
        if wait == "reinforcements_ready":
            return state.reinforcement_countdown <= 0
        if wait == "tower_frozen":
            return any(tower.frozen for tower in state.towers)
        key, _, raw_value = wait.partition(":")
        try:
            value = float(raw_value)
        except ValueError:
            return False
        if key == "gold_at_least":
            return state.gold >= value
        if key == "base_hp_below":
            return state.base_hp <= value
        if key == "hero_hp_below":
            return bool(state.hero and state.hero.hp <= value)
        if key == "enemy_progress_at_least":
            return any(enemy.progress >= value for enemy in state.visible_enemies)
        return False
