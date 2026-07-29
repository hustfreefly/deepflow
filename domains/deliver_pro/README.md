# Deliver Pro V3 — Code-First 交付执行引擎

> **版本**: V3.0.0 | **最后更新**: 2026-07-30  
> **架构**: Pulse 脉冲调度（Code-First，唯一生产路径）  
> **测试**: 347 passed  
> **ADR-009**: 读取 `ship_track.json` 优先（MD-first 对齐）

---

## 架构概述

```
Ship Pro 产出
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Deliver Pro (Pulse V1)                                       │
│                                                               │
│  cron 每 5min 点火                                            │
│    ↓                                                          │
│  pulse_cli.py pulse --project X                              │
│    ↓                                                          │
│  DeliverOrchestrator.pulse() 单次全量扫描                      │
│    ↓                                                          │
│  动作契约落盘 _pulse_actions.json                              │
│    ↓                                                          │
│  spawn Worker Agents → confirm 回执 → session 结束             │
│                                                               │
│  每个 WP 独立 5 Phase 流水线:                                   │
│    Phase 1: Analyze → Phase 2: Execute → Phase 3: Integrate  │
│    Phase 4: Validate → Phase 5: Package                       │
└─────────────────────────────────────────────────────────────┘
    ↓
交付物 (DELIVERABLE.md + track.json)
```

### 核心原则

| 原则 | 说明 |
|------|------|
| **Code-First** | Python 控制流，LLM 只做内容生成 |
| **Pulse 调度** | cron 点火 → 单次扫描 → 动作落盘 → session 结束 |
| **无状态 session** | 不依赖 session 长寿，状态靠文件系统 |
| **并发控制** | MAX_IN_FLIGHT=8, MAX_SPAWN_PER_PULSE=5 |
| **契约笼子** | Pydantic Schema 验证所有输入输出 |

---

## 快速开始

```python
from domains.deliver_pro import run_deliver_pro

# 启动 Deliver Pro（返回 Pulse 启动信息）
result = run_deliver_pro("my_project")

# 手动触发 Pulse（生产路径）
# python3 -m domains.deliver_pro.pulse_cli pulse --project "my_project"
```

### 前置条件

- Ship Pro 已完成，输出在 `.deepflow/blackboard/{project_name}/ship_pro/`
- `ship_track.json` 或 `ship_package.json` 存在

---

## 文件索引

### 核心模块

| 文件 | 职责 |
|:---|:---|
| `__init__.py` | 公共 API `run_deliver_pro()`（V3 入口） |
| `orchestrator.py` | DeliverOrchestrator — 批量驱动 WP 流水线 |
| `wp_runner.py` | DeliverWPRunner — 单 WP 5 Phase 执行 |
| `driver.py` | DeliverRunner — 单 WP 驱动（Phase 1-5） |
| `pulse_cli.py` | Pulse CLI — cron 点火入口 |
| `state_manager.py` | 状态管理（宽松模式） |
| `smart_assembler.py` | 智能组装器（Code-First Assembly） |

### 契约层

| 文件 | 职责 |
|:---|:---|
| `contracts/delivery_manifest.py` | 交付清单 Schema |
| `contracts/execution_plan.py` | 执行计划 Schema |
| `contracts/pipeline_state.py` | 管线状态 Schema |
| `contracts/pulse_report.py` | Pulse 报告 Schema |
| `contracts/validation_verdict.py` | 验证裁决 Schema |
| `contracts/work_package.py` | WorkPackage Schema |
| `contracts/worker_task.py` | Worker 任务 Schema |

### Prompt 文件

| 文件 | 职责 |
|:---|:---|
| `prompts/deliver_worker_base.md` | Worker 基础模板 |
| `prompts/deliver_analyze.md` | Phase 1: 分析 |
| `prompts/deliver_validate.md` | Phase 4: 验证 |
| `prompts/deliver_integrate.md` | Phase 3: 集成 |
| `prompts/deliver_pulse.md` | Pulse 调度 |
| `prompts/deliver_package.md` | Phase 5: 打包 |
| `prompts/_shared_subagent_rules.md` | 共享规则 |

### 辅助模块

| 文件 | 职责 |
|:---|:---|
| `blackboard.py` | Blackboard 状态持久化 |
| `phase_deriver.py` | Phase 推导（从文件系统状态） |
| `prompt_registry.py` | Prompt 加载器 |
| `failure_recovery.py` | Worker 失败恢复 |

---

## Pulse 调度机制

### 工作流程

```
1. cron 每 5min 点火 isolated session
2. pulse_cli.py pulse --project X
3. DeliverOrchestrator.pulse() 单次全量扫描
4. 动作契约落盘 _pulse_actions.json
5. spawn Worker Agents
6. confirm 回执
7. session 结束（不依赖 session 长寿）
```

### 并发控制

| 参数 | 值 | 说明 |
|------|-----|------|
| `MAX_IN_FLIGHT` | 8 | 全局在途 agent 硬上限 |
| `MAX_SPAWN_PER_PULSE` | 5 | 单次 pulse spawn 上限 |
| `ORPHAN_DISPATCH_WINDOW` | 600s | 未确认 dispatch 的孤儿窗口 |

---

## 5 Phase 流水线

每个 WP 独立执行 5 Phase：

| Phase | 名称 | 说明 |
|:-----:|------|------|
| 1 | **Analyze** | 分析 WP 需求，生成执行计划 |
| 2 | **Execute** | 执行代码生成/修改 |
| 3 | **Integrate** | 集成到主代码库 |
| 4 | **Validate** | 验证交付物质量 |
| 5 | **Package** | 打包交付物（DELIVERABLE.md + track.json） |

---

## ADR-009 对齐

Deliver Pro 读取 Ship Pro 产出的优先级：

```python
# 1. ship_track.json（Track 衍生，跨域元数据）— 优先
# 2. ship_package.json（JSON 衍生，向后兼容）
# 3. ship_pro/stages/ship_package.json（旧路径）
```

---

## 测试

```bash
cd .deepflow

# 单元测试
python3 -m pytest domains/deliver_pro/tests/ -v

# 当前状态: 347 passed
```

---

## 版本历史

| 版本 | 日期 | 核心变更 |
|:---|:---|:---|
| **V3.0.0** | 2026-07-30 | ADR-009 对齐：读 `ship_track.json` 优先 |
| **V3.0.0** | 2026-07-24 | Pulse V1 脉冲调度（唯一生产路径） |
| **V2.0.0** | 2026-07-28 | LLM Orchestrator 模式禁用（drive_all） |

---

## 禁止事项

- ❌ 使用 `drive_all()`（已禁用，仅测试用）
- ❌ 依赖 session 长寿（状态靠文件系统）
- ❌ 绕过并发控制（MAX_IN_FLIGHT=8）
- ❌ 手动拼接 blackboard 路径（使用 DeliverProBlackboard API）

---

详细变更见 [CHANGELOG.md](../../CHANGELOG.md)
