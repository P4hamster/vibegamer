#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from math import dist
from pathlib import Path
from typing import Any

from tower_referee.game.towermind import TowerMindAdapter


def path_length(points: list[tuple[float, float]]) -> float:
    return round(sum(dist(a, b) for a, b in zip(points, points[1:])), 3)


def static_profiles(config_dir: Path) -> list[dict[str, Any]]:
    levels = json.loads(
        (config_dir / "BenchmarkLevelsConfig.json").read_text(encoding="utf-8-sig")
    )["Levels"]
    waves = {
        int(item["ID"]): item
        for item in json.loads(
            (config_dir / "AllWavesConfig.json").read_text(encoding="utf-8-sig")
        )["Waves"]
    }
    enemies = json.loads(
        (config_dir / "AllEnemiesConfig.json").read_text(encoding="utf-8-sig")
    )["Enemies"]
    profiles = []
    for level in levels:
        enemy_ids = [
            enemy_id
            for wave_id in level["Waves"]
            for enemy_id in waves[int(wave_id)]["Enemies"]
        ]
        conventional_hp = sum(
            int(enemies[enemy_id]["Health"])
            for enemy_id in enemy_ids
            if enemies[enemy_id]["Name"] != "Hill King"
        )
        profiles.append(
            {
                "map_id": str(level["ID"]),
                "prefab": level["FilePath"],
                "preview": level["PicFilePath"],
                "initial_gold": int(level["InitialMoney"]),
                "coin_value": int(level["GoldCoinsValue"]),
                "sell_refund_ratio": float(level["TowerSellingDiscount"]),
                "enemy_count": len(enemy_ids),
                "conventional_enemy_hp": conventional_hp,
                "flying_count": sum(
                    enemies[enemy_id]["MovementType"] == "Flying"
                    for enemy_id in enemy_ids
                ),
                "hill_king_count": sum(
                    enemies[enemy_id]["Name"] == "Hill King"
                    for enemy_id in enemy_ids
                ),
                "enemy_types": sorted(
                    {enemies[enemy_id]["Name"] for enemy_id in enemy_ids}
                ),
            }
        )
    return profiles


def add_runtime_geometry(
    profiles: list[dict[str, Any]],
    app: Path,
    screen_width: int,
    screen_height: int,
    persistent: bool = False,
) -> None:
    adapter = None
    try:
        for profile in profiles:
            if adapter is None or not persistent:
                adapter = TowerMindAdapter(
                    app,
                    "vendor/TowerMind",
                    time_scale=20,
                    screen_width=screen_width,
                    screen_height=screen_height,
                )
            state = adapter.reset(profile["map_id"], seed=0, max_waves=5)
            lengths = [path_length(path) for path in state.enemy_paths]
            profile["path_count"] = len(state.enemy_paths)
            profile["path_lengths"] = lengths
            profile["shortest_path_length"] = min(lengths) if lengths else 0
            profile["build_site_count"] = len(state.build_sites)
            profile["build_sites"] = [
                [round(x, 3), round(y, 3)] for x, y in state.build_sites
            ]
            if not persistent:
                adapter.close()
                adapter = None
    finally:
        if adapter is not None:
            adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit all five official maps without calling an LLM"
    )
    parser.add_argument(
        "--app",
        default="vendor/TowerMind/plugin_runtime/mac_apple_silicon/td.app",
    )
    parser.add_argument("--runtime", action="store_true")
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Reuse one Unity process while switching through all maps",
    )
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument(
        "--output",
        default="artifacts/towermind-map-calibration.json",
    )
    args = parser.parse_args()
    app = Path(args.app)
    config_dir = (
        app
        / "Contents/Resources/Data/StreamingAssets/Config"
    )
    profiles = static_profiles(config_dir)
    if args.runtime:
        add_runtime_geometry(
            profiles,
            app,
            args.width,
            args.height,
            persistent=args.persistent,
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(profiles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(profiles, ensure_ascii=False, indent=2))
    print(f"report: {output.resolve()}")


if __name__ == "__main__":
    main()
