# DeepFlow V1.0 架构蓝图

> **版本**: V1.0 | **日期**: 2026-04-18 | **状态**: 待开发  
> **来源**: V0.0.0 经验 + 双模型架构审计 + Agent Depth 实测 + 6 专家减法论证  
> **代码量**: 7,700 → 5,200 行（减少 32%）| **模块**: 4 核心 + 2 辅助 + 1 入口

---

## 一、架构设计

### 1.1 Agent 树架构（V1.0 核心变更）

```
主 Agent（我，depth-0）
  ├── sessions_spawn → PipelineEngine Orchestrator Agent（depth-1）
  │     └── 内部调用 Python 辅助模块：
  │           ├── ConfigLoader → 读 YAML
  │           ├── QualityGate → 打分
  │           ├── ResilienceManager → 错误分类/重试
  │           ├── BlackboardManager → 状态字典 + 文件持久化
  │           └── Observability → 日志记录
  │
  └── PipelineEngine Agent 内部 spawn Worker Agent（depth-2, leaf）
        ├── spawn 审计 Agent A（depth-2）
        ├── spawn 审计 Agent B（depth-2）
        └── spawn 修复/验证 Agent（depth-2）
```

**关键设计**：
- PipelineEngine 是 Agent Orchestrator（depth-1），不是纯 Python 代码
- Python 模块降级为工具函数库，被 PipelineEngine Agent 调用
- 所有 Worker Agent 是 depth-2 leaf，不再 spawn

### 1.2 OpenClaw Agent Depth 限制（实测验证）

| 工具 | Depth-0 | Depth-1 | Depth-2 (Leaf) |
|:---|:---:|:---:|:---:|
| read/write/edit/exec/web_fetch/memory_search | ✅ | ✅ | ✅ |
| sessions_spawn/sessions_list/subagents | ✅ | ✅ | ❌ |

**Visibility**：depth-0=tree | depth-1=tree | depth-2=self

**配置**：`agents.defaults.subagents.maxSpawnDepth = 3`

### 1.3 模块结构（4 核心 + 2 辅助 + 1 入口）

```
PipelineEngine Agent（depth-1, Orchestrator）
  │
  ├── ConfigLoader（核心）：YAML 配置加载，0-100 尺度统一
  ├── QualityGate（核心）：4 维质量评估（准确性/完整性/时效性/深度）
  ├── ResilienceManager（核心）：L1 快速失败 → L2 有限重试 → L3 事务回滚
  ├── BlackboardManager（辅助）：内部状态字典 + 文件持久化（~150 行）
  ├── Observability（辅助）：logging facade（~200 行）
  └── Coordinator（入口）：轻量状态机 + 启动/恢复（~700 行）
```

**核心规则**：
- Python 辅助模块之间零依赖，只被 PipelineEngine Agent 注入调用
- Coordinator 是唯一外部入口，管理 spawn 和状态持久化

### 1.4 管线类型（3 种，复用实现）

| 类型 | 流程 | 实现 |
|:---|:---|:---|
| **Iterative** | Plan → Execute → Critique → Fix → 收敛 | 基类 |
| **Audit** | Plan → Collect → Critique×N → Consolidate | 继承 Iterative，跳过 Fix |
| **Gated** | Stage 1 → Gate（≥0.85 PASS）→ Stage 2 | 继承 Iterative，增加 Gate |

### 1.5 关键设计决策

| 决策点 | 最终方案 | 理由 |
|:---|:---|:---|
| **数据流** | Worker 结果 → PipelineEngine 内部字典 | 替代 BlackboardManager 共享总线，0 竞态风险 |
| **状态持久化** | 文件 + 目录扫描恢复（单保险 + 原子写入） | 双保险降级为文件，memory 索引后期加 |
| **HITL** | message + Blackboard 文件 | depth-1 sessions_send 不稳定，文件更可靠 |
| **Worker 返回** | 强制结构化 JSON（agent_type/status/findings） | 解析可靠性保障 |
| **错误处理** | 分类 + 有限重试 + 分级降级 | 传输重试 3 次，限流 2 次，应用错误 0 次 |
| **成本控制** | 内置 CostBudget 层 | 限制并发 Worker 数量，防止 token 失控 |

### 1.6 减法决策（6 专家团队论证通过）

