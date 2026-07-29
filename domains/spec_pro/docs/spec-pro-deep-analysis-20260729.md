# Spec Pro 深度分析报告

> 日期：2026-07-29
> 分析团队：4 位独立专家（Prompt 架构 / 信息流契约 / AI Native 纯度 / 对话体验）
> 分析范围：Spec Pro 全部代码 + 6 个 prompt 文件

---

## 一、核心结论（Executive Summary）

### 综合健康度评分

| 维度 | 评分 | 来源 |
|------|:----:|------|
| Prompt 架构质量 | **82/100** | Prompt 架构专家 |
| 信息流守恒 | **78/100** | 契约审计专家 |
| AI Native 纯度 | **74/100** | AI Native 审计专家 |
| 对话用户体验 | **68/100** | 对话设计专家 |
| **综合** | **75/100** | — |

### 三大核心发现

1. **🔴 最大体验缺陷：系统记得"问过什么"，但不记得"你说过什么"**
   - 提问由"最低分维度"驱动，不顺着用户话头聊 → "被审问感"的最大来源
   - 修复方案：引入"话头优先"规则（纯 prompt 改动）

2. **🔴 最大架构缺陷：SemanticAnchor 不可变性被 merge 逻辑违反**
   - `merge_semantic_anchors()` 同名覆盖，违反"只增不改不删"设计原则
   - 修复方案：改为"已存在则跳过"（约 5 行代码）

3. **🔴 最大 AI Native 缺陷：harness.py 的 SemanticGate 是"命名欺诈"**
   - 类名暗示语义分析，实际是关键词计数（检查 "%", "秒", "ms"）
   - 修复方案：重命名为 StructuralGate + 新增 LLM Layer 2

---

## 二、改进建议汇总（按优先级）

### 🔴 P0 — 必须修复（4 项）

| # | 问题 | 根因 | 修复方案 | 工作量 |
|---|------|------|---------|:------:|
| P0-1 | **提问不接话头** | guide.md "最低分维度优先" | 增加"话头优先"规则：用户上轮展开的话题 > 推断验证 > 最低分维度 | 纯 prompt |
| P0-2 | **SemanticAnchor 可被覆盖** | merge_spec.py L284 `anchors_map[name] = anchor` | 改为"已存在则跳过，记录 warning" | ~5 行代码 |
| P0-3 | **SemanticGate 命名欺诈** | harness.py 用关键词计数伪装语义分析 | 重命名为 StructuralGate + 新增 LLM-as-Judge Layer 2 | 中 |
| P0-4 | **意图评分关键词匹配脆弱** | assess.md 用精确中文短语匹配 | 改为语义模式描述，让 LLM 做语义匹配 | 纯 prompt |

### 🟡 P1 — 短期优化（8 项）

| # | 问题 | 修复方案 | 工作量 |
|---|------|---------|:------:|
| P1-1 | 问题数量口径矛盾（2-3 vs 3-5 vs 2-5） | 统一为"2-3 默认，硬上限 4"，写入 Pydantic | 低 |
| P1-2 | standard 模式 max_rounds=10 过多 | 降到 6 轮，第 4 轮后允许提前 summary | 改 MODE_CONFIG |
| P1-3 | process_guard.py 僵硬规则引擎 | EXPECTED_DELTA_BY_MODE 改为 LLM 评估进度 | 中 |
| P1-4 | 无收敛检测 → 过度提问 | 增加收敛信号（连续 2 轮 top_missing 相同 → summary） | 纯 prompt |
| P1-5 | 无回答质量评估 | Phase 1.5 新增回答质量评估步骤 | 纯 prompt |
| P1-6 | ProcessGuard 与 deliberately_omitted 脱节 | check_conversation_balance 排除 deliberately_omitted 维度 | ~5 行代码 |
| P1-7 | requirement_index 仅首次生成 | 每轮 _write_living_spec 都重新生成 | ~3 行代码 |
| P1-8 | 一致性检查只能精确匹配 | 用 LLM 做语义矛盾检测 | 中 |

### 🟢 P2 — 长期增强（6 项）

| # | 问题 | 修复方案 |
|---|------|---------|
| P2-1 | safety_stop 是开发者语言 | 强制输出部分小结 + 已完成度 + 补充建议 |
| P2-2 | 无用户退出通道 | 增加"退出意图识别"规则 |
| P2-3 | 苏格拉底类型按轮次映射过于机械 | 改为"按对话状态选类型" |
| P2-4 | 跨域示例偏向产品/项目范式 | 增加泛化原则声明 |
| P2-5 | 边界过滤器用户角色盲区 | 增加用户角色感知（技术型用户放宽 HOW 限制） |
| P2-6 | 新增 scope_boundary 问题类型 | 苏格拉底六类 → 七类 |

