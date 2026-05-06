# DeepFlow V4.0 完整实施方案

> **历史文档**: 本文档为 V4.0 架构设计阶段的历史记录，当前实现见 [ARCHITECTURE.md](ARCHITECTURE.md)
>
> **当前版本**: 0.1.0 (V4.0 内部代号)
## 基于 investment_summarizer.md 效果驱动的系统设计

**版本**: 4.0 Final  
**日期**: 2026-04-22 23:36  
**核心驱动**: investment_summarizer.md 的"论点驱动"效果

---

## 一、核心效果定义（从 Summarizer 反推）

### 1.1 Summarizer 输出效果

```markdown
# 京仪装备(688652.SH) 投资分析报告

## ⚡ 核心投资逻辑

1. **长期逻辑**：国产替代加速 + 环保政策趋严驱动半导体废气处理设备行业扩容
   （来源：researcher_macro_chain, confidence=0.88）

2. **短期风险**：净利率从2023年峰值16.05%降至2025Q3的10.37%，PE 108x显著偏高
   （来源：researcher_finance + auditor_factual, confidence=0.90）

3. **关键拐点**：净利率企稳回升至11%+ / 经营现金流转正 / 192层NAND设备认证通过

4. **核心矛盾**：长期景气度上行 vs 短期盈利能力恶化
   - 数据分歧：市占率 A说15%（有订单数据） vs B说10-12%（行业报告）
   - 判断：采纳 A，因 A 有具体订单支撑

5. **投资建议**：持有 | 中性目标价：¥59.4（-45%下行空间）
   - Bull Case：¥150（+39%）
   - Bear Case：¥39.6（-63%）
   - 置信度：0.76

---

## 情景分析与目标价

| 情景 | 目标价 | 隐含PE | 关键假设 | 概率 |
|------|--------|--------|----------|------|
| **乐观** | ¥150.0 | 80倍 | 营收增速20%+，净利率修复至13%+ | 20% |
| **中性** | ¥59.4 | 60倍 | 营收增速10-15%，净利率维持10-11% | 50% |
| **悲观** | ¥39.6 | 40倍 | 营收增速<5%，净利率下滑至8% | 30% |
```

### 1.2 为了实现这个效果，系统需要产出什么？

| 输出项 | 来源 | 要求 |
|:---|:---|:---|
| **核心矛盾** | researcher_finance + researcher_macro_chain + auditor_factual | 必须有"长期利好 vs 短期利空"的对立 |
| **数据分歧** | auditor_factual | 必须标记矛盾数据及判断依据 |
| **投资逻辑** | 所有 researcher | 必须有置信度 ≥0.85 的支撑 |
| **三情景目标价** | researcher_finance + researcher_market | 必须有隐含PE和关键假设 |
| **关键拐点** | researcher_tech + researcher_macro_chain | 必须可跟踪、可验证 |

---

## 二、全系统适配设计

### 2.1 数据流重新设计（效果驱动）

```
DataManager Worker
  ├── [采集] 财务/行情/行业基础数据
  ├── [整理] 生成 key_metrics.json（精简版）
  │     └── {current_price, pe_ttm, pb_ratio, market_cap}
  └── [搜索] 行业趋势/竞品对比/券商预期/风险因素
        └── 05_supplement/
              │
        ┌─────┴─────────────────────────────────────┐
        ▼                                           ▼
Researchers ×6（并行，输出结构化 JSON）        Auditors ×3（并行）
  │                                                │
  ├── researcher_finance                           ├── auditor_factual
  │     ├── 营收/利润/现金流分析                     │     ├── 事实验证
  │     ├── **每条结论含 confidence + source**      │     ├── **标记数据矛盾**
  │     └── 估值分析（PE/PB/PS）                    │     └── **给出判断依据**
  │                                                │
  ├── researcher_macro_chain                       ├── auditor_upside
  │     ├── 行业趋势                                 │     └── 挑战乐观假设
  │     ├── 国产化率/市场规模                        │
  │     └── **政策支撑证据**                         ├── auditor_downside
  │                                                │     └── 挑战悲观假设
  ├── researcher_tech
  │     ├── 技术壁垒
  │     └── **产品管线进展**
  │
  ├── researcher_market
  │     ├── 市场份额
  │     └── **可比公司估值**
  │
  ├── researcher_management
  │     └── 管理层/治理
  │
  └── researcher_sentiment
        └── 舆情/事件驱动
              │
        ┌─────┴─────────────────────────────────────┐
        ▼                                           ▼
Fixer Worker（读取所有输出，修正矛盾）         Summarizer Worker
  ├── 整合 researcher + auditor 输出               ├── **分层读取**
  ├── **解决数据矛盾**（采纳 auditor_factual）      │     ├── 第一层：factual + finance + macro
  ├── **修正乐观/悲观偏差**                         │     ├── 第二层：tech + market + fixer
  └── 输出修正后的统一数据                          │     └── 第三层：management + sentiment + upside/downside
                                                   ├── **提取核心矛盾**
                                                   ├── **构建投资逻辑**
                                                   ├── **生成三情景目标价**
                                                   └── 输出 final_report.md
```

