from tower_referee.micro import LocalTacticsController
from tower_referee.schema import (
    DroppedGold,
    Enemy,
    GameState,
    HeroState,
    KnightState,
    StandingOrders,
    Tower,
)


def state(**changes):
    result = GameState(
        wave=1,
        max_waves=5,
        base_hp=20,
        max_base_hp=20,
        gold=100,
        hero=HeroState(position=(0, 0), hp=1600, max_hp=1600),
        game_step=20,
    )
    for key, value in changes.items():
        setattr(result, key, value)
    return result


def test_micro_collects_gold_before_returning_to_anchor():
    controller = LocalTacticsController()
    controller.set_orders(
        StandingOrders(
            hero_anchor=(2, 2),
            collect_gold=True,
            collect_gold_radius_from_anchor=2.0,
        )
    )
    action = controller.decide(
        state(dropped_gold=DroppedGold(position=(1, 1), remaining_lifetime=10))
    )
    assert action.type == "move_hero"
    assert action.position == (1, 1)


def test_micro_commits_to_current_coin_instead_of_chasing_every_drop():
    controller = LocalTacticsController(poll_steps=1)
    controller.set_orders(
        StandingOrders(hero_anchor=(0, 0), collect_gold=True)
    )
    first = controller.decide(
        state(
            game_step=1,
            hero=HeroState(position=(0, 0), hp=1000, max_hp=1600),
            dropped_gold=DroppedGold((1, 0), 14),
        )
    )
    assert first.position == (1, 0)

    changed = controller.decide(
        state(
            game_step=30,
            hero=HeroState(position=(0.2, 0), hp=1000, max_hp=1600),
            dropped_gold=DroppedGold((-1, 0), 14),
        )
    )
    assert changed is None or changed.position != (-1, 0)


def test_micro_ignores_gold_outside_hero_anchor_leash():
    controller = LocalTacticsController()
    controller.set_orders(
        StandingOrders(
            hero_anchor=(0, 0),
            collect_gold=True,
            collect_gold_radius_from_anchor=1.25,
        )
    )

    action = controller.decide(
        state(dropped_gold=DroppedGold(position=(2, 2), remaining_lifetime=10))
    )

    assert action is None


def test_micro_uses_skill_for_ground_cluster():
    controller = LocalTacticsController()
    controller.set_orders(
        StandingOrders(
            hero_anchor=(0, 0),
            collect_gold=False,
            use_hero_skill_when_enemy_count=2,
            hero_skill_min_hp=700,
        )
    )
    action = controller.decide(
        state(
            visible_enemies=[
                Enemy("e1", "orc", 100, 0.5, position=(0.5, 0)),
                Enemy("e2", "orc", 100, 0.5, position=(0.8, 0)),
            ]
        )
    )
    assert action.type == "hero_skill"


def test_micro_does_not_burn_friendly_knights():
    controller = LocalTacticsController()
    controller.set_orders(
        StandingOrders(
            hero_anchor=(0, 0),
            collect_gold=False,
            use_hero_skill_when_enemy_count=2,
        )
    )
    action = controller.decide(
        state(
            visible_enemies=[
                Enemy("e1", "orc", 100, 0.5, position=(0.5, 0)),
                Enemy("e2", "orc", 100, 0.5, position=(0.8, 0)),
            ],
            knights=[KnightState("k1", (0.4, 0), 600)],
        )
    )
    assert action is None


def test_micro_relocates_knights_only_when_block_point_changes():
    controller = LocalTacticsController(poll_steps=1)
    controller.set_orders(
        StandingOrders(
            collect_gold=False,
            knight_block_point=(1.0, 0.5),
        )
    )
    battlefield = state(
        game_step=1,
        towers=[],
        knights=[KnightState("k1", (0, 0), 600)],
    )
    battlefield.towers = [
        # The micro controller only needs the semantic tower type here.
        Tower("tower_site_00", "knight", (0, 0))
    ]

    first = controller.decide(battlefield)
    battlefield.game_step = 200
    repeated = controller.decide(battlefield)
    controller.set_orders(
        StandingOrders(
            collect_gold=False,
            knight_block_point=(1.5, 0.5),
        )
    )
    battlefield.game_step = 400
    changed = controller.decide(battlefield)

    assert first and first.type == "relocate_knights"
    assert repeated is None
    assert changed and changed.position == (1.5, 0.5)
