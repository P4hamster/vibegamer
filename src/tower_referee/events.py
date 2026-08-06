from __future__ import annotations

from tower_referee.schema import GameEvent, GameState


class EventDetector:
    """Deterministic local monitor; detecting events never calls an LLM."""

    STRATEGIC_GROUND_TYPES = {
        "Orc Sorcerer",
        "Bone Chanter",
        "Duckman",
        "T-Rex Rider",
        "Pirate Commander",
        "Hill King",
    }

    def __init__(self) -> None:
        self._seen_ground_enemy_types: set[str] = set()
        self._ground_alerted_waves: set[int] = set()
        self._seen_flying_types: set[str] = set()
        self._seen_frozen_tower_ids: set[str] = set()
        self._obscured_tower_positions: set[tuple[float, float]] = set()

    def reset(self) -> None:
        self._seen_ground_enemy_types.clear()
        self._ground_alerted_waves.clear()
        self._seen_flying_types.clear()
        self._seen_frozen_tower_ids.clear()
        self._obscured_tower_positions.clear()

    def detect(self, before: GameState, after: GameState) -> list[GameEvent]:
        events: list[GameEvent] = []
        if after.done and not before.done:
            events.append(GameEvent("game_over", {"won": after.won}, 100))
        if after.wave != before.wave:
            events.append(
                GameEvent(
                    "wave_changed",
                    {"from": before.wave, "to": after.wave},
                    90,
                )
            )
        hp_thresholds = (0.75, 0.5, 0.25)
        crossed_hp_threshold = any(
            before.base_hp / max(before.max_base_hp, 1) > threshold
            >= after.base_hp / max(after.max_base_hp, 1)
            for threshold in hp_thresholds
        )
        if after.base_hp < before.base_hp and crossed_hp_threshold:
            events.append(
                GameEvent(
                    "base_damaged",
                    {"lost": before.base_hp - after.base_hp, "hp": after.base_hp},
                    100,
                )
            )
        visible_ground_types = {
            enemy.kind
            for enemy in after.visible_enemies
            if not enemy.flying
            and enemy.movement_type.lower() not in {"air", "flying"}
        }
        new_ground_types = sorted(
            visible_ground_types - self._seen_ground_enemy_types
        )
        if new_ground_types:
            self._seen_ground_enemy_types.update(new_ground_types)
            strategic = (
                after.wave not in self._ground_alerted_waves
                or bool(set(new_ground_types) & self.STRATEGIC_GROUND_TYPES)
            )
            if strategic:
                self._ground_alerted_waves.add(after.wave)
            events.append(
                GameEvent(
                    "new_ground_enemy_types",
                    {"types": new_ground_types},
                    80 if strategic else 60,
                )
            )
        visible_flying_types = {
            enemy.kind
            for enemy in after.visible_enemies
            if enemy.flying or enemy.movement_type.lower() in {"air", "flying"}
        }
        new_flying_types = sorted(
            visible_flying_types - self._seen_flying_types
        )
        if new_flying_types:
            self._seen_flying_types.update(new_flying_types)
            events.append(
                GameEvent(
                    "new_air_threat",
                    {"types": new_flying_types},
                    85,
                )
            )
        newly_frozen = sorted(
            tower.id
            for tower in after.towers
            if tower.frozen
            and tower.id not in self._seen_frozen_tower_ids
        )
        if newly_frozen:
            self._seen_frozen_tower_ids.update(newly_frozen)
            events.append(GameEvent("towers_frozen", {"tower_ids": newly_frozen}, 80))
        visible_after_positions = {
            tuple(round(value, 2) for value in tower.position)
            for tower in after.towers
        }
        lost_tower_visibility = [
            {
                "tower_id": tower.id,
                "tower_type": tower.kind,
                "position": tower.position,
            }
            for tower in before.towers
            if (
                tuple(round(value, 2) for value in tower.position)
                not in visible_after_positions
                and tuple(round(value, 2) for value in tower.position)
                not in self._obscured_tower_positions
            )
        ]
        if lost_tower_visibility and not after.done:
            self._obscured_tower_positions.update(
                tuple(round(value, 2) for value in item["position"])
                for item in lost_tower_visibility
            )
            events.append(
                GameEvent(
                    "tower_visibility_lost",
                    {"towers": lost_tower_visibility},
                    85,
                )
            )
        if before.dropped_gold is None and after.dropped_gold is not None:
            events.append(
                GameEvent(
                    "gold_dropped",
                    {
                        "position": after.dropped_gold.position,
                        "remaining_lifetime": after.dropped_gold.remaining_lifetime,
                    },
                    55,
                )
            )
        if (
            before.hero
            and after.hero
            and not before.hero.dead
            and (
                after.hero.dead
                or (
                    after.hero.max_hp > 0
                    and after.hero.hp / after.hero.max_hp <= 0.25
                    and before.hero.hp / max(before.hero.max_hp, 1) > 0.25
                )
            )
        ):
            events.append(
                GameEvent(
                    "hero_critical",
                    {"hp": after.hero.hp, "dead": after.hero.dead},
                    85,
                )
            )
        if (
            before.reinforcement_countdown > 0
            and after.reinforcement_countdown <= 0
        ):
            events.append(GameEvent("reinforcements_ready", {}, 45))
        return sorted(events, key=lambda event: event.priority, reverse=True)


