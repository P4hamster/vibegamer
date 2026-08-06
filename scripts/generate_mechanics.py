from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = (
    PROJECT_ROOT
    / "vendor/TowerMind/extracted/mac_apple_silicon/mac_apple_silicon"
    / "mac_apple_silicon/td.app/Contents/Resources/Data/StreamingAssets/Config"
)


def load_json(config_dir: Path, filename: str) -> dict[str, Any]:
    return json.loads((config_dir / filename).read_text(encoding="utf-8"))


def generate(config_dir: Path) -> dict[str, Any]:
    towers = load_json(config_dir, "TowerConfig.json")["Towers"]
    enemies = load_json(config_dir, "AllEnemiesConfig.json")["Enemies"]
    hero = load_json(config_dir, "HeroConfig.json")
    knight = load_json(config_dir, "KnightConfig.json")
    reinforcements = load_json(config_dir, "KnightReinforcementsConfig.json")
    environment = load_json(config_dir, "EnvConfig.json")

    return {
        "schema_version": "1.0",
        "source": {
            "game": "TowerMind",
            "game_config_version": environment.get("Version", "unknown"),
            "policy": (
                "Only public mechanics are included. Exact future wave composition "
                "and spawn order are intentionally excluded."
            ),
        },
        "objective": {
            "victory": "Complete all waves with base health above zero.",
            "failure": "Base health reaches zero.",
            "leak_cost": "Each enemy reaching the destination removes 1 base health.",
            "priority": [
                "complete more waves",
                "preserve base health",
                "use gold efficiently",
                "avoid invalid actions",
            ],
        },
        "towers": [
            {
                "id": {1: "knight", 2: "magician", 3: "archer"}[tower["Type"]],
                "official_name": tower["Name"],
                "price": tower["Price"],
                "upgrade_price": tower["UpgradePrice"],
                "upgrade_growth": tower["UpgradeGrowth"],
                "attack_interval_seconds": tower["AttackSpeed"],
                "base_damage": tower["AttackDamage"],
                "extra_random_damage": tower["AttackExtraDamage"],
                "range_diameter": tower["AttackRange"],
                "can_attack_air": tower["CanAttackAir"],
                "can_attack_ground": tower["CanAttackGround"],
                "description": tower["Description"],
            }
            for tower in towers
        ],
        "hero": {
            "health": hero["Health"],
            "movement_speed": hero["MovementSpeed"],
            "attack_interval_seconds": hero["AttackSpeed"],
            "base_damage": hero["AttackDamage"],
            "extra_random_damage": hero["AttackExtraDamage"],
            "range_diameter": hero["AttackRange"],
            "health_recovery_per_second": hero["RecoverHealthPerSec"],
            "revive_seconds": hero["ReviveTime"],
            "upgrade_gold": hero["UpgradeGoldCoinCost"],
            "upgrade_health_gain": hero["UpgradeHealthGrowthValue"],
            "description": hero["Description"],
            "skill": {
                "name": "Fire of Rage",
                "base_damage": hero["SkillAttackDamage"],
                "extra_random_damage": hero["SkillAttackExtraDamage"],
                "health_cost": hero["SkillCostHealth"],
                "duration_seconds": hero["SkillLastTime"],
                "range_diameter": hero["SkillAttackRange"],
                "description": hero["SkillDescription"],
            },
        },
        "air_combat": {
            "flying_enemies_can_be_damaged_by": [
                "Archer Tower",
                "Hero automatic fireball",
            ],
            "flying_enemies_cannot_be_damaged_by": [
                "Magician Tower",
                "Knights",
                "Knight reinforcements",
                "Hero Fire of Rage active skill",
            ],
            "flying_enemies_can_be_blocked": False,
            "hero_automatic_fireball_condition": (
                "The hero can auto-target a flying enemy only while alive, "
                "stationary, not following a movement path, and not occupied "
                "by a ground target."
            ),
        },
        "status_effects": {
            "tower_freeze": {
                "effect": "A frozen tower cannot attack.",
                "duration": (
                    "Temporary: it clears automatically after the freezing "
                    "Wizard or Bone Chanter is no longer in the tower's range."
                ),
                "tower_is_not_destroyed": True,
            },
            "moving_cloud_fog": {
                "effect": (
                    "Covered heroes, enemies, knights, coins, and towers are "
                    "hidden from the official observation. A covered tower "
                    "remains owned but cannot attack."
                ),
                "reveal_rule": (
                    "A Hero Fire of Rage burning zone overlapping the cloud "
                    "temporarily illuminates it and reveals covered objects."
                ),
                "observer_fields": {
                    "under_fog": "True when a remembered own tower is cloud-covered.",
                    "operational": (
                        "False when an own tower is frozen or cloud-covered."
                    ),
                },
            },
        },
        "knights": {
            "health": knight["Health"],
            "movement_speed": knight["MovementSpeed"],
            "attack_interval_seconds": knight["AttackSpeed"],
            "base_damage": knight["AttackDamage"],
            "extra_random_damage": knight["AttackExtraDamage"],
            "range_diameter": knight["AttackRange"],
            "friendly_fire_compensation_gold": knight["FFCompensationValue"],
            "friendly_fire_compensation_probability": knight[
                "FFCompensationProbability"
            ],
            "reinforcements": {
                "count": reinforcements["Number"],
                "lifetime_seconds": reinforcements["ExistTime"],
                "description": reinforcements["Description"],
            },
        },
        "enemy_archetypes": [
            {
                "type": enemy["Type"],
                "name": enemy["Name"],
                "health": enemy["Health"],
                "movement_speed": enemy["MovementSpeed"],
                "attack_interval_seconds": enemy["AttackSpeed"],
                "base_damage": enemy["AttackDamage"],
                "extra_random_damage": enemy["AttackExtraDamage"],
                "movement_type": enemy["MovementType"],
                "description": enemy["Description"],
            }
            for enemy in enemies
        ],
        "semantic_actions": {
            "build": {"required": ["site_id", "tower"]},
            "upgrade": {"required": ["site_id"]},
            "sell": {"required": ["site_id"]},
            "show_range": {"required": ["site_id"]},
            "relocate_knights": {"required": ["site_id", "position"]},
            "deploy_reinforcements": {"required": ["position"]},
            "move_hero": {"required": ["position"]},
            "hero_skill": {"required": []},
            "upgrade_hero": {"required": []},
            "noop": {"required": []},
        },
        "observer_contract": {
            "site_id": "Stable build-slot ID within a map/run.",
            "path_progress": "0.0 at entrance and 1.0 at destination.",
            "objective_zone": "Geometric entrance/middle/exit third; not a recommendation.",
            "path_coverage": "Whether each tower type's official radius intersects each path.",
            "estimated_seconds_to_base": (
                "Path distance divided by official movement speed; ignores blocking/combat."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate public TowerMind mechanics without leaking future waves."
    )
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "plugin/generated/mechanics.json",
    )
    args = parser.parse_args()
    payload = generate(args.config_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
