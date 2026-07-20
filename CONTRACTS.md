# DeepFlow 契约清单 V3.0.0

> 契约 = 域间/域内的显式约定。用 Pydantic 模型或 YAML 定义，验证失败绝不静默降级。

---

## 契约笼子（Cage）

契约笼子是 DeepFlow 的契约管理机制。每个域的契约 YAML 存放在 `cage/active/`，定义了该域的版本、入口、依赖、输出格式。

### 生效中的契约

| 契约文件 | 域 | 版本 |
|:---|:---|:---|
| `spec_pro_v2.0.yaml` | Spec Pro | V2.2.0 |
| `solution_pro_v2.0.yaml` | Solution Pro | V2.1.1 |
| `ship_pro_v2.0.yaml` | Ship Pro | V2.0.0 |
| `research_pro_v1.0.yaml` | Research Pro | V1.0 |
| `deepflow_cleanup_v1.0.yaml` | 全局 | V1.0 |
| `integrate_codegraph.yaml` | 全局 | — |
| `version_mgmt_migration.yaml` | 全局 | — |

> 已废弃: `ship_pro_v3.0.yaml` → `cage/active/_deprecated/`

---

## 全局契约（contracts/）

### 共享契约（contracts/shared/）

| 文件 | 说明 |
|:---|:---|
| `handoff_contract.py` | **Spec Pro → Solution Pro 跨域交接契约**。Pydantic 模型 `HandoffPackage`，包含 density_gate_result、quality_level、scenario 等字段。验证失败 → raise ValueError。 |
| `pipeline_watcher_design.md` | Pipeline Watcher 设计文档 |
| `pipeline_watcher_v2_design.md` | Pipeline Watcher V2 设计文档 |
| `watcher_prompt_v3.md` | Watcher Prompt V3 |

### 集成契约（contracts/integration/）

| 文件 | 说明 |
|:---|:---|
| `spec_to_solution.md` | Spec Pro → Solution Pro 集成规范 |

### 框架契约（contracts/）

| 文件 | 说明 |
|:---|:---|
| `cage_framework.md` | 契约笼子框架说明 |
| `coding_standards.md` | 编码规范 |
| `development_workflow.md` | 开发工作流 |
| `directory_structure.md` | 目录结构规范 |
| `skill_md_unification_contract.md` | Skill MD 统一契约 |
| `version_control.md` | 版本控制规范 |

---

## 域内契约

### Spec Pro

| 路径 | 说明 |
|:---|:---|
| `domains/spec_pro/contracts/` | 域内契约目录 |

### Solution Pro

| 路径 | 说明 |
|:---|:---|
| `domains/solution_pro/contracts/pipeline_state.py` | 管线状态契约 |
| `domains/solution_pro/contracts/stage_contract.py` | 阶段契约基类 |

### Ship Pro

| 路径 | 说明 |
|:---|:---|
| `domains/ship_pro/contracts/gates.py` | 门控契约 |
| `domains/ship_pro/contracts/planner_output.py` | Planner 输出契约 |
| `domains/ship_pro/contracts/ship_package.py` | ShipPackage 交付契约 |
| `domains/ship_pro/contracts/worker_deliverable.py` | Worker 交付物契约 |
| `domains/ship_pro/contracts/repair_adapters.py` | 修复适配器契约 |

### Deliver Pro

| 路径 | 说明 |
|:---|:---|
| `domains/deliver_pro/contracts/execution_plan.py` | 执行计划契约（任务分解+依赖图） |
| `domains/deliver_pro/contracts/worker_output.py` | Worker 输出契约（内容+元数据） |
| `domains/deliver_pro/contracts/deliver_package.py` | 交付包契约（最终交付物结构） |
| `domains/deliver_pro/contracts/validation_verdict.py` | 验证裁决契约（6维度评分+保留率门禁） |

---

## 跨域数据流

```
Spec Pro
  │
  │ HandoffPackage (handoff_contract.py)
  │ → frozen_spec.json
  ▼
Solution Pro
  │
  │ solution_document.json
  ▼
Ship Pro
  │
  │ ShipPackage (ship_package.py)
  ▼
Deliver Pro
  │
  │ DeliverPackage (deliver_package.py)
  │ Code-First Assembly（确定性拼接，保留率≥95%）
  ▼
最终交付物 (deliver_final.md)
```

---

## 目录结构

```
.deepflow/
├── cage/
│   ├── active/              # 生效中的契约 YAML
│   │   ├── spec_pro_v2.0.yaml
│   │   ├── solution_pro_v2.0.yaml
│   │   ├── ship_pro_v2.0.yaml
│   │   ├── research_pro_v1.0.yaml
│   │   ├── deepflow_cleanup_v1.0.yaml
│   │   ├── integrate_codegraph.yaml
│   │   ├── version_mgmt_migration.yaml
│   │   └── _deprecated/
│   │       └── ship_pro_v3.0.yaml
│   └── archive/             # 归档契约
│
├── contracts/
│   ├── __init__.py
│   ├── cage_framework.md
│   ├── coding_standards.md
│   ├── development_workflow.md
│   ├── directory_structure.md
│   ├── skill_md_unification_contract.md
│   ├── version_control.md
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── handoff_contract.py      # Spec Pro → Solution Pro
│   │   ├── pipeline_watcher_design.md
│   │   ├── pipeline_watcher_v2_design.md
│   │   ├── watcher_prompt_v3.md
│   │   └── _archived/
│   │       └── pipeline_watcher_v3.py
│   └── integration/
│       └── spec_to_solution.md
│
└── domains/
    ├── spec_pro/contracts/
    ├── solution_pro/contracts/
    └── ship_pro/contracts/
```

---

## 铁律

1. **验证失败 → raise ValueError**，绝不静默降级
2. **契约笼子优先**：域间交互必须经过契约验证
3. **版本对齐**：cage YAML 版本必须与域 SKILL.md 版本一致
4. **无 investment 域**：V0.4.0 已移除，任何 investment 相关引用均为废弃

---

*DeepFlow V3.0.0 — 契约是域间协作的唯一真相。*
