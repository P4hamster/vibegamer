import pytest
import sys
import json
from types import SimpleNamespace

from tower_referee.config import ModelConfig
from tower_referee.models import (
    AFFORDABILITY_PREFLIGHT_V1,
    CONCISE_REASONING_POLICY_V1,
    LiteLLMModelAdapter,
    THREAT_TRADEOFF_PREFLIGHT_V1,
    TIMELINE_PROJECTION_V1,
    TARGET_LOCK_LEDGER_V1,
    compact_battlefield,
    parse_decision,
)


def test_all_llm_adapters_receive_the_concise_reasoning_policy():
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="Test", provider="litellm", model="provider/test")
    )

    assert adapter.system_prompt.endswith(CONCISE_REASONING_POLICY_V1)
    assert "1000 个字符以内" in adapter.system_prompt
    assert "优先完整输出最终行动 JSON" in adapter.system_prompt


def test_parse_structured_decision():
    decision = parse_decision(
        '{"analysis_summary":"守路口","actions":[{"type":"build","tower":"archer","position":[2,1]}],'
        '"cancel_pending_plans":true,"reserve_gold":100}'
    )
    assert decision.actions[0].position == (2, 1)
    assert decision.reserve_gold == 100
    assert decision.cancel_pending_plans is True


def test_parse_standing_orders():
    decision = parse_decision(
        '{"analysis_summary":"持续守口","actions":[],"standing_orders":'
        '{"hero_anchor":[1.9,-0.4],"collect_gold":true,'
        '"collect_gold_radius_from_anchor":0.8,'
        '"knight_block_point":[1.8,0.7],"use_hero_skill_when_enemy_count":5}}'
    )
    assert decision.standing_orders is not None
    assert decision.standing_orders.hero_anchor == (1.9, -0.4)
    assert decision.standing_orders.collect_gold_radius_from_anchor == 0.8
    assert decision.standing_orders.knight_block_point == (1.8, 0.7)


def test_parse_normalizes_documented_tower_labels():
    decision = parse_decision(
        '{"actions":[{"type":"build","tower":"Knight Tower","position":[1,1]}]}'
    )
    assert decision.actions[0].tower == "knight"


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError):
        parse_decision("not json")


def test_claude_can_omit_temperature():
    adapter = LiteLLMModelAdapter(
        ModelConfig(
            name="Claude",
            provider="litellm",
            model="anthropic/claude-opus-4-8",
            omit_temperature=True,
        )
    )
    assert adapter.omit_temperature is True


def test_reasoning_effort_is_kept_in_request_profile():
    adapter = LiteLLMModelAdapter(
        ModelConfig(
            name="GPT",
            provider="litellm",
            model="openai/gpt-5.6-sol",
            reasoning_effort="medium",
        )
    )
    assert adapter.reasoning_effort == "medium"


def test_model_request_timeout_and_retries_are_explicit():
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="DeepSeek", provider="litellm", model="deepseek/test"),
        request_timeout=12,
        request_retries=1,
    )

    assert adapter.request_timeout == 12
    assert adapter.request_retries == 1


def test_openai_compatible_model_uses_its_configured_key_environment(monkeypatch):
    calls = []

    class Message:
        content = '{"actions":[{"type":"noop"}]}'

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="response-qwen-1",
            model="qwen3.8-max",
            system_fingerprint=None,
            choices=[SimpleNamespace(message=Message(), finish_reason="stop")],
        )

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-qwen-key")
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(
            name="Qwen3.8-Max",
            provider="litellm",
            model="openai/qwen3.8-max",
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key_env="DASHSCOPE_API_KEY",
        )
    )

    adapter.decide(SimpleNamespace(public_dict=lambda _fog: {"wave": 0}))

    assert calls[0]["api_base"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert calls[0]["api_key"] == "test-qwen-key"


def test_provider_seed_is_added_to_request_and_audited(monkeypatch):
    calls = []

    class Message:
        content = '{"actions":[{"type":"noop"}]}'

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="response-1",
            model="deepseek-v4-flash",
            system_fingerprint="fp-test",
            choices=[SimpleNamespace(message=Message(), finish_reason="stop")],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(
            name="DeepSeek",
            provider="litellm",
            model="deepseek/test",
        ),
        provider_seed=100,
    )

    decision = adapter.decide(
        SimpleNamespace(public_dict=lambda _fog: {"wave": 0}),
    )

    assert calls[0]["seed"] == 100
    assert decision.request_trace[0]["requested_seed"] == 100
    assert decision.request_trace[0]["system_fingerprint"] == "fp-test"
    assert decision.request_trace[0]["reasoning_content"] is None
    assert decision.request_trace[0]["reasoning_content_complete"] is True