---

## 三、各专家详细发现

### 专家 A：Prompt 架构分析

#### 当前设计优势（保留）

| # | 优势 | 为什么有效 |
|---|------|-----------|
| A1 | 三测试边界过滤器（回答者/文档归属/WHAT-HOW） | 纵深防御，三个独立维度交叉验证 |
| A2 | 意图判断式评分 — 从"填空式"到"意图判断式" | 消除"用户说了但字段为空所以扣分"的荒谬循环 |
| A3 | deliberately_omitted 机制 | 尊重用户自主权 |
| A4 | 正反例对比表 | Few-shot 效果极强 |
| A5 | 动态阈值计算 | 避免死锁 |
| A6 | 域上下文注入（YAML 配置驱动） | 扩展性好 |

#### 改进机会

**P0-1：意图评分关键词匹配脆弱**

当前 assess.md L219-225 用精确中文短语匹配（"参考业界最优实践"、"对标 XXX"），用户说"按照行业标准来"、"跟主流做法一致"等变体不会被识别。

**修复**：将关键词列表改为语义模式描述，让 LLM 做语义匹配。同时增加"意图置信度"字段区分"用户懂但委托" vs "用户不懂所以模糊"。

**P0-2：无回答质量评估 → 无法动态调整提问策略**

guide.md 的提问策略只有"按轮次调整类型权重"一个维度，完全不考虑用户上一轮回答的质量。

**修复**：在 assess_guide.md Phase 2 前增加回答质量评估步骤（信息密度/具体度/主动性/参与度），根据回答质量动态调整下轮策略。

**P0-3：inferred 层信息孤儿化风险**

如果用户连续几轮不确认/不拒绝推断，这些推断就永远悬空。

**修复**：连续 2 轮未被确认的推断 → 生成批量确认问题。

**P1-1：边界过滤器用户角色盲区**

当前过滤器假设用户是业务方。但技术创始人本身就能回答设计问题。

**修复**：parse 阶段推断用户角色（business/technical/mixed），边界过滤器根据角色动态调整。

**P1-2：苏格拉底六类缺"范围边界"类型**

新增第 7 类 `scope_boundary`：直接探测"什么在范围内、什么在范围外"。

**P1-3：无收敛检测 → 可能过度提问**

增加收敛信号：(1) 连续 2 轮 top_missing 相同；(2) 用户回答信息密度持续下降；(3) 用户给出元信号。触发 → 建议 action="summary"。

#### 泛化性评估

- **架构层面**：✅ 良好（YAML 配置 + LLM 语义推断 + 7 维度框架）
- **Prompt 示例层面**：⚠️ 中等 — 存在轻微的产品/项目偏向
- **风险点**：所有跨域示例都假设有"用户"角色、量化指标、交付物。非产品型域（研究、创作、政策）可能硬套产品框架
- **建议**：不增加更多域示例，而是增加一条泛化原则声明

---

### 专家 B：信息流与契约审计

#### 信息流全链路

```
用户原始输入 (input.md)
    ↓
ParseWorker (LLM 语义解析)
    ↓ round_NN_parse.json
merge_spec.py (确定性合并)
    ├─ merge_confirmed() → confirmed 层
    ├─ merge_inferred() → inferred 层
    ├─ merge_guardrails() → guardrails
    ├─ merge_semantic_anchors() → semantic_anchors
    └─ merge_conversation_digest() → conversation_digest
    ↓
living_spec.md + living_spec.json (双写)
    ↓
确认阶段 (confirmation)
    ├─ Semantic Anchor 提取 (LLM)
    ├─ 输入要素守恒 Gate (LLM)
    └─ Density Gate (代码)
    ↓
build_handoff_cli.py → spec_handoff_package.json
    ↓
下游 Solution Pro 消费
```

#### 信息丢失风险点

| # | 位置 | 丢失的信息 | 严重程度 | 修复方案 |
|---|------|-----------|:--------:|---------|
| 1 | merge_spec.py:284 | SemanticAnchor 同名覆盖，违反不可变性 | 🔴 高 | 改为"已存在则跳过" |
| 2 | coordinator.py:1362 | requirement_index 仅首次生成，多轮后过时 | 🟡 中 | 每轮强制重新生成 |
| 3 | gate_input_conservation.py:127 | user_input[:5000] 截断 | 🟡 中 | 增大阈值或分段提取 |
| 4 | merge_spec.py | conversation_digest 死代码 | 🟡 低 | 删除 |

