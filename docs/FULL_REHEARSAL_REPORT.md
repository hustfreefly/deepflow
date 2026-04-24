# DeepFlow 单轮模式 全链路预演报告
# 基于契约笼子 (Contract Cage) 理念
# 版本: 1.0 | 日期: 2026-04-22
# **当前版本**: 0.1.0 (V4.0) — 本文档为 V1.0 时期预演报告

---

## 一、全链路概览

### 执行顺序（单轮模式）

```
主 Agent (Depth-0)
  └── sessions_spawn → Orchestrator Agent (Depth-1)
        └── OrchestratorAgent.run()
              ├── Step 1: PipelineEngine 初始化
              │     └── 加载 domains/investment.yaml（13个agents, 7个stages）
              │
              ├── Step 2: engine.run() → _run_pipeline()
              │     └── Iteration 0（唯一一轮）
              │           ├── Stage 1: data_manager
              │           ├── Stage 2: planner
              │           ├── Stage 3: researcher_finance (并行)
              │           ├── Stage 4: researcher_tech (并行)
              │           ├── Stage 5: researcher_market (并行)
              │           ├── Stage 6: researcher_macro_chain (并行)
              │           ├── Stage 7: researcher_management (并行)
              │           ├── Stage 8: researcher_sentiment (并行)
              │           ├── Stage 9: auditor_factual (并行)
              │           ├── Stage 10: auditor_upside (并行)
              │           ├── Stage 11: auditor_downside (并行)
              │           ├── Stage 12: fixer
              │           └── Stage 13: summarizer
              │
              └── Step 3: 保存结果到 blackboard/{session_id}/
```

### 关键约定

| 约定 | 说明 |
|:---|:---|
| Session ID | `京仪装备_688652_{uuid前8位}` |
| Blackboard 根目录 | `/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/` |
| 数据目录 | `blackboard/{session_id}/data/` |
| Stage 输出 | `blackboard/{session_id}/stages/{stage_id}_output.json` |
| 最终报告 | `blackboard/{session_id}/final_report.md` |
| Orchestrator 结果 | `blackboard/{session_id}/orchestrator_result.json` |

---

## 二、逐 Stage 详细预演

### Stage 1: data_manager

#### 2.1.1 契约定义

**Interface:**
```python
data_manager(
    domain: str = "investment",
    code: str = "688652.SH",
    name: str = "京仪装备",
    session_id: str,
    output_dir: str
) -> Dict[str, Any]
```

**Input:**
| 参数 | 来源 | 说明 |
|:---|:---|:---|
| domain | 环境变量 DEEPFLOW_DOMAIN | 投资领域 |
| code | 环境变量 DEEPFLOW_CODE | 股票代码 |
| name | 环境变量 DEEPFLOW_NAME | 公司名称 |
| session_id | Orchestrator 生成 | 统一会话ID |

**Output:**
```json
{
  "status": "completed",
  "datasets_collected": 8,
  "output_path": "blackboard/{session_id}/data/",
  "files": [
    "INDEX.json",
    "01_financials/financial_data.json",
    "02_market_quote/realtime_quote.json",
    "02_market_quote/daily_basics.json",
    "03_industry/industry_data.json",
    "04_news/news_sentiment.json",
    "05_research_reports/analyst_reports.json",
    "key_metrics.json"
  ]
}
```

**Boundaries:**
- Tushare API 限流 → 等待重试
- Sina 接口超时 → 降级处理
- 数据采集失败 → 返回部分数据 + 错误列表

#### 2.1.2 执行命令

**DataManager Agent 执行的 Python 代码：**

