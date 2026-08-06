from __future__ import annotations

import json
import os
import random
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from tower_referee.config import ModelConfig
from tower_referee.schema import Action, Decision, GameState, StandingOrders

CONCISE_REASONING_POLICY_V1 = """
输出预算规则：如果接口提供独立的 reasoning/思考内容，必须控制在 1000 个字符以内。
不要复述输入的战场状态；最多比较两个候选方案；不要在思考中生成 JSON 草稿；
不要反复自我否定或重新开始分析。无论分析是否穷尽，都必须及时停止思考，
优先完整输出最终行动 JSON。analysis_summary 不超过 100 个字符，最终 JSON 只填写
本次决策实际需要的字段。
"""

SYSTEM_PROMPT = """你是一名参加统一塔防测试的指挥官。
你只能根据提供的当前战场状态决策，不能假设未提供的敌人或地图信息。
目标依次是：存活更多波次、保住基地生命、有效使用金币、减少无效操作。
只输出 JSON，不要 Markdown。格式：
{"analysis_summary":"一句简短理由","actions":[{"id":"a1","type":"build|upgrade|sell|show_range|relocate_knights|deploy_reinforcements|move_hero|hero_skill|upgrade_hero|noop","tower":"archer|magician|knight","position":[x,y],"tower_id":"tower_site_01","after":["a1"],"wait":"wave_changed|gold_at_least:N|base_hp_below:N|hero_hp_below:N|enemy_progress_at_least:0.8|reinforcements_ready|tower_frozen"}],"standing_orders":{"hero_anchor":[x,y],"hero_retreat_position":[x,y],"hero_retreat_below_hp":350,"collect_gold":true,"collect_gold_radius_from_anchor":1.25,"knight_block_point":[x,y],"reinforcement_point":[x,y],"use_hero_skill_when_enemy_count":5,"hero_skill_min_hp":700},"cancel_pending_plans":false,"reserve_gold":0}
参数规则：build 需要 tower 和合法 position；upgrade/sell/show_range 需要 tower_id；
relocate_knights/deploy_reinforcements/move_hero 需要 position；hero_skill 和 upgrade_hero 不需要 position。
site_insights 是裁判计算的客观地图几何：其中 position 是合法建塔坐标，path_coverage
说明各塔射程是否覆盖路线，objective_zone 仅表示入口/中段/出口，不代表推荐。
升级、出售必须使用 towers[].id，不能把 site_id 当作 tower_id。
public_mechanics 是赛前公开规则；current_wave_enemy_types 只列当前已经可见的类型，
任何尚未出现的本波敌人和未来波次组成仍然未知。
threat_summary 是裁判从当前可见敌人计算的客观威胁摘要；其中会单列飞行怪数量、
总生命、距基地进度以及现有对空单位。它不包含未来敌人，也不代表策略推荐。
collect_gold 只会在 hero_anchor 周围 collect_gold_radius_from_anchor 半径内捡钱，
避免“驻守”和“全图追金币”互相冲突。被云雾覆盖的己方塔仍会保留在 towers 中，
但 under_fog=true、operational=false，不能攻击或接受塔操作。
不要提交当前金币无法支付的即时动作；可以用 wait="gold_at_least:N" 延后执行。
previous_wave_summary.pending_plans 会列出尚未触发的计划；默认继续保留。
只有确实要撤销旧计划时才设置 cancel_pending_plans=true。
只填写动作所需字段。可以一次提交短期计划；after 表示依赖的动作 ID，wait 表示条件满足后由本地裁判执行，不会再次调用模型。""" + CONCISE_REASONING_POLICY_V1

PLANNING_SYSTEM_PROMPT = """你是一名参加统一塔防测试的指挥官，当前只负责规划。
只能根据提供的当前战场状态分析，不能假设未提供的敌人或地图信息。
目标依次是：存活更多波次、保住基地生命、有效使用金币、减少无效操作。
保持 high 推理强度，认真比较当前合法方案。最终用简洁自然语言写出明确行动计划；
本阶段不要输出行动 JSON，下一阶段会根据你的计划生成严格 JSON。
"""