### 2.2 所有 Worker 输出格式标准化

为了实现 Summarizer 的分层读取和矛盾识别，**所有 Worker 必须输出统一格式的 JSON**：

```json
{
  "role": "worker_role",
  "session_id": "xxx",
  "timestamp": "2026-04-22T10:00:00Z",
  
  "findings": [
    {
      "id": "finding_001",
      "category": "财务|行业|技术|市场|管理|舆情",
      "finding": "具体结论描述",
      "confidence": 0.90,
      "source": "数据来源（Tushare/研报/搜索）",
      "data_points": {
        "metric": "指标名称",
        "value": "数值",
        "unit": "单位"
      },
      "contradictions": [
        {
          "with": "哪个 worker 矛盾",
          "their_value": "对方数值",
          "our_value": "我方数值",
          "resolution": "如何解决（采纳谁）"
        }
      ]
    }
  ],
  
  "summary": {
    "overall_assessment": "整体评估",
    "key_risks": ["风险1", "风险2"],
    "key_opportunities": ["机会1", "机会2"]
  },
  
  "quality_self_assessment": {
    "data_completeness": 85,
    "analysis_depth": 90,
    "overall_score": 87.5
  }
}
```

### 2.3 各 Worker 专属输出要求

#### DataManager Worker
```json
{
  "role": "data_manager",
  "key_metrics": {
    "company_code": "688652.SH",
    "company_name": "京仪装备",
    "industry": "半导体设备",
    "current_price": 110.28,
    "pe_ttm": 108.92,
    "pb_ratio": 7.57,
    "ps_ratio": 16.09,
    "market_cap": 150.0,
    "total_shares": 1.36,
    "analysis_date": "2026-04-22"
  },
  "datasets": [
    {"name": "financials", "records": 50, "source": "Tushare"},
    {"name": "market_quote", "records": 100, "source": "Sina"}
  ]
}
```

#### Researcher Workers
```json
{
  "role": "researcher_finance",
  "findings": [
    {
      "id": "fin_001",
      "category": "财务",
      "finding": "近三年营收CAGR 38.6%，但净利率从16.05%降至10.37%",
      "confidence": 0.90,
      "source": "Tushare fina_indicator",
      "data_points": {
        "revenue_cagr_3y": 0.386,
        "net_margin_2023": 0.1605,
        "net_margin_2025q3": 0.1037
      }
    }
  ],
  "valuation": {
    "pe_ttm": 108.92,
    "pb_ratio": 7.57,
    "ps_ratio": 16.09,
    "assessment": "overvalued"
  }
}
```

#### Auditor Workers
```json
{
  "role": "auditor_factual",
  "verifications": [
    {
      "claim": "市占率15%",
      "claimed_by": "researcher_market",
      "verified": true,
      "verified_value": "12-15%",
      "source": "行业报告+公司年报",
      "confidence": 0.85
    }
  ],
  "contradictions": [
    {
      "finding_1": {"worker": "researcher_market", "value": "15%"},
      "finding_2": {"worker": "researcher_macro", "value": "10-12%"},
      "resolution": "采纳 12-15%，因 researcher_market 有订单数据支撑",
      "confidence": 0.80
    }
  ]
}
```

