import os

from tower_referee.cli import build_parser, load_local_env


def test_load_local_env_without_overwriting_shell_value(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "EXISTING_KEY=from-file\nNEW_TEST_KEY='loaded-value'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING_KEY", "from-shell")
    monkeypatch.delenv("NEW_TEST_KEY", raising=False)

    load_local_env(env_file)

    assert os.environ["EXISTING_KEY"] == "from-shell"
    assert os.environ["NEW_TEST_KEY"] == "loaded-value"


def test_load_local_env_maps_ark_key_for_litellm(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ARK_API_KEY=test-ark-key\n", encoding="utf-8")
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_API_KEY", raising=False)

    load_local_env(env_file)

    assert os.environ["VOLCENGINE_API_KEY"] == "test-ark-key"


def test_smoke_parser_accepts_decision_budget_override():
    args = build_parser().parse_args(
        ["smoke", "--model", "DeepSeek", "--max-decisions", "50"]
    )

    assert args.max_decisions == 50
