# TowerMind 插件审计记录

## 结论

- TowerMind 使用 Unity Mono；核心逻辑保留在 `Assembly-CSharp.dll`。当前方案
  通过 Cecil 向专用副本插入极小的托管回调，无需 Unity Editor。
- BepInEx `5.4.23.5` 的 `libdoorstop.dylib` 虽同时包含 `arm64` 和 `x86_64`，
  但未能在 Unity 2023.2 完成 Chainloader 启动；`5.4.23.4` 在 Rosetta 下明确
  报告找不到 `mono_jit_init_version`。因此运行时改为托管程序集注入。
- 插件只安装到 `vendor/TowerMind/plugin_runtime` 副本，原始可运行环境不改动。
- 安装器保留副本中的 `Assembly-CSharp.original.dll`。启动回调放在
  `GameLoop.Awake` 初始化末尾；关卡开始、伤害、漏怪、动作确认和结算仅增加
  旁路记录调用，插件主体仍在独立 DLL 中。

## 已核对的原生接口

- `GameLoop.DispatchAgentBehavior` 覆盖 12 类动作。
- `GameLoop.GetTowers`、`GetAllEnemies`、`GetHero` 和
  `LanguageDescriptionCollector.m_structureDescriptionData` 提供完整战局。
- `GameLoop.OnActionLanguageInfo` 在原生动作成功后确认经济动作。
- `Character.ExecuteBeAttacked` 的入口回调可计算实际有效伤害。
- `Enemy.OnArrivalDest` 的入口回调可精确记录漏怪。
- `GameLoop.OnGameOver` 的入口回调可冻结终局状态。

原生动作编号为：0 弓箭塔、1 魔法塔、2 骑士塔、3 升级、4 出售、
5 显示射程、6 空操作、7 骑士集结、8 援军、9 英雄移动、10 英雄技能、
11 英雄升级。

## 公平性

`mechanics.json` 由官方配置自动生成，但刻意不读取或输出
`AllWavesConfig.json`，第一轮不会泄露未来波次。插件添加的路线进度、覆盖关系
和距离均为几何事实，不包含策略推荐。

地图 0 已用相同固定动作和长期命令完成原版/插件版 A/B。两边在 4999 个游戏步
后均守完 5 波、基地剩 1、金币 861，塔型、位置和等级逐项一致；报告保存在
`artifacts/plugin-ab-map0-final.json`。
