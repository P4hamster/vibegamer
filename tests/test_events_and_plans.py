from tower_referee.events import EventDetector, StrategicEventBatcher
from tower_referee.plan_queue import ActionPlanQueue
from tower_referee.game.towermind import TowerMindAdapter
from tower_referee.schema import (
    Action,
    DroppedGold,
    Enemy,
    GameEvent,
    GameState,
    HeroState,
    Tower,
)


def state(**changes):
    base = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=100,
        hero=HeroState(hp=1000, max_hp=1600),
    )
    for key, value in changes.items():
        setattr(base, key, value)
    return base


def test_event_detector_finds_important_changes():
    before = state()
    after = state(
        base_hp=14,
        dropped_gold=DroppedGold((1, 2), 10),
        towers=[Tower("t1", "archer", (0, 0), frozen=True)],
    )
    types = {event.type for event in EventDetector().detect(before, after)}
    assert {"base_damaged", "gold_dropped", "towers_frozen"} <= types


def test_raw_tower_position_uses_same_stable_id_as_plugin_site():
    tower_id = TowerMindAdapter._stable_tower_id(
        (1.36, 0.38),
        [(-0.23, 0.22), (1.35, 0.39), (2.48, -0.9)],
        fallback_index=7,
    )

    assert tower_id == "tower_site_01"


def test_same_tower_freeze_only_triggers_once_per_run():
    detector = EventDetector()
    clear = state(towers=[Tower("t1", "archer", (0, 0), frozen=False)])
    frozen = state(towers=[Tower("t1", "archer", (0, 0), frozen=True)])

    first = detector.detect(clear, frozen)
    detector.detect(frozen, clear)
    repeated = detector.detect(clear, frozen)

    assert any(event.type == "towers_frozen" for event in first)
    assert not any(event.type == "towers_frozen" for event in repeated)


def test_first_visible_flying_enemy_is_an_immediate_strategic_event():
    before = state()
    after = state(
        visible_enemies=[
            Enemy(
                "bat",
                "Demon Bat",
                550,
                0.1,
                flying=True,
                movement_type="Flying",
            )
        ]
    )

    events = EventDetector().detect(before, after)
    air_event = next(event for event in events if event.type == "new_air_threat")

    assert air_event.priority >= 75
    assert air_event.detail["types"] == ["Demon Bat"]


def test_same_flying_type_only_triggers_once_per_run():
    detector = EventDetector()
    empty = state()
    bats = state(
        visible_enemies=[
            Enemy("bat", "Demon Bat", 550, 0.1, flying=True)
        ]
    )

    first = detector.detect(empty, bats)
    detector.detect(bats, empty)
    repeated = detector.detect(empty, bats)

    assert any(event.type == "new_air_threat" for event in first)
    assert not any(event.type == "new_air_threat" for event in repeated)


def test_each_ground_enemy_type_triggers_once_per_run():
    detector = EventDetector()
    empty = state()
    duck = state(
        visible_enemies=[
            Enemy("duck", "Duckman", 400, 0.1, movement_type="Ground")
        ]
    )

    first = detector.detect(empty, duck)
    detector.detect(duck, empty)
    repeated = detector.detect(empty, duck)

    ground = next(
        event for event in first if event.type == "new_ground_enemy_types"
    )
    assert ground.priority >= 75
    assert ground.detail["types"] == ["Duckman"]
    assert not any(
        event.type == "new_ground_enemy_types" for event in repeated
    )


def test_routine_second_ground_type_in_same_wave_is_logged_but_not_strategic():
    detector = EventDetector()
    empty = state(wave=2)
    first = state(
        wave=2,
        visible_enemies=[Enemy("orc", "Orc Warrior", 500, 0.1)],
    )
    routine_second = state(
        wave=2,
        visible_enemies=[
            Enemy("orc", "Orc Warrior", 500, 0.2),
            Enemy("zombie", "Zombie", 500, 0.1),
        ],
    )

    detector.detect(empty, first)
    events = detector.detect(first, routine_second)
    ground = next(
        event for event in events if event.type == "new_ground_enemy_types"
    )

    assert ground.detail["types"] == ["Zombie"]
    assert ground.priority < 75


def test_losing_sight_of_an_owned_tower_is_a_strategic_event():
    detector = EventDetector()
    before = state(
        towers=[Tower("tower_site_01", "archer", (1.35, 0.39), level=3)]
    )
    after = state(towers=[])

    events = detector.detect(before, after)
    lost = next(
        event for event in events if event.type == "tower_visibility_lost"
    )
    repeated = detector.detect(before, after)

    assert lost.priority >= 75
    assert lost.detail["towers"][0]["tower_type"] == "archer"
    assert not any(
        event.type == "tower_visibility_lost" for event in repeated
    )