#### 契约一致性

| 字段/规则 | Pydantic 验证 | 代码强制 | Prompt 声明 | 状态 |
|-----------|:------------:|:--------:|:----------:|------|
| SemanticAnchor 不可变性 | ❌ 无验证 | ❌ 违反 | ✅ 声明 | 🔴 不一致 |
| core_summary ≥ 10 chars | ✅ | ❌ 无强制 | ❌ 未声明 | ⚠️ 弱约束 |
| requirement_index 非空 | ❌ | ✅ 硬检查 | ✅ | ✅ 一致 |
| conversation_digest | ✅ 定义 | ✅ 合并 | ❌ | 🟡 死代码 |

---

### 专家 C：AI Native 纯度审计

#### 纯度评分

| 维度 | 评分 | 证据 |
|------|:----:|------|
| 语义判断交 LLM | 65 | harness.py SemanticGate 名不副实 |
| 代码只做格式 | 70 | process_guard.py 僵硬规则引擎 |
| 域知识非硬编码 | 85 | YAML 配置驱动 + 开放枚举 |
| 泛化性真实 | 75 | 无跨域测试证据 |
| **综合** | **74** | — |

#### 伪 AI Native 模式

| # | 位置 | 问题 | 严重程度 |
|---|------|------|:--------:|
| 1 | harness.py SemanticGate.check_clarity() | 命名欺诈：关键词计数伪装语义分析 | 🔴 高 |
| 2 | harness.py check_executability() | 字段计数伪装语义 | 🟡 中 |
| 3 | harness.py check_consistency() | 天真矛盾检测（只精确字符串匹配） | 🟡 中 |
| 4 | process_guard.py EXPECTED_DELTA_BY_MODE | 僵硬规则引擎 | 🔴 高 |
| 5 | process_guard.py check_conversation_balance() | 机械维度平衡（不考虑域特性） | 🟡 中 |

#### 泛化性真实评估

- **声称支持**：software / investment / hardware / business / general
- **实际测试**：❓ 无证据（无跨域测试用例）
- **伪泛化风险**：
  - EXPECTED_DELTA_BY_MODE 不区分域
  - check_conversation_balance() 假设维度均衡
  - SUGGESTED_ANCHOR_CATEGORIES 覆盖不全
  - parse.md 域推断示例偏向软件

---

### 专家 D：对话设计与用户体验

#### 用户感受曲线

```
😀 期待期 → 🤔 被理解期 → 😐 疲劳风险期 → 😟 突兀收尾期
Round 0      Round 1-2      Round 3-6       Round 7-10

用户感受曲线: ▁▃▅▆▅▃▃▂▂▁
              ↑        ↑      ↑
            峰值    开始疲劳  信任流失
```

**核心发现**：前 2 轮体验好（边界过滤 + 意图判断 + 推断验证），但第 3 轮后退化为"按维度扫楼"。

#### 用户体验痛点

| # | 痛点 | 根因 | 严重程度 |
|---|------|------|:--------:|
| 1 | 问题由"最低分维度"驱动，不顺着用户话头聊 | guide.md "最低分维度优先" | 🔴 高 |
| 2 | 问题数量上限自相矛盾 | 四处口径不一（2-3 / 3-5 / 2-5） | 🔴 高 |
| 3 | standard 模式 max_rounds=10 过多 | 10 轮 × 5 题 = 50 题 = 尽职调查 | 🔴 高 |
| 4 | 停滞时系统"悄悄放弃" | 动态阈值下调无透明说明 | 🟡 中 |
| 5 | safety_stop 是开发者语言 | 英文系统消息，无部分成果 | 🟡 中 |
| 6 | 无用户退出通道 | 无"就到这里吧"处理协议 | 🟡 中 |

#### 最重要发现

> **系统记得"问过什么"，但不记得"你说过什么"。**

当前链路：`用户回答 → parse → 合并 → 评分 → 找最低分维度 → 出题`

链路里没有"用户上轮说了什么"这个变量。conversation_log.json 只用于去重，不用于话题承接。

**填空思维替代了对话思维**，这是"被审问感"的最大来源。

#### 跨域对话差异

