"""Run deterministic strategy probes without starting the Unity game."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from tower_referee.cli import load_local_env
from tower_referee.config import ExperimentConfig
from tower_referee.diagnostics import (
    grade_decision,
    load_suite,
    replay_counterfactual,
    state_from_dict,
    validate_reference,
)
from tower_referee.models import (
    AFFORDABILITY_PREFLIGHT_V1,
    THREAT_TRADEOFF_PREFLIGHT_V1,
    TIMELINE_PROJECTION_V1,
    TARGET_LOCK_LEDGER_V1,
    build_model,
    parse_decision,
)


def _scaffold_id(parts: list[str]) -> str:
    names = {
        "affordability_preflight_v1": "affordability",
        "threat_tradeoff_preflight_v1": "threat_tradeoff",
        "timeline_projection_v1": "timeline",
        "target_lock_ledger_v1": "target_lock",
    }
    return "direct_action_" + "_".join(names[item] for item in parts) + "_v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.official-six.json")
    parser.add_argument("--suite", default="configs/diagnostic-suite.v1.json")
    parser.add_argument("--model")
    parser.add_argument("--output", default="artifacts/diagnostic-suite.json")
    parser.add_argument(
        "--replay-from",
        help="Existing diagnostic JSON to re-score without a model API call.",
    )
    parser.add_argument(
        "--affordability-scaffold",
        action="store_true",
        help="Run the explicit affordability-preflight A/B prompt variant.",
    )
    parser.add_argument(
        "--threat-tradeoff-scaffold",
        action="store_true",
        help="Run the explicit visible air-ground trade-off A/B prompt variant.",
    )
    parser.add_argument(
        "--timeline-projection-scaffold",
        action="store_true",
        help="Run the published diagnostic-assumption combat-timeline A/B prompt variant.",
    )
    parser.add_argument(
        "--target-lock-ledger-scaffold",
        action="store_true",
        help="Run the target-lock and switch event-ledger A/B prompt variant.",
    )
    args = parser.parse_args()

    load_local_env()
    config = ExperimentConfig.load(args.config)
    suite = load_suite(args.suite)
    if not args.model and not args.replay_from:
        parser.error("one of --model or --replay-from is required")
    if args.model and args.replay_from:
        parser.error("--model and --replay-from cannot be used together")
    if (
        args.affordability_scaffold
        or args.threat_tradeoff_scaffold
        or args.timeline_projection_scaffold
        or args.target_lock_ledger_scaffold
    ) and args.replay_from:
        parser.error("scaffold flags require a live --model run")

    scaffold_suffix = ""
    scaffold_parts: list[str] = []
    if args.affordability_scaffold:
        scaffold_suffix += AFFORDABILITY_PREFLIGHT_V1
        scaffold_parts.append("affordability_preflight_v1")
    if args.threat_tradeoff_scaffold:
        scaffold_suffix += THREAT_TRADEOFF_PREFLIGHT_V1
        scaffold_parts.append("threat_tradeoff_preflight_v1")
    if args.timeline_projection_scaffold:
        scaffold_suffix += TIMELINE_PROJECTION_V1
        scaffold_parts.append("timeline_projection_v1")
    if args.target_lock_ledger_scaffold:
        scaffold_suffix += TARGET_LOCK_LEDGER_V1
        scaffold_parts.append("target_lock_ledger_v1")

    previous_by_task = {}
    previous_scaffold_id = None
    previous_scaffold_addendum = None
    model = None
    if args.replay_from:
        previous = json.loads(Path(args.replay_from).read_text(encoding="utf-8"))
        previous_by_task = {item["task_id"]: item for item in previous["results"]}
        previous_scaffold_id = previous.get("scaffold_id")
        previous_scaffold_addendum = previous.get("scaffold_addendum")
    else:
        selected = next(item for item in config.models if item.name == args.model)
        model = build_model(
            selected,
            config.seed,
            config.temperature,
            config.max_tokens,
            system_prompt_suffix=scaffold_suffix,
        )

    results = []
    for task in suite["tasks"]:
        reference_validation = validate_reference(task)
        state = state_from_dict(task["state"])
        previous_result = previous_by_task.get(task["id"])
        if previous_result:
            decision = parse_decision(previous_result["raw_response"])
            model_name = previous_result["model"]
            model_id = previous_result["model_id"]
        else:
            assert model is not None
            decision = model.decide(state)
            model_name = model.name
            model_id = model.model_id
        grade = grade_decision(state, decision, task["checks"])
        primary_grader = task.get("primary_grader", "deterministic")
        if primary_grader == "counterfactual_replay":
            primary_assessment = replay_counterfactual(task, state, decision)
        elif primary_grader == "human_review":
            primary_assessment = {
                "status": "pending_human_review",
                "rubric": task.get("review_rubric", []),
                "auxiliary_legality_grade": grade,
            }
        else:
            primary_assessment = {
                "status": "scored",
                "score": grade["score"],
                "passed": grade["score"] == 1,
            }
        results.append(
            {
                "task_id": task["id"],
                "capability": task["capability"],
                "primary_grader": primary_grader,
                "reference_validation": reference_validation,
                "model": model_name,
                "model_id": model_id,
                "analysis_summary": decision.analysis_summary,
                "actions": [asdict(action) for action in decision.actions],
                "raw_response": decision.raw_response,
                "request_trace": decision.request_trace,
                "grade": grade,
                "primary_assessment": primary_assessment,
            }
        )

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite_id": suite["suite_id"],
        "suite_version": suite["version"],
        "harness_version": config.harness_version,
        "observation_mode": config.observation_mode,
        "scaffold_id": (
            _scaffold_id(scaffold_parts)
            if scaffold_parts
            else previous_scaffold_id or config.scaffold_id
        ),
        "scaffold_addendum": (
            "+".join(scaffold_parts) if scaffold_parts else previous_scaffold_addendum
        ),
        "replayed_from": args.replay_from,
        "results": results,
        "deterministic_mean_score": round(
            sum(
                item["grade"]["score"]
                for item in results
                if item["primary_grader"] == "deterministic"
            )
            / max(
                sum(
                    item["primary_grader"] == "deterministic"
                    for item in results
                ),
                1,
            ),
            4,
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
