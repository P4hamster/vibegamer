#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from time import monotonic, sleep
from pathlib import Path

from tower_referee.game.towermind import TowerMindAdapter
from tower_referee.schema import Action


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the real TowerMind build")
    parser.add_argument(
        "--app",
        default="vendor/TowerMind/plugin_runtime/mac_apple_silicon/td.app",
    )
    parser.add_argument("--map", default="0")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--hold-seconds", type=float, default=0)
    parser.add_argument(
        "--transition",
        choices=("success", "failure"),
        default=None,
    )
    args = parser.parse_args()
    adapter = TowerMindAdapter(
        Path(args.app),
        Path("vendor/TowerMind"),
        screen_width=args.width,
        screen_height=args.height,
        fullscreen=args.fullscreen,
        plugin_url=(
            "http://127.0.0.1:17871" if args.transition else None
        ),
        plugin_required=bool(args.transition),
    )
    try:
        initial = adapter.reset(args.map, seed=0, max_waves=5)
        if not initial.build_sites:
            raise RuntimeError("TowerMind observation contains no legal build sites")
        after = adapter.apply_actions(
            [Action(type="build", tower="archer", position=initial.build_sites[0])]
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "wave": after.wave,
                    "base_hp": after.base_hp,
                    "gold": after.gold,
                    "built_towers": [
                        {
                            "id": tower.id,
                            "kind": tower.kind,
                            "position": tower.position,
                            "level": tower.level,
                        }
                        for tower in after.towers
                    ],
                    "tower_sites": after.build_sites,
                    "observation_keys": sorted(adapter.raw),
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        if args.transition == "success":
            adapter.publish_transition(
                "success",
                "YOU DID IT!",
                "第 1 关通关 · 下一关：地图 1",
            )
            print("transition published: success", flush=True)
        elif args.transition == "failure":
            adapter.publish_transition(
                "failure",
                "YOU FAILED",
                "止步第 3 关 · 可选择再试一次或停止",
                can_retry=True,
            )
            print("transition published: failure", flush=True)
        if args.transition:
            adapter.pump_transition_frame()
            print("transition frame pumped", flush=True)
        if args.hold_seconds > 0 and args.transition:
            deadline = monotonic() + args.hold_seconds
            while monotonic() < deadline:
                adapter.pump_transition_frame()
                action = adapter.transition_action()
                if action:
                    print(f"transition action: {action}", flush=True)
                    break
                sleep(0.1)
        elif args.hold_seconds > 0:
            sleep(args.hold_seconds)
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