ACTION_FROM_PLAN_PROMPT = """
你已完成同一战场的规划。现在只执行格式化：依据提供的 planning_result 和 battlefield，
输出一份完整、合法、简洁的行动 JSON。不要重新展开长篇分析，不要输出 Markdown。
"""

_DEFAULT_REASONING = object()

AFFORDABILITY_PREFLIGHT_V1 = """
本次是资源可负担性 A/B 变体。决策前先逐项核对当前 gold、reserve_gold 和每个即时
动作的价格。任何当前无法支付的 build、upgrade 或 upgrade_hero 都不能作为即时动作
提交；若打算未来购买，必须用 wait=\"gold_at_least:N\" 表示明确门槛，或改为当前合法的
免费行动/有理由的等待。analysis_summary 必须说明当前是否可负担，以及下一步的资源触发条件。
这只是把已公开的金币与价格做显式预检，不提供塔型、塔位或威胁权衡建议。
"""

THREAT_TRADEOFF_PREFLIGHT_V1 = """
本次是空地混合威胁权衡 A/B 变体。仅当当前可见敌人同时包含空中与地面单位时，决策前
比较至少两种当前合法候选：分别写出它们覆盖的敌人、各威胁的到达时间和生命、以及现有
防线能够承担什么。不要把“能对空”直接当作全局最优；选择你预计能使这批可见敌人的基地
生命损失最小的动作。analysis_summary 必须简述比较依据。
这只是要求使用已公开的当前状态做权衡，不提供候选的战斗结果、塔型、塔位或未来敌人信息。
"""

TIMELINE_PROJECTION_V1 = """
本次是战斗时间线推演 A/B 变体。仅当当前有可见敌人且 game_rules.tower_combat 已公开时，
才对每个已在比较中的候选，按照公开的诊断 targeting 假设模拟：
新塔立即攻击谁、在下一名敌人抵达基地前能造成多少 DPS×时间伤害、目标死亡后才会切换给谁，
直到当前可见敌人死亡或抵达基地。用该时间线计算会漏掉哪些敌人及对应基地伤害，再排序候选。
其余状态不使用本步骤，按原目标决策。
不要假设未公开的攻击、增援或未来敌人；这不新增候选、不推荐塔型或塔位，也不提供模拟答案。
"""

TARGET_LOCK_LEDGER_V1 = """
本次是目标锁定/切换时间线 A/B 变体。仅在时间线推演适用时，对每个已在比较中的候选建立
内部事件账本：每一步只能锁定当前仍在场、可攻击且 estimated_seconds_to_base 最小的敌人；
计算到该敌人死亡或抵达基地两者中更早时的 DPS×时间伤害。敌人抵达基地后必须从账本移除，
仅在目标死亡或移除后才能选择下一个目标。不得把更晚抵达的敌人当作当前目标。
这只规定如何执行已公开的诊断 targeting 假设，不新增候选、不推荐塔型或塔位，也不提供账本结果；
它不是对 TowerMind 原生目标逻辑的断言。
"""


class ModelAdapter(ABC):
    name: str
    model_id: str

    @abstractmethod
    def decide(
        self, state: GameState, memory: str | None = None, fog_of_war: bool = False
    ) -> Decision:
        raise NotImplementedError

    def review(self, metrics: dict[str, Any]) -> str:
        return (
            "上一局复盘："
            f"守到第 {metrics['waves_survived']} 波，基地剩余 {metrics['base_hp']}，"
            f"无效操作 {metrics['invalid_actions']} 次。"
            "下一局优先修补漏怪位置，并避免重复无效操作。"
        )


