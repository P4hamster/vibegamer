from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from tower_referee.schema import (
    Action,
    ActionRejection,
    Decision,
    Enemy,
    GameState,
    HeroState,
    Tower,
)
from tower_referee.validator import ActionValidator


def load_suite(path: str | Path) -> dict[str, Any]:
    suite = json.loads(Path(path).read_text(encoding="utf-8"))
    if not suite.get("tasks"):
        raise ValueError("A diagnostic suite needs at least one task")
    for task in suite["tasks"]:
        _validate_counterfactual_public_mechanics(task)
    return suite


def _validate_counterfactual_public_mechanics(task: dict[str, Any]) -> None:
    """Keep replay assumptions visible, aligned, and explicitly non-native."""
    if task.get("primary_grader") != "counterfactual_replay":
        return
    replay = task.get("counterfactual_replay")
    combat = task.get("state", {}).get("game_rules", {}).get("tower_combat")
    if not isinstance(replay, dict) or not isinstance(combat, dict):
        raise ValueError(
            f"Counterfactual task {task['id']} must publish its combat mechanics"
        )
    provenance = combat.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("classification") != (
        "diagnostic_assumption"
    ):
        raise ValueError(
            f"Counterfactual task {task['id']} must label its replay as a "
            "diagnostic assumption"
        )
    paired_fields = {
        "provenance": "provenance",
        "targeting": "targeting",
        "time_step_seconds": "simulation_time_step_seconds",
        "tower_profiles": "tower_profiles",
        "enemy_profiles": "enemy_leak_profiles",
    }
    mismatches = [
        replay_name
        for replay_name, public_name in paired_fields.items()
        if replay.get(replay_name) != combat.get(public_name)
    ]
    if mismatches:
        raise ValueError(
            f"Counterfactual task {task['id']} hides or mismatches replay assumptions: "
            f"{', '.join(mismatches)}"
        )


def state_from_dict(data: dict[str, Any]) -> GameState:
    payload = dict(data)
    payload["build_sites"] = [tuple(item) for item in payload.get("build_sites", [])]
    payload["enemy_paths"] = [
        [tuple(point) for point in path]
        for path in payload.get("enemy_paths", [])
    ]
    payload["towers"] = [
        Tower(
            **{
                **item,
                "position": tuple(item["position"]),
                "rally_position": (
                    tuple(item["rally_position"])
                    if item.get("rally_position") is not None
                    else None
                ),
            }
        )
        for item in payload.get("towers", [])
    ]
    payload["visible_enemies"] = [
        Enemy(
            **{
                **item,
                "position": (
                    tuple(item["position"])
                    if item.get("position") is not None
                    else None
                ),
            }
        )
        for item in payload.get("visible_enemies", [])
    ]
    if payload.get("hero") is not None:
        hero = dict(payload["hero"])
        if hero.get("position") is not None:
            hero["position"] = tuple(hero["position"])
        payload["hero"] = HeroState(**hero)
    return GameState(**payload)


def action_from_dict(data: dict[str, Any]) -> Action:
    payload = dict(data)
    if payload.get("position") is not None:
        payload["position"] = tuple(payload["position"])
    return Action(**payload)