- ✅ 评分层（assess.md）：跨域锚点做得好
- ✅ 上下文注入：机制存在
- ❌ 对话策略层（guide.md）：除了示例换了行业词，策略完全是同一套

**体验裂缝**：
- 投资域：七维度是产品需求框架，套到投资场景会"答非所问"
- 商业域：餐饮老板不懂"集成""接口"，integration 维度持续低分 → 被反复追问

---

## 四、改进路线图

### Phase 1：P0 紧急修复（预计 1-2 天）

1. **guide.md 增加"话头优先"规则**
   - 用户上轮主动展开的话题 > 推断验证 > 最低分维度
   - 要求承接句式："你刚才提到X，我想顺着问…"

2. **merge_semantic_anchors 修复不可变性**
   - 改为"已存在则跳过，记录 warning"
   - 添加测试 `test_semantic_anchor_immutability`

3. **assess.md 意图判断改为语义模式**
   - 从精确短语匹配 → 语义模式描述
   - 增加意图置信度字段

4. **harness.py SemanticGate 重命名**
   - SemanticGate → StructuralGate
   - 新增 LLM Layer 2（可后续补充）

### Phase 2：P1 短期优化（预计 3-5 天）

5. 统一问题数量口径（2-3 默认，硬上限 4）
6. standard 模式 max_rounds 10 → 6
7. process_guard.py 引入 LLM 进度评估
8. 增加收敛检测
9. 增加回答质量评估
10. 修复 ProcessGuard 与 deliberately_omitted 脱节
11. requirement_index 每轮重新生成
12. 一致性检查改为 LLM 语义矛盾检测

### Phase 3：P2 长期增强（预计 1-2 周）

13. safety_stop 优雅收尾
14. 用户退出通道
15. 苏格拉底类型去轮次化
16. 泛化原则声明
17. 用户角色感知
18. 新增 scope_boundary 问题类型
19. 跨域测试用例

---

## 五、泛化性专项评估

### 当前状态

| 层面 | 泛化程度 | 说明 |
|------|:--------:|------|
| 架构层 | ✅ 强 | YAML 配置 + LLM 推断 + 开放枚举 |
| Prompt 示例层 | ⚠️ 中 | 投资/硬件/商业示例有，但偏向产品/项目范式 |
| 对话策略层 | ❌ 弱 | 七维度框架是产品需求框架，非产品域会"答非所问" |
| 评估层 | ⚠️ 中 | 跨域锚点好，但 process_guard 不区分域 |
| 测试层 | ❌ 无 | 无跨域测试用例 |

### 伪泛化风险

1. **七维度框架的产品偏向**：objective/users/capabilities/quality_attributes/constraints/integration/risks 是产品需求框架。投资场景的"users"应该是"投资决策标准"，创作场景没有"integration"
2. **capabilities 三层结构的功能偏向**：Always/Should/Never 适合功能描述，不适合研究方法论选择或创作边界
3. **integration 维度的系统偏向**："已有系统、集成接口"对非系统型项目需要语义映射

### 建议（保持域无关）

不增加更多域的硬编码示例，而是：
1. 增加泛化原则声明："维度含义需要语义映射而非字面套用"
2. 在 parse 阶段推断用户角色和项目类型，动态调整维度权重
3. 补充跨域测试用例验证泛化性

---

## 六、附录：代码证据索引

| 发现 | 文件 | 行号/函数 |
|------|------|----------|
| SemanticAnchor 不可变性声明 | living_spec.py | L8 类文档字符串 |
| merge_semantic_anchors 覆盖逻辑 | merge_spec.py | L284 `anchors_map[name] = anchor` |
| SemanticGate 关键词计数 | harness.py | L108-115 `check_clarity()` |
| EXPECTED_DELTA_BY_MODE 硬编码 | process_guard.py | L23-35 |
| 意图判断关键词匹配 | assess.md | L219-225 |
| 问题数量口径矛盾 | guide.md / assess_guide.md / coordinator.py | 多处 |
| standard max_rounds=10 | models.py | MODE_CONFIG |
| conversation_digest 死代码 | living_spec.py | L232 |
| requirement_index 条件生成 | coordinator.py | L1362 |
| 输入截断 5000 字符 | gate_input_conservation.py | L127 |
| ProcessGuard 不排除 deliberately_omitted | process_guard.py | L68 check_conversation_balance() |

---

*报告完成。四位专家独立分析，综合评分 75/100。核心改进方向：话头优先、SemanticAnchor 不可变性、AI Native 纯度提升、泛化性验证。*