def test_non_streaming_reasoning_content_is_audited(monkeypatch):
    class Message:
        content = '{"actions":[{"type":"noop"}]}'
        reasoning_content = "先比较当前威胁，再决定等待。"

    def fake_completion(**kwargs):
        return SimpleNamespace(
            id="response-reasoning-1",
            model="reasoning-model",
            system_fingerprint="fp-reasoning",
            choices=[SimpleNamespace(message=Message(), finish_reason="stop")],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="Reasoner", provider="litellm", model="provider/reasoner")
    )
    decision = adapter.decide(SimpleNamespace(public_dict=lambda _fog: {"wave": 0}))

    trace = decision.request_trace[0]
    assert trace["reasoning_content"] == "先比较当前威胁，再决定等待。"
    assert trace["reasoning_content_chars"] == len(trace["reasoning_content"])
    assert trace["reasoning_content_complete"] is True


def test_length_truncation_does_not_spend_a_second_request(monkeypatch):
    calls = []

    class Message:
        content = ""
        reasoning_content = "未完成的长思考"

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="response-truncated-1",
            model="reasoning-model",
            system_fingerprint="fp-truncated",
            choices=[SimpleNamespace(message=Message(), finish_reason="length")],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="Reasoner", provider="litellm", model="provider/reasoner")
    )

    decision = adapter.decide(SimpleNamespace(public_dict=lambda _fog: {"wave": 0}))

    assert len(calls) == 1
    assert decision.parse_status == "repair_failed"
    assert decision.parse_error_type == "OutputTruncated"
    assert decision.repair_attempted is False
    assert len(decision.request_trace) == 1
    assert decision.request_trace[0]["finish_reason"] == "length"


def test_two_phase_pipeline_keeps_high_planning_and_disables_action_thinking(
    monkeypatch,
):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            message = SimpleNamespace(
                content="",
                reasoning_content="先完整比较防线，再选择弓箭塔。",
            )
            finish_reason = "length"
        else:
            message = SimpleNamespace(
                content='{"analysis_summary":"补充对空","actions":[{"type":"noop"}]}',
                reasoning_content=None,
            )
            finish_reason = "stop"
        return SimpleNamespace(
            id=f"response-{len(calls)}",
            model="deepseek-v4-flash",
            system_fingerprint=None,
            choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(
            name="DeepSeek",
            provider="litellm",
            model="deepseek/deepseek-v4-flash",
            omit_temperature=True,
            reasoning_effort="high",
            decision_pipeline="plan_then_action",
            planning_max_tokens=8192,
            action_max_tokens=2048,
            planning_request_params={
                "stream": False,
                "extra_body": {"thinking": {"type": "enabled"}},
            },
            action_request_params={
                "stream": False,
                "response_format": {"type": "json_object"},
                "extra_body": {"thinking": {"type": "disabled"}},
            },
        )
    )

    decision = adapter.decide(
        SimpleNamespace(public_dict=lambda _fog: {"wave": 2, "gold": 120})
    )

    assert len(calls) == 2
    assert calls[0]["reasoning_effort"] == "high"
    assert calls[0]["max_tokens"] == 8192
    assert calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "response_format" not in calls[0]
    assert "reasoning_effort" not in calls[1]
    assert calls[1]["max_tokens"] == 2048
    assert calls[1]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert calls[1]["response_format"] == {"type": "json_object"}
    assert "先完整比较防线" in calls[1]["messages"][1]["content"]
    assert decision.parse_status == "valid"
    assert [item["phase"] for item in decision.request_trace] == [
        "planning",
        "action",
    ]
    assert decision.request_trace[0]["finish_reason"] == "length"
    assert decision.request_trace[0]["reasoning_effort"] == "high"
    assert decision.request_trace[1]["reasoning_effort"] is None


