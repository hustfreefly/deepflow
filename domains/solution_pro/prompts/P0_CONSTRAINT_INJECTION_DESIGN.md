# P0 约束动态注入设计

> 作者: 小满
> 日期: 2026-07-02
> 状态: 待忠礼确认

---

## 设计原则

两层结合：
1. **动态层**: Meta Planner (LLM) 识别 P0 约束 → 自动注入下游所有 Worker prompt
2. **软约束层**: 所有 Worker 的系统级提示词（可实现性意识、环境感知）

---

## Layer 1: Meta Planner P0 约束识别

### 插入位置
在 Meta Planner prompt 的 Step 1 之前，增加 Step 0。

### Prompt 段落（要加到 planning_meta_planner.md）

```markdown
## Step 0: 基础约束识别（P0 Constraints）

在开始专家规划之前，先识别**不可违反的基础约束**。
这些约束将自动注入到所有下游 Worker 的 prompt 中，确保方案在正确的边界内设计。

### 识别三个维度

**维度 1: 运行环境约束 (platform)**
- 这个方案最终在什么环境上运行？（云平台、本地服务器、特定框架、特定平台）
- 该环境有哪些固有能力？哪些是它做不到的？
- 从输入数据中推断运行环境，不要猜测
- 如果输入提到特定平台名，该平台的能力边界就是硬约束

**维度 2: 业务红线约束 (business)**
- 需求中明确声明的"必须"、"不能"、"禁止"
- 数据合规性要求（GDPR、数据本地化等）
- SLA 要求（延迟、可用性、吞吐量）

**维度 3: 技术边界约束 (technical)**
- 需求暗示的技术限制
- 实时系统有时间约束，分布式系统有一致性约束
- 安全系统有加密约束，AI 系统有模型能力约束

### 判断标准
一个约束是 P0 当且仅当：
- 违反它 = 整个方案不可用（不是"不好"，是"不能跑"）
- 它不依赖于设计选择，而是客观存在的边界
- 任何合理的方案设计都必须遵守它

### 输出格式
在输出 JSON 中增加字段 `p0_constraints`：

```json
{
  "p0_constraints": [
    {
      "id": "P0-001",
      "category": "platform",
      "description": "具体约束描述（一句话）",
      "reasoning": "为什么这是 P0（不可违反）",
      "downstream_impact": "这个约束对下游 Worker 的设计意味着什么"
    }
  ]
}
```
```

---

## Layer 2: 系统级软约束

### 插入位置
在 `_build_phase_task()` 方法中，所有 Worker prompt 末尾自动追加。

### 软约束文本

```markdown
## 系统级约束（自动注入，不可跳过）

### 1. 可实现性
你的输出必须区分「设计意图」和「实现路径」：
- ❌ "使用微服务架构"（只有意图，没有路径）
- ✅ "使用 3 个独立进程，通过 HTTP API 通信，服务注册使用 Consul"（有实现路径）

### 2. P0 约束遵守
上游已注入 P0 约束列表。你的输出不得违反这些约束。
如果某个需求与 P0 冲突，标注 `[P0_CONFLICT: P0-XXX]` 并说明为什么。

### 3. 环境感知
你的方案必须在声明的运行环境中可执行。
不要设计该环境不存在的机制。如果确实需要某个不存在的机制，
标注 `[NEEDS_EXTENSION: 描述]` 并说明需要什么扩展。
```

---

## 代码实现: _build_phase_task() 修改

### 当前代码（PlanningOrchestrator._build_phase_task）

```python
def _build_phase_task(self, role, role_desc, prompt_key,
                      context, output_stage, instructions):
    prompt_content = self._prompts.get(prompt_key, "")
    # ... 序列化 context ...
    task = f"""# {role}
> {role_desc}
## Prompt
{prompt_content[:5000]}
## 上游上下文
{context_str}
## 指令
{instructions}
## 输出
将结果写入 Blackboard stage: `{output_stage}`
"""
    return task
```

### 修改后

