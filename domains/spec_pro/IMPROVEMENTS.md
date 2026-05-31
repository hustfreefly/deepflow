# Spec Pro 改进方案

> 基于 6 轮测试的完整复盘，识别出 8 个设计层面的问题。
> 每个问题标注了：根因定位 → 影响范围 → 改进方案 → 改动文件 → 工作量。

---

## 问题总览

| # | 严重性 | 问题 | 一句话根因 | 影响 |
|---|--------|------|-----------|------|
| P1 | 🔴 致命 | 管线太慢，每轮 3-5 分钟 | 每轮 3-4 次串行 subagent spawn | 6 轮耗时 30 分钟 |
| P2 | 🔴 致命 | 问题反复重复 | QuestionWorker 没有对话记忆 | 用户角色被问 5 次，风险被问 4 次 |
| P3 | 🔴 致命 | 评分不区分"缺失"和"拒绝" | assess.md 硬编码 checklist | users 永远 0 分，系统永远不结束 |
| P4 | 🟡 重要 | 反馈信息丢失 | round_result 只返回总分 | 用户看不到 7 维逐项进展 |
| P5 | 🟡 重要 | Process Guard 无力纠正 | 只能追加文字建议，不能修改规则 | 检测到问题但每轮都犯同样的错 |
| P6 | 🟡 重要 | 只有提问模式，没有方案确认模式 | 状态机设计缺陷 | 信息够了还在问，不会主动给草稿 |
| P7 | 🟢 改进 | Spec 膨胀无去重 | merge_spec.py 只追加不去重 | 19 条重复质量属性浪费 token |
| P8 | 🟢 改进 | 阈值僵硬无停滞检测 | MODE_CONFIG 固定值 | 用户不配合时，跑满 10 轮才停 |

---

## P1：管线太慢 — 每轮 3-5 分钟

### 根因定位

`coordinator.py` 的 `_collecting_phase_instructions()` 定义了串行流程：

```
ResponseWorker (spawn → yield, 60-90s)
  → merge_spec.py (exec, 1s)
  → AssessWorker (spawn → yield, 60-90s)
  → process_guard.py (exec, 1s)
  → QuestionWorker (spawn → yield, 30-60s)
  → 写 round_result (exec, 1s)
```

每轮 **3-4 次 subagent spawn + yield**。每次 spawn 的 overhead（创建 session → 加载上下文 → LLM 推理 → 写文件 → 完成通知）至少 30-90 秒。

### 影响

- 单次用户回答 → 等待 3-5 分钟才看到下一轮问题
- 对比：直接和一个大模型对话，10 分钟内可完成全部需求收集

### 改进方案

**方案 A（最小改动）：ResponseWorker + AssessWorker 并行**

AssessWorker 只需要 merge 后的 living_spec，不依赖 ResponseWorker 的解析过程。可以：
1. spawn ResponseWorker
2. 等 ResponseWorker 完成 → merge_spec.py
3. **同时 spawn** AssessWorker + ProcessGuard（并行）
4. 等 AssessWorker 完成 → spawn QuestionWorker

预估：每轮从 3-5 分钟 → 2-3 分钟。

**方案 B（推荐）：合并为单次 spawn**

把 ResponseWorker + AssessWorker + QuestionWorker 合并为一个 Worker，一次 spawn 完成全部推理：

```
1. 解析用户回答 → 生成 parsed_updates
2. 评估当前 Spec 质量 → 生成 dimension_scores
3. 基于评估结果生成下一轮问题
```

一个 LLM 调用就能完成这三步，因为它们本质上是一个连续的推理链。

预估：每轮 30-60 秒。

**方案 C（最彻底）：去掉 SubAgent，直接在主 Agent 上下文执行**

整个 Spec Pro 的"推理"部分（解析回答、评估质量、生成问题）完全可以在主 Agent 的上下文中完成。主 Agent 已经有 living_spec.json 和 conversation_log.json 的完整上下文。

只需要保留 `merge_spec.py` 和 `process_guard.py` 作为 exec 脚本。

预估：每轮 10-30 秒。

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `coordinator.py` | `_collecting_phase_instructions()` 重写流程编排 |
| `prompts/orchestrator.md` | 如果是方案 B/C，改为单 Worker 或多步骤合一 |
| `models.py` | `WORKER_TIMEOUT` 可能需要调整 |

### 工作量评估

- 方案 A：半天
- 方案 B：1-2 天
- 方案 C：2-3 天（需要重新设计主 Agent 的 prompt）

---