def grade_decision(
    state: GameState,
    decision: Decision,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    validator = ActionValidator()
    accepted, rejected = _validate_diagnostic_actions(
        validator, state, decision.actions, decision.reserve_gold
    )
    results = [
        _grade_check(check, decision.actions, accepted, rejected)
        for check in checks
    ]
    passed = sum(bool(item["passed"]) for item in results)
    return {
        "passed_checks": passed,
        "total_checks": len(results),
        "score": round(passed / max(len(results), 1), 4),
        "checks": results,
        "accepted": [asdict(action) for action in accepted],
        "pending": [
            asdict(action) for action in accepted if action.wait is not None or action.after
        ],
        "rejected": [asdict(item) for item in rejected],
    }


def _validate_diagnostic_actions(
    validator: ActionValidator,
    state: GameState,
    actions: list[Action],
    reserve_gold: int,
) -> tuple[list[Action], list[ActionRejection]]:
    """Validate current actions and explicit gold-gated plans fairly.

    The full runner queues ``gold_at_least:N`` actions and validates them only
    after the state has reached N gold.  Diagnostics have no running game loop,
    so they reproduce that specific scheduling rule here instead of incorrectly
    treating the plan as an unaffordable immediate purchase.
    """
    immediate = [action for action in actions if not action.wait]
    accepted, rejected = validator.validate(state, immediate, reserve_gold)
    for action in actions:
        if not action.wait:
            continue
        if action.wait.startswith("gold_at_least:"):
            _, _, raw_threshold = action.wait.partition(":")
            try:
                threshold = int(raw_threshold)
            except ValueError:
                rejected.append(
                    ActionRejection(
                        validator._action_dict(action), "invalid gold wait threshold"
                    )
                )
                continue
            planned_state = replace(state, gold=max(state.gold, threshold))
            planned_action = replace(action, wait=None)
            valid, plan_rejected = validator.validate(
                planned_state, [planned_action], reserve_gold
            )
            if valid:
                accepted.append(action)
            else:
                rejected.extend(
                    ActionRejection(
                        validator._action_dict(action), item.reason
                    )
                    for item in plan_rejected
                )
            continue
        valid, plan_rejected = validator.validate(state, [action], reserve_gold)
        accepted.extend(valid)
        rejected.extend(plan_rejected)
    return accepted, rejected


def validate_reference(task: dict[str, Any]) -> dict[str, Any]:
    if task.get("primary_grader", "deterministic") != "deterministic":
        return {
            "status": "not_applicable",
            "reason": "This task requires counterfactual replay or human review.",
        }
    if not task.get("reference_solution"):
        raise ValueError(f"Deterministic task {task['id']} needs a reference solution")
    state = state_from_dict(task["state"])
    decision = Decision(
        analysis_summary="reference solution",
        actions=[action_from_dict(item) for item in task["reference_solution"]],
        reserve_gold=int(task.get("reference_reserve_gold", 0)),
    )
    result = grade_decision(state, decision, task["checks"])
    if result["score"] < 1:
        raise ValueError(
            f"Reference solution does not pass task {task['id']}: {result['checks']}"
        )
    return result


def replay_counterfactual(
    task: dict[str, Any], state: GameState, decision: Decision
) -> dict[str, Any]:
    """Compare the submitted immediate build with every legal one-build option.

    This is intentionally a small, public diagnostic model rather than an
    approximation of a full TowerMind level.  It keeps the state, gold and
    visible enemies fixed, then reports simulated short-battle outcomes for every
    candidate. Targeting is the task's published diagnostic assumption, not an
    assertion about TowerMind's native policy.
    """
    spec = task.get("counterfactual_replay")
    if not isinstance(spec, dict):
        raise ValueError(f"Counterfactual task {task['id']} needs replay settings")
    profiles = spec.get("tower_profiles")
    enemy_profiles = spec.get("enemy_profiles")
    if not isinstance(profiles, dict) or not isinstance(enemy_profiles, dict):
        raise ValueError("Counterfactual replay needs tower and enemy profiles")
    _validate_counterfactual_public_mechanics(task)

    validator = ActionValidator()
    accepted, rejected = validator.validate(
        state, decision.actions, decision.reserve_gold
    )
    immediate_builds = [
        action
        for action in accepted
        if action.type == "build" and action.wait is None and not action.after
    ]
    submitted = immediate_builds[0] if len(immediate_builds) == 1 else None
    candidates = [None]
    for site in state.build_sites:
        for tower in profiles:
            candidate = Action(type="build", tower=tower, position=site)
            legal, _ = validator.validate(state, [candidate], 0)
            if legal:
                candidates.append(candidate)

    outcomes = [_replay_outcome(state, spec, action) for action in candidates]
    submitted_outcome = _replay_outcome(state, spec, submitted)
    best_objective = min(tuple(item["objective"]) for item in outcomes)
    optimal = [
        item["candidate"]
        for item in outcomes
        if tuple(item["objective"]) == best_objective
    ]
    return {
        "status": "scored",
        "simulator_version": spec.get("simulator_version", "unknown"),
        "objective_order": list(spec.get("objective_order", [])),
        "submitted_immediate_build": _action_or_noop(submitted),
        "submitted_actions_were_valid": not rejected,
        "submitted_outcome": submitted_outcome,
        "candidate_outcomes": outcomes,
        "best_objective": list(best_objective),
        "optimal_candidates": optimal,
        "passed": tuple(submitted_outcome["objective"]) == best_objective
        and not rejected,
        "score": float(
            tuple(submitted_outcome["objective"]) == best_objective and not rejected
        ),
    }


def _replay_outcome(
    state: GameState, spec: dict[str, Any], build: Action | None
) -> dict[str, Any]:
    profiles = spec["tower_profiles"]
    enemy_profiles = spec["enemy_profiles"]
    step = float(spec.get("time_step_seconds", 0.05))
    if step <= 0:
        raise ValueError("Counterfactual replay time_step_seconds must be positive")

    enemies = [
        {
            "id": enemy.id,
            "kind": enemy.kind,
            "flying": enemy.flying or enemy.movement_type.lower() in {"air", "flying"},
            "lane": enemy.lane,
            "hp": float(enemy.hp),
            "eta": max(0.0, float(enemy.estimated_seconds_to_base)),
            "progress": float(enemy.progress),
        }
        for enemy in state.visible_enemies
    ]
    tower = profiles.get(build.tower) if build is not None else None
    current_time = 0.0
    defeated: list[dict[str, Any]] = []
    leaked: list[dict[str, Any]] = []
    epsilon = 1e-9

    while enemies:
        next_arrival = min(enemy["eta"] for enemy in enemies)
        if next_arrival <= current_time + epsilon:
            arrivals = [
                enemy for enemy in enemies if enemy["eta"] <= current_time + epsilon
            ]
            leaked.extend(arrivals)
            enemies = [enemy for enemy in enemies if enemy not in arrivals]
            continue
        duration = min(step, next_arrival - current_time)
        if tower and build and _tower_has_coverage(state, build, tower, enemies):
            target = _select_replay_target(enemies, tower)
            if target is not None:
                target["hp"] -= float(tower["dps"]) * duration
                if target["hp"] <= epsilon:
                    defeated.append(target)
                    enemies.remove(target)
        current_time += duration

    def profile(enemy: dict[str, Any]) -> dict[str, Any]:
        if enemy["kind"] not in enemy_profiles:
            raise ValueError(f"Missing replay profile for {enemy['kind']}")
        return enemy_profiles[enemy["kind"]]

    base_hp_lost = sum(int(profile(enemy)["base_damage"]) for enemy in leaked)
    weighted_leaks = sum(int(profile(enemy)["leak_weight"]) for enemy in leaked)
    return {
        "candidate": _action_or_noop(build),
        "base_hp_before": state.base_hp,
        "base_hp_after": max(0, state.base_hp - base_hp_lost),
        "base_hp_lost": base_hp_lost,
        "weighted_leaks": weighted_leaks,
        "enemies_defeated": [enemy["id"] for enemy in defeated],
        "enemies_leaked": [
            {"id": enemy["id"], "kind": enemy["kind"]} for enemy in leaked
        ],
        "objective": [base_hp_lost, weighted_leaks],
    }


def _tower_has_coverage(
    state: GameState,
    build: Action,
    tower: dict[str, Any],
    enemies: list[dict[str, Any]],
) -> bool:
    site = next(
        (
            item
            for item in state.site_insights
            if tuple(item.get("position", [])) == build.position
        ),
        None,
    )
    if site is None:
        return False
    coverage = site.get("path_coverage", {}).get(build.tower or "", [])
    return any(enemy["lane"] in coverage for enemy in enemies) and bool(tower)


def _select_replay_target(
    enemies: list[dict[str, Any]], tower: dict[str, Any]
) -> dict[str, Any] | None:
    targets = set(tower.get("targets", []))
    eligible = [
        enemy
        for enemy in enemies
        if ("air" if enemy["flying"] else "ground") in targets
    ]
    return min(eligible, key=lambda enemy: (enemy["eta"], -enemy["progress"], enemy["id"])) if eligible else None


def _action_or_noop(action: Action | None) -> dict[str, Any]:
    if action is None:
        return {"type": "noop"}
    return {
        "type": action.type,
        "tower": action.tower,
        "position": list(action.position) if action.position else None,
    }


def _grade_check(
    check: dict[str, Any],
    submitted: list[Action],
    accepted: list[Action],
    rejected: list[Any],
) -> dict[str, Any]:
    kind = check["kind"]
    passed = False
    evidence: Any = None
    if kind == "no_invalid_actions":
        passed = not rejected
        evidence = len(rejected)
    elif kind == "build_at_any":
        allowed = {tuple(item) for item in check["positions"]}
        matching = [
            action
            for action in accepted
            if action.type == "build" and action.position in allowed
        ]
        passed = bool(matching)
        evidence = [asdict(action) for action in matching]
    elif kind == "build_tower_type":
        allowed = set(check["tower_types"])
        matching = [
            action
            for action in accepted
            if action.type == "build" and action.tower in allowed
        ]
        passed = bool(matching)
        evidence = [asdict(action) for action in matching]
    elif kind == "avoid_immediate_action_types":
        forbidden = set(check["action_types"])
        offending = [
            action
            for action in submitted
            if action.type in forbidden and action.wait is None and not action.after
        ]
        passed = not offending
        evidence = [asdict(action) for action in offending]
    else:
        raise ValueError(f"Unknown diagnostic check: {kind}")
    return {
        "kind": kind,
        "passed": passed,
        "evidence": evidence,
        "description": check.get("description", ""),
    }