def test_compact_battlefield_keeps_dynamic_fields_and_removes_rule_duplication():
    public = {
        "wave": 2,
        "gold": 240,
        "towers": [{"id": "t1", "kind": "archer", "under_fog": False}],
        "visible_enemies": [
            {"id": "e1", "kind": "Demon Bat", "hp": 550, "description": "x" * 500}
        ],
        "available_actions": ["build", "noop"],
        "site_insights": [{"site_id": "s1", "position": [1, 2]}],
        "threat_summary": {"visible_flying_count": 1},
        "previous_wave_summary": {"pending_plans": []},
        "observer_meta": {"connected": True, "scene": "long-scene-name"},
        "game_rules": {
            "objective": "duplicate",
            "tower_types": [{"name": "duplicate", "description": "x" * 500}],
            "hero": {"Description": "duplicate"},
            "sell_refund_ratio": 0.5,
            "public_mechanics": {
                "schema_version": "1.0",
                "source": {"policy": "x" * 500},
                "observer_contract": {"description": "x" * 500},
                "semantic_actions": {"build": "x" * 500},
                "objective": {"victory": "survive"},
                "towers": [{"id": "archer", "price": 120, "description": "x" * 500}],
                "hero": {"health": 1600, "description": "x" * 500},
                "enemy_archetypes": [
                    {"name": "Demon Bat", "health": 550, "description": "x" * 500}
                ],
            },
        },
    }

    compact = compact_battlefield(public)

    assert compact["wave"] == 2
    assert compact["gold"] == 240
    assert compact["towers"] == public["towers"]
    assert compact["visible_enemies"][0]["hp"] == 550
    assert compact["available_actions"] == ["build", "noop"]
    assert compact["site_insights"] == public["site_insights"]
    assert compact["threat_summary"] == public["threat_summary"]
    assert compact["previous_wave_summary"] == public["previous_wave_summary"]
    assert compact["game_rules"]["sell_refund_ratio"] == 0.5
    assert "tower_types" not in compact["game_rules"]
    assert "description" not in compact["visible_enemies"][0]
    assert compact["observer_meta"] == {"connected": True}
    assert len(json.dumps(compact)) < len(json.dumps(public)) * 0.4


def test_provider_seed_sequence_can_resume_after_import(monkeypatch):
    calls = []

    class Message:
        content = '{"actions":[{"type":"noop"}]}'

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="response-resumed",
            model="kimi-k3",
            system_fingerprint="fp-resumed",
            choices=[SimpleNamespace(message=Message(), finish_reason="stop")],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="Kimi", provider="litellm", model="moonshot/kimi-k3"),
        provider_seed=100,
    )
    adapter.restore_request_index(12)

    adapter.decide(SimpleNamespace(public_dict=lambda _fog: {"wave": 0}))

    assert calls[0]["seed"] == 112


def test_provider_seed_best_effort_falls_back_when_provider_rejects(monkeypatch):
    calls = []

    class Message:
        content = '{"actions":[{"type":"noop"}]}'

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if "seed" in kwargs:
            raise RuntimeError("unsupported seed parameter")
        return SimpleNamespace(
            id="response-2",
            model="provider-model",
            system_fingerprint="fp-test",
            choices=[SimpleNamespace(message=Message(), finish_reason="stop")],
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="Only", provider="litellm", model="provider/test"),
        provider_seed=7,
    )

    decision = adapter.decide(
        SimpleNamespace(public_dict=lambda _fog: {"wave": 0}),
    )

    assert len(calls) == 2
    assert "seed" not in calls[1]
    assert decision.request_trace[0]["seed_status"] == "rejected_fallback"


def test_streaming_response_is_aggregated_and_audited(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return iter(
            [
                SimpleNamespace(
                    id="response-stream-1",
                    model="kimi-k3",
                    system_fingerprint="fp-stream",
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                reasoning_content="先分析",
                                content=None,
                            ),
                            finish_reason=None,
                        )
                    ],
                ),
                SimpleNamespace(
                    id="response-stream-1",
                    model="kimi-k3",
                    system_fingerprint="fp-stream",
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                reasoning_content=None,
                                content='{"actions":[',
                            ),
                            finish_reason=None,
                        )
                    ],
                ),
                SimpleNamespace(
                    id="response-stream-1",
                    model="kimi-k3",
                    system_fingerprint="fp-stream",
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                reasoning_content=None,
                                content='{"type":"noop"}]}',
                            ),
                            finish_reason="stop",
                        )
                    ],
                ),
            ]
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(
        ModelConfig(
            name="Kimi",
            provider="litellm",
            model="moonshot/kimi-k3",
            request_params={"stream": True},
        )
    )

    decision = adapter.decide(
        SimpleNamespace(public_dict=lambda _fog: {"wave": 0}),
    )

    assert calls[0]["stream"] is True
    assert decision.actions[0].type == "noop"
    assert decision.request_trace[0]["stream"] is True
    assert decision.request_trace[0]["finish_reason"] == "stop"
    assert decision.request_trace[0]["response_id"] == "response-stream-1"
    assert decision.request_trace[0]["reasoning_content"] == "先分析"
    assert decision.request_trace[0]["reasoning_content_complete"] is True