class RuleModelAdapter(ModelAdapter):
    """A transparent development bot. It never appears as a real LLM claim."""

    def __init__(self, config: ModelConfig, seed: int = 0) -> None:
        self.name = config.name
        self.model_id = f"rule/{config.model}/{config.name}"
        self.style = config.model
        self.rng = random.Random(f"{seed}:{config.name}")

    def decide(
        self, state: GameState, memory: str | None = None, fog_of_war: bool = False
    ) -> Decision:
        empty = [site for site in state.build_sites if site not in {t.position for t in state.towers}]
        actions: list[Action] = []
        reserve = {"conservative": 220, "balanced": 100, "aggressive": 0}.get(self.style, 80)
        preferred = {
            "conservative": "knight",
            "aggressive": "magician",
            "balanced": "archer",
        }.get(self.style, self.rng.choice(["archer", "magician", "knight"]))
        if memory and state.wave == 0:
            reserve = max(0, reserve - 50)

        if state.towers and state.gold >= 170 + reserve and (
            self.style == "aggressive" or state.wave >= 3
        ):
            target = min(state.towers, key=lambda tower: (tower.level, tower.damage))
            actions.append(Action(type="upgrade", tower_id=target.id))
        if empty and state.gold >= 120 + reserve:
            strategic = [site for site in empty if site in {(2, 1), (2, 2), (2, 4)}]
            position = strategic[0] if strategic else self.rng.choice(empty)
            actions.append(Action(type="build", tower=preferred, position=position))
        if not actions:
            actions.append(Action(type="noop"))
        return Decision(
            analysis_summary=f"{self.name}按{self.style}策略分配当前资源",
            actions=actions,
            reserve_gold=reserve,
            raw_response=json.dumps(
                {"agent": "development-rule-bot", "style": self.style},
                ensure_ascii=False,
            ),
        )


