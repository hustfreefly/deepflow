# DryRun V3.3 审计报告 — Agent C: Prompt 语义质量 (Kimi Code)

**审计时间**: 2026-07-07  
**审计对象**: P0 修复后 Prompt 质量 (commit 1c4d744)  
**审计范围**: domains/solution_pro/prompts/  

---

## 维度 1: Prompt 信噪比（§5）

**状态**: ✅ PASS

**评估文件**:
| 文件 | 信噪比 | 说明 |
|------|--------|------|
| research_expert_base.md | ~85% | 结构清晰，输入/输出/约束分明，无冗余 |
| summary_base_synthesizer.md | ~85% | 职责明确，输入来源清晰，格式规范完整 |
| planning_expert_base.md | ~85% | 约束提取要求具体，结构化输出定义明确 |

**发现**:
1. ✅ 3 个核心 prompt 均无 gap_analysis / devil_advocate 残留引用
2. ✅ 内容聚焦，指令具体可执行（如"每个 Finding 不少于 200 字"、"必须执行至少 15 次 web_search"）
3. ✅ 输入来源、输出格式、关键约束三区分离清晰

---

## 维度 2: Prompt 内部一致性（§5.1）

**状态**: ⚠️ CONDITIONAL

**发现**:
1. ✅ **核心 prompt 变量名已统一**:
   - `research_expert_base.md`: `{evaluation_lens}`, `{focus_areas}`, `{focus_req_ids}`, `{expert_filename}` ✓
   - `planning_expert_base.md`: `{evaluation_lens}`, `{focus_areas}`, `{focus_req_ids}`, `{expert_filename}` ✓
   - `summary_base_synthesizer.md`: 不涉及上述变量 ✓

2. ❌ **planning_module.md 残留旧变量名** (line ~107):
   ```
   **分析视角**:{expert_perspective}
   ```
   应改为: `{evaluation_lens}`

3. ⚠️ **researcher_harness.md 使用不同模板语法** (`{{ expert.angle }}` 等 Jinja2 语法):
   此为 v2.0.0 harness 文件，使用 Jinja2 而非 Python str.format。本次 P0 修复未覆盖此文件（修复范围是 2.0.0 核心 prompt）。建议标记为 "legacy harness" 或在后续版本中统一。

---

## 维度 3: Prompt-Runner 一致性（§6）

**状态**: ✅ PASS

**验证结果**:
```
$ python3 scripts/checks/check_prompt_vars.py
✅ PASS: 所有模板变量有对应替换
```

**发现**:
1. ✅ 所有模板变量在 runner 中有对应替换链
2. ✅ 无悬空变量引用

---

## 维度 4: 跨 Agent 信息守恒（§6）

**状态**: ⚠️ CONDITIONAL

**发现**:
1. ✅ **Planning → Research 信息流**:
   - `planning_convergence` → Research Expert 强制读取（"必须读,确保研究与约束对齐"）
   - 约束标注要求：每个 Finding 必须标注 Related Constraints

2. ✅ **Research → Summary 信息流**:
   - `research_digest` 作为 Summary 的唯一 Research 输入（"🔴 唯一 Research 输入"）
   - Base Synthesizer 明确职责："完整吸收 Research 的所有发现"
   - 信息守恒铁律："34 条 Finding 不能写成多条发现"，"ID 保 ID"

3. ✅ **gap_analysis / devil_advocate 已清除**:
   - 3 个核心 prompt 中无引用
   - runner 代码中无 phantom stage 调用

4. ❌ **researcher_harness.md 残留引用**:
   ```json
   "downstream_consumers": ["Base Synthesizer", "Devil's Advocate"]
   ```
   "Devil's Advocate" 仍作为下游消费者列出。虽然 harness 文件可能不在主流程中直接使用，但如果被调用会导致信息流向不存在的 Agent。

---

## 维度 5: Prompt 基础设施检测（§7）

**状态**: ✅ PASS

**验证结果**:
```
$ python3 scripts/checks/check_phantom_stages.py
✅ PASS: 无 phantom stages
```

**发现**:
1. ✅ 无 phantom stages 残留
2. ✅ _archive/ 目录存在（devil_advocate.md, gap_analyst.md, reviewqc_module.md），属于预期归档
3. ✅ 所有引用的文件路径真实存在:
   - `core.blackboard.blackboard_manager` → 存在
   - `prompts/planning_expert_base.md` → 存在
   - `prompts/planning_planner.md` → 存在
   - `data/living_spec` / `data/frozen_spec` → 存在

---

## 综合判定

| 维度 | 状态 | 权重 | 加权得分 |
|------|------|------|----------|
| 维度 1: 信噪比 | ✅ PASS | 20% | 20 |
| 维度 2: 内部一致性 | ⚠️ CONDITIONAL | 25% | 15 |
| 维度 3: Prompt-Runner 一致性 | ✅ PASS | 20% | 20 |
| 维度 4: 跨 Agent 信息守恒 | ⚠️ CONDITIONAL | 25% | 15 |
| 维度 5: 基础设施 | ✅ PASS | 10% | 10 |
| **综合** | | **100%** | **80/100** |

**综合判定**: ⚠️ CONDITIONAL PASS

P0 修复基本完成，核心 prompt 质量达标，但存在 2 处需要修复的问题。

---

## 问题清单

| # | 问题 | 严重度 | 位置 | 修复建议 |
|---|------|--------|------|----------|
| 1 | planning_module.md 残留旧变量名 `{expert_perspective}` | 🔴 Medium | planning_module.md:107 | 改为 `{evaluation_lens}` |
| 2 | researcher_harness.md 残留 "Devil's Advocate" 下游引用 | 🔴 Medium | researcher_harness.md:74 | 从 downstream_consumers 中移除 "Devil's Advocate" |

---

## 修复验证建议

修复后运行以下命令验证:
```bash
cd /Users/allen/.openclaw/workspace/.deepflow
python3 scripts/checks/check_prompt_vars.py
python3 scripts/checks/check_phantom_stages.py
grep -ri "devil_advocate\|gap_analysis\|{expert_perspective}\|{research_questions}" domains/solution_pro/prompts/ --exclude-dir=_archive
```

预期输出:
- check_prompt_vars.py: ✅ PASS
- check_phantom_stages.py: ✅ PASS
- grep: 无匹配（_archive 目录除外）
