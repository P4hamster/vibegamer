from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HudRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class HudLayout:
    screen: HudRect
    playfield: HudRect
    left_letterbox: HudRect
    commander_card: HudRect | None
    scrollable: bool


def calculate_hud_layout(width: int, height: int) -> HudLayout:
    """Mirror the standalone plugin's safe-margin geometry.

    This is a layout contract test, not a pixel-perfect Unity renderer. It
    protects the important invariant: the commander card never intersects the
    centered square game viewport, and long content has a scrollable region.
    """
    screen = HudRect(0, 0, float(width), float(height))
    playfield_size = float(min(width, height))
    side_width = (float(width) - playfield_size) / 2.0
    playfield = HudRect(side_width, 0, playfield_size, float(height))
    left_letterbox = HudRect(0, 0, side_width, float(height))
    if side_width < 224.0:
        return HudLayout(screen, playfield, left_letterbox, None, False)
    card_width = min(260.0, side_width - 28.0)
    card = HudRect(14.0, 14.0, card_width, max(0.0, float(height) - 28.0))
    return HudLayout(screen, playfield, left_letterbox, card, True)


def rectangles_intersect(first: HudRect, second: HudRect) -> bool:
    return not (
        first.right <= second.x
        or second.right <= first.x
        or first.bottom <= second.y
        or second.bottom <= first.y
    )
