# Solution Pro 2.0.0 改进方案 — AI Native 修正版

> **版本**: 2.0.0（AI Native 修正）| **日期**: 2026-07-01
> **背景**: 2.0.0 方案（Fix 1/4/5）经 AI Native 自审，发现 Fix 1 是硬编码、Fix 4 是伪 AI Native
> **原则**: Code controls flow & format, LLM judges semantics (AGENTS.md Zone 4.3)

---

## 自审结果：2.0.0 方案的 AI Native 合规性

### ❌ Fix 1（研究利用追踪）— 硬编码，违反 Zone 4.1

**问题**: 用 `expert_id in solution_text` 和关键词匹配来判断"研究是否被利用"

```python
# 2.0.0 实现（硬编码）
expert_cited = expert_id in solution_text
finding_keywords = [f[:20] for f in findings if len(f) > 5]
expert_cited = any(kw.lower() in solution_text.lower() for kw in finding_keywords)
```

**为什么不是 AI Native**:
- 语义任务（"finding 是否影响了设计"）用了代码（字符串匹配）
- 关键词出现 ≠ 设计吸收。Expert 说"需要心跳检测"，方案写了"心跳检测"四个字但没有任何设计 → 字符串匹配会判 PASS，但实际是 FAIL
- AGENTS.md Zone 4.1: "输出是否依赖 meaning？" → 是 → 应该用 LLM

### ⚠️ Fix 4（Finding Ledger）— 伪 AI Native

**问题**: 代码正确强制了结构（每个 finding 必须有 decision + rationale），但 decision 本身的判断逻辑是硬编码

```python
# 2.0.0 实现（伪 AI Native）
if entry["source"] in ("devil_advocate", "gap_analysis") and "unaddressed_findings" in fixed_types:
    entry["decision"] = "adopted"  # 代码直接赋值，不是 LLM 判断
```

**部分正确**:
- ✅ 结构层（代码强制字段存在）→ 正确，属于格式检查
- ❌ 语义层（decision 应该是 LLM 判断"这个 finding 是否真的被解决了"）→ 用了代码

### ✅ Fix 5（确定性检查）— 正确 AI Native

6 个检查全部是格式/结构检查，不涉及语义判断：
- 文件存在性 → 格式
- JSON 有效性 → 格式
- ID 引用一致性 → 结构
- 章节编号一致性 → 结构
- TBD 参数检测 → 正则（固定格式提取，OK）
- 大小演进 → 数值比较

**结论**: Fix 5 是正确的 Code for format 层。

---

## 2.0.0 修正方案：三层 Gate 架构

### 架构总览

```
Pipeline Stage 完成
  │
  ├── Layer 1: 确定性 Gate（Python 代码，<1s，零 LLM）
  │   ├── 文件存在 + 非空
  │   ├── JSON Schema 验证
  │   ├── 跨文件 ID 引用一致性
  │   ├── 章节编号一致性
  │   ├── TBD/FIXME 残留检测
  │   └── 大小演进合理性
  │
  ├── Layer 2: 语义 Gate（LLM-as-Judge，独立 spawn）
  │   ├── Research Utilization Judge:
  │   │   "Expert Finding X 的核心洞察是否体现在方案设计中？"
  │   │   "是实质性吸收，还是仅提及关键词？"
  │   ├── Finding Decision Judge:
  │   │   "Fix Plan 对这个 finding 的处理是否真正解决了问题？"
  │   │   "rationale 是否合理？是否存在确认偏差？"
  │   └── Information Conservation Judge:
  │       "从 frozen_spec 到 final_solution，信息是否有语义层面的丢失？"
  │
  └── Layer 3: 合并决策
      ├── L1 PASS + L2 PASS → PASS
      ├── L1 PASS + L2 CONDITIONAL → CONDITIONAL（列出未通过的语义项）
      ├── L1 FAIL → FAIL（格式错误，无需语义检查）
      └── L2 FAIL → FAIL（语义问题，即使格式正确）
```

### Layer 2 详细设计

#### 2a. Research Utilization Judge（替代 Fix 1 的字符串匹配）

**输入**:
- Expert Finding（finding_id + description + key insight）
- Solution Document（相关 section）

