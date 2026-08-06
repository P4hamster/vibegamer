import json

from tower_referee.config import ExperimentConfig
from tower_referee.runner import ExperimentRunner


def test_three_round_simulation_outputs_audit_files(tmp_path):
    config_data = json.loads(
        open("configs/experiment.example.json", encoding="utf-8").read()
    )
    config_data["experiment_id"] = "e2e"
    config_data["max_waves"] = 3
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_data), encoding="utf-8")
    config = ExperimentConfig.load(config_path)
    dashboard = ExperimentRunner(config, tmp_path).run()

    root = tmp_path / "e2e"
    assert dashboard.exists()
    assert (root / "events.jsonl").exists()
    assert (root / "manifest.json").exists()
    summaries = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    assert len(summaries) == 18
    assert {item["round_id"] for item in summaries} == {1, 2, 3}
    assert all(item["trial_id"] for item in summaries)
    assert all(item["harness_version"] == "2.0" for item in summaries)
    events = (root / "events.jsonl").read_text(encoding="utf-8")
    assert '"event_type": "private_review"' in events