```python
import sys
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from data_manager import DataEvolutionLoop, ConfigDrivenCollector
from data_providers.investment import register_providers
import os

# 注册数据源
register_providers()

# 初始化采集器
config_path = "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
collector = ConfigDrivenCollector(config_path)

# 创建数据循环
data_loop = DataEvolutionLoop(collector, blackboard_manager)

# 设置上下文
context = {
    "code": os.environ.get("DEEPFLOW_CODE", "688652.SH"),
    "name": os.environ.get("DEEPFLOW_NAME", "京仪装备")
}

# 执行 bootstrap 采集
print(f"开始采集 {context['name']}({context['code']}) 数据...")
data_loop.bootstrap_phase(context)

# 验证数据
index_path = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/INDEX.json"
if os.path.exists(index_path):
    print(f"✅ 数据采集完成")
else:
    print(f"⚠️ 数据采集可能不完整")
```

**实际调用的外部 API：**

| API | 用途 | 可能问题 |
|:---|:---|:---|
| Tushare `pro.daily()` | 日线行情 | 限流（2次/日） |
| Tushare `pro.fina_indicator()` | 财务指标 | 需要 token |
| Tushare `pro.income()` | 利润表 | 数据延迟 |
| Sina Finance | 实时行情 | 反爬/超时 |
| web_fetch | 补充数据 | 验证码 |

#### 2.1.3 输出文件清单

```
blackboard/{session_id}/data/
├── INDEX.json                     # 数据索引
├── key_metrics.json               # 精简指标（200字节）
├── v0/
│   ├── financials.json            # 财务数据
│   ├── daily_basics.json          # 日线基础
│   └── realtime_quote.json        # 实时行情
├── 01_financials/
│   └── financial_data.json
├── 02_market_quote/
│   └── market_data.json
├── 03_industry/
│   └── industry_data.json
├── 04_news/
│   └── news_data.json
└── 05_research_reports/
    └── reports.json
```

#### 2.1.4 风险提示

| 风险 | 影响 | 缓解措施 |
|:---|:---|:---|
| Tushare 限流 | 财务数据缺失 | 改用新浪财经实时数据 |
| Sina 超时 | 实时行情缺失 | 使用缓存/默认值 |
| 网络波动 | 部分数据缺失 | 重试 3 次 |

---

### Stage 2: planner

#### 2.2.1 契约定义

**Interface:**
```python
planner(
    code: str,
    name: str,
    industry: str,
    data_summary: Dict[str, Any]
) -> Dict[str, Any]
```

**Input:**
| 参数 | 来源 | 说明 |
|:---|:---|:---|
| code/name | 环境变量 | 股票代码和名称 |
| key_metrics | data_manager 输出 | 精简财务指标 |
| industry | 配置/推断 | 所属行业 |

**Output:**
```json
{
  "role": "planner",
  "research_plan": {
    "objectives": ["财务分析", "技术评估", "市场定位"],
    "dimensions": ["finance", "tech", "market", "macro", "management", "sentiment"],
    "key_questions": [
      "公司核心竞争力是什么？",
      "行业增长空间多大？",
      "估值是否合理？"
    ],
    "data_gaps": ["缺少可比公司数据", "管理层访谈缺失"]
  }
}
```

**Boundaries:**
- 数据不足 → 标记 data_gaps，不阻塞后续流程
- 行业识别失败 → 使用默认配置

#### 2.2.2 执行命令

```python
# Planner Agent 读取 data_manager 输出
import json
import os

session_id = os.environ.get("DEEPFLOW_SESSION_ID")

# 读取 key_metrics
metrics_path = f"blackboard/{session_id}/data/key_metrics.json"
with open(metrics_path) as f:
    key_metrics = json.load(f)

# 生成研究计划
plan = {
    "code": os.environ.get("DEEPFLOW_CODE"),
    "name": os.environ.get("DEEPFLOW_NAME"),
    "current_price": key_metrics.get("current_price"),
    "pe_ttm": key_metrics.get("pe_ttm"),
    "research_dimensions": ["finance", "tech", "market", "macro", "management", "sentiment"]
}

# 写入输出
output_path = f"blackboard/{session_id}/stages/planner_output.json"
with open(output_path, "w") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)
```

