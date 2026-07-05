---
name: deepflow-pipeline
description: "DeepFlow 全链路编排: Spec Pro → Solution Pro → Ship Pro。触发: 全链路、完整流程、需求到交付、从需求到工作包。"
version: "2.0.0"
---

# DeepFlow Pipeline — 全链路编排指南

> **版本**: 2.0.0 | **适用**: Spec Pro + Solution Pro + Ship Pro 三域串联

---

## 核心概念

DeepFlow 是三段式管线：**需求梳理 → 解决方案设计 → 交付包生成**。

```
用户需求（自然语言）
  │
  ▼
┌─────────────────────────┐
│  Phase 1: Spec Pro      │  多轮对话 → LivingSpec
│  入口: SpecProCoordinator │
│  产出: spec/living_spec.json │
└────────────┬────────────┘
             │ is_done() == True
             ▼
┌─────────────────────────┐
│  Phase 2: Solution Pro  │  Orchestrator → Planning + Research + Summary
│  入口: run_solution_pro() │
│  产出: data/frozen_spec.json │
└────────────┬────────────┘
             │ 完成事件到达
             ▼
┌─────────────────────────┐
│  Phase 3: Ship Pro      │  Orchestrator → Workers → Consolidator
│  入口: run_ship_pro()    │
│  产出: ShipPackage (WPs) │
└─────────────────────────┘
```

**数据桥接**：统一 Blackboard（`.deepflow/blackboard/{session_id}/`），三个域通过文件路径约定传递数据。

---

## 执行步骤

### Phase 1: Spec Pro — 需求梳理

**触发条件**: 用户描述了项目需求，需要结构化梳理。

```python
# Step 1.1: 启动 Spec Pro Coordinator
from domains.spec_pro.coordinator import SpecProCoordinator

coordinator = SpecProCoordinator(
    scenario="genesis",          # 新需求用 genesis
    mode="standard",             # standard = 完整流程
    session_prefix=None,         # 自动生成 session_id
    architecture_version="v3_flat"  # V3 扁平架构
)
```

```python
# Step 1.2: 运行对话循环
# coordinator.run() 返回 spawn_params，用 sessions_spawn 启动
# 子 Agent 会进行多轮苏格拉底式对话
```

```python
# Step 1.3: 检测完成
# coordinator.is_done() → True 表示 LivingSpec 已确认
# 产出文件: {blackboard}/{session_id}/spec/living_spec.json
```

**完成信号**: `is_done()` 返回 True
**产出**: `spec/living_spec.json`（22 个字段，含 semantic_anchors）

---

### Phase 2: Solution Pro — 解决方案设计

**触发条件**: Spec Pro 完成（`is_done() == True`），living_spec.json 已写入。

```python
# Step 2.1: 调用 run_solution_pro()
from domains.solution_pro import run_solution_pro

result = run_solution_pro(
    user_input="用户的原始需求描述",  # 或从 living_spec.confirmed.objective 提取
    topic="项目名称",               # 用于 blackboard 目录名
    # 可选参数:
    # living_spec=living_spec_dict,  # 直接传入 living_spec（跳过文件读取）
)

# result 包含 spawn_params，用 sessions_spawn 启动 Orchestrator
```

```python
# Step 2.2: spawn Orchestrator
sessions_spawn(
    task=result["spawn_params"]["task"],
    mode="run",
    taskName="solution-pro-orchestrator",
)
# sessions_yield() 等待完成事件
```

```python
# Step 2.3: 等待完成
# Orchestrator 完成后会发送完成事件
# 产出文件: {blackboard}/{topic}/data/frozen_spec.json
# frozen_spec 包含: requirements + semantic_anchors + executive_summary + guardrails 等 13 个字段
```

**完成信号**: 子 Agent 完成事件到达
**产出**: `data/frozen_spec.json`（13 个字段）

---

### Phase 3: Ship Pro — 交付包生成

**触发条件**: Solution Pro 完成，frozen_spec.json 已写入。

```python
# Step 3.1: 调用 run_ship_pro()
from domains.ship_pro import run_ship_pro

result = run_ship_pro(
    project_name="项目名称",  # ⚠️ 必须与 Solution Pro 的 topic 一致！
    # project_name 用于定位 blackboard 目录
)

# result 包含 spawn_params，用 sessions_spawn 启动 Orchestrator
```

