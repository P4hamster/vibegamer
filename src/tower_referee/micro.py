from __future__ import annotations

from math import dist

from tower_referee.schema import Action, GameState, StandingOrders


class LocalTacticsController:
    """Deterministically carries out an LLM's standing orders."""

    def __init__(self, poll_steps: int = 20) -> None:
        self.orders: StandingOrders | None = None
        self.poll_steps = max(1, poll_steps)
        self.last_poll_step = -self.poll_steps
        self.last_skill_step = -250
        self.last_knight_step = -100
        self.last_knight_target: tuple[float, float] | None = None
        self.last_reinforcement_step = -100
        self.last_move_step = -100
        self.last_move_target: tuple[float, float] | None = None
        self.coin_target: tuple[float, float] | None = None
        self.coin_target_step = -500

    def set_orders(self, orders: StandingOrders | None) -> None:
        if orders is not None:
            self.orders = orders

    def decide(self, state: GameState) -> Action | None:
        orders = self.orders
        if orders is None or state.game_step - self.last_poll_step < self.poll_steps:
            return None
        self.last_poll_step = state.game_step
        hero = state.hero

        if hero and not hero.dead:
            if (
                hero.hp <= orders.hero_retreat_below_hp
                and orders.hero_retreat_position
                and self._far(hero.position, orders.hero_retreat_position)
                and self._move_is_due(state, orders.hero_retreat_position)
            ):
                self._mark_move(state, orders.hero_retreat_position)
                return Action(type="move_hero", position=orders.hero_retreat_position)
            if (
                orders.collect_gold
                and state.dropped_gold
                and self._coin_is_within_leash(
                    state.dropped_gold.position,
                    hero.position,
                    orders,
                )
            ):
                reached = (
                    self.coin_target is not None
                    and not self._far(hero.position, self.coin_target, 0.2)
                )
                expired = state.game_step - self.coin_target_step >= 300
                if self.coin_target is None or reached or expired:
                    self.coin_target = state.dropped_gold.position
                    self.coin_target_step = state.game_step
                if (
                    self._far(hero.position, self.coin_target, 0.15)
                    and self._move_is_due(state, self.coin_target)
                ):
                    self._mark_move(state, self.coin_target)
                    return Action(type="move_hero", position=self.coin_target)
            elif state.dropped_gold is None:
                self.coin_target = None
            nearby_ground = sum(
                1
                for enemy in state.visible_enemies
                if not enemy.flying
                and enemy.position
                and hero.position
                and dist(hero.position, enemy.position) <= 1.5
            )
            if (
                orders.use_hero_skill_when_enemy_count > 0
                and nearby_ground >= orders.use_hero_skill_when_enemy_count
                and hero.hp
                >= max(orders.hero_skill_min_hp, hero.max_hp * 0.6)
                and not self._friendly_knights_near_hero(state)
                and state.game_step - self.last_skill_step >= 250
            ):
                self.last_skill_step = state.game_step
                return Action(type="hero_skill")
            if (
                orders.hero_anchor
                and self._far(hero.position, orders.hero_anchor, 0.3)
                and self._move_is_due(state, orders.hero_anchor)
            ):
                self._mark_move(state, orders.hero_anchor)
                return Action(type="move_hero", position=orders.hero_anchor)

        if (
            orders.reinforcement_point
            and state.reinforcement_countdown <= 0
            and state.game_step - self.last_reinforcement_step >= 100
        ):
            self.last_reinforcement_step = state.game_step
            return Action(
                type="deploy_reinforcements",
                position=orders.reinforcement_point,
            )
        if (
            orders.knight_block_point
            and any(tower.kind == "knight" for tower in state.towers)
            and state.knights
            and (
                self.last_knight_target is None
                or dist(
                    self.last_knight_target,
                    orders.knight_block_point,
                )
                > 0.15
            )
        ):
            self.last_knight_step = state.game_step
            self.last_knight_target = orders.knight_block_point
            return Action(
                type="relocate_knights",
                position=orders.knight_block_point,
            )
        return None

    @staticmethod
    def _far(
        current: tuple[float, float] | None,
        target: tuple[float, float],
        threshold: float = 0.25,
    ) -> bool:
        return current is None or dist(current, target) > threshold

    def _move_is_due(
        self, state: GameState, target: tuple[float, float]
    ) -> bool:
        return (
            self.last_move_target is None
            or dist(self.last_move_target, target) > 0.15
            or state.game_step - self.last_move_step >= 100
        )

    def _mark_move(
        self, state: GameState, target: tuple[float, float]
    ) -> None:
        self.last_move_target = target
        self.last_move_step = state.game_step

    @staticmethod
    def _coin_is_within_leash(
        coin: tuple[float, float],
        hero_position: tuple[float, float] | None,
        orders: StandingOrders,
    ) -> bool:
        anchor = orders.hero_anchor or hero_position
        if anchor is None:
            return False
        return dist(anchor, coin) <= orders.collect_gold_radius_from_anchor

    @staticmethod
    def _friendly_knights_near_hero(state: GameState) -> bool:
        if not state.hero or not state.hero.position:
            return False
        return any(
            dist(state.hero.position, knight.position) <= 1.5
            for knight in state.knights
        )
