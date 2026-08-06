# vibegamer

`vibegamer` 是一套让不同大模型接管 TowerMind，并完成可验证实验的 Agent 运行时与评测系统。

接入一个模型 API，系统负责读取战场、请求决策、执行动作、连续运行关卡、判定结果，
并输出可复查的实验记录。

项目基于 [TowerMind](https://github.com/tb6147877/TowerMind) 和
[LiteLLM](https://github.com/BerriAI/litellm)。本仓库不包含 TowerMind 游戏二进制。

当前版本：`v0.1.0` / Harness `2.5` / Python `3.10-3.12`

## 核心系统

### 1. 大模型可操作的 TowerMind 语义环境

Observer 将 Unity/Gym 状态转换成稳定塔位、路线、可见敌情、金币、生命和冷却等语义字段，
并提供建造、升级、出售、英雄、骑士和援军等 12 类游戏动作。

### 2. LLM Agent 运行时

运行时通过 LiteLLM 接入不同供应商，形成“观察战场 → 模型决策 → 动作校验与执行 →
推进游戏 → 事件触发下一次决策”的完整循环。它支持条件计划、本地微操、流式响应和
规划/行动两阶段请求。

### 3. 可验证实验裁判

裁判采用三项会直接影响实验结论的核心规则：

- **结果只认原生终局**：进入最后一波不算通关，完整地图必须收到 ML-Agents terminal。
- **每关先验新开局**：模型调用前检查波次、步数、经济、预建塔和地图指纹；脏状态自动
  reset 或重启 Unity，仍异常则不调用模型。
- **异常不进入成绩**：中断、watchdog、决策预算耗尽和模型请求失败统一标为 invalid；
  续跑只继承连续且已确认通关的关卡，中断关卡重新开始。

## 架构

| 模块 | 职责 |
| --- | --- |
| `plugin/TowerMind.Observer/` | 游戏状态投影、命令桥、遥测和 HUD |
| `src/tower_referee/game/` | TowerMind 与模拟后端适配 |
| `src/tower_referee/models.py` | 模型供应商、流式响应和两阶段决策 |
| `src/tower_referee/runner.py` | 决策循环、关卡编排、终局和续跑 |
| `src/tower_referee/recorder.py` | 事件、有效性、成绩和看板 |

```text
TowerMind -> Observer -> structured state -> LLM
          <- ML-Agents <- validated actions <- referee
                                  |
                                  -> events / validity / summary / dashboard
```

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

Harness 2.5 支持 `decision_pipeline=plan_then_action`：第一阶段完成规划，第二阶段关闭
thinking，只生成行动 JSON。两次请求分别记录为 `planning` 和 `action`，规划输出被截断
也不会挤掉行动阶段。

provider seed 只做 best effort，不能保证第三方 API 完全确定。

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

`tower-campaign-local` 只读取本地事件并打印关卡、终局和错误，不会为了监控比赛而额外
调用模型。结束后会生成 `model_decisions.md`。

## 实验边界

当前通天塔采用单次娱乐化展示口径，不能作为科学模型排名。正式研究需要重复试验，
并冻结模型版本和参数。本仓库不发布现有模型成绩。

公开：裁判源码、Observer 源码、无密钥配置、测试和构建脚本。

不公开：TowerMind 二进制、API Key、`.env`、模型成绩、本地 artifact、录屏、临时文件、
内部调试记录和未验证配置。

## 文档

- [v0.1.0 发布说明](RELEASE_NOTES.md)
- [Observer 构建与接口](plugin/README.md)

## 许可

本项目代码使用 [MIT License](LICENSE)。TowerMind 和 LiteLLM 仍遵循各自仓库的许可。