```python
def _build_phase_task(self, role, role_desc, prompt_key,
                      context, output_stage, instructions):
    prompt_content = self._prompts.get(prompt_key, "")
    
    # --- Layer 1: 动态注入 P0 约束 ---
    p0_block = self._load_p0_constraints_prompt_block()
    
    # --- Layer 2: 系统级软约束 ---
    soft_constraints = self._get_system_soft_constraints()
    
    # ... 序列化 context（保持不变）...
    
    task = f"""# {role}
> {role_desc}

## P0 约束（由 Meta Planner 识别，不可违反）
{p0_block}

## Prompt
{prompt_content[:5000] if prompt_content else "(使用以下指令)"}

## 上游上下文
{context_str}

## 指令
{instructions}

{soft_constraints}

## 输出
将结果写入 Blackboard stage: `{output_stage}`
"""
    return task


def _load_p0_constraints_prompt_block(self) -> str:
    """从 blackboard 读取 P0 约束，格式化为 prompt 段落"""
    try:
        p0_data = self.blackboard.read_json("stages/p0_constraints.json")
        if not p0_data:
            return "(Meta Planner 未识别 P0 约束)"
        
        constraints = p0_data.get("p0_constraints", [])
        if not constraints:
            return "(Meta Planner 未识别 P0 约束)"
        
        lines = []
        for c in constraints:
            lines.append(f"- **{c['id']}** [{c['category']}]: {c['description']}")
            lines.append(f"  - 影响: {c.get('downstream_impact', 'N/A')}")
        
        return "\n".join(lines)
    except Exception:
        return "(P0 约束加载失败，请基于常识判断)"


def _get_system_soft_constraints(self) -> str:
    """系统级软约束，自动追加到所有 Worker prompt"""
    return """## 系统级约束（自动注入，不可跳过）

1. **可实现性**: 你的输出必须区分「设计意图」和「实现路径」。
   - ❌ "使用微服务架构"（只有意图）
   - ✅ "使用 3 个独立进程，通过 HTTP API 通信"（有实现路径）

2. **P0 约束遵守**: 上游已注入 P0 约束列表。你的输出不得违反这些约束。
   如果某个需求与 P0 冲突，标注 `[P0_CONFLICT: P0-XXX]` 并说明为什么。

3. **环境感知**: 你的方案必须在声明的运行环境中可执行。
   不要设计该环境不存在的机制。如果确实需要，标注 `[NEEDS_EXTENSION: 描述]`。
"""
```

---

## Convergence Planner 改动

在 Convergence Planner prompt 中增加 P0 约束合并段落：

```markdown
## P0 约束合并

所有 Expert Planner 输出的 p0_constraints 需要合并：
- 相同语义的约束去重（语义相同，不是字符串相同）
- 冲突的 P0 约束标注 [P0_CONFLICT] 并在 conflict_resolutions 中说明
- 输出到 `p0_constraints_merged` 字段

输出格式：
```json
{
  "p0_constraints_merged": [
    {
      "id": "P0-001",
      "category": "platform",
      "description": "...",
      "source_experts": ["expert_architecture", "expert_infrastructure"],
      "conflict_resolved": false
    }
  ]
}
```
```

---

## 信息流总结

```
living_spec → Meta Planner
  → Step 0: 识别 P0 约束（运行环境 + 业务红线 + 技术边界）
  → 输出 p0_constraints → 写入 stages/p0_constraints.json

Expert Planners（收到 P0 约束 + 软约束）
  → 各自也输出 p0_constraints（从自己视角补充）

Convergence Planner
  → 合并所有 p0_constraints → p0_constraints_merged
  → 写回 stages/p0_constraints.json

Summary Workers（收到 P0 约束 + 软约束）
  → 产出的方案自然遵守这些约束
  → 标注 NEEDS_EXTENSION 的机制被明确识别

Verification（独立 LLM Judge）
  → 额外检查 "P0 约束是否被遵守"
  → 检查 NEEDS_EXTENSION 标注是否合理
```

---

## 预期效果

**改之前**:
- Meta Planner 不识别 P0 → Expert Planners 在真空中设计
- Worker 不知道运行环境 → 产出论文风格方案
- Verification 只检查文本匹配 → 41/41 PASS 无意义

**改之后**:
- Meta Planner 自动识别 P0（LLM 语义理解）→ 动态注入
- Worker 知道 P0 约束 + 软约束 → 产出可实现方案
- Verification 额外检查 P0 覆盖 → 真正有意义的验证