## P2：问题反复重复 — QuestionWorker 没有对话记忆

### 根因定位

`guide.md` 定义的 QuestionWorker 输入**只有两个文件**：

```
- spec/living_spec.json
- spec/quality_report.json
```

**缺失**：
- `conversation_log.json`（历史对话）
- `stages/round_XX_questions.json`（之前问过的问题）
- `stages/round_XX_response.json`（用户的回答和 meta_signals）

`coordinator.py` 的 `_collecting_phase_instructions()` Step 6 里，QuestionWorker 的上下文注入也只写了：

```
- 读取: {Blackboard}/spec/living_spec.json
- 读取: {Blackboard}/spec/quality_report.json
- 写入: {Blackboard}/stages/round_{nn}_questions.json
```

**没有注入任何历史对话信息。**

### 测试中的表现

| 维度 | 被问次数 | 轮次 | 用户立场 |
|------|---------|------|---------|
| 用户角色/画像 | 5 次 | R1, R2, R3, R4, R5 | R2 已回答"泛化方案"，R5 明确说"不要再问" |
| 风险 | 4 次 | R2, R3, R4, R6 | R4 明确说"风险是设计方的责任" |
| 引用质量 | 4 次 | R2, R3-1, R3-2, R4 | R2 已给出详细回答 |

### 改进方案

**必须注入的上下文**：

1. `conversation_log.json` 的 `meta_directives` 和 `stop_asking_dimensions`
2. 上一轮的 `questions`（让 Worker 知道刚问了什么）
3. 上一轮的 `response` 的 `meta_signals`（用户是否表达了不耐烦）

**在 guide.md 中增加硬性规则**：

```markdown
## 已问去重（硬性规则）

在生成问题前，必须检查以下信息：

1. 读取 conversation_log.json 中所有轮的 meta_directives
   - 如果用户明确说"不要再问 X"，则该维度**禁止提问**
   
2. 读取上一轮 questions.json
   - 如果某个维度的某类问题已经问过且用户已回答，不再重复

3. 读取上一轮 response.json 的 meta_signals
   - 如果 directive_stop_asking = true，遵守 stop_asking_dimensions
   - 如果 user_said_enough = true，减少问题数量到 1-2 个
```

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `prompts/guide.md` | 增加"已问去重"硬性规则段 |
| `coordinator.py` | `_collecting_phase_instructions()` 给 QuestionWorker 注入 conversation_log + 上轮 questions + 上轮 response |

### 工作量评估

- 半天（主要是 prompt 修改 + coordinator 注入逻辑）

---

## P3：评分不区分"缺失"和"用户主动拒绝"

### 根因定位

`assess.md` 的评分规则是硬编码的 checklist：

```
users 有 1+ 角色: +40
角色有 count/key_needs: +30
key_scenarios 有 2+ 场景: +30
```

如果 users 字段为空 → **0 分**。

但用户 R2 就说了"面向普通用户，不区分角色"，R5 说"不要再问用户相关的问题"。这是**用户主动选择**，不是信息缺失。

### 影响

- users 维度永远 0 分（权重 15%，永久扣 15 分）
- QuestionWorker 被驱动反复追问 users
- 总分永远到不了 75 分阈值
- 系统永远不结束（直到 max_rounds=10 safety_stop）

**这是个死循环**：评分低 → 追问 → 用户拒绝 → 评分还是低 → 继续追问

### 改进方案

**方案 1：living_spec 增加 `user_directives` 字段**

在 `LivingSpec` dataclass 和 living_spec.json 中新增：

```json
{
  "user_directives": [
    {
      "dimension": "users",
      "directive": "deliberately_omitted",
      "reason": "用户明确表示不需要用户角色差异化，不要再问",
      "round_declared": 5
    }
  ]
}
```

**方案 2：assess.md 评分规则增加 `deliberately_omitted` 处理**

```markdown
## 特殊状态：deliberately_omitted

如果某个维度在 user_directives 中标记为 deliberately_omitted：
- 该维度**不扣分**，给默认分 50（表示"用户选择不提供，非缺失"）
- 该维度不出现在 top_missing 中
- 该维度不计入维度分差检查
```

**方案 3：ResponseWorker 输出 user_directives**

在 `parse_response.md` 中增加：

