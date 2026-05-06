# Changelog

> **版本号规则**: 0.1.0 = V4.0 内部代号（表示第四次架构迭代）

## [0.1.1] - 2026-05-05

### Added
- Solution Pro V3.1: Planning Agent语义理解+自我验证+结构化理由+反例+术语澄清+置信度
- Planning Agent Prompt增强：6步自我验证机制（技术领域/专长/匹配度/产出能力/更高匹配/辩护理由）
- 分配理由结构化输出：allocation_rationale字段（技术领域判定+专长匹配逻辑+产出能力评估+反例说明）
- 置信度评分机制：1-10分，≤6分重新考虑
- 契约笼子：solution_orchestrator_v3_1_documentation.yaml

### Improved
- Planning Harness评分：81 → 91 (+10)
- 需求覆盖率：75% → 87.5% (+12.5%)
- REQ-ID错配率：24.2% → 0%
- 遗留问题：10 → 5 (-50%)
- Audit发现问题：15 → 11 (-26.7%)

### Fixed
- 上次V3的8项REQ-ID错配全部解决（如REQ-027 GPU虚拟化分配给隐私专家等）
- 需求缺失从2项降至0项

### Verified
- "搭建算力中转平台"端到端回归测试通过
- Harness Final: 85分 PASS
- 10阶段全部成功产出

## [0.1.0] - 2026-04-24

### Added
- V4.0 架构：DataManager Worker + 统一搜索层 + 配置化改造
- Orchestrator Agent 调度系统（支持 10 并发子Agent）
- 契约笼子（Contract Cage）验证框架
- 6 Researchers + 3 Auditors + Fixer + Summarizer + SendReporter 完整管线
- 搜索配置化：core/search_engine.py + search_config.yaml
- 配置分离：search/output/credentials 三文件管理
- 凭证安全：core/config_loader.py 集中加载，禁止硬编码
- 飞书自动发送：创建文档 + 发送链接
- force_rebuild 参数：强制重新分析，禁止复用历史数据
- 文档对齐：README/SKILL/ARCHITECTURE 统一描述

### Fixed
- Worker 路径问题（相对路径 → 绝对路径）
- 并发限制（maxChildrenPerAgent 5→10）
- key_metrics 全 null 问题（Tushare 范围查询 + fallback 链）
- DataManager 导入路径错误（data_manager → core.data_manager）
- 飞书发送方式（本地路径 → 文档链接）

### Tested
- 华虹公司(688347.SH) 端到端测试通过
- 中芯国际(688981.SH) 端到端测试通过（含飞书发送）
- key_metrics 6/6 字段真实数据填充
- 产出率 100% (15/15 Workers)

---

## [0.0.1] - 2026-04-14

### Added
- 初始架构设计
- PipelineEngine FSM 管线执行器
- QualityGate 四维质量评估
- ResilienceManager L1-L4 故障隔离