class LiteLLMModelAdapter(ModelAdapter):
    def __init__(
        self,
        config: ModelConfig,
        temperature: float = 0.0,
        max_tokens: int = 900,
        request_timeout: float = 30.0,
        request_retries: int = 0,
        provider_seed: int | None = None,
        provider_seed_mode: str = "best_effort",
        system_prompt_suffix: str = "",
    ) -> None:
        self.name = config.name
        self.model_id = config.model
        self.api_base = config.api_base
        self.api_key_env = config.api_key_env
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_timeout = max(1.0, float(request_timeout))
        self.request_retries = max(0, int(request_retries))
        self.provider_seed = provider_seed
        self.provider_seed_mode = provider_seed_mode
        self._request_index = 0
        self.last_request_metadata: dict[str, Any] = {}
        self.omit_temperature = config.omit_temperature
        self.reasoning_effort = config.reasoning_effort
        self.request_params = dict(config.request_params)
        self.decision_pipeline = config.decision_pipeline
        self.planning_max_tokens = config.planning_max_tokens or self.max_tokens
        self.action_max_tokens = config.action_max_tokens or self.max_tokens
        self.planning_request_params = dict(
            config.planning_request_params or self.request_params
        )
        self.planning_request_params.pop("response_format", None)
        self.action_request_params = dict(config.action_request_params)
        self.system_prompt = SYSTEM_PROMPT + system_prompt_suffix
        self.planning_system_prompt = PLANNING_SYSTEM_PROMPT + system_prompt_suffix

    def restore_request_index(self, next_index: int) -> None:
        """Continue provider-seed sequencing when resuming an audited campaign."""
        self._request_index = max(self._request_index, int(next_index))

    def decide(
        self, state: GameState, memory: str | None = None, fog_of_war: bool = False
    ) -> Decision:
        full_battlefield = state.public_dict(fog_of_war)
        battlefield = compact_battlefield(full_battlefield)
        prompt = {"battlefield": battlefield}
        if memory:
            prompt["private_review_from_previous_round"] = memory
        if self.decision_pipeline == "plan_then_action":
            return self._decide_in_two_phases(prompt, full_battlefield)
        raw = self._completion(
            prompt,
            phase="action",
            input_chars=_json_chars(battlefield),
            full_input_chars=_json_chars(full_battlefield),
        )
        request_trace = [dict(self.last_request_metadata)]
        return self._parse_or_repair(raw, prompt, request_trace)

    def _decide_in_two_phases(
        self,
        prompt: dict[str, Any],
        full_battlefield: dict[str, Any],
    ) -> Decision:
        battlefield = prompt["battlefield"]
        planning_prompt = {
            "task": "分析当前战场并形成明确、可执行的行动计划。不要输出 JSON。",
            **prompt,
        }
        planning_raw = self._completion(
            planning_prompt,
            phase="planning",
            max_tokens=self.planning_max_tokens,
            request_params=self.planning_request_params,
            system_prompt=self.planning_system_prompt,
            input_chars=_json_chars(battlefield),
            full_input_chars=_json_chars(full_battlefield),
        )
        request_trace = [dict(self.last_request_metadata)]
        planning_result = planning_raw.strip() or str(
            self.last_request_metadata.get("reasoning_content") or ""
        ).strip()
        action_prompt: dict[str, Any] = {
            "task": "把既定规划转换成行动 JSON。",
            "planning_result": planning_result,
            "battlefield": battlefield,
        }
        raw = self._completion(
            action_prompt,
            phase="action",
            max_tokens=self.action_max_tokens,
            request_params=(self.action_request_params or self.request_params),
            reasoning_effort=None,
            system_prompt=self.system_prompt + ACTION_FROM_PLAN_PROMPT,
            input_chars=_json_chars(battlefield),
            full_input_chars=_json_chars(full_battlefield),
        )
        request_trace.append(dict(self.last_request_metadata))
        return self._parse_or_repair(raw, action_prompt, request_trace)

    def _parse_or_repair(
        self,
        raw: str,
        prompt: dict[str, Any],
        request_trace: list[dict[str, Any]],
    ) -> Decision:
        try:
            decision = parse_decision(raw)
            decision.request_trace = request_trace
            return decision
        except (ValueError, KeyError, TypeError):
            if self.last_request_metadata.get("finish_reason") == "length":
                return Decision(
                    analysis_summary="模型输出达到上限且没有形成合法 JSON，本局判为无效",
                    actions=[Action(type="noop")],
                    raw_response=raw,
                    parse_status="repair_failed",
                    parse_error_type="OutputTruncated",
                    repair_attempted=False,
                    request_trace=request_trace,
                )
            repair_prompt = {
                "error": "上一条输出无法解析。请严格按指定 JSON 结构重答一次。",
                "invalid_output": raw,
                "battlefield": prompt["battlefield"],
            }
            if "planning_result" in prompt:
                repair_prompt["planning_result"] = prompt["planning_result"]
            repaired = self._completion(
                repair_prompt,
                phase="action_repair",
                max_tokens=(
                    self.action_max_tokens
                    if self.decision_pipeline == "plan_then_action"
                    else self.max_tokens
                ),
                request_params=(
                    self.action_request_params
                    if self.decision_pipeline == "plan_then_action"
                    and self.action_request_params
                    else self.request_params
                ),
                reasoning_effort=(
                    None
                    if self.decision_pipeline == "plan_then_action"
                    else _DEFAULT_REASONING
                ),
                system_prompt=(
                    self.system_prompt + ACTION_FROM_PLAN_PROMPT
                    if self.decision_pipeline == "plan_then_action"
                    else self.system_prompt
                ),
                input_chars=_json_chars(prompt["battlefield"]),
            )
            request_trace.append(dict(self.last_request_metadata))
            try:
                decision = parse_decision(repaired)
                decision.raw_response = repaired
                decision.parse_status = "repair_succeeded"
                decision.repair_attempted = True
                decision.request_trace = request_trace
                return decision
            except (ValueError, KeyError, TypeError) as exc:
                # Do not turn a malformed model response into a strategic noop.
                # The runner will mark the run invalid and preserve both outputs.
                return Decision(
                    analysis_summary="模型连续两次未返回合法 JSON，本局判为无效",
                    actions=[Action(type="noop")],
                    raw_response=json.dumps(
                        {
                            "model_error": type(exc).__name__,
                            "first_output": raw,
                            "repair_output": repaired,
                        },
                        ensure_ascii=False,
                    ),
                    parse_status="repair_failed",
                    parse_error_type=type(exc).__name__,
                    repair_attempted=True,
                    request_trace=request_trace,
                )

    def review(self, metrics: dict[str, Any]) -> str:
        prompt = {
            "task": "复盘上一局塔防表现，输出三条可执行且可迁移的策略，不得引用其他模型。",
            "own_run_metrics": metrics,
        }
        return self._completion(prompt)

    def _completion(
        self,
        payload: dict[str, Any],
        *,
        phase: str = "review",
        max_tokens: int | None = None,
        request_params: dict[str, Any] | None = None,
        reasoning_effort: str | None | object = _DEFAULT_REASONING,
        system_prompt: str | None = None,
        input_chars: int | None = None,
        full_input_chars: int | None = None,
    ) -> str:
        try:
            from litellm import completion
        except ImportError as exc:
            raise RuntimeError(
                "LiteLLM is not installed. Run: pip install -e '.[llm]'"
            ) from exc
        request_index = self._request_index
        self._request_index += 1
        requested_seed = None
        if self.provider_seed is not None and self.provider_seed_mode != "off":
            requested_seed = int(self.provider_seed) + request_index
        active_request_params = dict(
            self.request_params if request_params is None else request_params
        )
        active_reasoning_effort = (
            self.reasoning_effort
            if reasoning_effort is _DEFAULT_REASONING
            else reasoning_effort
        )
        active_max_tokens = self.max_tokens if max_tokens is None else max_tokens
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt if system_prompt is None else system_prompt,
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "max_tokens": active_max_tokens,
            "timeout": self.request_timeout,
            "num_retries": self.request_retries,
        }
        if not self.omit_temperature:
            kwargs["temperature"] = self.temperature
        if active_reasoning_effort:
            kwargs["reasoning_effort"] = active_reasoning_effort
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key_env:
            api_key = os.environ.get(self.api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"Missing required API key environment variable: {self.api_key_env}"
                )
            kwargs["api_key"] = api_key
        # Provider-specific options are explicit in the experiment config so the
        # exact request profile remains auditable alongside the model version.
        kwargs.update(active_request_params)
        if requested_seed is not None and "seed" not in active_request_params:
            kwargs["seed"] = requested_seed
        metadata: dict[str, Any] = {
            "phase": phase,
            "request_index": request_index,
            "requested_seed": requested_seed,
            "provider_seed_mode": self.provider_seed_mode,
            "reasoning_effort": active_reasoning_effort,
            "max_tokens": active_max_tokens,
            "input_chars": input_chars,
            "full_input_chars": full_input_chars,
            "seed_status": (
                "not_requested" if requested_seed is None else "requested"
            ),
        }
        try:
            response = completion(**kwargs)
        except Exception as exc:
            error_text = str(exc).lower()
            seed_rejected = "seed" in error_text or (
                "unsupported" in error_text and "parameter" in error_text
            )
            if (
                requested_seed is not None
                and self.provider_seed_mode == "best_effort"
                and "seed" not in active_request_params
                and seed_rejected
            ):
                fallback_kwargs = dict(kwargs)
                fallback_kwargs.pop("seed", None)
                response = completion(**fallback_kwargs)
                metadata["seed_status"] = "rejected_fallback"
                metadata["seed_error"] = str(exc)[:300]
            else:
                metadata["seed_status"] = "request_failed"
                metadata["error_type"] = type(exc).__name__
                metadata["error"] = str(exc)[:300]
                metadata["reasoning_content"] = None
                metadata["reasoning_content_chars"] = 0
                metadata["reasoning_content_complete"] = False
                self.last_request_metadata = metadata
                raise
        if kwargs.get("stream"):
            return self._consume_stream(response, metadata)
        metadata.update(
            {
                "response_id": getattr(response, "id", None),
                "response_model": getattr(response, "model", None),
                "system_fingerprint": getattr(response, "system_fingerprint", None),
            }
        )
        choices = getattr(response, "choices", None) or []
        if choices:
            metadata["finish_reason"] = getattr(choices[0], "finish_reason", None)
        message = response.choices[0].message
        content = message.content or ""
        reasoning = _reasoning_text(message)
        metadata["reasoning_content"] = reasoning or None
        metadata["reasoning_content_chars"] = len(reasoning)
        metadata["reasoning_content_complete"] = (
            metadata.get("finish_reason") != "length"
        )
        self.last_request_metadata = metadata
        if content:
            return content
        # Some reasoning providers expose the final payload in an auxiliary
        # field when the OpenAI-compatible `content` field is empty.
        if reasoning.strip().startswith(("{", "```")):
            return reasoning
        return ""

    def _consume_stream(
        self, response: Any, metadata: dict[str, Any]
    ) -> str:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        try:
            for chunk in response:
                metadata["response_id"] = _field(
                    chunk, "id", metadata.get("response_id")
                )
                metadata["response_model"] = _field(
                    chunk, "model", metadata.get("response_model")
                )
                metadata["system_fingerprint"] = _field(
                    chunk,
                    "system_fingerprint",
                    metadata.get("system_fingerprint"),
                )
                choices = _field(chunk, "choices", []) or []
                if not choices:
                    continue
                choice = choices[0]
                finish_reason = _field(choice, "finish_reason")
                if finish_reason is not None:
                    metadata["finish_reason"] = finish_reason
                delta = _field(choice, "delta", {}) or {}
                content = _field(delta, "content")
                if isinstance(content, str):
                    content_parts.append(content)
                reasoning = _reasoning_text(delta)
                if reasoning:
                    reasoning_parts.append(reasoning)
        except Exception as exc:
            reasoning = "".join(reasoning_parts)
            partial_content = "".join(content_parts)
            metadata["seed_status"] = "request_failed"
            metadata["error_type"] = type(exc).__name__
            metadata["error"] = str(exc)[:300]
            metadata["stream"] = True
            metadata["reasoning_content"] = reasoning or None
            metadata["reasoning_content_chars"] = len(reasoning)
            metadata["reasoning_content_complete"] = False
            metadata["response_content_partial"] = partial_content or None
            self.last_request_metadata = metadata
            raise

        metadata["stream"] = True
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        metadata["reasoning_content"] = reasoning or None
        metadata["reasoning_content_chars"] = len(reasoning)
        metadata["reasoning_content_complete"] = (
            metadata.get("finish_reason") != "length"
        )
        self.last_request_metadata = metadata
        if content:
            return content
        if reasoning.strip().startswith(("{", "```")):
            return reasoning
        return ""


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _reasoning_text(value: Any) -> str:
    """Read reasoning from common OpenAI-compatible response shapes."""
    for name in ("reasoning_content", "reasoning"):
        reasoning = _field(value, name)
        if isinstance(reasoning, str) and reasoning:
            return reasoning
    details = _field(value, "reasoning_details", []) or []
    if not isinstance(details, (list, tuple)):
        return ""
    return "".join(
        text
        for detail in details
        if isinstance((text := _field(detail, "text")), str)
    )


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def compact_battlefield(public_state: dict[str, Any]) -> dict[str, Any]:
    """Remove repeated prose while retaining every dynamic decision field."""
    data = deepcopy(public_state)
    for enemy in data.get("visible_enemies") or []:
        enemy.pop("description", None)

    rules = data.get("game_rules") or {}
    mechanics = rules.get("public_mechanics")
    if isinstance(mechanics, dict):
        mechanics.pop("schema_version", None)
        mechanics.pop("source", None)
        mechanics.pop("observer_contract", None)
        mechanics.pop("semantic_actions", None)
        if mechanics.get("objective"):
            rules.pop("objective", None)
        if mechanics.get("towers"):
            rules.pop("tower_types", None)
        if mechanics.get("hero"):
            rules.pop("hero", None)
        for tower in mechanics.get("towers") or []:
            tower.pop("description", None)
            tower.pop("official_name", None)
        hero = mechanics.get("hero") or {}
        hero.pop("description", None)
        if isinstance(hero.get("skill"), dict):
            hero["skill"].pop("description", None)
        knights = mechanics.get("knights") or {}
        reinforcements = knights.get("reinforcements") or {}
        if isinstance(reinforcements, dict):
            reinforcements.pop("description", None)
        for enemy in mechanics.get("enemy_archetypes") or []:
            enemy.pop("description", None)

    observer = data.get("observer_meta")
    if isinstance(observer, dict):
        data["observer_meta"] = {
            key: observer[key]
            for key in ("connected", "plugin_version", "initial_state_validated")
            if key in observer
        }
    return data