def test_same_tower_cloud_cover_only_triggers_once_per_run():
    detector = EventDetector()
    visible = state(
        towers=[Tower("tower_site_01", "archer", (1.35, 0.39), level=3)]
    )
    obscured = state(towers=[])

    first = detector.detect(visible, obscured)
    detector.detect(obscured, visible)
    repeated = detector.detect(visible, obscured)

    assert any(event.type == "tower_visibility_lost" for event in first)
    assert not any(
        event.type == "tower_visibility_lost" for event in repeated
    )


def test_cloud_visibility_event_is_deferred_until_batch_window_elapses():
    batcher = StrategicEventBatcher(window_seconds=3.0)
    cloud = GameEvent("tower_visibility_lost", {"tower_id": "t1"}, 85)

    ready, audit = batcher.push([cloud], game_time=10.0)
    still_waiting, _ = batcher.push([], game_time=12.9)
    flushed, flush_audit = batcher.push([], game_time=13.0)

    assert ready == []
    assert still_waiting == []
    assert [item.type for item in flushed] == ["tower_visibility_lost"]
    assert audit[0]["event_type"] == "monitor_trigger_deferred"
    assert flush_audit[-1]["flush_reason"] == "window_elapsed"
    assert flush_audit[-1]["deferred_seconds"] == 3.0


def test_high_priority_event_flushes_pending_cloud_event_immediately():
    batcher = StrategicEventBatcher(window_seconds=3.0)
    cloud = GameEvent("tower_visibility_lost", {}, 85)
    air = GameEvent("new_air_threat", {"types": ["Demon Bat"]}, 85)

    batcher.push([cloud], game_time=1.0)
    ready, audit = batcher.push([air], game_time=1.5)

    assert [item.type for item in ready] == [
        "tower_visibility_lost",
        "new_air_threat",
    ]
    assert audit[-1]["flush_reason"] == "immediate_event"
    assert audit[-1]["merged_with"] == ["new_air_threat"]


def test_immediate_event_without_pending_batch_has_no_empty_flush_audit():
    batcher = StrategicEventBatcher(window_seconds=3.0)

    ready, audit = batcher.push(
        [GameEvent("wave_changed", {"to": 2}, 90)],
        game_time=4.0,
    )

    assert [item.type for item in ready] == ["wave_changed"]
    assert audit == []


def test_plan_queue_releases_actions_when_conditions_are_met():
    queue = ActionPlanQueue()
    queued, rejected = queue.enqueue(
        [
            Action(
                id="build-later",
                type="build",
                tower="archer",
                position=(0, 0),
                wait="gold_at_least:120",
            )
        ]
    )
    assert queued and not rejected
    assert queue.pop_ready(state(gold=119), set()) == []
    assert queue.pop_ready(state(gold=120), set())[0].id == "build-later"


def test_plan_queue_rejects_unknown_wait():
    queue = ActionPlanQueue()
    _, rejected = queue.enqueue(
        [Action(type="noop", wait="wait_forever")]
    )
    assert len(rejected) == 1


def test_plan_queue_replaces_same_id_without_cancelling_other_plans():
    queue = ActionPlanQueue()
    queue.enqueue(
        [
            Action(
                id="exit-tower",
                type="build",
                tower="archer",
                position=(2, 2),
                wait="wave_changed",
            ),
            Action(
                id="reserve-upgrade",
                type="upgrade",
                tower_id="tower_001",
                wait="gold_at_least:300",
            ),
        ]
    )
    queue.enqueue(
        [
            Action(
                id="exit-tower",
                type="build",
                tower="magician",
                position=(2, 2),
                wait="wave_changed",
            )
        ]
    )

    assert len(queue.pending) == 2
    assert next(item for item in queue.pending if item.id == "exit-tower").tower == (
        "magician"
    )


def test_observed_enemy_damage_counts_health_loss_and_kills():
    before = state(
        visible_enemies=[
            Enemy("hurt", "orc", 100, 0.2),
            Enemy("killed", "orc", 50, 0.3),
        ]
    )
    after = state(visible_enemies=[Enemy("hurt", "orc", 70, 0.3)])
    assert TowerMindAdapter._observed_enemy_damage(before, after) == 80
