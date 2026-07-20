---
name: spec-pro
description: "DeepFlow Spec Pro — 需求梳理引擎。触发：梳理需求、需求分析、Living Spec。"
version: "V2.2.0"
---

# Spec Pro - Agent 执行指南

> **版本**: V2.2.0 | **最后更新**: 2026-07-08  
> **架构**: 多轮对话 → LivingSpec 构建 → Harness 2.0.0 评估 → Solution Pro 上下文注入  
> **核心理念**: 通过结构化对话提取需求，生成可执行的 LivingSpec

---

## 🚀 主 Agent 执行步骤

### Step 0.0: 上下文注入（FIX-1/2/4/5）🔴

**当 spawn 任何 Spec Pro 子 Agent 时，必须在 task prompt 前注入上下文**：

```python
# 在 spawn 前执行:
exec(
    command="cd {deepflow_root} && PYTHONPATH=. python3 -c \"from core.blackboard.context_injector import build_agent_context; print(build_agent_context(deepflow_root=__import__('pathlib').Path('.'), blackboard_id='<session_id>'))\"",
    workdir="{deepflow_root}"
)
# 将输出拼接到 spawn task 的前面
```

这提供: 目录树 + BM API 文档 + 环境能力 + 数据分析流程。

### Step 0: 入口守卫（防偏检查）🔴

**当用户输入包含以下任一条件时，必须进入 Spec Pro 流程**：
- 明确说"Spec Pro"、"帮我分析需求"、"做一个XXX系统"
- 提供了背景材料/调研文档，且隐含"基于这个做一个项目"

**🔴 防偏规则（绝对禁止）**：
- ❌ 禁止自己出方案/写代码/设计架构
- ❌ 禁止跳过对话直接生成 LivingSpec
- ❌ 禁止自己解读用户意图（必须由 Spec Pro 对话流程提取）

**✅ 正确行为**：
- 必须：调用 `spec_pro_api.py init` → 走多轮对话流程
- 如果用户提供了调研材料，作为 init 的输入传入（不要自己解析）

---

### Step 0.5: 欢迎界面（用户展示层）🔴

**在调用 `spec_pro_api.py init` 之前，必须先向用户展示以下欢迎界面：**

---

## 📋 Spec Pro — 需求梳理引擎

> 通过苏格拉底式对话，帮你把模糊想法变成可执行的需求规格书（LivingSpec）
> ⏱️ 预计 3-6 轮对话，5-10 分钟

### 🚀 快速开始

| # | 场景 | 示例 |
|---|------|------|
| 1 | 🆕 新项目 (genesis) | "做一个 AI 算力调度平台" |
| 2 | 🔄 改进现有系统 (evolution) | "优化客服系统，提升响应速度" |
| 3 | 🔀 迁移/重构 (migration) | "单体架构迁移到微服务" |

### 📎 也可以提供背景材料
- 调研报告、竞品分析、会议纪要
- 我会基于材料提取需求，减少对话轮次

**请告诉我你想做什么，或选择场景编号：**

---

**🔴 铁律**：
- 展示欢迎界面后，**等待用户输入**
- 用户回复后，根据输入内容确定 `--scenario` 参数，再调用 `spec_pro_api.py init`
- 如果用户已经提供了具体需求（如"做一个XX系统"），**跳过欢迎界面**，直接进入 Step 1

---

### Step 1: 初始化 Spec Pro 会话

**触发条件**：Step 0 判定需要进入 Spec Pro

**执行逻辑**：
```python
# 主 Agent 调用 spec_pro_api.py
exec(
    command="PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py init '{user_input}' --mode standard --scenario genesis",
    workdir="{deepflow_root}"
)
```

**返回结果**：
```json
{
  "session_id": "spec_spec_abc123",
  "status": "initialized",
  "current_round": 1,
  "max_rounds": 6
}
```

**输出文件**：
- `blackboard/{session_id}/spec/living_spec.md` — 初始 LivingSpec
- `blackboard/{session_id}/spec/conversation_log.json` — 对话日志

---

### Step 2: 多轮对话（自动循环）

**触发条件**：用户回复 Spec Pro 的提问

**执行逻辑**：
```python
# 1. 提交用户回复
exec(
    command="PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py next_round {session_id} '{user_response}'",
    workdir="{deepflow_root}"
)

# 2. 读取 Orchestrator 生成的下一个问题
exec(
    command="PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py read_output {session_id}",
    workdir="{deepflow_root}"
)

# 3. 检查状态
exec(
    command="PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py status {session_id}",
    workdir="{deepflow_root}"
)
```