| 减法项 | 处理方式 | 代码量 | 理由 |
|:---|:---|:---|:---|
| **BlackboardManager** | 简化为内部字典 + 文件持久化 | 479→~150 行 | Agent 树天然传递结果 |
| **Observability** | logging facade | 822→~200 行 | 结构化日志覆盖 80% 场景 |
| **ResilienceManager L4** | 砍掉，依赖平台 | -200 行 | 与平台可能冲突 |
| **Protocol 接口定义** | 砍掉，用类型注解 | -400 行 | Python 类型注解足够 |
| **Protocol 尺度转换** | **保留** | 0 | 防止 0-1/0-100 混用回归 |
| **Coordinator** | 精简 | 984→~700 行 | 保留状态管理，精简非核心 |
| **测试结构** | 3 层→2 层 | 减少 33% | contract 合并到 unit |

**必须保留（6 份报告一致反对砍掉）**：ResilienceManager L3、Coordinator 类、QualityGate 4 维、JSON Schema 强制、尺度转换工具、PipelineEngine Agent + Agent 树。

---

## 二、OpenClaw 能力整合

### 2.1 补强索引表

| 编号 | 补强点 | 优先级 | 归属模块 | 对应方法/接口 |
|:---|:---|:---|:---|:---|
| **P0-A** | idempotencyKey | P0 | PipelineEngine | `_spawn_agent()` |
| **P0-B** | 错误分类 | P0 | ResilienceManager | `ErrorClassifier.classify()` |
| **P0-C** | unknown-tool guard | P0 | PipelineEngine | `sessions_spawn()` |
| **P0-D** | registry 校验 | P0 | Coordinator | `validate_agent_registry()` |
| **P1-A** | 分层超时 | P1 | PipelineEngine/ResilienceManager | `_get_timeout()` |
| **P1-B** | 上下文预算 | P1 | BlackboardManager | `get_context_for_agent(budget=)` |
| **P1-C** | per-channel-peer 隔离 | P1 | BlackboardManager | `__init__(channel, session_id)` |
| **P1-D** | /btw 侧边通道 | P1 | PipelineEngine | `notify_progress()` |
| **P1-E** | Engine ID 校验 | P1 | Coordinator | `__init__(engine_id=)` |
| **P2-A** | Active Memory | P2 | BlackboardManager | 预留 `memory_recall()` |
| **P2-B** | Compaction | P2 | Coordinator | 预留 `compact_state()` |
| **P2-C** | Plugin Hooks | P2 | Observability | 预留 `register_hook()` |

### 2.2 架构风险

| 风险 | 处理 |
|:---|:---|
| CircuitBreaker 与平台熔断器冲突 | 保留为"平台熔断器的上层封装"，只做统计告警 |
| Session 隔离违规 | 所有 session_id 遵循 per-channel-peer |
| 指标命名空间 | 统一 `deepflow_` 前缀 |

---

## 三、开发规范

### 3.1 开发流程

```
定义契约 → 写测试 → 实现代码 → 验证闭环
```

### 3.2 编码规范

| 规则 | 标准 |
|:---|:---|
| bare except | 0（zero tolerance）|
| 评分尺度 | 统一 0-100，配置文件写 85 不写 0.85 |
| 类型注解 | 100% 覆盖 |
| Docstring | 每个公开方法必须有 |
| 单模块行数 | ≤ 500（超过则拆分）|
| 重复代码 | 零容忍（DRY）|

### 3.3 协议简化

- protocols.py：从 952 行 → ~200 行（只保留 Protocol 定义）
- dataclass 移到各自模块内部
- 模块必须引用协议（编译时检查）

---

## 四、测试体系

### 4.1 目录结构

```
.deepflow/tests/
├── unit/         # 单元测试（含契约测试）
├── integration/  # 集成测试
└── conftest.py   # 共享 fixture
```

### 4.2 质量门禁

```
□ 编码规范 P0=0
□ 契约测试全通过
□ 单元测试覆盖率 ≥ 80%
□ 无 bare except / 无重复代码
□ 评分尺度统一 0-100
□ 所有公开方法有 docstring + 类型注解
```

---

## 五、清理清单

### 5.1 必须删除

`deepflow_lite*.py` | `deepflow_runner.py` | `deepflow_quick_test.py` | `demo_mode_d.py` | `full_feature/` | `archive/` | `.cage/` | `check_*.py` (散落 30+) | `test_*.py` (散落) | `debug_trace.py` | `quick_verification.py`