def parse_decision(raw: str) -> Decision:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    data = json.loads(text)
    actions: list[Action] = []
    for item in data.get("actions", []):
        position = item.get("position")
        tower = item.get("tower")
        if isinstance(tower, str):
            normalized = tower.strip().lower().replace("_", " ")
            normalized = normalized.removesuffix(" tower").strip()
            tower = {
                "mage": "magician",
                "magic": "magician",
                "archer": "archer",
                "magician": "magician",
                "knight": "knight",
            }.get(normalized, normalized)
        actions.append(
            Action(
                type=item["type"],
                tower=tower,
                position=tuple(position) if position is not None else None,
                tower_id=item.get("tower_id"),
                skill=item.get("skill"),
                id=item.get("id"),
                after=list(item.get("after", [])),
                wait=item.get("wait"),
            )
        )
    if not actions:
        actions = [Action(type="noop")]
    orders_raw = data.get("standing_orders")
    standing_orders = None
    if isinstance(orders_raw, dict):
        def point(name: str) -> tuple[float, float] | None:
            value = orders_raw.get(name)
            if not isinstance(value, list) or len(value) != 2:
                return None
            return (float(value[0]), float(value[1]))

        standing_orders = StandingOrders(
            hero_anchor=point("hero_anchor"),
            hero_retreat_position=point("hero_retreat_position"),
            hero_retreat_below_hp=max(
                0, float(orders_raw.get("hero_retreat_below_hp", 350))
            ),
            collect_gold=bool(orders_raw.get("collect_gold", True)),
            collect_gold_radius_from_anchor=max(
                0.0,
                float(
                    orders_raw.get(
                        "collect_gold_radius_from_anchor",
                        1.25,
                    )
                ),
            ),
            knight_block_point=point("knight_block_point"),
            reinforcement_point=point("reinforcement_point"),
            use_hero_skill_when_enemy_count=max(
                0, int(orders_raw.get("use_hero_skill_when_enemy_count", 5))
            ),
            hero_skill_min_hp=max(
                0, float(orders_raw.get("hero_skill_min_hp", 700))
            ),
        )
    return Decision(
        analysis_summary=str(data.get("analysis_summary", ""))[:300],
        actions=actions,
        reserve_gold=max(0, int(data.get("reserve_gold", 0))),
        raw_response=raw,
        standing_orders=standing_orders,
        cancel_pending_plans=bool(data.get("cancel_pending_plans", False)),
    )


def build_model(
    config: ModelConfig,
    seed: int,
    temperature: float,
    max_tokens: int,
    request_timeout: float = 30.0,
    request_retries: int = 0,
    provider_seed: int | None = None,
    system_prompt_suffix: str = "",
) -> ModelAdapter:
    if config.provider == "rule":
        return RuleModelAdapter(config, seed)
    return LiteLLMModelAdapter(
        config,
        temperature,
        max_tokens,
        request_timeout=request_timeout,
        request_retries=request_retries,
        provider_seed=provider_seed,
        provider_seed_mode=config.provider_seed_mode,
        system_prompt_suffix=system_prompt_suffix,
    )