**状态判断**：
- `status == "collecting"` → 继续对话，把 `next_question` 发给用户
- `status == "done"` → 跳到 Step 3
- `status == "safety_stop"` → 强制停止（超过 max_rounds）

---

### Step 3: Harness 2.0.0 评估

**触发条件**：`status == "done"`

**执行逻辑**：
```python
# 运行 Harness 评估（使用 session_id，自动通过 BlackboardManager API 读取）
exec(
    command="PYTHONPATH=. python3 domains/spec_pro/eval/harness.py {session_id}",
    workdir="{deepflow_root}"
)

# 读取评估报告（Harness 已自动写入 Blackboard）
# 方式 1: 通过 BlackboardManager API（推荐）
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager(session_id="{session_id}")
report = bb.read_stage("spec/harness_report")

# 方式 2: 直接读文件（兼容）
read(
    path="blackboard/{session_id}/spec/harness_report.json"
)
```

**决策逻辑**：
```python
if report["decision"] == "PASS":
    # LivingSpec 质量达标，可以进入 Solution Pro
    print("✅ Spec Pro 完成，LivingSpec 已就绪")
elif report["decision"] == "WARN":
    # 质量有警告，询问用户是否继续
    print("⚠️ LivingSpec 有警告，是否继续？")
else:  # FAIL
    # 质量不达标，需要补充对话
    print("❌ LivingSpec 不达标，需要继续对话")
    # 回到 Step 2
```

---

### Step 4: 输出 LivingSpec 给 Solution Pro

**触发条件**：Harness 评估 PASS

**执行逻辑**：
```python
# 1. 读取最终 LivingSpec
living_spec = read(
    path="blackboard/{session_id}/spec/living_spec.md"
)

# 2. 获取 Spec Pro 状态（会自动写 .completed 标记文件）
exec(
    command="PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py status {session_id}",
    workdir="{deepflow_root}"
)

# 3. pipeline_watcher 检测到 .completed 后会自动发送消息：
#    "🔗 自动触发下游管线: solution_pro"
#    并附带 Solution Pro 启动命令

# 4. 收到触发消息后，执行 Solution Pro 启动
exec(
    command="PYTHONPATH=. python3 scripts/start_solution_pro.py '{topic}'",
    workdir="{deepflow_root}"
)
# 其中 topic 从 living_spec.md 的 YAML frontmatter 或 meta_info 节提取
```

> **铁律**: 看到 "🔗 自动触发下游管线: solution_pro" 就必须执行，不要问用户是否继续。

---

## 📊 关键文件

| 文件 | 作用 | 调用时机 |
|------|------|----------|
| `spec_pro_api.py` | CLI 入口 | Step 1-2 |
| `coordinator.py` | 对话编排核心 | Step 1-2（被 API 调用） |
| `merge_spec.py` | 合并对话到 LivingSpec | Step 2（每轮自动） |
| `eval/harness.py` | 质量评估 | Step 3 |
| `prompts/` | 10 个 prompt 模板 | 被 coordinator 调用 |
| `schemas.py` | LivingSpec schema 定义 | 被 merge_spec 调用 |

---

## 🔑 核心概念

### LivingSpec 结构

```json
{
  "meta": {
    "spec_version": "2.1",
    "created_at": "2026-07-05T10:00:00Z",
    "updated_at": "2026-07-05T10:30:00Z",
    "conversation_rounds": 3
  },
  "confirmed": {
    "objective": "为电商团队构建订单自动通知系统",
    "pain_points": ["手动发邮件经常漏发", "客户投诉3次"],
    "capabilities": {
      "always_do": ["自动发送订单确认邮件"],
      "never_do": ["微服务架构"]
    },
    "constraints": {
      "platform": "阿里云",
      "tech_stack": ["Vue", "Node.js"],
      "data_source": ["订单数据库"]
    }
  },
  "inferred": [...],
  "guardrails": {...},
  "core_summary": "≤5KB 核心摘要，下游 Agent 优先读取此字段快速理解全貌",
  "narrative": "完整的用户需求叙述（苏格拉底对话提取，主体）",
  "requirement_index": [
    {"id": "REQ-001", "description": "...", "priority": "P0", "source_section": "confirmed.objective"}
  ],
  "semantic_anchors": [
    {
      "name": "sessions_spawn",
      "category": "platform_api",
      "constraint": "必须用 sessions_spawn 调度子 Agent，禁止 Python import",
      "source_quote": "对话中用户提到的原文",
      "confidence": 0.9,
      "applicable_to": ["all"]
    }
  ],
  "solution_pro_hints": {
    "focus_areas": ["订单状态监听", "邮件模板引擎"],
    "complexity_notes": ["需要支持批量发送"]
  }
}
```