```markdown
### 用户指令检测

如果用户明确说"不要再问 X"、"X 不需要考虑"等：
- 在 parsed_updates 中新增 user_directives 数组
- 每条指令包含：dimension, directive, reason

示例输出：
```json
"parsed_updates": {
  "user_directives": [
    {
      "dimension": "users",
      "directive": "deliberately_omitted",
      "reason": "用户原话：'不要再问用户相关的问题'"
    }
  ]
}
```
```

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `models.py` | `LivingSpec` dataclass 增加 `user_directives` 字段 |
| `merge_spec.py` | 增加 `merge_user_directives()` 函数 |
| `prompts/parse_response.md` | 增加"用户指令检测"段 |
| `prompts/assess.md` | 评分规则增加 deliberately_omitted 处理 |
| `prompts/guide.md` | 检查 user_directives，跳过被标记的维度 |

### 工作量评估

- 1 天（需要改 5 个文件，但每个改动量不大）

---

## P4：反馈信息丢失 — round_result 只返回总分

### 根因定位

`coordinator.py` 的 `_collecting_phase_instructions()` 在 Step 6 定义 round_result.json：

```json
{
  "action": "questions",
  "round": N,
  "questions": [...],
  "quality": {"overall_score": N, "level": "C"},
  "inferred_items": [...]
}
```

`quality` 字段**只有总分和等级**，7 维逐项分数被丢弃了。

但 `quality_report.json` 里有完整的 7 维数据，`quality_trajectory.json` 里有历史对比数据。

### 影响

用户每轮只看到 "52 分 Level C"，不知道：
- 哪些维度提升了
- 哪些维度没变
- 哪些维度下降了
- 距离目标还差多远

### 改进方案

round_result.json 的 quality 字段改为：

```json
{
  "quality": {
    "overall_score": 52,
    "level": "C",
    "threshold": 75,
    "dimension_scores": {
      "objective": {"score": 55, "prev_score": 40, "delta": 15, "status": "up"},
      "users": {"score": 10, "prev_score": 0, "delta": 10, "status": "up", "note": "deliberately_omitted"},
      "capabilities": {"score": 100, "prev_score": 70, "delta": 30, "status": "up"},
      "quality_attributes": {"score": 70, "prev_score": 70, "delta": 0, "status": "flat"},
      "constraints": {"score": 30, "prev_score": 30, "delta": 0, "status": "flat"},
      "integration": {"score": 100, "prev_score": 50, "delta": 50, "status": "up"},
      "risks": {"score": 35, "prev_score": 35, "delta": 0, "status": "flat"}
    },
    "top_improvements": [
      {"dimension": "integration", "delta": 50, "reason": "集成目标和平台定位明确"},
      {"dimension": "capabilities", "delta": 30, "reason": "never_do 层补充了能力边界"}
    ],
    "top_missing": [
      {"dimension": "constraints", "reason": "缺少 timeline 和 tech_stack"},
      {"dimension": "risks", "reason": "未识别关键风险和外部依赖"}
    ]
  }
}
```

主 Agent 收到后展示为表格：

```
📊 需求质量：52/100 (Level C) — 目标 75 分

┌──────────────┬──────┬──────┬────────┐
│ 维度          │ 上轮  │ 本轮  │ 变化   │
├──────────────┼──────┼──────┼────────┤
│ 目标清晰度    │ 40   │ 55   │ +15 ↑  │
│ 用户定义      │ 0    │ 10   │ +10 ↑  │
│ 能力边界      │ 70   │ 100  │ +30 ↑  │
│ 质量属性      │ 70   │ 70   │ —      │
│ 约束条件      │ 30   │ 30   │ —      │
│ 系统集成      │ 50   │ 100  │ +50 ↑  │
│ 风险与假设    │ 35   │ 35   │ —      │
└──────────────┴──────┴──────┴────────┘

✅ 本轮提升：integration(+50), capabilities(+30), objective(+15)
⏳ 待补齐：constraints(缺timeline/tech_stack), risks(缺风险识别)
```

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `coordinator.py` | `_collecting_phase_instructions()` 和 `_init_phase_instructions()` 修改 round_result 组装逻辑 |
| `models.py` | `RoundAction` 或新增 `QualityDisplay` dataclass |

### 工作量评估

- 半天

---

## P5：Process Guard 无力纠正

### 根因定位

`process_guard.py` 能检测到 3 类异常：
- 进度过慢（delta 低于预期）
- 推断确认率低
- 维度分差过大

但输出只是一段 `adjustment_instruction` 文本，被**追加**到 QuestionWorker 的 task prompt 末尾。

**问题**：
1. 这段文字只是"建议"，QuestionWorker 的 prompt 规则优先级更高
2. 比如 prompt 写"评分最低的维度优先提问"，Process Guard 说"维度分差太大，别问了" → 矛盾
3. Process Guard 不能修改 QuestionWorker 的 `target_dimensions` 列表