---

### Stage 3-8: Researchers（6个并行）

#### 2.3.1 契约定义

**Interface（每个 researcher 相同）：**
```python
researcher(
    role: str,           # researcher_finance / researcher_tech / ...
    code: str,
    name: str,
    planner_output: Dict,
    data_dir: str
) -> Dict[str, Any]
```

**Input:**
| 参数 | 来源 | 说明 |
|:---|:---|:---|
| role | 配置 | researcher 类型 |
| planner_output | Stage 2 | 研究计划 |
| key_metrics | data_manager | 精简指标 |
| raw_data | data_manager | 原始数据 |

**Output（以 researcher_finance 为例）：**
```json
{
  "role": "researcher_finance",
  "analysis": {
    "revenue_growth_3y": 0.386,
    "profit_growth_3y": -0.0326,
    "roe": 0.0692,
    "debt_ratio": 0.516,
    "cash_flow_status": "warning",
    "valuation_assessment": "overvalued"
  },
  "key_findings": [
    {
      "category": "财务",
      "finding": "近三年营收CAGR为38.6%，但净利率从16.05%降至10.37%",
      "confidence": 0.9,
      "source": "Tushare"
    }
  ],
  "confidence": 0.85
}
```

**Boundaries:**
- 数据缺失 → 降低 confidence，标注 data_gap
- 计算错误 → 使用原始数据，不臆造

#### 2.3.2 执行命令（并行）

```python
# 每个 researcher 并行执行
import json
import os

session_id = os.environ.get("DEEPFLOW_SESSION_ID")
role = os.environ.get("DEEPFLOW_ROLE")  # researcher_finance

# 读取输入数据
metrics_path = f"blackboard/{session_id}/data/key_metrics.json"
planner_path = f"blackboard/{session_id}/stages/planner_output.json"

with open(metrics_path) as f:
    key_metrics = json.load(f)
with open(planner_path) as f:
    planner = json.load(f)

# 执行分析（根据 role 调用不同方法）
if role == "researcher_finance":
    analysis = analyze_finance(key_metrics, planner)
elif role == "researcher_tech":
    analysis = analyze_technology(key_metrics, planner)
# ...

# 写入输出
output_path = f"blackboard/{session_id}/stages/{role}_output.json"
with open(output_path, "w") as f:
    json.dump(analysis, f, ensure_ascii=False, indent=2)
```

#### 2.3.3 并行风险

| 风险 | 影响 | 缓解措施 |
|:---|:---|:---|
| 6个 researcher 同时读写 Blackboard | 文件冲突 | 每个 researcher 只读共享数据，只写自己的输出文件 |
| 部分 researcher 超时 | 输出不完整 | PipelineEngine 的 ResilienceManager 处理 |
| 模型 quota 耗尽 | researcher 失败 | Fallback 到备用模型 |

---

### Stage 9-11: Auditors（3个并行）

#### 2.4.1 契约定义

**Interface:**
```python
auditor(
    role: str,           # auditor_factual / auditor_upside / auditor_downside
    researcher_outputs: List[Dict],
    data_dir: str
) -> Dict[str, Any]
```

**Input:**
| 参数 | 来源 | 说明 |
|:---|:---|:---|
| researcher_outputs | Stage 3-8 | 6个 researcher 的输出 |
| key_metrics | data_manager | 原始数据 |

**Output（以 auditor_factual 为例）：**
```json
{
  "role": "auditor_factual",
  "audit_type": "factual",
  "findings": [
    {
      "issue": "市占率数据不一致",
      "severity": "high",
      "description": "researcher_market 说15-20%，researcher_tech 说10-12%",
      "recommendation": "以订单数据为准，确认真实市占率"
    }
  ],
  "verified_facts": [
    {"fact": "营收CAGR 38.6%", "verified": true, "source": "Tushare"}
  ],
  "data_gaps": ["缺少可比公司估值数据"],
  "confidence": 0.88
}
```

