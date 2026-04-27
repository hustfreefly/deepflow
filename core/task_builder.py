"""
Task Builder V4.0
=================

为所有 Workers 构建增强版 Task。

核心功能：
1. 读取原始提示词
2. 提取数据摘要
3. 注入完整上下文
4. 生成最终 Task

契约: cage/task_builder_contract.yaml
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional


# DeepFlow 基础路径
DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)


# ==================== 模块级辅助函数 ====================

def read_original_prompt(prompt_file: str) -> str:
    """读取原始提示词文件"""
    prompt_path = os.path.join(DEEPFLOW_BASE, "prompts", prompt_file)
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"# {prompt_file}\n\n执行分析任务。"


def extract_data_summary(session_id: str) -> Dict[str, Any]:
    """从 Blackboard 提取数据摘要，并检测数据完整性"""
    km_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}/data/key_metrics.json"
    defaults = {
        "company_code": "未知", "company_name": "未知", "industry": "半导体设备",
        "current_price": "未知", "pe_ttm": "未知", "pb_ratio": "未知",
        "ps_ratio": "未知", "market_cap": "未知", "total_shares": "未知"
    }
    try:
        with open(km_path, 'r') as f:
            data = json.load(f)
        
        # 检测 null 字段
        null_fields = [k for k, v in data.items() if v is None]
        total_fields = len(data)
        null_ratio = len(null_fields) / total_fields if total_fields > 0 else 0
        
        # 构建结果
        result = {k: data.get(k, v) for k, v in defaults.items()}
        result["_data_quality"] = {
            "null_fields": null_fields,
            "null_ratio": null_ratio,
            "total_fields": total_fields,
            "warning": null_ratio > 0.5
        }
        
        return result
    except:
        return {**defaults, "_data_quality": {"null_fields": list(defaults.keys()), "null_ratio": 1.0, "warning": True}}


def replace_template_vars(text: str, variables: dict) -> str:
    """替换模板变量 {{var_name}}"""
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return text


def extract_planner_focus(session_id: str) -> str:
    """从 Planner 输出提取研究重点"""
    planner_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}/stages/planner_output.json"
    try:
        with open(planner_path, 'r') as f:
            data = json.load(f)
        objectives = data.get("research_plan", {}).get("objectives", [])
        return "\n".join([f"- {obj}" for obj in objectives[:5]]) if objectives else "综合分析"
    except:
        return "综合分析"


# ==================== Task 构建函数 ====================

def build_data_manager_task(session_id: str, company_code: str, company_name: str, industry: str = "半导体设备") -> str:
    """构建 DataManager Worker Task（使用 DataManagerWorker 类）"""
    
    return f'''你是 DataManager Agent。

## 执行代码

请执行以下 Python 代码完成数据采集：

```python
import sys, os, json
sys.path.insert(0, "{DEEPFLOW_BASE}/")

from core.data_manager_worker import DataManagerWorker

# 初始化 Worker
worker = DataManagerWorker(
    session_id="{session_id}",
    company_code="{company_code}",
    company_name="{company_name}",
    industry="{industry}"
)

# 执行完整流程（bootstrap + 搜索 + ensure_key_metrics）
result = worker.run()

# 输出结果
print("\\n" + json.dumps(result, ensure_ascii=False, indent=2))

# 检查 key_metrics 是否生成
km_path = "{DEEPFLOW_BASE}/blackboard/{session_id}/data/key_metrics.json"
if os.path.exists(km_path):
    with open(km_path) as f:
        km = json.load(f)
    null_count = sum(1 for k, v in km.items() if v is None and k not in ["company_code", "company_name", "industry", "analysis_date"])
    total = len([k for k in km if k not in ["company_code", "company_name", "industry", "analysis_date"]])
    print("\\nkey_metrics.json: " + str(total - null_count) + "/" + str(total) + " 字段已填充")
    if null_count > 0:
        print("⚠️ 仍为 null 的字段: " + str([k for k, v in km.items() if v is None]))
else:
    print("\\n❌ key_metrics.json 未生成")
```

## 输出要求
- 数据写入 blackboard/{session_id}/data/
- 必须生成 key_metrics.json（含 PE/PB/PS/市值等估值数据）
- 补充搜索写入 data/05_supplement/
- data_manager_result.json 记录执行结果
- 所有错误记录到控制台，不阻断流程
'''
    
    return task


def build_planner_task(session_id: str, company_code: str, company_name: str) -> str:
    """构建 Planner Worker Task"""
    data = extract_data_summary(session_id)
    prompt = read_original_prompt("investment/planner.md")
    
    # 替换模板变量 {{var_name}}
    variables = {
        "code": company_code,
        "name": company_name,
        "session_id": session_id,
        "iteration": 1,
        "task_description": f"分析 {company_name}({company_code}) 的投资价值"
    }
    prompt = replace_template_vars(prompt, variables)
    
    return f'''# 🎯 任务上下文

## 目标公司
- 股票代码：{company_code}
- 公司名称：{company_name}
- 行业：{data["industry"]}
- 最新股价：{data["current_price"]}

## 输入数据
- {DEEPFLOW_BASE}/blackboard/{session_id}/data/key_metrics.json

## 输出
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/planner_output.json

---

{prompt}
'''


def build_researcher_task(angle: str, session_id: str, company_code: str, company_name: str, industry: str = "半导体设备") -> str:
    """构建 Researcher Worker Task"""
    data = extract_data_summary(session_id)
    focus = extract_planner_focus(session_id)
    prompt = read_original_prompt(f"investment/researcher_{angle}.md")
    
    # 检测数据质量并添加警告
    data_quality_warning = ""
    if data.get("_data_quality", {}).get("warning", False):
        null_fields = data["_data_quality"].get("null_fields", [])
        data_quality_warning = f"""
