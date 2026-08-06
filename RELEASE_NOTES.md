# vibegamer v0.1.0

**目标**

在 TowerMind 上建立可复现的大模型塔防评测。统一六个模型的输入、动作、终局判定和结果记录。

**范围**

- 接入 TowerMind ML-Agents 和 LiteLLM
- 增加 Observer/HUD、稳定对象 ID 和战斗遥测
- 实现事件驱动决策、动作校验、条件计划和本地微操
- 支持五地图闯关、原生终局门禁、断点续跑和无效结果熔断
- 支持流式 reasoning trace、两阶段规划/行动和本地零模型监控
- 导出 events、manifest、validity、summary、dashboard 和 model decision log

**验收**

- Python 回归测试：113 项通过
- 模拟后端可在零 API 费用下跑完整流程
- Observer 地图 0 固定脚本 A/B：原版与插件版 4999 个游戏步一致
- 密钥、TowerMind 二进制、模型成绩、artifact 和临时文件不入库

**影响和依赖**

- Python 3.10-3.12
- 真实游戏后端依赖 TowerMind、ML-Agents 1.1.0 和本仓库 Observer
- 多模型调用依赖 LiteLLM 1.x 及各供应商 API
- TowerMind 游戏本体不随本仓库发布
- 当前单次通天塔结果用于节目展示，不用于科学排名