#### Fixer Worker
```json
{
  "role": "fixer",
  "corrections": [
    {
      "original": {"worker": "researcher_finance", "value": "营收14.26亿"},
      "corrected": "营收14.26亿（已确认）",
      "reason": "auditor_factual 验证通过",
      "confidence": 0.95
    }
  ],
  "consolidated_findings": [
    {
      "id": "consolidated_001",
      "topic": "市占率",
      "final_value": "12-15%",
      "sources": ["researcher_market", "auditor_factual"],
      "confidence": 0.85
    }
  ]
}
```

---

## 三、Orchestrator 调度设计

### 3.1 执行顺序（确保数据依赖）

```python
# Phase 1: DataManager（数据入口）
data_manager_task = build_data_manager_task(session_id, code, name)
spawn_worker("data_manager", data_manager_task)
wait_for_completion("data_manager")

# Phase 2: Planner（制定计划）
planner_task = build_planner_task(session_id, code, name)
spawn_worker("planner", planner_task)
wait_for_completion("planner")

# Phase 3: Researchers ×6（并行分析）
for researcher in RESEARCHERS:
    task = build_researcher_task(researcher, session_id, code, name)
    spawn_worker(researcher, task)
wait_for_all_completion(RESEARCHERS)

# Phase 4: Auditors ×3（并行审计）
for auditor in AUDITORS:
    task = build_auditor_task(auditor, session_id, code, name)
    spawn_worker(auditor, task)
wait_for_all_completion(AUDITORS)

# Phase 5: Fixer（整合修正）
fixer_task = build_fixer_task(session_id, code, name)
spawn_worker("fixer", fixer_task)
wait_for_completion("fixer")

# Phase 6: Summarizer（论点驱动汇总）
summarizer_task = build_summarizer_task(session_id, code, name)
spawn_worker("summarizer", summarizer_task)
wait_for_completion("summarizer")
```

### 3.2 Task 构建器（核心）

```python
def build_summarizer_task(session_id, code, name):
    """
    构建 Summarizer Task（论点驱动）
    """
    # 读取所有前置输出
    inputs = {
        "planner": read_json(f"stages/planner_output.json"),
        "finance": read_json(f"stages/researcher_finance_output.json"),
        "macro": read_json(f"stages/researcher_macro_chain_output.json"),
        "tech": read_json(f"stages/researcher_tech_output.json"),
        "market": read_json(f"stages/researcher_market_output.json"),
        "management": read_json(f"stages/researcher_management_output.json"),
        "sentiment": read_json(f"stages/researcher_sentiment_output.json"),
        "factual": read_json(f"stages/auditor_factual_output.json"),
        "upside": read_json(f"stages/auditor_upside_output.json"),
        "downside": read_json(f"stages/auditor_downside_output.json"),
        "fixer": read_json(f"stages/fixer_output.json"),
        "key_metrics": read_json(f"data/key_metrics.json")
    }
    
    # 构建 Task
    task = f"""
# 🎯 Summarizer 任务（论点驱动）

## 目标公司
- 股票代码：{code}
- 公司名称：{name}

## 输入数据（已准备，按优先级排序）

### 第一层（核心，投入50%时间）
1. **auditor_factual**: {json.dumps(inputs['factual'], ensure_ascii=False)[:500]}
2. **researcher_finance**: {json.dumps(inputs['finance'], ensure_ascii=False)[:500]}
3. **researcher_macro_chain**: {json.dumps(inputs['macro'], ensure_ascii=False)[:500]}

### 第二层（辅助，投入30%时间）
4. **researcher_tech**: {json.dumps(inputs['tech'], ensure_ascii=False)[:300]}
5. **researcher_market**: {json.dumps(inputs['market'], ensure_ascii=False)[:300]}
6. **fixer**: {json.dumps(inputs['fixer'], ensure_ascii=False)[:300]}

### 第三层（参考，投入20%时间）
7. **management**: {json.dumps(inputs['management'], ensure_ascii=False)[:200]}
8. **sentiment**: {json.dumps(inputs['sentiment'], ensure_ascii=False)[:200]}
9. **auditor_upside**: {json.dumps(inputs['upside'], ensure_ascii=False)[:200]}
10. **auditor_downside**: {json.dumps(inputs['downside'], ensure_ascii=False)[:200]}

### 关键指标
{json.dumps(inputs['key_metrics'], ensure_ascii=False)}

## 任务要求

### Step 1: 提取核心矛盾（读第一层）
- 找出"最大利好" vs "最大利空"
- 识别数据分歧（如市占率不一致）
- 给出判断依据

### Step 2: 构建投资逻辑（提炼1-2条）
- 长期逻辑：一句话 + 数据来源 + 置信度
- 短期风险：一句话 + 数据来源 + 置信度
- 关键拐点：什么时候从"观望"变"买入"

### Step 3: 生成三情景目标价
- Bull Case：目标价 + 隐含PE + 关键假设 + 概率
- Base Case：同上
- Bear Case：同上

### Step 4: 生成最终报告
- 采用"论点驱动"结构
- 先写"核心投资逻辑"段落
- 再写标准模块

## 输出要求
- **JSON**: stages/summarizer_output.json
- **Markdown**: final_report.md
- 必须包含：核心矛盾、投资逻辑、三情景目标价、数据缺口

---

# 原始提示词
{read_prompt("investment_summarizer.md")}
"""
    
    return task
```