⚠️ **数据质量警告**：key_metrics.json 中 {len(null_fields)} 个字段为 null（{data['_data_quality']['null_ratio']*100:.0f}%缺失）。
缺失字段：{', '.join(null_fields)}
**建议**：如果 60 秒内无法获取数据，使用行业默认值继续分析。
"""
    
    # 替换模板变量 {{var_name}}
    variables = {
        "code": company_code,
        "name": company_name,
        "session_id": session_id,
        "iteration": 1,
        "task_description": f"{angle}角度分析 {company_name}({company_code})",
        "industry": industry
    }
    prompt = replace_template_vars(prompt, variables)
    
    return f'''# 🎯 任务上下文

## 目标公司
- 股票代码：{company_code}
- 公司名称：{company_name}
- 行业：{data["industry"]}
- PE：{data["pe_ttm"]}, PB：{data["pb_ratio"]}

## 研究重点
{focus}
{data_quality_warning}

## 输入数据
- {DEEPFLOW_BASE}/blackboard/{session_id}/data/
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/planner_output.json

## 自行搜索（按需）
- Gemini CLI: gemini -p "查询"
- DuckDuckGo: DDGS().text("查询")
- Tushare: ts.pro_api()

## 输出要求
- 文件：{DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_{angle}_output.json
- 格式：JSON，包含 findings（每项带 confidence 和 source）

---

{prompt}
'''


def build_auditor_task(auditor_type: str, session_id: str, company_code: str, company_name: str) -> str:
    """构建 Auditor Worker Task"""
    perspective = {"factual": "事实准确性", "upside": "乐观偏差", "downside": "悲观偏差"}.get(auditor_type, auditor_type)
    prompt = read_original_prompt("investment/auditor.md")
    
    # 替换模板变量 {{var_name}}
    variables = {
        "code": company_code,
        "name": company_name,
        "session_id": session_id,
        "iteration": 1,
        "task_description": f"{perspective}审计 {company_name}({company_code})",
        "AUDIT_PERSPECTIVE": perspective
    }
    prompt = replace_template_vars(prompt, variables)
    
    return f'''# 🎯 任务上下文

## 目标公司
- 股票代码：{company_code}
- 公司名称：{company_name}

## 审计视角
{perspective}审计

## 输入数据
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_*_output.json

## 输出要求
- 文件：{DEEPFLOW_BASE}/blackboard/{session_id}/stages/auditor_{auditor_type}_output.json
- 格式：JSON，包含 verifications 和 contradictions

---

{prompt}
'''


def build_fixer_task(session_id: str, company_code: str, company_name: str) -> str:
    """构建 Fixer Worker Task"""
    prompt = read_original_prompt("investment/fixer.md")
    
    # 替换模板变量 {{var_name}}
    variables = {
        "deepflow_base": DEEPFLOW_BASE,
        "session_id": session_id,
        "blackboard_base_path": f"{DEEPFLOW_BASE}/blackboard/{session_id}",
        "task_description": f"修正 {company_name}({company_code}) 分析报告中的问题"
    }
    prompt = replace_template_vars(prompt, variables)
    
    return f'''# 🎯 任务上下文

## 目标公司
- 股票代码：{company_code}
- 公司名称：{company_name}

## 输入数据
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_*_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/auditor_*_output.json

## 任务
整合修正数据矛盾，输出统一视图

## 输出
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/fixer_output.json

---

{prompt}
'''


def build_summarizer_task(session_id: str, company_code: str, company_name: str) -> str:
    """构建 Summarizer Worker Task（论点驱动）"""
    data = extract_data_summary(session_id)
    prompt = read_original_prompt("investment/summarizer.md")
    
    # 替换模板变量 {{var_name}}
    variables = {
        "deepflow_base": DEEPFLOW_BASE,
        "session_id": session_id,
        "blackboard_base_path": f"{DEEPFLOW_BASE}/blackboard/{session_id}",
        "task_description": f"生成 {company_name}({company_code}) 投资分析报告"
    }
    prompt = replace_template_vars(prompt, variables)
    
    return f'''# 🎯 Summarizer 任务（论点驱动）

## 目标公司
- 股票代码：{company_code}
- 公司名称：{company_name}
- 当前股价：{data["current_price"]}
- PE：{data["pe_ttm"]}, PB：{data["pb_ratio"]}

## 分层读取（按优先级）

### 第一层（50%时间）- 核心
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/auditor_factual_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_finance_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_macro_chain_output.json

### 第二层（30%时间）- 辅助
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_tech_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_market_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/fixer_output.json

### 第三层（20%时间）- 参考
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_management_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/researcher_sentiment_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/auditor_upside_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/auditor_downside_output.json

## 任务要求

### Step 1: 提取核心矛盾
- 找出"最大利好" vs "最大利空"
- 识别数据分歧

### Step 2: 构建投资逻辑（1-2条）
- 长期逻辑：一句话 + confidence + source
- 短期风险：一句话 + confidence + source
- 关键拐点：可跟踪的指标

### Step 3: 生成三情景目标价
- Bull Case：目标价 + 隐含PE + 假设 + 概率
- Base Case：同上
- Bear Case：同上

### Step 4: 生成最终报告
- 论点驱动结构
- Markdown格式

## 输出
- JSON: {DEEPFLOW_BASE}/blackboard/{session_id}/stages/summarizer_output.json
- Markdown: {DEEPFLOW_BASE}/blackboard/{session_id}/final_report.md

---

{prompt}
'''


def build_send_reporter_task(session_id: str, company_code: str, company_name: str) -> str:
    """构建 Send Reporter Worker Task"""
    prompt = read_original_prompt("investment/send_reporter.md")
    
    variables = {
        "session_id": session_id,
        "company_code": company_code,
        "company_name": company_name,
        "blackboard_base_path": f"{DEEPFLOW_BASE}/blackboard/{session_id}"
    }
    prompt = replace_template_vars(prompt, variables)
    
    return f'''# 🎯 Send Reporter 任务

## 目标公司
- 股票代码：{company_code}
- 公司名称：{company_name}

## 输入文件
- {DEEPFLOW_BASE}/blackboard/{session_id}/stages/summarizer_output.json
- {DEEPFLOW_BASE}/blackboard/{session_id}/final_report.md

## 任务
1. 读取 summarizer_output.json 和 final_report.md
2. 提取核心投资摘要：
   - 评级（买入/持有/卖出）
   - 目标价（中性/乐观/悲观）
   - 置信度
   - 核心逻辑（2-3句话）
   - 关键风险（1-2条）
3. 使用 message 工具发送飞书消息给用户

## 飞书消息格式
```
# 📊 {company_name}({company_code}) 投资分析完成

**评级**: {{rating}} | **目标价**: ¥{{target_price}} | **置信度**: {{confidence}}

**核心逻辑**:
{{executive_summary}}

**关键风险**:
{{top_risks}}

**完整报告**: {{final_report_path}}
```

## 用户配置
- 飞书用户 OpenID: ou_d55068472a52a0f34ff72c3b6930044c
- 发送渠道: feishu

## 输出
- 飞书消息发送确认
- 如发送失败，记录错误但不阻塞

---

{prompt}
'''


# 导出所有构建函数
__all__ = [
    'build_data_manager_task',
    'build_planner_task', 
    'build_researcher_task',
    'build_auditor_task',
    'build_fixer_task',
    'build_summarizer_task',
    'build_send_reporter_task',
    'extract_data_summary',
    'extract_planner_focus',
]
