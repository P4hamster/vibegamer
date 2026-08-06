import json

import pytest

from tower_referee.config import ExperimentConfig


def test_config_requires_six_models(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "experiment_id": "x",
                "backend": "sim",
                "runs_per_round": 1,
                "seed": 1,
                "fixed_map": "river_gate",
                "unseen_map": "fog_crossroads",
                "max_waves": 2,
                "models": [
                    {"name": "one", "provider": "rule", "model": "balanced"}
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="six"):
        ExperimentConfig.load(path)


def test_example_config_loads():
    config = ExperimentConfig.load("configs/experiment.example.json")
    assert config.backend == "sim"
    assert len(config.models) == 6
