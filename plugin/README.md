# TowerMind Observer

这是“6 个 AI 守城”的游戏内插件。它消除坐标、对象 ID 和统计口径造成的
接口难度，但不替模型选择塔型、阵地、预算或战术。

## 边界

- `Observer`：输出官方原始状态，以及稳定 `site_id`、路线进度、客观覆盖关系。
- `Commander`：把语义动作交给 TowerMind 原生校验，返回成功状态和错误码。
- `Telemetry`：记录真实伤害、击杀、按敌人类型统计的漏怪、建造、升级和出售事件。
- `HUD`：在游戏左侧安全边距显示当前模型、完整换行的策略摘要、即时行动和长期策略，
  不遮挡游戏左上角的金币、资源和基地生命值；安全边距使用低对比度美式西部像素背景。
- Python 裁判仍负责模型调用、暂停、三轮隔离、日志、评分和排行榜。

若战争迷雾使新塔位在比赛中途出现，插件会给新位置分配新 ID，已有塔位编号
不会发生位移。终局自动重置前的完整遥测也会保留在 `last_completed`。
己方已确认的塔位和已建塔会被插件记住；移动云雾遮住它们时，不会从状态中删除，
而会标记 `under_fog=true`、`operational=false`。

插件不会输出“最佳建塔位”“推荐塔型”或自动经济策略。

## 本地接口

默认监听 `127.0.0.1:17871`。运行时可通过环境变量
`TOWERMIND_OBSERVER_PORT` 覆盖端口，Python 裁判会从 `towermind_plugin_url`
自动传入对应端口：

- `GET /health`
- `GET /mechanics`
- `GET /state`
- `GET /events?after=0`
- `GET /decision`
- `GET /transition-action`
- `POST /decision`
- `POST /command`

语义命令示例：

```json
{
  "request_id": "decision-01",
  "actions": [
    {"id": "a1", "type": "build", "site_id": "site_02", "tower": "archer"},
    {"id": "a2", "type": "move_hero", "position": [1.2, -0.5]}
  ]
}
```

## 构建和安装

运行时副本位于：

```text
vendor/TowerMind/plugin_runtime/mac_apple_silicon/td.app
```

默认采用不依赖 BepInEx 注入器的托管程序集方案。它只修改专用游戏副本，
并保留 `Assembly-CSharp.original.dll`：

```bash
.venv/bin/python scripts/generate_mechanics.py
./scripts/build_towermind_standalone_plugin.sh
./scripts/install_towermind_standalone_plugin.sh
```

`build_towermind_plugin.sh` / `install_towermind_plugin.sh` 保留为 BepInEx
兼容路线，但当前 TowerMind 的 Unity 2023 macOS 运行时不使用它。

当前正式裁判用官方 ML-Agents 通道提交动作，Observer 的 `/command` 保留为
调试接口。这样模型思考暂停、逐步推进和原生动作结算仍由官方接口控制。

HUD 除了显示模型理由，还负责显示 `YOU DID IT!` / `YOU FAILED` 关卡结算层，
并将“下一关”“再试一次”“停止”的选择回传给 Python 裁判。因为 ML-Agents
在 Python 不提交动作时会冻结 Unity，裁判在结算等待期间会发送无操作帧，只刷新
界面和按钮，不将该过程计入已经完成的比赛成绩。

HUD 背景资源为 `plugin/generated/hud_background.png`。standalone 安装脚本会将它复制到
`StreamingAssets/TowerMind.Observer/hud_background.png`；BepInEx 兼容安装路径会将它复制到
插件程序集旁边。HUD 只绘制宽屏游戏视口两侧的 letterbox 区域，不覆盖实际地图和原生 HUD。

## 验证

- Python/C# 构建与接口测试：51 项通过。
- 地图 0 固定脚本 A/B：原版与插件版逐步完全一致。
- 终局：均为 4999 步、守完 5 波、基地 1 点、金币 861，塔型/位置/等级一致。
- 报告：`artifacts/plugin-ab-map0-final.json`。

正式录屏前仍遵守项目的录屏门禁。