### 测试中的表现

Process Guard 每轮都检测到"维度分差过大: capabilities=100 vs users=0"，每轮都输出调整指令，但 QuestionWorker 每轮都继续问 users 相关的问题。

### 改进方案

**方案 1：Process Guard 直接修改 QuestionWorker 的输入参数**

Process Guard 的输出不只是文本建议，而是一个结构化的 JSON：

```json
{
  "anomalies": [...],
  "adjustments": {
    "remove_dimensions": ["users"],
    "force_dimensions": ["constraints", "risks"],
    "max_questions": 2,
    "strategy_override": "implication"
  }
}
```

QuestionWorker 的 prompt 中增加规则：

```markdown
## Process Guard 调整（优先级高于默认策略）

如果收到 Process Guard 的 adjustments：
- remove_dimensions 中的维度**禁止提问**
- force_dimensions 中的维度**必须包含至少 1 个问题**
- strategy_override 覆盖默认的轮次策略
```

**方案 2（更简单）：在 coordinator.py 中硬编码**

在 `_collecting_phase_instructions()` 中，如果 Process Guard 输出了 anomalies，直接在 QuestionWorker 的 task 中注入：

```
⚠️ 以下维度已被 Process Guard 锁定，本轮禁止提问：users
本轮必须覆盖的维度：constraints, risks
```

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `process_guard.py` | 输出结构化 adjustments JSON（不只是文本） |
| `coordinator.py` | 读取 adjustments 并注入 QuestionWorker 上下文 |
| `prompts/guide.md` | 增加 Process Guard 调整优先级规则 |

### 工作量评估

- 半天

---

## P6：只有提问模式，没有方案确认模式

### 根因定位

`coordinator.py` 的状态机：

```
START → PARSING → COLLECTING → ASKING → CONFIRMING → COMPLETED
```

进入 CONFIRMING 的唯一条件是 `overall_score >= threshold (75)`。

但如果分数永远上不去（比如 users=0 导致永久扣分），就**永远进不了确认阶段**。

`RoundAction` 枚举只有：`QUESTIONS | SUMMARY | DONE | ERROR | SAFETY_STOP`。

没有 `PROPOSAL`（给用户看草稿让确认/修改）动作。

### 测试中的表现

R2 之后用户已经给出了大量有效信息（用户角色、benchmark、成本约束），信息量已经足够生成一份 Spec 草稿。但系统继续问了 4 轮同样的问题。

### 改进方案

**增加停滞检测 + 自动切换到 PROPOSAL 模式**

在 `process_guard.py` 或 coordinator 中增加：

```python
def check_stagnation(trajectory: list) -> bool:
    """连续 2 轮 delta < 3 分 → 停滞"""
    if len(trajectory) < 3:
        return False
    last_two = trajectory[-2:]
    return all(abs(p.get("delta", 0)) < 3 for p in last_two)
```

当检测到停滞时：
1. 不再问问题
2. 直接输出当前 Spec 的草稿（summary）
3. 让用户确认/修改
4. 用户修改后重新评估

```python
# coordinator.py 中的逻辑
if stagnation_detected and current_round >= 3:
    action = "proposal"  # 而不是 "questions"
    # 输出 Spec 草稿 + "以下维度信息不足，需要你确认是否继续补充"
```

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `models.py` | `RoundAction` 增加 `PROPOSAL` 枚举 |
| `coordinator.py` | `_collecting_phase_instructions()` 增加停滞检测分支 |
| `process_guard.py` | 增加 `check_stagnation()` 函数 |
| `prompts/structure.md` | 增加 proposal 模式的输出格式 |

### 工作量评估

- 1 天

---

## P7：Spec 膨胀无去重

### 根因定位

`merge_spec.py` 的 `append_unique()` 函数用的是**精确匹配去重**：

```python
def append_unique(target: list, source: list, key: str = None) -> None:
    if key:
        existing = {item.get(key) for item in target if isinstance(item, dict)}
        for item in source:
            if isinstance(item, dict):
                item_key = item.get(key)
                if item_key not in existing:
                    target.append(item)
```

但 quality_attributes 是 dict 类型，没有指定 key，所以用的是 `if item not in target` 的精确匹配。

**问题**：同一个意思，不同轮次可能用不同措辞：
- "引用质量（非仅数量）是用户最看重的差异化能力"
- "引用数据源和网页质量高，非低质量网页"
- "引用的数据源和网页质量很高，非低质量来源"

