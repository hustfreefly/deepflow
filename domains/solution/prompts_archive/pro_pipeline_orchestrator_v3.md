# Solution Pro Pipeline Orchestrator V3

> Deprecated compatibility placeholder. Do not use this prompt for new Solution Pro runs.

Solution Pro 的当前主路径是 `pipeline_orchestrator_v4.md`：

- 固定 B 方案 10 阶段执行拓扑
- Planner 只生成控制平面数据，不增删阶段和 worker
- 研究专家画像写入 `control_contract.json`，再映射到固定 `expert_1`、`expert_2`、`expert_3` 槽位
- 所有正式质量评分统一使用 `harness_scoring.md` 定义的 4 维标准：
  - 完整性 30%
  - 必要性 20%
  - 目标一致性 30%
  - 全局影响 20%

如仍有调用方读取本文件，应迁移到：

```text
solution/pipeline_orchestrator_v4
solution/harness_scoring
```