**Boundaries:**
- 无法验证 → 标记为 unverified，不臆造
- 发现矛盾 → 明确标注，给出倾向性判断

#### 2.4.2 执行命令（并行）

```python
# 每个 auditor 读取所有 researcher 输出
import json
import os
import glob

session_id = os.environ.get("DEEPFLOW_SESSION_ID")
role = os.environ.get("DEEPFLOW_ROLE")  # auditor_factual

# 读取所有 researcher 输出
researcher_outputs = []
researcher_roles = [
    "researcher_finance", "researcher_tech", "researcher_market",
    "researcher_macro_chain", "researcher_management", "researcher_sentiment"
]

for r_role in researcher_roles:
    path = f"blackboard/{session_id}/stages/{r_role}_output.json"
    if os.path.exists(path):
        with open(path) as f:
            researcher_outputs.append(json.load(f))

# 执行审计
if role == "auditor_factual":
    audit_result = audit_factual(researcher_outputs)
elif role == "auditor_upside":
    audit_result = audit_upside(researcher_outputs)
elif role == "auditor_downside":
    audit_result = audit_downside(researcher_outputs)

# 写入输出
output_path = f"blackboard/{session_id}/stages/{role}_output.json"
with open(output_path, "w") as f:
    json.dump(audit_result, f, ensure_ascii=False, indent=2)
```

---

### Stage 12: fixer

#### 2.5.1 契约定义

**Interface:**
```python
fixer(
    researcher_outputs: List[Dict],
    auditor_outputs: List[Dict],
    planner_output: Dict
) -> Dict[str, Any]
```

**Input:**
| 参数 | 来源 | 说明 |
|:---|:---|:---|
| researcher_outputs | Stage 3-8 | 原始研究输出 |
| auditor_outputs | Stage 9-11 | 3个审计意见 |
| planner_output | Stage 2 | 研究计划 |

**Output:**
```json
{
  "role": "fixer",
  "fixed_analysis": {
    "key_findings": [
      {
        "category": "财务",
        "finding": "修正后：近三年营收CAGR为38.6%，净利率下滑至10.37%（原数据已核实）",
        "confidence": 0.92,
        "source": "Tushare + auditor_factual"
      }
    ],
    "corrections_made": [
      {
        "original": "市占率15-20%",
        "corrected": "市占率12-15%（基于订单数据）",
        "auditor": "auditor_factual"
      }
    ]
  },
  "confidence": 0.88
}
```

**Boundaries:**
- 审计意见矛盾 → 优先采纳 factual 审计
- 数据缺失 → 标注 gap，不臆造

#### 2.5.2 执行命令

```python
import json
import os

session_id = os.environ.get("DEEPFLOW_SESSION_ID")

# 读取所有 researcher 和 auditor 输出
researcher_outputs = []
auditor_outputs = []

for role in researcher_roles:
    path = f"blackboard/{session_id}/stages/{role}_output.json"
    if os.path.exists(path):
        with open(path) as f:
            researcher_outputs.append(json.load(f))

for role in ["auditor_factual", "auditor_upside", "auditor_downside"]:
    path = f"blackboard/{session_id}/stages/{role}_output.json"
    if os.path.exists(path):
        with open(path) as f:
            auditor_outputs.append(json.load(f))

# 执行修正
fixed = apply_corrections(researcher_outputs, auditor_outputs)

# 写入输出
output_path = f"blackboard/{session_id}/stages/fixer_output.json"
with open(output_path, "w") as f:
    json.dump(fixed, f, ensure_ascii=False, indent=2)
```

---

### Stage 13: summarizer

#### 2.6.1 契约定义

**Interface:**
```python
summarizer(
    fixer_output: Dict,
    researcher_outputs: List[Dict],
    auditor_outputs: List[Dict],
    key_metrics: Dict
) -> Dict[str, Any]
```

