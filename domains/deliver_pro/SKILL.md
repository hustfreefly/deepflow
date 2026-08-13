---
name: deliver-pro
description: "DeepFlow Deliver Pro — Code-First 交付执行引擎。触发：执行工作包、代码生成、交付编译。"
version: "V3.0.0"
---

# Deliver Pro V3 — Agent 执行指南

> **版本**: V3.0.0 | **最后更新**: 2026-07-30  
> **架构**: Pulse 脉冲调度（Code-First，唯一生产路径）  
> **入口**: `run_deliver_pro(project_name)` — Main Agent 唯一调用  
> **ADR-009**: 读取 `ship_track.json` 优先（MD-first 对齐）

---

## 🏗️ 架构总览

```
Main Agent (depth-0)
  └─ exec: run_deliver_pro(project_name) → pulse_config
  └─ 设置 cron 每 5min 点火

Pulse 循环 (isolated session, depth-1)
  ├─ pulse_cli.py pulse --project X
  ├─ DeliverOrchestrator.pulse() 单次全量扫描
  ├─ 动作契约落盘 _pulse_actions.json
  ├─ spawn Worker Agents (depth-2)
  └─ session 结束（无状态）

Worker Agent (depth-2)
  └─ 5 Phase 流水线: Analyze → Execute → Integrate → Validate → Package
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

## 🚀 主 Agent 执行步骤

### Step 1: 启动 Deliver Pro

```python
from domains.deliver_pro import run_deliver_pro

# 返回 Pulse 启动信息
result = run_deliver_pro("my_project")

# result 包含:
# - project_name: 项目名
# - blackboard_path: blackboard 路径
# - mode: "pulse"
# - launch_command: 手动触发命令
```

### Step 2: 设置 Cron 点火

```python
cron(
    action="add",
    job={
        "name": f"deliver_pro_pulse_{project_name}",
        "schedule": {"kind": "every", "everyMs": 300000},  # 5min
        "sessionTarget": "isolated",
        "payload": {
            "kind": "agentTurn",
            "message": f"cd .deepflow && python3 -m domains.deliver_pro.pulse_cli pulse --project {project_name}",
            "timeoutSeconds": 120
        },
        "enabled": True
    }
)
```

### Step 3: 等待完成

Deliver Pro 完成后会写入 `.deliver_completed.json`，可通过以下方式检查：

```bash
ls .deepflow/blackboard/{project_name}/deliver_pro/.deliver_completed.json
```

---

## 📐 5 Phase 流水线

每个 WP 独立执行 5 Phase：

| Phase | 名称 | 说明 |
|:-----:|------|------|
| 1 | **Analyze** | 分析 WP 需求，生成执行计划 |
| 2 | **Execute** | 执行代码生成/修改 |
| 3 | **Integrate** | 集成到主代码库 |
| 4 | **Validate** | 验证交付物质量 |
| 5 | **Package** | 打包交付物（DELIVERABLE.md + track.json） |

### Phase 推导

Deliver Pro 通过文件系统状态推导当前 Phase：

```python
from domains.deliver_pro.phase_deriver import derive_wp_status

status = derive_wp_status(wp_dir)
# 返回: {"phase": "execute", "validate_round": 0, "status": "in_progress"}
```

---

## 🔒 契约笼子

### 并发控制

| 参数 | 值 | 说明 |
|------|-----|------|
| `MAX_IN_FLIGHT` | 8 | 全局在途 agent 硬上限 |
| `MAX_SPAWN_PER_PULSE` | 5 | 单次 pulse spawn 上限 |
| `ORPHAN_DISPATCH_WINDOW` | 600s | 未确认 dispatch 的孤儿窗口 |

### Schema 验证

| 模型 | 关键字段约束 |
|------|-------------|
| `WorkPackage` | wp_id, title, description, acceptance_criteria |
| `DeliveryManifest` | semantic_anchors, requirement_traceability |
| `ValidationVerdict` | verdict (pass/fail), issues |
| `PulseReport` | actions, in_flight, completed |

---

## 📁 Blackboard 目录结构

```
blackboard/{project_name}/
├── ship_pro/
│   ├── ship_track.json         ← 优先读取（ADR-009）
│   └── ship_package.json       ← fallback
│
└── deliver_pro/
    ├── .deliver_completed.json ← 完成标记
    ├── _pulse_actions.json     ← Pulse 动作契约
    ├── wp_001/
    │   ├── data/
    │   │   ├── wp.json         ← WP 定义
    │   │   └── DELIVERABLE.md  ← 交付物
    │   ├── track.json          ← WP Track
    │   └── ...
    ├── wp_002/
    └── ...
```

---

## 🔄 ADR-009 对齐

Deliver Pro 读取 Ship Pro 产出的优先级：

```python
# 1. ship_track.json（Track 衍生，跨域元数据）— 优先
# 2. ship_package.json（JSON 衍生，向后兼容）
# 3. ship_pro/stages/ship_package.json（旧路径）
```

---

## ⛔ 禁止

```python
# ❌ 使用 drive_all()（已禁用，仅测试用）
# ❌ 依赖 session 长寿（状态靠文件系统）
# ❌ 绕过并发控制（MAX_IN_FLIGHT=8）
# ❌ 手动拼接 blackboard 路径（使用 DeliverProBlackboard API）
```

---

## 🧪 测试

```bash
cd .deepflow

# 单元测试
python3 -m pytest domains/deliver_pro/tests/ -v

# 当前状态: 395 passed（2026-08-14 体检修复后）
```

---

## 🚦 调度器状态机（2026-08-14 体检修复）

| 状态 | 含义 | 退出码 | 恢复方式 |
|------|------|:---:|------|
| `active` / `idle` | 正常运行 | 0 | — |
| `locked` | 另一个 pulse 持锁 | 2 | 自动（锁释放/stale 清理） |
| `completed` | 终态（成功或终态自停） | 3 | —（cron 自停 / pulse_all 跳过） |
| `blocked` | 前置条件缺失（living_spec），首次 CRITICAL 告警后降级 INFO | 0 | 补齐 living_spec 后自愈 |
| `frozen` | 熔断触发（同一 JSON 连续损坏 ≥3 次） | 0 | `pulse_cli unfreeze --project X` |

**终态自停**：全部 WP 已解决但含永久失败（terminal_failed > 0）时，
pulse 自动写 `.deliver_completed.json`（outcome=terminal_failed_self_stop）并自停，
防止僵尸项目被无限轮询（2026-08 生产事故：两个项目被轮询 ~3700 次）。

**熔断计数器**：独立隐藏文件 `.{name}.corrupt_count`（成功读取自动清零），
冻结标记 `_circuit_breaker.json`。

---

## 📖 参考文档

- **README.md**: 项目说明
- **contracts/**: Pydantic Schema 定义
- **prompts/**: Prompt 模板

---

*最后更新: 2026-07-30 V3.0.0 (ADR-009 MD-first)*