### 5.2 必须保留

`domains/*.yaml` | `pipelines/*.yaml` | `prompts/*.md` | `config/*.yaml` | `contracts/*.md` | `reviews/*.md` | `output/`

### 5.3 必须更新

`README.md` | `DEVELOPMENT_RULES.md` | `protocols.py` | `SYSTEM_PROMPT.md`

---

## 六、目录结构（最终形态）

```
.deepflow/
├── 📦 Python 辅助模块（7 个）
│   ├── pipeline_engine.py
│   ├── quality_gate.py
│   ├── resilience_manager.py       ← L1/L2/L3
│   ├── observability.py            ← logging facade
│   ├── blackboard_manager.py       ← 内部字典 + 文件
│   ├── config_loader.py            ← YAML 加载
│   └── coordinator.py              ← 轻量状态机
├── 🔒 契约笼子（Contract Cage）
│   ├── README.md                   ← 使用说明
│   ├── schema.yaml                 ← 契约 Schema 定义
│   ├── validate.py                 ← 契约验证脚本
│   ├── check_standards.py          ← 编码规范检查
│   ├── templates/
│   │   └── module_contract.yaml    ← 契约模板
│   ├── examples/
│   │   └── config_loader.yaml      ← ConfigLoader 契约示例
│   └── [module].yaml               ← 每个模块的契约文件
├── 📋 协议与规范
│   ├── protocols.py                ← ~124 行（尺度转换+Protocol）
│   └── DEVELOPMENT_RULES.md
├── 📋 配置
│   ├── domains/ | pipelines/ | prompts/ | config/
├── 🧪 测试
│   └── tests/ (unit + integration + contract)
├── 💾 状态管理
│   ├── state/{session_id}/         ← checkpoint.json
│   └── blackboard/{session_id}/    ← HITL 文件
├── 📊 参考文档（只读）
│   ├── reviews/ | output/
└── 📝 项目文件
    ├── README.md | V1_BLUEPRINT.md
    └── LAUNCH_REPORT.md（待开发）
```

## 六.1 契约笼子规范

### 每个模块必须有：

| 文件 | 位置 | 大小限制 | 内容 |
|:---|:---|:---|:---|
| 契约定义 | `cage/[module].yaml` | 2-10KB（分级）| 接口 + 行为 + 边界 |
| 契约测试 | `tests/contract/test_[module].py` | 不限 | 验证契约实现 |
| 编码规范 | `cage/check_standards.py` 自动检查 | P0=0 | 类型注解 + docstring + bare except |

### 开发流程

```
1. 写契约 YAML（cage/[module].yaml，≤ 2KB）
2. 写契约测试（tests/contract/test_[module].py）
3. 实现代码（[module].py，在笼子约束下）
4. 自动验证：
   ├── python cage/validate.py [module]      ← 契约验证
   ├── python cage/check_standards.py [file]  ← 编码规范
   └── python -m pytest tests/contract/       ← 契约测试
5. 全部通过 → 进入下一模块
```

---

## 七、开发阶段计划

| Phase | 内容 | 验收标准 | 预计工期 |
|:---|:---|:---|:---|
| **0** | 清理残留 + 搭目录 + 协议简化 | 目录符合蓝图 | 0.5 天 |
| **1** | ConfigLoader + BlackboardManager + Observability | P0=0 + 覆盖率≥80% | 1 天 |
| **2** | QualityGate + ResilienceManager | P0=0 + 覆盖率≥80% | 1.5 天 |
| **3** | PipelineEngine Agent + 最小 Worker 闭环 | Worker 结果正确返回 | 3-5 天 |
| **4** | Coordinator + HITL + 状态持久化 | 跨实例恢复成功 | 2-3 天 |
| **5** | 端到端验证 + 压力测试 | 全链路跑通 | 2 天 |
| **6** | 上线准备（文档 + 报告） | 交付物齐全 | 1 天 |

**合计约 10-13 天**。每 Phase 必须通过质量门禁，否则不得进入下一 Phase。

---

*蓝图版本: V1.0 | 2026-04-18*  
*核心决策: 减法方案 6 专家论证通过 | 代码 7,700→5,200 行*  
*契约笼子: cage/ 模块已创建，含验证脚本 + 编码规范检查*  
*下一步: Phase 1 开发（ConfigLoader / BlackboardManager / Observability）*