```python
# Step 3.2: spawn Orchestrator
sessions_spawn(
    task=result["spawn_params"]["task"],
    mode="run",
    taskName="ship-pro-orchestrator",
)
# sessions_yield() 等待完成事件
```

```python
# Step 3.3: 获取结果
# 产出: ShipPackage（work_packages + dependency_graph + semantic_anchors）
# 文件: {blackboard}/{project_name}/ship_pro/stages/ship_package.json
```

**完成信号**: 子 Agent 完成事件到达
**产出**: ShipPackage（N 个 WorkPackage，每个含 title/description/ACs/deliverables）

---

## ⚠️ 关键约束

### 1. project_name 必须一致

```
Solution Pro 的 topic == Ship Pro 的 project_name
```

两者都用于定位 `.deepflow/blackboard/{name}/` 目录。如果不一致，Ship Pro 会 FileNotFoundError。

**建议**: 从 Spec Pro 的 session_id 或用户需求中提取一个统一的 project_name，全程使用。

### 2. Semantic Anchors 必须非空

- Spec Pro coordinator 步骤 4 负责提取 semantic_anchors
- 如果跳过这步，anchors 为空 → Ship Pro conservation_judge 会 FAIL
- **建议**: 在 Spec Pro 完成后检查 `living_spec.semantic_anchors` 是否非空

### 3. 不要手动传递数据

三个域通过 **统一 Blackboard** 传递数据，不需要手动读取/传递文件：
- Spec Pro 写入 `spec/living_spec.json`
- Solution Pro 读取 living_spec → 写入 `data/frozen_spec.json`
- Ship Pro 读取 frozen_spec → 产出 ShipPackage

**例外**: 如果你想直接传入 living_spec 而不走文件，`run_solution_pro()` 支持 `living_spec=` 参数。

### 4. 每阶段完成后才启动下一阶段

```
Phase 1 完成 → 检查 is_done() → 启动 Phase 2
Phase 2 完成 → 收到完成事件 → 启动 Phase 3
```

不要并行启动多个阶段。数据流是串行的。

---

## 快速参考

| 阶段 | 入口函数 | 参数 | 完成信号 | 产出 |
|------|---------|------|---------|------|
| Spec Pro | `SpecProCoordinator()` | scenario, mode | `is_done()` | living_spec.json |
| Solution Pro | `run_solution_pro()` | user_input, topic | 子 Agent 完成事件 | frozen_spec.json |
| Ship Pro | `run_ship_pro()` | project_name | 子 Agent 完成事件 | ShipPackage |

---

## 故障排除

| 症状 | 原因 | 解决 |
|------|------|------|
| Ship Pro FileNotFoundError | project_name ≠ topic | 确保两者一致 |
| conservation_judge FAIL | semantic_anchors 为空 | 检查 Spec Pro 步骤 4 |
| Phase 2 卡住不完成 | Orchestrator 超时 | 检查 sessions.json 大小 |
| 子 Agent 不回复 | LCM 卡死 | 清理 sessions.json |

---

## 示例：完整全链路调用

```python
# === Phase 1: Spec Pro ===
from domains.spec_pro.coordinator import SpecProCoordinator

coordinator = SpecProCoordinator(scenario="genesis", mode="standard")
spawn_params = coordinator.run()
sessions_spawn(**spawn_params, mode="run", taskName="spec-pro")
sessions_yield()  # 等待完成

# === 检查完成 ===
assert coordinator.is_done(), "Spec Pro 未完成"

# === Phase 2: Solution Pro ===
from domains.solution_pro import run_solution_pro

PROJECT_NAME = "我的项目"
result = run_solution_pro(
    user_input="用户需求描述",
    topic=PROJECT_NAME,
)
sessions_spawn(**result["spawn_params"], mode="run", taskName="solution-pro")
sessions_yield()  # 等待完成

# === Phase 3: Ship Pro ===
from domains.ship_pro import run_ship_pro

result = run_ship_pro(project_name=PROJECT_NAME)
sessions_spawn(**result["spawn_params"], mode="run", taskName="ship-pro")
sessions_yield()  # 等待完成

# === 完成 ===
print("全链路完成！查看 ShipPackage:")
print(f"  .deepflow/blackboard/{PROJECT_NAME}/ship_pro/stages/ship_package.json")
```