def test_minimax_streaming_reasoning_details_are_aggregated(monkeypatch):
    def fake_completion(**_kwargs):
        return iter(
            [
                {
                    "id": "response-minimax-stream-1",
                    "model": "MiniMax-M3",
                    "choices": [{
                        "delta": {
                            "reasoning_details": [
                                {"type": "reasoning.text", "text": "先看金币，"},
                                {"type": "reasoning.text", "text": "再看路线。"},
                            ]
                        },
                        "finish_reason": None,
                    }],
                },
                {
                    "id": "response-minimax-stream-1",
                    "model": "MiniMax-M3",
                    "choices": [{
                        "delta": {"content": '{"actions":[{"type":"noop"}]}'},
                        "finish_reason": "stop",
                    }],
                },
            ]
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    adapter = LiteLLMModelAdapter(ModelConfig(
        name="MiniMax",
        provider="litellm",
        model="openai/MiniMax-M3",
        request_params={"stream": True},
    ))

    decision = adapter.decide(SimpleNamespace(public_dict=lambda _fog: {"wave": 0}))

    trace = decision.request_trace[0]
    assert decision.actions[0].type == "noop"
    assert trace["response_model"] == "MiniMax-M3"
    assert trace["reasoning_content"] == "先看金币，再看路线。"
    assert trace["reasoning_content_chars"] == len("先看金币，再看路线。")


def test_partial_streaming_reasoning_is_preserved_on_failure(monkeypatch):
    def broken_stream():
        yield SimpleNamespace(
            id="response-stream-broken",
            model="kimi-k3",
            system_fingerprint="fp-stream",
            choices=[SimpleNamespace(
                delta=SimpleNamespace(reasoning_content="已收到的思考", content=None),
                finish_reason=None,
            )],
        )
        raise ConnectionError("stream disconnected")

    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(completion=lambda **_kwargs: broken_stream())
    )
    adapter = LiteLLMModelAdapter(ModelConfig(
        name="Kimi",
        provider="litellm",
        model="moonshot/kimi-k3",
        request_params={"stream": True},
    ))

    with pytest.raises(ConnectionError, match="stream disconnected"):
        adapter.decide(SimpleNamespace(public_dict=lambda _fog: {"wave": 0}))

    assert adapter.last_request_metadata["reasoning_content"] == "已收到的思考"
    assert adapter.last_request_metadata["reasoning_content_complete"] is False


def test_affordability_scaffold_is_a_prompt_only_addendum():
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="DeepSeek", provider="litellm", model="deepseek/test"),
        system_prompt_suffix=AFFORDABILITY_PREFLIGHT_V1,
    )
    assert adapter.system_prompt.endswith(AFFORDABILITY_PREFLIGHT_V1)
    assert "不提供塔型、塔位或威胁权衡建议" in adapter.system_prompt


def test_threat_tradeoff_scaffold_does_not_contain_a_prescribed_tower():
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="DeepSeek", provider="litellm", model="deepseek/test"),
        system_prompt_suffix=THREAT_TRADEOFF_PREFLIGHT_V1,
    )
    assert adapter.system_prompt.endswith(THREAT_TRADEOFF_PREFLIGHT_V1)
    assert "不提供候选的战斗结果、塔型、塔位" in adapter.system_prompt


def test_timeline_scaffold_requires_reasoning_without_prescribing_a_choice():
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="DeepSeek", provider="litellm", model="deepseek/test"),
        system_prompt_suffix=TIMELINE_PROJECTION_V1,
    )
    assert adapter.system_prompt.endswith(TIMELINE_PROJECTION_V1)
    assert "不新增候选、不推荐塔型或塔位，也不提供模拟答案" in adapter.system_prompt
    assert "仅当当前有可见敌人且 game_rules.tower_combat 已公开时" in adapter.system_prompt


def test_target_lock_ledger_scaffold_has_no_tower_or_result_hint():
    adapter = LiteLLMModelAdapter(
        ModelConfig(name="DeepSeek", provider="litellm", model="deepseek/test"),
        system_prompt_suffix=TARGET_LOCK_LEDGER_V1,
    )
    assert adapter.system_prompt.endswith(TARGET_LOCK_LEDGER_V1)
    assert "不新增候选、不推荐塔型或塔位，也不提供账本结果" in adapter.system_prompt
