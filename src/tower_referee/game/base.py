from __future__ import annotations

from abc import ABC, abstractmethod

from tower_referee.schema import (
    Action,
    ActionRejection,
    Decision,
    GameEvent,
    GameState,
    StandingOrders,
    WaveResult,
)


class InvalidInitialStateError(RuntimeError):
    """The backend did not produce a trustworthy fresh map state."""

    def __init__(
        self,
        reason: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


class GameAdapter(ABC):
    @abstractmethod
    def reset(self, map_id: str, seed: int, max_waves: int) -> GameState:
        raise NotImplementedError

    @abstractmethod
    def pause(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def resume(self) -> None:
        raise NotImplementedError

    def set_standing_orders(self, orders: StandingOrders | None) -> None:
        """Install persistent local tactics. Backends may ignore unsupported orders."""

    def drain_micro_actions(self) -> list[dict]:
        return []

    def drain_monitor_audit(self) -> list[dict]:
        return []

    def publish_decision(
        self,
        model_name: str,
        decision: Decision,
        accepted: list[Action],
        rejected: list[ActionRejection],
    ) -> None:
        """Expose the current decision to an optional spectator HUD."""

    def publish_transition(
        self,
        outcome: str,
        title: str,
        detail: str,
        can_retry: bool = False,
    ) -> None:
        """Show an optional between-level result screen."""

    def transition_action(self) -> str | None:
        """Return a spectator transition choice such as retry/stop/next."""
        return None

    def pump_transition_frame(self) -> None:
        """Let an externally driven game repaint/process transition UI."""

    @abstractmethod
    def apply_actions(self, actions: list[Action]) -> GameState:
        raise NotImplementedError

    @abstractmethod
    def play_wave(self) -> tuple[GameState, WaveResult]:
        raise NotImplementedError

    def advance_until_event(
        self, max_steps: int = 600
    ) -> tuple[GameState, list[GameEvent], WaveResult]:
        state, result = self.play_wave()
        return state, [GameEvent("wave_changed", {"wave": state.wave}, 90)], result

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
