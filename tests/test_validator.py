from tower_referee.schema import Action, GameState, Tower
from tower_referee.validator import ActionValidator


def state(gold=300):
    return GameState(
        wave=0,
        max_waves=4,
        base_hp=100,
        max_base_hp=100,
        gold=gold,
        build_sites=[(1, 1), (2, 2)],
    )


def test_rejects_illegal_position_and_overspend():
    validator = ActionValidator()
    accepted, rejected = validator.validate(
        state(200),
        [
            Action(type="build", tower="archer", position=(9, 9)),
            Action(type="build", tower="magician", position=(1, 1)),
            Action(type="build", tower="archer", position=(2, 2)),
        ],
    )
    assert len(accepted) == 1
    assert len(rejected) == 2
    assert {item.reason for item in rejected} == {
        "position is not a legal build site",
        "insufficient gold after reserve",
    }


def test_rejects_missing_tower():
    accepted, rejected = ActionValidator().validate(
        state(), [Action(type="upgrade", tower_id="missing")]
    )
    assert not accepted
    assert rejected[0].reason == "tower does not exist"


def test_reserve_gold_is_respected():
    accepted, rejected = ActionValidator().validate(
        state(200),
        [Action(type="build", tower="archer", position=(1, 1))],
        reserve_gold=100,
    )
    assert not accepted
    assert rejected[0].reason == "insufficient gold after reserve"


def test_sell_then_rebuild_same_site_uses_refund():
    current = state(20)
    current.towers = [Tower("tower_1", "archer", (1, 1), spent=120)]
    current.game_rules["sell_refund_ratio"] = 1.0
    accepted, rejected = ActionValidator().validate(
        current,
        [
            Action(type="sell", tower_id="tower_1"),
            Action(type="build", tower="magician", position=(1, 1)),
        ],
    )
    assert [action.type for action in accepted] == ["sell", "build"]
    assert not rejected


def test_tower_under_fog_cannot_receive_targeted_commands():
    current = state()
    current.towers = [
        Tower(
            "tower_site_01",
            "archer",
            (1, 1),
            under_fog=True,
            operational=False,
        )
    ]

    accepted, rejected = ActionValidator().validate(
        current,
        [Action(type="upgrade", tower_id="tower_site_01")],
    )

    assert not accepted
    assert rejected[0].reason == "tower is under fog and cannot receive commands"
