from __future__ import annotations

from tower_referee.game.sim import TOWER_COSTS, SimulatedTowerDefense
from tower_referee.schema import Action, ActionRejection, GameState


class ActionValidator:
    def validate(
        self, state: GameState, actions: list[Action], reserve_gold: int = 0
    ) -> tuple[list[Action], list[ActionRejection]]:
        accepted: list[Action] = []
        rejected: list[ActionRejection] = []
        budget = state.gold
        occupied = {tower.position for tower in state.towers}
        tower_by_id = {tower.id: tower for tower in state.towers}
        seen_targets: set[str] = set()

        for action in actions:
            reason: str | None = None
            cost = 0
            if action.type == "build":
                if action.tower not in TOWER_COSTS:
                    reason = "unknown tower type"
                elif action.position not in state.build_sites:
                    reason = "position is not a legal build site"
                elif action.position in occupied:
                    reason = "build site is occupied"
                else:
                    cost = TOWER_COSTS[action.tower]
            elif action.type in {"upgrade", "sell"}:
                if not action.tower_id or action.tower_id not in tower_by_id:
                    reason = "tower does not exist"
                elif tower_by_id[action.tower_id].under_fog:
                    reason = "tower is under fog and cannot receive commands"
                elif action.tower_id in seen_targets:
                    reason = "tower already targeted in this decision"
                elif action.type == "upgrade":
                    cost = SimulatedTowerDefense.upgrade_cost(tower_by_id[action.tower_id])
            elif action.type == "upgrade_hero":
                cost = 500
            elif action.type == "show_range":
                if not action.tower_id or action.tower_id not in tower_by_id:
                    reason = "tower does not exist"
                elif tower_by_id[action.tower_id].under_fog:
                    reason = "tower is under fog and cannot receive commands"
            elif action.type in {
                "relocate_knights",
                "deploy_reinforcements",
                "move_hero",
            }:
                if action.position is None:
                    reason = "position is required"
                elif (
                    action.type == "deploy_reinforcements"
                    and state.reinforcement_countdown > 0
                ):
                    reason = "reinforcements are on cooldown"
                elif action.type == "move_hero" and (
                    state.hero is None or state.hero.dead
                ):
                    reason = "hero is unavailable"
            elif action.type == "hero_skill":
                if state.hero is None or state.hero.dead:
                    reason = "hero is unavailable"
            elif action.type != "noop":
                reason = "unknown action type"

            if reason is None and cost > budget - max(0, reserve_gold):
                reason = "insufficient gold after reserve"
            if reason:
                rejected.append(ActionRejection(self._action_dict(action), reason))
                continue

            accepted.append(action)
            budget -= cost
            if action.type == "build" and action.position:
                occupied.add(action.position)
            elif action.type == "sell" and action.tower_id:
                sold = tower_by_id.pop(action.tower_id)
                occupied.discard(sold.position)
                refund_ratio = float(
                    state.game_rules.get("sell_refund_ratio", 0.0)
                )
                budget += int(sold.spent * refund_ratio)
            if action.tower_id:
                seen_targets.add(action.tower_id)
        return accepted, rejected

    @staticmethod
    def _action_dict(action: Action) -> dict:
        return {
            "type": action.type,
            "tower": action.tower,
            "position": action.position,
            "tower_id": action.tower_id,
            "skill": action.skill,
            "id": action.id,
            "after": action.after,
            "wait": action.wait,
        }
