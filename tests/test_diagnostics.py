import json

from tower_referee.diagnostics import (
    grade_decision,
    load_suite,
    replay_counterfactual,
    state_from_dict,
    validate_reference,
)
from tower_referee.schema import Action, Decision


def test_all_diagnostic_references_are_solvable():
    suite = load_suite("configs/diagnostic-suite.v1.json")
    results = [validate_reference(task) for task in suite["tasks"]]
    assert results[0]["score"] == 1
    assert results[1]["status"] == "not_applicable"
    assert results[2]["status"] == "not_applicable"


def test_decoy_site_grader_rejects_legal_but_strategically_wrong_site():
    suite = load_suite("configs/diagnostic-suite.v1.json")
    task = suite["tasks"][0]
    state = state_from_dict(task["state"])
    decision = Decision(
        analysis_summary="选入口",
        actions=[Action(type="build", tower="knight", position=(-2.0, 0.0))],
    )
    result = grade_decision(state, decision, task["checks"])
    assert result["checks"][0]["passed"] is True
    assert result["checks"][1]["passed"] is False


def test_diagnostic_suite_is_explicitly_draft():
    suite = json.loads(
        open("configs/diagnostic-suite.v1.json", encoding="utf-8").read()
    )
    assert suite["status"] == "draft_pending_human_review"


def test_counterfactual_replay_scores_simulated_outcomes_not_tower_name():
    suite = load_suite("configs/diagnostic-suite.v1.json")
    task = suite["tasks"][1]
    state = state_from_dict(task["state"])

    archer = replay_counterfactual(
        task,
        state,
        Decision(
            analysis_summary="先补防空",
            actions=[Action(type="build", tower="archer", position=(0.0, 0.0))],
        ),
    )
    knight = replay_counterfactual(
        task,
        state,
        Decision(
            analysis_summary="先压地面漏怪",
            actions=[Action(type="build", tower="knight", position=(0.0, 0.0))],
        ),
    )

    assert archer["passed"] is False
    assert knight["passed"] is True
    assert archer["submitted_outcome"]["base_hp_lost"] > knight["submitted_outcome"]["base_hp_lost"]
    assert {item["candidate"]["tower"] for item in archer["candidate_outcomes"] if item["candidate"]["type"] == "build"} == {"archer", "magician", "knight"}


def test_counterfactual_replay_mechanics_are_visible_to_the_model():
    suite = load_suite("configs/diagnostic-suite.v1.json")
    task = suite["tasks"][1]
    replay = task["counterfactual_replay"]
    combat = task["state"]["game_rules"]["tower_combat"]

    assert replay["tower_profiles"] == combat["tower_profiles"]
    assert replay["enemy_profiles"] == combat["enemy_leak_profiles"]
    assert replay["targeting"] == combat["targeting"]
    assert replay["provenance"] == combat["provenance"]
    assert replay["provenance"]["classification"] == "diagnostic_assumption"


def test_counterfactual_replay_must_be_labeled_as_a_diagnostic_assumption():
    suite = json.loads(
        open("configs/diagnostic-suite.v1.json", encoding="utf-8").read()
    )
    task = suite["tasks"][1]
    task["state"]["game_rules"]["tower_combat"]["provenance"] = {
        "classification": "TowerMind_native_rule"
    }

    try:
        load_suite_from_bad_task = {"tasks": [task]}
        # Exercise the public loader boundary without mutating the checked-in suite.
        from tower_referee.diagnostics import _validate_counterfactual_public_mechanics

        _validate_counterfactual_public_mechanics(load_suite_from_bad_task["tasks"][0])
    except ValueError as error:
        assert "diagnostic assumption" in str(error)
    else:
        raise AssertionError("expected an unlabeled replay assumption to be rejected")


def test_diagnostic_grader_accepts_a_valid_gold_gated_build_plan():
    suite = load_suite("configs/diagnostic-suite.v1.json")
    task = suite["tasks"][2]
    state = state_from_dict(task["state"])
    result = grade_decision(
        state,
        Decision(
            analysis_summary="等攒够钱再建塔",
            actions=[
                Action(
                    type="build",
                    tower="archer",
                    position=(0.0, 0.0),
                    wait="gold_at_least:120",
                )
            ],
        ),
        task["checks"],
    )

    assert result["score"] == 1.0
    assert result["pending"][0]["wait"] == "gold_at_least:120"