**Input:**
| 参数 | 来源 | 说明 |
|:---|:---|:---|
| fixer_output | Stage 12 | 修正后的分析 |
| researcher_outputs | Stage 3-8 | 原始研究（参考） |
| auditor_outputs | Stage 9-11 | 审计意见（参考） |
| key_metrics | data_manager | 关键指标 |

**Output（完整格式）：**
```json
{
  "role": "summarizer",
  "analysis_date": "2026-04-22",
  "current_price": 108.85,
  "executive_summary": "京仪装备是国内半导体温控设备龙头...",
  
  "company_overview": {
    "code": "688652.SH",
    "name": "京仪装备",
    "industry": "半导体设备",
    "current_price": 108.85,
    "market_cap": 165.16,
    "pe_ttm": 108.92,
    "pb_ratio": 7.57
  },
  
  "scenario_analysis": {
    "bull_case": { "target_price": 150.0, "probability": "20%" },
    "base_case": { "target_price": 59.4, "probability": "50%" },
    "bear_case": { "target_price": 39.6, "probability": "30%" }
  },
  
  "key_findings": [...],
  "recommendation": {
    "rating": "持有",
    "target_price_base": 59.4,
    "confidence": 0.76
  },
  
  "audit_summary": {
    "factual_accuracy": "已通过事实审计",
    "quality_score": 0.76
  }
}
```

**Boundaries:**
- 数据矛盾 → 诚实标注，给出倾向性判断
- confidence < 0.70 → 标注"数据不足"

#### 2.6.2 执行命令

```python
import json
import os

session_id = os.environ.get("DEEPFLOW_SESSION_ID")

# 读取所有输入
with open(f"blackboard/{session_id}/stages/fixer_output.json") as f:
    fixer_output = json.load(f)

with open(f"blackboard/{session_id}/data/key_metrics.json") as f:
    key_metrics = json.load(f)

# 读取所有 researcher 和 auditor（参考用）
researcher_outputs = []
auditor_outputs = []
# ... 读取逻辑同 fixer

# 生成报告
report = generate_report(fixer_output, key_metrics, researcher_outputs, auditor_outputs)

# 写入 JSON 输出
json_path = f"blackboard/{session_id}/stages/summarizer_output.json"
with open(json_path, "w") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

# 写入 Markdown 最终报告
md_path = f"blackboard/{session_id}/final_report.md"
with open(md_path, "w") as f:
    f.write(report["markdown_content"])
```

---

## 三、数据流图

### 3.1 文件依赖关系

```
data_manager
  ├──→ key_metrics.json
  ├──→ v0/financials.json
  ├──→ v0/daily_basics.json
  └──→ INDEX.json
       │
       ▼
planner ←── key_metrics.json
  └──→ planner_output.json
       │
       ▼
researcher_* ←── key_metrics.json + planner_output.json + raw_data
  ├──→ researcher_finance_output.json
  ├──→ researcher_tech_output.json
  ├──→ researcher_market_output.json
  ├──→ researcher_macro_chain_output.json
  ├──→ researcher_management_output.json
  └──→ researcher_sentiment_output.json
       │
       ▼
auditor_* ←── all researcher_*_output.json
  ├──→ auditor_factual_output.json
  ├──→ auditor_upside_output.json
  └──→ auditor_downside_output.json
       │
       ▼
fixer ←── researcher_*_output.json + auditor_*_output.json
  └──→ fixer_output.json
       │
       ▼
summarizer ←── fixer_output.json + key_metrics.json + reference_data
  ├──→ summarizer_output.json
  └──→ final_report.md
```

### 3.2 关键数据契约

| 文件 | 生产者 | 消费者 | 格式 |
|:---|:---|:---|:---|
| key_metrics.json | data_manager | 所有后续 stages | JSON |
| planner_output.json | planner | researchers | JSON |
| researcher_*_output.json | researchers | auditors, fixer | JSON |
| auditor_*_output.json | auditors | fixer | JSON |
| fixer_output.json | fixer | summarizer | JSON |
| summarizer_output.json | summarizer | 用户 | JSON |
| final_report.md | summarizer | 用户 | Markdown |