这三条语义相同但字符串不同，全部被追加。

### 测试中的表现

`quality_attributes` 从初始 2 条膨胀到 19 条，大量重复（"引用质量"出现 5 次，"研究体验统一标准"出现 6 次）。

### 改进方案

**在 merge_spec.py 中增加语义去重步骤**

方案 A（简单）：对 quality_attributes 增加基于 `category` 字段的去重：

```python
# merge quality_attributes 时按 category 去重
new_qa = updates.get("quality_attributes", [])
existing_qa = confirmed.get("quality_attributes", [])
existing_categories = {item.get("category", "") + "|" + item.get("spec", "")[:20] for item in existing_qa}
for item in new_qa:
    key = item.get("category", "") + "|" + item.get("spec", "")[:20]
    if key not in existing_categories:
        existing_qa.append(item)
        existing_categories.add(key)
```

方案 B（更好）：定期执行 dedup 步骤，由 orchestrator 在每 3 轮触发一次。

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `merge_spec.py` | `merge_confirmed()` 中 quality_attributes 增加 category 级去重 |

### 工作量评估

- 2 小时

---

## P8：阈值僵硬无停滞检测

### 根因定位

`models.py` 中 MODE_CONFIG 是固定值：

```python
MODE_CONFIG = {
    "standard": {"max_rounds": 10, "threshold": 75},
}
```

没有动态调整机制。如果用户不配合某些维度，75 分永远达不到，只能跑满 10 轮然后 safety_stop。

### 改进方案

**动态阈值 + 提前结束**

```python
def calculate_effective_threshold(trajectory: list, user_directives: list) -> int:
    """根据用户配合度动态调整阈值"""
    base = 75
    omitted_count = len(user_directives)
    
    # 每有一个 deliberately_omitted 维度，降低 5 分
    adjustment = omitted_count * 5
    
    # 如果连续 2 轮停滞，再降 5 分
    if is_stagnated(trajectory):
        adjustment += 5
    
    return max(base - adjustment, 50)  # 最低 50 分
```

或者更简单：**在 R5 之后如果分数还在 50-60 之间，自动进入 proposal 模式**（参见 P6）。

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `models.py` | MODE_CONFIG 增加 `min_threshold` 和 `stagnation_rounds` |
| `coordinator.py` | 增加动态阈值计算逻辑 |

### 工作量评估

- 半天

---

## 实施优先级

### 第一优先级（解决核心体验问题）

| 改什么 | 改哪些文件 | 工作量 |
|--------|-----------|--------|
| P1: 合并 Worker 提速 | coordinator.py, prompts/ | 1-2 天 |
| P2: QuestionWorker 加记忆 | prompts/guide.md, coordinator.py | 半天 |
| P3: 评分区分拒绝 | models.py, merge_spec.py, prompts/ | 1 天 |

**改完这三个**：体验从"绕圈 30 分钟"变成"3-4 轮 10 分钟出结果"。

### 第二优先级（补全功能）

| 改什么 | 改哪些文件 | 工作量 |
|--------|-----------|--------|
| P4: 反馈 7 维分数 | coordinator.py | 半天 |
| P5: Process Guard 有力 | process_guard.py, coordinator.py | 半天 |
| P6: 增加 PROPOSAL 模式 | models.py, coordinator.py | 1 天 |

### 第三优先级（打磨）

| 改什么 | 改哪些文件 | 工作量 |
|--------|-----------|--------|
| P7: Spec 去重 | merge_spec.py | 2 小时 |
| P8: 动态阈值 | models.py, coordinator.py | 半天 |

---

## 如果只改一个文件

**改 `coordinator.py` 的 `_collecting_phase_instructions()`**。

这一个方法里集中了大部分问题：
- Worker 串行编排（P1）
- QuestionWorker 上下文注入不全（P2）
- round_result 只有总分（P4）
- 没有停滞检测分支（P6/P8）

---

## 如果重新设计

最根本的问题是：**Spec Pro 把需求收集设计成了"审讯"而不是"对话"。**

一个更好的模式：

1. **R1**：解析用户输入 → 生成推断 → 展示 Spec 草稿 + 需要确认的推断
2. **R2**：用户确认/修改 → 更新 Spec → 给出 2-3 个需要澄清的具体点
3. **R3**：用户回答 → 输出最终 Spec + 路由建议

三轮搞定。苏格拉底提问应该是**辅助手段**，不是**唯一手段**。
