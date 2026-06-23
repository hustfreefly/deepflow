# Spec Pro - Agent 执行指南

> **版本**: V2.1 | **最后更新**: 2026-06-22  
> **架构**: 多轮对话 → LivingSpec 构建 → Harness V2 评估 → Solution Pro 上下文注入  
> **核心理念**: 通过结构化对话提取需求，生成可执行的 LivingSpec

---

## 🚀 主 Agent 执行步骤

### Step 1: 初始化 Spec Pro 会话

**触发条件**：用户说"帮我分析需求"、"做一个XXX系统"、"Spec Pro"

**执行逻辑**：
```python
# 主 Agent 调用 spec_pro_api.py
exec(
    command="python3 domains/spec_pro/spec_pro_api.py init '{user_input}' --mode standard --scenario genesis",
    workdir="/Users/allen/.openclaw/workspace/.deepflow"
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
- `blackboard/{session_id}/spec/living_spec.json` — 初始 LivingSpec
- `blackboard/{session_id}/spec/conversation_log.json` — 对话日志

---

### Step 2: 多轮对话（自动循环）

**触发条件**：用户回复 Spec Pro 的提问

**执行逻辑**：
```python
# 1. 提交用户回复
exec(
    command="python3 domains/spec_pro/spec_pro_api.py next_round {session_id} '{user_response}'",
    workdir="/Users/allen/.openclaw/workspace/.deepflow"
)

# 2. 读取 Orchestrator 生成的下一个问题
exec(
    command="python3 domains/spec_pro/spec_pro_api.py read_output {session_id}",
    workdir="/Users/allen/.openclaw/workspace/.deepflow"
)

# 3. 检查状态
exec(
    command="python3 domains/spec_pro/spec_pro_api.py status {session_id}",
    workdir="/Users/allen/.openclaw/workspace/.deepflow"
)
```

**状态判断**：
- `status == "collecting"` → 继续对话，把 `next_question` 发给用户
- `status == "done"` → 跳到 Step 3
- `status == "safety_stop"` → 强制停止（超过 max_rounds）

---

### Step 3: Harness V2 评估

**触发条件**：`status == "done"`

**执行逻辑**：
```python
# 运行 Harness 评估
exec(
    command="python3 domains/spec_pro/eval/harness.py {session_id}",
    workdir="/Users/allen/.openclaw/workspace/.deepflow"
)

# 读取评估报告
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
# 读取最终 LivingSpec
living_spec = read(
    path="blackboard/{session_id}/spec/living_spec.json"
)

# 传递给 Solution Pro
exec(
    command="python3 domains/solution_pro/SKILL.md --living-spec blackboard/{session_id}/spec/living_spec.json",
    workdir="/Users/allen/.openclaw/workspace/.deepflow"
)
```

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
    "created_at": "2026-06-22T10:00:00Z",
    "updated_at": "2026-06-22T10:30:00Z",
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
  "conversation_digest": {
    "summary": "用户需求摘要...",
    "key_excerpts": [
      {
        "excerpt": "每天50多个订单要手动发邮件通知",
        "dimension": "pain_points",
        "importance": "critical",
        "source_round": 1
      }
    ],
    "full_conversation_path": "spec/conversation_log.json"
  }
}
```

### Harness V2 评估

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
exec("python3 domains/spec_pro/spec_pro_api.py init '电商订单自动通知系统'")
# 返回 session_id = "spec_spec_abc123"
```

**Spec Pro (Round 1)**: "请描述一下当前的订单处理流程，以及您希望自动化的具体场景？"

**用户**: "现在每天50个订单，手动发邮件通知，经常漏发，客户投诉3次了"

**Agent**:
```python
exec("python3 domains/spec_pro/spec_pro_api.py next_round spec_spec_abc123 '现在每天50个订单，手动发邮件通知，经常漏发，客户投诉3次了'")
exec("python3 domains/spec_pro/spec_pro_api.py read_output spec_spec_abc123")
# 返回下一个问题
```

**Spec Pro (Round 2)**: "您希望系统支持哪些通知渠道？邮件、短信、还是其他？"

**用户**: "邮件就行，但要支持批量发送"

**Agent**: 继续调用 `next_round` 和 `read_output`...

**最终**：
```python
exec("python3 domains/spec_pro/spec_pro_api.py status spec_spec_abc123")
# 返回 status = "done"

exec("python3 domains/spec_pro/eval/harness.py spec_spec_abc123")
# 返回 decision = "PASS"

# LivingSpec 已就绪，可以进入 Solution Pro
```

---

## 🔗 相关文档

- [LivingSpec Schema](schemas.py)
- [Harness V2 评估逻辑](eval/harness.py)
- [Prompt 模板](prompts/)
- [Solution Pro SKILL.md](../solution/SKILL.md)
