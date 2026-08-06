# vibegamer

`vibegamer` 是一套 TowerMind 大模型塔防评测工具。它统一模型输入、合法动作、
关卡终局和结果记录，让不同模型在同一套规则下完成五地图闯关。

项目基于 [TowerMind](https://github.com/tb6147877/TowerMind) 和
[LiteLLM](https://github.com/BerriAI/litellm)。本仓库不包含 TowerMind 游戏二进制。

当前版本：`v0.1.0` / Harness `2.5` / Python `3.10-3.12`

## 做了什么

- 为 TowerMind 增加 Observer/HUD，输出稳定塔位 ID、路线、可见敌情和精确战斗遥测。
- 实现事件驱动裁判、动作校验、条件计划和统一的本地微操器。
- 通过 LiteLLM 接入不同供应商，记录请求参数、流式思考、最终 JSON 和修复过程。
- 只接受 ML-Agents 原生 terminal 作为完整关卡结果；中断、超时和预算耗尽记为无效。
- 导出原始事件、有效性报告、JSON/CSV 成绩、HTML 看板和逐次决策记录。

## 结构

| 模块 | 职责 |
| --- | --- |
| `src/tower_referee/` | 模型调用、动作校验、事件调度、评分和审计 |
| `plugin/TowerMind.Observer/` | 游戏状态投影、命令桥、遥测和 HUD |
| `configs/` | 模型、赛制和录屏配置 |
| `scripts/` | 插件安装、机制生成、A/B 和诊断工具 |
| `tests/` | 模型适配、终局、续跑、插件桥和评分回归 |

```text
TowerMind -> Observer -> structured state -> LiteLLM model
          <- ML-Agents <- validated actions <- referee
                                  |
                                  -> events / validity / summary / dashboard
```

## 四轮核心优化

内部记录有 26 个调试阶段。发布版只保留四轮会改变评测结论或运行稳定性的改动。

1. `7 月 28-30 日`：拆分感知、策略和执行问题；增加动作白名单、条件计划和反事实诊断，
   避免把接口缺失误判成模型能力。
2. `7 月 31 日`：接通真实 TowerMind；完成 Observer/HUD、12 类原生动作、事件召回、
   稳定对象 ID 和整局遥测。
3. `7 月 31 日-8 月 4 日`：删除按波次猜胜负的逻辑；增加原生终局快照、新开局门禁、
   跨图指纹、watchdog、断点续跑、流式响应和 reasoning trace。
4. `8 月 5-6 日`：升级 Harness 2.5；规划与行动分两次请求，压缩重复战场字段，
   合并低价值事件，并加入不消耗额外模型调用的本地比赛监控。

## 快速验证

模拟后端不需要 Unity，也不调用模型 API：

```bash
uv venv --python 3.10
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
tower-referee run --config configs/experiment.example.json
```

输出目录：

```text
artifacts/<experiment>/
├── events.jsonl
├── manifest.json
├── validity.json
├── summary.json
├── summary.csv
└── dashboard.html
```

## 接入模型

```bash
uv pip install -e ".[llm,dev]"
cp .env.example .env
```

模型通过配置选择；密钥只写入 `.env` 或 shell 环境变量。自建 OpenAI 兼容端点使用
`api_base` 和 `api_key_env`，不要把实际密钥写入 JSON、日志或 Git。

Harness 2.5 支持 `decision_pipeline=plan_then_action`：第一阶段保留高强度规划，第二阶段
关闭 thinking，只生成行动 JSON。两次请求分别记录为 `planning` 和 `action`，规划输出
被截断也不会挤掉行动阶段。

## 接入 TowerMind

```bash
uv pip install -e ".[llm,towermind,dev]"
```

1. 按 [TowerMind 官方说明](https://github.com/tb6147877/TowerMind)准备游戏环境。
2. 将原版放在 `vendor/TowerMind/`；该目录被 Git 忽略。
3. 按 [插件说明](plugin/README.md)构建并安装 Observer。
4. 在配置中填写 `towermind_executable`，先运行单模型 smoke，再运行五图 campaign。

```bash
tower-referee smoke \
  --config configs/experiment.official-six.recording.json \
  --model DeepSeek \
  --waves 1

tower-campaign-local --model DeepSeek
```

`tower-campaign-local` 只读取本地事件并打印关卡、终局和错误。它不改变游戏逻辑，
也不会为了监控比赛而额外调用模型。结束后会生成 `model_decisions.md`。

## 有效性规则

- 完整地图只认 ML-Agents 原生 terminal；`wave=5` 不等于通关。
- 每张图在首次模型调用前检查波次、步数、金币、生命、预建塔和地图几何指纹。
- 模型请求失败、JSON 修复失败、决策预算耗尽、watchdog 超时和 interrupted terminal
  均写入 `validity.json`，不计分。
- 漏怪数以基地生命差为准；伤害和击杀优先使用 Observer 的整局累计值。
- provider seed 只是 best effort，不能保证第三方 API 完全确定。

当前通天塔采用单次娱乐化展示口径，不能作为科学模型排名。正式研究需要重复试验，
并冻结模型版本和参数。本仓库不发布现有模型成绩。

## 发布边界

公开：裁判源码、Observer 源码、无密钥配置、规则、测试和构建脚本。

不公开：TowerMind 二进制、API Key、`.env`、模型成绩、本地 artifact、录屏、临时文件、
内部调试记录和未验证配置。

## 文档

- [v0.1.0 发布说明](RELEASE_NOTES.md)
- [Observer 构建与接口](plugin/README.md)

## 许可

本项目代码使用 [MIT License](LICENSE)。TowerMind 和 LiteLLM 仍遵循各自仓库的许可。
