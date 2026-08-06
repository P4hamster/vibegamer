from __future__ import annotations

import argparse
import json

from tower_referee.hud_layout import calculate_hud_layout, rectangles_intersect


def validate(width: int, height: int) -> dict[str, object]:
    layout = calculate_hud_layout(width, height)
    card = layout.commander_card
    checks = {
        "card_inside_screen": card is None or (
            card.x >= layout.screen.x
            and card.right <= layout.screen.right
            and card.y >= layout.screen.y
            and card.bottom <= layout.screen.bottom
        ),
        "card_outside_playfield": card is None
        or not rectangles_intersect(card, layout.playfield),
        "long_text_scrollable": layout.scrollable,
    }
    return {
        "screen": {"width": width, "height": height},
        "card": None
        if card is None
        else {
            "x": card.x,
            "y": card.y,
            "width": card.width,
            "height": card.height,
        },
        "checks": checks,
        "ok": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate TowerMind HUD layout contract")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    print(json.dumps(validate(args.width, args.height), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
