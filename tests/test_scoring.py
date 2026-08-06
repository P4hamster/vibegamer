from tower_referee.schema import RunSummary
from tower_referee.scoring import derive_metrics, score_all


def summary(round_id, hp, damage=500):
    return RunSummary(
        experiment_id="x",
        model_name="m",
        model_id="m1",
        round_id=round_id,
        run_index=1,
        map_id="map",
        seed=1,
        waves_survived=5,
        max_waves=5,
        base_hp=hp,
        max_base_hp=100,
        gold_remaining=100,
        gold_spent=500,
        damage_dealt=damage,
        invalid_actions=0,
        total_actions=5,
        accepted_actions=5,
        won=True,
        outcome="won",
        outcome_valid=True,
        terminal_confirmed=True,
        terminal_interrupted=False,
        score_eligible=True,
    )


def test_round_two_gets_improvement_component():
    first = summary(1, 50)
    second = summary(2, 100, 800)
    score_all([first, second])
    assert second.improvement > 0
    assert second.score > first.score


def test_research_metrics_keep_units_separate():
    item = summary(1, 50, damage=1000)
    derive_metrics(item)
    assert item.completion_ratio == 1
    assert item.base_hp_ratio == 0.5
    assert item.action_validity_rate == 1
    assert item.damage_per_gold == 2
    assert item.unspent_gold_ratio == round(100 / 600, 4)