---

## 四、文件结构（最终版）

```
.deepflow/
├── orchestrator_agent.py          # V4.0：纯调度，Task构建器
├── core/
│   ├── __init__.py
│   ├── search_tools.py            # 统一搜索层（DataManager用）
│   ├── task_builder.py            # Task构建器（所有Worker）
│   └── output_validator.py        # 输出格式验证器
├── prompts/
│   ├── data_manager_v4.md         # DataManager（含bootstrap代码）
│   ├── investment_planner.md      # Planner（保持）
│   ├── investment_researcher_*.md # Researchers（保持）
│   ├── investment_auditor.md      # Auditors（保持）
│   ├── investment_fixer.md        # Fixer（保持）
│   └── investment_summarizer.md   # Summarizer（论点驱动）
├── domains/
│   └── investment.yaml            # 领域配置（含agents列表）
└── blackboard/
    └── {session_id}/
        ├── data/
        │   ├── INDEX.json
        │   ├── key_metrics.json     # ← 精简版（Summarizer快速读取）
        │   ├── 01_financials/
        │   ├── 02_market_quote/
        │   └── 05_supplement/
        └── stages/
            ├── planner_output.json
            ├── researcher_*_output.json  # ← 统一格式（含confidence）
            ├── auditor_*_output.json     # ← 统一格式（含contradictions）
            ├── fixer_output.json         # ← 统一格式（含corrections）
            ├── summarizer_output.json    # ← 结构化JSON
            └── final_report.md           # ← Markdown报告
```

---

## 五、实施计划（效果驱动）

### Step 1: 设计输出格式契约（1小时）
- [ ] 定义 `key_metrics.json` 格式（精简版）
- [ ] 定义 Worker 输出统一格式（含 confidence/source）
- [ ] 定义 Auditor 输出格式（含 contradictions）
- [ ] 定义 Fixer 输出格式（含 corrections）
- [ ] 定义 Summarizer 输出格式（三情景目标价）

### Step 2: 实现 Task 构建器（2小时）
- [ ] `build_data_manager_task()` - 含 bootstrap 代码
- [ ] `build_planner_task()` - 上下文注入
- [ ] `build_researcher_task()` - 上下文注入 + 搜索指引
- [ ] `build_auditor_task()` - 上下文注入 + 审计视角
- [ ] `build_fixer_task()` - 读取所有前置输出
- [ ] `build_summarizer_task()` - **分层读取 + 论点驱动**

### Step 3: 重写 DataManager Worker（1.5小时）
- [ ] 含完整 `bootstrap_phase()` 代码
- [ ] 含统一搜索代码（行业趋势/竞品/券商预期/风险）
- [ ] 生成 `key_metrics.json`（精简版）

