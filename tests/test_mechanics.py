from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_mechanics import generate


def test_mechanics_exposes_rules_but_not_future_waves(tmp_path: Path) -> None:
    fixtures = {
        "TowerConfig.json": {
            "Towers": [
                {
                    "Type": 3,
                    "Name": "Archer Tower",
                    "Price": 120,
                    "UpgradePrice": 120,
                    "UpgradeGrowth": 1.4,
                    "AttackSpeed": 0.8,
                    "AttackDamage": 100,
                    "AttackExtraDamage": 50,
                    "AttackRange": 3,
                    "CanAttackAir": True,
                    "CanAttackGround": True,
                    "Description": "single target",
                }
            ]
        },
        "AllEnemiesConfig.json": {
            "Enemies": [
                {
                    "Type": 2,
                    "Name": "Bat",
                    "Health": 550,
                    "MovementSpeed": 0.8,
                    "AttackSpeed": 0.8,
                    "AttackDamage": 0,
                    "AttackExtraDamage": 0,
                    "MovementType": "Flying",
                    "Description": "fast air unit",
                }
            ]
        },
        "HeroConfig.json": {
            "Health": 1600,
            "MovementSpeed": 0.9,
            "AttackSpeed": 0.7,
            "AttackDamage": 200,
            "AttackExtraDamage": 150,
            "AttackRange": 1,
            "RecoverHealthPerSec": 50,
            "ReviveTime": 10,
            "UpgradeGoldCoinCost": 500,
            "UpgradeHealthGrowthValue": 200,
            "Description": "hero",
            "SkillAttackDamage": 100,
            "SkillAttackExtraDamage": 100,
            "SkillCostHealth": 100,
            "SkillLastTime": 5,
            "SkillAttackRange": 0.5,
            "SkillDescription": "fire",
        },
        "KnightConfig.json": {
            "Health": 600,
            "MovementSpeed": 0.6,
            "AttackSpeed": 0.7,
            "AttackDamage": 150,
            "AttackExtraDamage": 50,
            "AttackRange": 1,
            "FFCompensationValue": 50,
            "FFCompensationProbability": 1,
        },
        "KnightReinforcementsConfig.json": {
            "Number": 2,
            "ExistTime": 10,
            "Description": "temporary squad",
        },
        "EnvConfig.json": {"Version": "1.0.0"},
    }
    for name, data in fixtures.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")

    mechanics = generate(tmp_path)
    encoded = json.dumps(mechanics).lower()

    assert mechanics["towers"][0]["id"] == "archer"
    assert mechanics["enemy_archetypes"][0]["movement_type"] == "Flying"
    assert "Archer Tower" in mechanics["air_combat"][
        "flying_enemies_can_be_damaged_by"
    ]
    assert mechanics["air_combat"]["flying_enemies_can_be_blocked"] is False
    assert mechanics["status_effects"]["tower_freeze"][
        "tower_is_not_destroyed"
    ] is True
    assert "Fire of Rage" in mechanics["status_effects"]["moving_cloud_fog"][
        "reveal_rule"
    ]
    assert "wave composition" in mechanics["source"]["policy"]
    assert "allwaves" not in encoded
    assert "spawn_order" not in encoded
    assert "future_waves" not in encoded