class StrategicEventBatcher:
    """Debounce cloud visibility churn without hiding it from the audit log."""

    DEFERRED_TYPES = {"tower_visibility_lost", "tower_visibility_restored"}

    def __init__(self, window_seconds: float = 3.0) -> None:
        self.window_seconds = max(0.0, float(window_seconds))
        self._pending: list[GameEvent] = []
        self._started_at: float | None = None

    @property
    def pending(self) -> bool:
        return bool(self._pending)

    def reset(self) -> None:
        self._pending.clear()
        self._started_at = None

    def push(
        self,
        events: list[GameEvent],
        game_time: float,
    ) -> tuple[list[GameEvent], list[dict]]:
        deferred = [
            event for event in events if event.type in self.DEFERRED_TYPES
        ]
        immediate = [
            event
            for event in events
            if event.priority >= 75 and event.type not in self.DEFERRED_TYPES
        ]
        audit: list[dict] = []
        if deferred:
            if self._started_at is None:
                self._started_at = game_time
            self._pending.extend(deferred)
            audit.append(
                {
                    "event_type": "monitor_trigger_deferred",
                    "events": [event.type for event in deferred],
                    "game_time": game_time,
                    "window_seconds": self.window_seconds,
                }
            )
        if immediate:
            return self._flush(game_time, "immediate_event", immediate, audit)
        if (
            self._pending
            and self._started_at is not None
            and game_time - self._started_at >= self.window_seconds
        ):
            return self._flush(game_time, "window_elapsed", [], audit)
        return [], audit

    def flush(
        self,
        game_time: float,
        reason: str,
    ) -> tuple[list[GameEvent], list[dict]]:
        if not self._pending:
            return [], []
        return self._flush(game_time, reason, [], [])

    def _flush(
        self,
        game_time: float,
        reason: str,
        immediate: list[GameEvent],
        audit: list[dict],
    ) -> tuple[list[GameEvent], list[dict]]:
        started_at = self._started_at if self._started_at is not None else game_time
        pending = list(self._pending)
        self.reset()
        if not pending:
            return immediate, audit
        audit.append(
            {
                "event_type": "monitor_trigger_batch_flushed",
                "events": [event.type for event in pending],
                "deferred_seconds": round(max(0.0, game_time - started_at), 3),
                "flush_reason": reason,
                "merged_with": [event.type for event in immediate],
            }
        )
        return pending + immediate, audit