---

## 四、风险矩阵与应对

### 4.1 高风险项

| 风险 | 概率 | 影响 | 应对 |
|:---|:---|:---|:---|
| **DataManager 采集失败** | 中 | 高 | 降级使用缓存数据，标注数据缺口 |
| **并行 researcher 超时** | 高 | 中 | ResilienceManager 重试，fallback 模型 |
| **auditor 发现重大矛盾** | 中 | 高 | fixer 修正，降低 confidence |
| **summarizer 数据不足** | 低 | 中 | 标注"数据不足"，不强行下结论 |

### 4.2 边界情况处理

| 场景 | 处理 |
|:---|:---|
| 某个 researcher 失败 | 继续执行，该维度标注为"分析失败" |
| 所有 auditor 发现 P0 问题 | fixer 修正，如无法修正则标注风险 |
| 关键指标缺失 | 使用替代数据源，或标注"数据缺口" |
| 模型 quota 耗尽 | 自动切换 fallback 模型 |

---

## 五、验证检查清单

### 5.1 启动前检查

```
□ orchestrator_agent.py 存在且最新
□ domains/investment.yaml 已精简（13 agents, 7 stages）
□ pipeline_engine.py 已修复（单轮模式）
□ prompts/ 目录下所有 prompt 文件存在
□ data_sources/investment.yaml 配置正确
□ Blackboard 目录可写
```

### 5.2 执行中检查

```
□ data_manager 输出 INDEX.json
□ planner 输出 planner_output.json
□ 6 个 researcher 各输出 _output.json
□ 3 个 auditor 各输出 _output.json
□ fixer 输出 fixer_output.json
□ summarizer 输出 summarizer_output.json + final_report.md
```

### 5.3 结果验证

```
□ final_report.md 存在且非空
□ summarizer_output.json 包含所有必需字段
□ 报告包含分析日期、当前股价、三情景目标价
□ 投资建议与 confidence 匹配
```

---

## 六、时间估算

| Stage | 数量 | 单实例耗时 | 并行耗时 | 累积 |
|:---|:---|:---|:---|:---|
| data_manager | 1 | 2-3 min | 2-3 min | 2-3 min |
| planner | 1 | 1-2 min | 1-2 min | 3-5 min |
| researcher_* | 6 | 3-5 min | 3-5 min | 6-10 min |
| auditor_* | 3 | 2-3 min | 2-3 min | 8-13 min |
| fixer | 1 | 2-3 min | 2-3 min | 10-16 min |
| summarizer | 1 | 2-3 min | 2-3 min | 12-19 min |

**总计：12-20 分钟**

---

## 七、执行命令（主 Agent 启动）

```python
# 主 Agent 执行
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="orchestrator",
    task="""
# DeepFlow Orchestrator Agent 执行脚本

你是 DeepFlow V1.0 Orchestrator Agent。

## 执行步骤
1. 读取 /Users/allen/.openclaw/workspace/.deepflow/orchestrator_agent.py
2. 按代码逻辑执行：
   - 初始化 OrchestratorAgent
   - 调用 agent.run() 执行完整管线
3. 所有 sessions_spawn 调用必须设置 label 参数

## 关键规则
- 必须执行 orchestrator_agent.py 的代码
- PipelineEngine 自动执行所有 stages
- 单轮模式（max_iterations=1）

## 禁止
- 不得跳过 PipelineEngine
- 不得简化执行流程
""",
    env={
        "DEEPFLOW_DOMAIN": "investment",
        "DEEPFLOW_CODE": "688652.SH",
        "DEEPFLOW_NAME": "京仪装备"
    },
    timeout_seconds=1200  # 20分钟
)
```

---

**预演完成。所有环节已梳理，可以执行。**