> **重要**：`conversation_digest` 已废弃，不再使用。对话日志存储在 `spec/conversation_log.json`。
> 
> **下游读取策略**（Solution Pro / Ship Pro）：
> 1. 先读 `core_summary`（快速理解全貌）
> 2. 按需深入读 `narrative` 的特定段落
> 3. `requirement_index` 用于 REQ-ID 追溯
> 4. `semantic_anchors` 全链路透传（不可变实体）

### Harness 2.0.0 评估

**Layer 1 (S1-S10)**：10 项结构化检查
- S1-S10 分别检查 objective、pain_points、capabilities、constraints 等字段的完整性和可执行性

**Layer 2 (SC1-SC2)**：2 项语义检查
- SC1: InferenceAuditGate — 检查 inferred 字段是否合理
- SC2: TrajectoryAuditGate — 检查对话轨迹是否一致

**决策**：
- `PASS`: 所有 S1-S10 PASS 且 SC1-SC2 PASS
- `WARN`: 部分 S1-S10 WARN 或 SC1-SC2 WARN
- `FAIL`: 任何 S1-S10 FAIL 或 SC1-SC2 FAIL

---

## ⚠️ 常见问题

### Q1: 对话超过 max_rounds 还没完成？
**A**: Spec Pro 会自动 `safety_stop`，此时 LivingSpec 可能不完整。可以选择：
1. 接受当前 LivingSpec（质量可能较低）
2. 手动编辑 LivingSpec 补充关键信息
3. 重新开始 Spec Pro 会话

### Q2: Harness 评估 FAIL 怎么办？
**A**: 查看 `harness_report.json` 中的具体失败项，通常是：
- 缺少关键字段（objective、pain_points）
- 字段过于笼统（capabilities 太抽象）
- 约束不合理（constraints 相互矛盾）

可以继续对话补充信息，或手动编辑 LivingSpec。

### Q3: 如何跳过 Spec Pro 直接跑 Solution Pro？
**A**: Solution Pro 支持直接输入 topic，会使用轻量级推断生成 LivingSpec。但质量可能不如完整的 Spec Pro 流程。

---

## 📝 示例对话

**用户**: "帮我做一个电商订单自动通知系统"

**Agent**: 
```python
exec("PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py init '电商订单自动通知系统'")
# 返回 session_id = "spec_spec_abc123"
```

**Spec Pro (Round 1)**: "请描述一下当前的订单处理流程，以及您希望自动化的具体场景？"

**用户**: "现在每天50个订单，手动发邮件通知，经常漏发，客户投诉3次了"

**Agent**:
```python
exec("PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py next_round spec_spec_abc123 '现在每天50个订单，手动发邮件通知，经常漏发，客户投诉3次了'")
exec("PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py read_output spec_spec_abc123")
# 返回下一个问题
```

**Spec Pro (Round 2)**: "您希望系统支持哪些通知渠道？邮件、短信、还是其他？"

**用户**: "邮件就行，但要支持批量发送"

**Agent**: 继续调用 `next_round` 和 `read_output`...

**最终**：
```python
exec("PYTHONPATH=. python3 domains/spec_pro/spec_pro_api.py status spec_spec_abc123")
# 返回 status = "done"

exec("PYTHONPATH=. python3 domains/spec_pro/eval/harness.py spec_spec_abc123")
# 返回 decision = "PASS"

# LivingSpec 已就绪，可以进入 Solution Pro
```

---

## 🔗 相关文档

- [LivingSpec Schema](schemas.py)
- [Harness 2.0.0 评估逻辑](eval/harness.py)
- [Prompt 模板](prompts/)
- [Solution Pro SKILL.md](../solution/SKILL.md)

### V2.2.0 变更（2026-07-08）
- **域推断重构**: 删除 `infer_domain_from_input()` 规则引擎 → parse.md LLM 自推断 domain_type
- **三层门控**: gate_harness_decision Layer 1(代码) + Layer 2(LLM) + Layer 3(合并)
- **反模式修复**: 2 个 P1 修复
  - Jaccard bigram 语义去重 → 精确匹配（语义去重交 LLM）
  - 子串匹配做修改定位 → 精确匹配
- **Prompt 泛化**: parse/guide/harness/structure 4 个核心 prompt 清除硬编码，加入多域示例
- **契约层增强**: compute_complexity_score + gate_harness_decision + merge_semantic_anchors
- **测试**: 52 passed