### Step 4: 重写 Orchestrator（1.5小时）
- [ ] 纯调度逻辑
- [ ] 按顺序 spawn Workers
- [ ] 检查数据依赖

### Step 5: 验证论点驱动效果（2小时）
- [ ] 测试 Summarizer 分层读取
- [ ] 测试核心矛盾提取
- [ ] 测试三情景目标价生成
- [ ] 测试最终报告格式

**总计：8小时**

---

## 六、验证标准（效果验收）

### 6.1 Summarizer 输出检查清单

```python
SUMMARIZER_CHECKLIST = {
    "structure": {
        "has_executive_summary": True,      # 有核心投资逻辑段落
        "has_scenario_analysis": True,       # 有三情景目标价
        "has_key_findings": True,            # 有 key_findings 列表
        "has_risks": True,                   # 有风险列表
    },
    "content": {
        "core_contradiction_identified": True,  # 识别了核心矛盾
        "investment_logic_clear": True,         # 投资逻辑清晰（1-2条）
        "three_scenarios_present": True,        # 三情景都有
        "scenarios_consistent": True,           # 悲观<中性<乐观
        "data_sources_cited": True,             # 标注了数据来源
        "confidence_scores_present": True,      # 有置信度
    },
    "quality": {
        "executive_summary_200_300_words": True,
        "key_findings_at_least_5": True,
        "risks_at_least_3": True,
        "data_gaps_identified": True,
    }
}
```

### 6.2 最终验收测试

```python
def test_summarizer_effect(session_id: str) -> dict:
    """
    测试 Summarizer 的论点驱动效果
    """
    # 读取 Summarizer 输出
    summarizer_output = read_json(f"stages/summarizer_output.json")
    report = read_file(f"final_report.md")
    
    checks = {
        # 结构检查
        "has_executive_summary": "核心投资逻辑" in report,
        "has_scenario_table": "| 情景 |" in report,
        "has_bull_case": "Bull" in report or "乐观" in report,
        "has_bear_case": "Bear" in report or "悲观" in report,
        
        # 内容检查
        "has_core_contradiction": "矛盾" in report or "vs" in report,
        "has_investment_logic": "逻辑" in report or "论点" in report,
        "has_target_prices": "目标价" in report,
        
        # 质量检查
        "has_confidence_scores": "confidence" in str(summarizer_output).lower(),
        "has_data_sources": "来源" in report or "source" in str(summarizer_output).lower(),
    }
    
    return {
        "all_passed": all(checks.values()),
        "checks": checks,
        "score": sum(checks.values()) / len(checks)
    }
```

---

## 七、关键设计决策

### 7.1 为什么 DataManager 做统一搜索？

| 方案 | 优点 | 缺点 |
|:---|:---|:---|
| **DataManager 做搜索**（选定） | 数据入口统一，Orchestrator 纯调度 | DataManager 任务重 |
| Orchestrator 做搜索 | 调度者准备数据 | 违反"Orchestrator 只做调度"原则 |
| Workers 各自搜索 | 灵活 | 可能重复搜索，数据不一致 |

**决策**：DataManager 是数据唯一入口，包括采集和搜索。

### 7.2 为什么 Summarizer 分层读取？

从 investment_summarizer.md：

> **从"平均汇总"升级为"论点驱动"**
> **只读第一层文件，找出"最大矛盾"**

**效果**：
- 避免信息过载
- 聚焦核心矛盾
- 提高分析深度

### 7.3 为什么所有 Worker 输出统一格式？

**为了 Summarizer 能**：
1. 按优先级分层读取
2. 识别数据矛盾
3. 判断置信度
4. 生成结构化报告

---

## 八、确认清单

- [x] Summarizer 效果定义清晰（论点驱动 + 三情景目标价）
- [x] 全系统输出格式标准化（含 confidence/source）
- [x] DataManager 是数据唯一入口（采集 + 搜索）
- [x] Orchestrator 纯调度（不采集不分析）
- [x] Workers 可以按需自行搜索
- [x] 分层读取逻辑定义（第一层50%时间）
- [x] 验证标准定义（效果验收）

**确认后开始实施？**