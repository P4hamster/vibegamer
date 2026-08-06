from __future__ import annotations

from collections import defaultdict

from tower_referee.schema import RunSummary


def derive_metrics(summary: RunSummary) -> None:
    """Populate interpretable metrics without combining unlike units."""
    summary.completion_ratio = round(
        min(summary.waves_survived / max(summary.max_waves, 1), 1.0), 4
    )
    summary.base_hp_ratio = round(
        max(0.0, summary.base_hp / max(summary.max_base_hp, 1)), 4
    )
    summary.action_validity_rate = round(
        summary.accepted_actions / max(summary.total_actions, 1), 4
    )
    summary.damage_per_gold = round(
        summary.damage_dealt / max(summary.gold_spent, 1), 4
    )
    available_gold = summary.gold_spent + summary.gold_remaining
    summary.unspent_gold_ratio = round(
        summary.gold_remaining / max(available_gold, 1), 4
    )


def showcase_score(summary: RunSummary) -> float:
    """A transparent video index, not a scientific measure of strategy.

    Efficiency stays separate because damage/gold is not comparable across maps
    without a calibrated reference policy for every task.
    """
    derive_metrics(summary)
    if not summary.score_eligible:
        return 0.0
    score = (
        60 * summary.completion_ratio
        + 20 * summary.base_hp_ratio
        + 10 * summary.action_validity_rate
        + (10 if summary.won else 0)
    )
    return round(max(0.0, min(100.0, score)), 2)


# Backwards-compatible name used by the campaign code.
base_score = showcase_score


def score_all(summaries: list[RunSummary]) -> None:
    first_round: dict[tuple[str, int], float] = {}
    for summary in summaries:
        raw = showcase_score(summary)
        if summary.round_id == 1:
            first_round[(summary.model_id, summary.run_index)] = raw
        if summary.round_id == 2:
            baseline = first_round.get((summary.model_id, summary.run_index), raw)
            summary.improvement = round(raw - baseline, 2)
            improvement_points = max(0.0, min(15.0, summary.improvement))
            summary.score = round(min(100.0, raw + improvement_points), 2)
        else:
            summary.score = raw
        summary.personality = (
            infer_personality(summary)
            if summary.score_eligible
            else "结果无效"
        )


def score_campaign(
    summaries: list[RunSummary],
    total_stages: int | None = None,
) -> dict[str, object]:
    """Score stages and return the entertainment-focused tower progress score.

    Every reached stage keeps its normal 0-100 showcase score. Unplayed later
    stages contribute zero, so the campaign score visibly rewards climbing the
    tower while retaining the detailed per-map scores for viewers.
    """
    for summary in summaries:
        summary.score = showcase_score(summary)
        summary.improvement = 0.0
        summary.personality = (
            infer_personality(summary)
            if summary.score_eligible
            else "结果无效"
        )
    latest_by_stage: dict[int, RunSummary] = {}
    for summary in summaries:
        latest_by_stage[summary.round_id] = summary
    stage_count = max(total_stages or 0, max(latest_by_stage, default=0), 1)
    ordered = [latest_by_stage[index] for index in sorted(latest_by_stage)]
    cleared = sum(1 for item in ordered if item.score_eligible and item.won)
    campaign_score = round(
        sum(item.score for item in ordered if item.score_eligible) / stage_count,
        2,
    )
    return {
        "formula": "sum(latest reached stage score) / total stages; unplayed stages=0",
        "total_stages": stage_count,
        "reached_stages": len(ordered),
        "cleared_stages": cleared,
        "progress_percent": round(100 * cleared / stage_count, 2),
        "campaign_score": campaign_score,
        "last_stage": (
            {
                "round_id": ordered[-1].round_id,
                "map_id": ordered[-1].map_id,
                "outcome": ordered[-1].outcome,
                "score": ordered[-1].score,
            }
            if ordered
            else None
        ),
        "stages": [
            {
                "round_id": item.round_id,
                "map_id": item.map_id,
                "outcome": item.outcome,
                "score": item.score,
                "won": item.won,
                "base_hp": item.base_hp,
                "waves_survived": item.waves_survived,
            }
            for item in ordered
        ],
    }


def infer_personality(summary: RunSummary) -> str:
    hp_ratio = summary.base_hp / max(summary.max_base_hp, 1)
    invalid_ratio = summary.invalid_actions / max(summary.total_actions, 1)
    if summary.won and hp_ratio < 0.3:
        return "极限守城"
    if summary.won and hp_ratio >= 0.5:
        return "稳健城防"
    if summary.invalid_actions >= 5 and invalid_ratio >= 0.5:
        return "纸上谈兵"
    if summary.gold_remaining > summary.gold_spent * 0.8:
        return "囤币守财"
    if summary.gold_spent > summary.gold_remaining * 4 and hp_ratio < 0.4:
        return "火力梭哈"
    return "均衡应变"


def aggregate_leaderboards(
    summaries: list[RunSummary],
) -> dict[str, list[dict[str, float | str]]]:
    grouped: dict[tuple[int, str], list[RunSummary]] = defaultdict(list)
    for summary in summaries:
        grouped[(summary.round_id, summary.model_name)].append(summary)
    boards: dict[str, list[dict[str, float | str]]] = {}
    names = {1: "blind", 2: "review", 3: "generalization"}
    for round_id, board_name in names.items():
        rows = []
        for (rid, model_name), items in grouped.items():
            if rid != round_id:
                continue
            rows.append(
                {
                    "model": model_name,
                    "score": round(sum(item.score for item in items) / len(items), 2),
                    "base_hp": round(sum(item.base_hp for item in items) / len(items), 1),
                    "waves": round(
                        sum(item.waves_survived for item in items) / len(items), 1
                    ),
                    "improvement": round(
                        sum(item.improvement for item in items) / len(items), 2
                    ),
                }
            )
        boards[board_name] = sorted(rows, key=lambda row: row["score"], reverse=True)
    return boards