**Prompt**:
```
你是一个独立的研究利用审查员。

## 你的任务
判断以下 Expert Finding 是否被方案设计**实质性吸收**（不是仅仅提及关键词）。

## Expert Finding
{expert_id}: {finding_description}
核心洞察: {key_insight}

## 方案相关段落
{solution_section}

## 评判标准
1. **实质性吸收** (PASS): 方案的设计决策、参数选择、架构设计中体现了这个 finding 的核心洞察
2. **表面提及** (WEAK): 方案提到了相关概念但没有基于 finding 做具体设计
3. **完全忽略** (FAIL): 方案中找不到与这个 finding 相关的设计

## 输出格式
{"verdict": "PASS|WEAK|FAIL", "evidence": "引用方案中的具体段落", "reasoning": "为什么判这个等级"}
```

**与 2.0.0 的区别**:
- 2.0.0: `"stall detection" in solution_text` → True/False
- 2.0.0: LLM 判断"方案是否真正设计了停滞检测机制，还是只写了'停滞检测'四个字"

#### 2b. Finding Decision Judge（替代 Fix 4 的代码赋值）

**输入**:
- Finding（description + severity）
- Fix Plan（proposed fix + rationale）

**Prompt**:
```
你是一个独立的修复质量审查员。

## Finding
{finding_description}
严重程度: {severity}

## 修复方案
{fix_description}
决策: {decision}
理由: {rationale}

## 评判标准
1. **真正解决** (PASS): 修复方案直接针对 finding 的根因
2. **部分解决** (PARTIAL): 修复方案触及了表面但未解决根因
3. **未解决** (FAIL): 修复方案与 finding 无关，或 rationale 存在确认偏差
4. **合理拒绝** (PASS): 拒绝这个 finding 的理由充分且经过深思熟虑

## 输出格式
{"verdict": "PASS|PARTIAL|FAIL", "evidence": "...", "reasoning": "..."}
```

### 实现路径

```python
class SemanticGate:
    """Layer 2: LLM-as-Judge 语义检查"""

    def check_research_utilization(
        self, expert_findings: list[dict], solution_document: str, spawn_fn
    ) -> dict:
        """用 LLM 判断每个 expert finding 是否被方案实质性吸收"""
        judgments = []
        for finding in expert_findings:
            # spawn 独立 Judge（不同模型或同模型不同 session）
            judgment = spawn_fn(
                task=f"Read prompt from file and execute: {prompt_path}",
                # 不传大 prompt 作为 task（吸取 E2E 2.0.0 教训）
            )
            judgments.append(judgment)

        pass_count = sum(1 for j in judgments if j["verdict"] == "PASS")
        return {
            "total": len(expert_findings),
            "passed": pass_count,
            "rate": pass_count / len(expert_findings),
            "judgments": judgments,
        }

    def check_finding_decisions(
        self, finding_ledger: list[dict], fix_plan: dict, spawn_fn
    ) -> dict:
        """用 LLM 判断每个 finding decision 是否合理"""
        # 类似实现...
```

---

## 2.0.0 vs 2.0.0 对比

| 维度 | 2.0.0（当前实现） | 2.0.0（AI Native 修正） |
|------|--------------|---------------------|
| **研究利用检查** | `keyword in text` 字符串匹配 | LLM-as-Judge 语义评估 |
| **Finding 决策** | 代码赋值 decision | LLM 评估 rationale 合理性 |
| **确定性检查** | 6 个代码检查（正确） | 保持不变 |
| **LLM 调用成本** | 0（但语义判断缺失） | 每轮 N 次 Judge 调用 |
| **泛化能力** | 低（依赖特定关键词） | 高（LLM 理解语义，任何领域通用） |
| **AI Native 合规** | ❌ Fix 1 违规 | ✅ 三层 Gate 完全合规 |

---

## 泛化性分析

**2.0.0 为什么不泛化**:
- 关键词匹配依赖特定 expert 的 finding 措辞
- 换一个领域（如"医疗系统"vs"AI Agent"），关键词完全不同
- 每次换领域需要重写匹配规则 → 不可维护

**2.0.0 为什么泛化**:
- LLM-as-Judge 的 prompt 是领域无关的（"finding 是否被吸收"这个判断标准通用）
- 确定性检查也是领域无关的（JSON 格式、文件存在性）
- 换领域只需要换 frozen_spec + research，不需要改检查逻辑

---

## 待讨论

1. **成本 vs 质量**: Layer 2 每次 E2E 需要 N 次 LLM Judge 调用。是否可以接受？
2. **Judge 模型选择**: 同模型 vs 不同模型？同模型 = 运动员兼裁判风险；不同模型 = 成本翻倍
3. **Layer 2 失败策略**: CONDITIONAL 时是阻塞还是继续？
4. **与现有 Fix Loop 的集成**: Layer 2 在 Fix Loop 内还是 Fix Loop 后？

---

*Created: 2026-07-01 | 2.0.0 AI Native 修正版*
