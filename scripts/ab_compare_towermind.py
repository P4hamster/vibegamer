from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tower_referee.game.towermind import TowerMindAdapter
from tower_referee.schema import Action, Decision, StandingOrders


def compact_state(state) -> dict[str, Any]:
    return {
        "wave": state.wave,
        "base_hp": state.base_hp,
        "gold": state.gold,
        "game_step": state.game_step,
        "sites": [[round(x, 3), round(y, 3)] for x, y in state.build_sites],
        "towers": [
            {
                "id": tower.id,
                "kind": tower.kind,
                "position": [
                    round(tower.position[0], 3),
                    round(tower.position[1], 3),
                ],
                "level": tower.level,
            }
            for tower in state.towers
        ],
        "done": state.done,
        "won": state.won,
    }


def scripted_actions(state) -> list[Action]:
    if len(state.build_sites) < 3:
        raise RuntimeError(
            f"A/B map requires at least three sites, got {len(state.build_sites)}"
        )
    return [
        Action(type="build", tower="knight", position=state.build_sites[0]),
        Action(type="build", tower="magician", position=state.build_sites[1]),
        Action(type="build", tower="archer", position=state.build_sites[2]),
    ]


def scripted_orders(state) -> StandingOrders:
    path = state.enemy_paths[0]
    entrance = path[0]
    middle = path[len(path) // 2]
    exit_point = path[-2] if len(path) >= 2 else path[-1]
    return StandingOrders(
        hero_anchor=exit_point,
        hero_retreat_position=middle,
        hero_retreat_below_hp=350,
        collect_gold=True,
        knight_block_point=middle,
        reinforcement_point=entrance,
        use_hero_skill_when_enemy_count=5,
        hero_skill_min_hp=700,
    )


def run_one(
    label: str,
    executable: str,
    plugin_url: str | None,
    map_id: str,
    time_scale: float,
    worker_id: int,
) -> dict[str, Any]:
    adapter = TowerMindAdapter(
        executable,
        "vendor/TowerMind",
        time_scale=time_scale,
        plugin_url=plugin_url,
        plugin_required=plugin_url is not None,
        worker_id=worker_id,
    )
    trace: list[dict[str, Any]] = []
    try:
        state = adapter.reset(map_id, seed=20260724, max_waves=5)
        trace.append({"point": "initial", "state": compact_state(state)})
        actions = scripted_actions(state)
        orders = scripted_orders(state)
        adapter.publish_decision(
            "A/B 固定脚本",
            Decision(
                analysis_summary="使用完全相同的三塔布阵验证插件是否改变战局",
                actions=actions,
                standing_orders=orders,
            ),
            actions,
            [],
        )
        adapter.set_standing_orders(orders)
        state = adapter.apply_actions(actions)
        trace.append({"point": "after_builds", "state": compact_state(state)})

        segment = 0
        while not state.done and segment < 30:
            state, events, result = adapter.advance_until_event(600)
            segment += 1
            trace.append(
                {
                    "point": f"segment_{segment:02}",
                    "events": [asdict(event) for event in events],
                    "result": asdict(result),
                    "state": compact_state(state),
                }
            )
        if not state.done:
            raise TimeoutError(f"{label} did not finish within 30 monitor segments")
        return {
            "label": label,
            "trace": trace,
            "final": compact_state(state),
        }
    finally:
        adapter.close()


def comparable(result: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for item in result["trace"]:
        state = dict(item["state"])
        # Wall-clock-independent observer data is intentionally not compared.
        output.append(
            {
                "point": item["point"],
                "wave": state["wave"],
                "base_hp": state["base_hp"],
                "gold": state["gold"],
                "game_step": state["game_step"],
                "sites": state["sites"],
                "towers": state["towers"],
                "done": state["done"],
                "won": state["won"],
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", default="0", dest="map_id")
    parser.add_argument("--time-scale", type=float, default=20.0)
    parser.add_argument("--output", default="artifacts/plugin-ab.json")
    parser.add_argument(
        "--original",
        default=(
            "vendor/TowerMind/extracted/mac_apple_silicon/"
            "mac_apple_silicon/mac_apple_silicon/td.app"
        ),
    )
    parser.add_argument(
        "--patched",
        default="vendor/TowerMind/plugin_runtime/mac_apple_silicon/td.app",
    )
    args = parser.parse_args()

    original = run_one(
        "original", args.original, None, args.map_id, args.time_scale, 0
    )
    patched = run_one(
        "plugin",
        args.patched,
        "http://127.0.0.1:17871",
        args.map_id,
        args.time_scale,
        1,
    )
    original_trace = comparable(original)
    patched_trace = comparable(patched)
    exact_match = original_trace == patched_trace
    payload = {
        "schema_version": "1.0",
        "map_id": args.map_id,
        "script": "three fixed towers plus identical local standing orders",
        "exact_match": exact_match,
        "original": original,
        "plugin": patched,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "exact_match": exact_match,
                "original_final": original["final"],
                "plugin_final": patched["final"],
                "report": str(output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not exact_match:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
