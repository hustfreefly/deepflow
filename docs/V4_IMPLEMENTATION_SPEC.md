# DeepFlow V4.0 全面实施方案
## DataManager Worker 代码执行 + 统一搜索层 + 上下文注入

**版本**: 4.0  
**日期**: 2026-04-22  
**状态**: 实施规范  
**参考**: pipeline_engine_orchestrator.md.bak.20260419

---

## 一、架构总览

### 1.1 执行链路

```
主Agent(depth-0)
  └── sessions_spawn → Orchestrator Agent(depth-1) [Python代码执行]
        ├── [本地] 初始化：session_id、目录、配置加载
        ├── [本地] 统一搜索层：Gemini → DDG → Tushare
        ├── sessions_spawn → DataManager Worker(depth-2) [执行bootstrap代码]
        │     └── 执行 data_loop.bootstrap_phase(context)
        │     └── 写入 blackboard/{session_id}/data/
        ├── sessions_spawn → Planner Worker(depth-2) [上下文注入]
        │     └── 读取 data/ → 制定研究计划
        ├── sessions_spawn → Researchers ×6(depth-2) 并行 [上下文注入]
        │     └── 读取 data/ + planner_output → 分析
        ├── sessions_spawn → Auditors ×3(depth-2) 并行 [上下文注入]
        │     └── 读取 researcher_outputs → 审计
        ├── sessions_spawn → Fixer Worker(depth-2) [上下文注入]
        │     └── 读取所有输出 → 修正
        └── sessions_spawn → Summarizer Worker(depth-2) [上下文注入]
              └── 生成 final_report.md
```

### 1.2 核心设计原则

| 原则 | 说明 |
|:---|:---|
| **Agent 编程范式** | Orchestrator 执行 Python 代码，不是读文本指南 |
| **DataManager Worker 代码化** | Worker 执行真正的 bootstrap，不是文本提示 |
| **统一搜索层本地执行** | Orchestrator 本地执行搜索，结果写入 blackboard |
| **上下文强制注入** | 所有 Workers 必须收到完整上下文 |
| **数据驱动** | Workers 从 blackboard 读取数据，不自己采集 |

---

## 二、文件结构

```
.deepflow/
├── orchestrator_agent.py          # ← V4.0 重写：Python代码执行
├── orchestrator_agent_v3.py       # 备份：V3.0 文本指南版
├── prompts/
│   ├── data_manager_v4.md         # ← 重写：包含完整bootstrap代码
│   ├── investment_planner.md      # 保持：原始提示词
│   ├── investment_researcher_*.md # 保持：原始提示词
│   ├── investment_auditor.md      # 保持：原始提示词
│   ├── investment_fixer.md        # 保持：原始提示词
│   └── investment_summarizer.md   # 保持：原始提示词
├── core/                          # 新增：核心工具库
│   ├── __init__.py
│   ├── search_tools.py            # 统一搜索层
│   ├── task_builder.py            # Task构建器
│   └── context_extractor.py       # 上下文提取器
├── docs/
│   └── V4_IMPLEMENTATION_SPEC.md  # 本文档
└── cage/
    └── v4_contract.yaml           # 契约文件
```

---

## 三、核心模块实现

### 3.1 统一搜索层 (core/search_tools.py)

```python
"""
统一搜索层 - 强制工具优先级

优先级：
1. Gemini CLI（首选）- 内置 Google Search grounding
2. DuckDuckGo（fallback）- Python 库
3. Tushare API（财务专用）
4. web_fetch（最后手段）
"""

import subprocess
import json
from typing import Optional, Dict, Any


def gemini_search(query: str, timeout: int = 30) -> Optional[str]:
    """
    Gemini CLI 搜索（首选）
    
    优势：
    - 内置 Google Search grounding
    - 直接返回搜索结果摘要
    - 无需额外认证
    """
    try:
        result = subprocess.run(
            ["gemini", "-p", query],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout
        else:
            print(f"Gemini error: {result.stderr}")
            return None
    except Exception as e:
        print(f"Gemini search failed: {e}")
        return None


def duckduckgo_search(query: str, max_results: int = 5) -> Optional[list]:
    """
    DuckDuckGo 搜索（fallback）
    """
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=max_results)
        return results
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}")
        return None


def tushare_financial(ts_code: str) -> Optional[Dict[str, Any]]:
    """
    Tushare 财务数据查询（财务专用）
    """
    try:
        import tushare as ts
        pro = ts.pro_api()
        
        # 财务指标
        indicators = pro.fina_indicator(ts_code=ts_code)
        
        # 利润表
        income = pro.income(
            ts_code=ts_code,
            fields="ts_code,end_date,total_revenue,net_profit"
        )
        
        return {
            "indicators": indicators.to_dict() if indicators is not None else {},
            "income": income.to_dict() if income is not None else {}
        }
    except Exception as e:
        print(f"Tushare query failed: {e}")
        return None


def unified_search(
    query: str,
    search_type: str = "auto",
    ts_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    统一搜索接口
    
    Args:
        query: 搜索查询
        search_type: "auto" | "gemini" | "duckduckgo" | "tushare"
        ts_code: 股票代码（仅 tushare 需要）
    
    Returns:
        {
            "source": "gemini" | "duckduckgo" | "tushare" | "failed",
            "data": 搜索结果,
            "query": 原始查询
        }
    """
    # 1. Tushare（财务专用）
    if search_type in ["auto", "tushare"] and ts_code:
        result = tushare_financial(ts_code)
        if result:
            return {
                "source": "tushare",
                "data": result,
                "query": query
            }
    
    # 2. Gemini CLI（首选）
    if search_type in ["auto", "gemini"]:
        result = gemini_search(query)
        if result:
            return {
                "source": "gemini",
                "data": result,
                "query": query
            }
    
    # 3. DuckDuckGo（fallback）
    if search_type in ["auto", "duckduckgo"]:
        result = duckduckgo_search(query)
        if result:
            return {
                "source": "duckduckgo",
                "data": result,
                "query": query
            }
    
    # 4. 全部失败
    return {
        "source": "failed",
        "data": None,
        "query": query
    }


def run_supplement_search(
    session_id: str,
    company_code: str,
    company_name: str,
    industry: str = "半导体设备"
) -> Dict[str, Any]:
    """
    执行补充搜索（STEP 2）
    
    搜索维度：
    1. 行业趋势
    2. 竞品对比
    3. 券商预期
    4. 风险因素
    """
    import os
    
    supplement_dir = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/05_supplement"
    os.makedirs(supplement_dir, exist_ok=True)
    
    search_tasks = [
        ("行业趋势", f"{industry}行业 2025 2026 市场规模 增长趋势"),
        ("竞品对比", f"{company_name} {company_code} 竞争对手 市场份额 对比"),
        ("券商预期", f"{company_name} {company_code} 券商 一致预期 目标价 2026"),
        ("风险因素", f"{company_name} {company_code} 风险 挑战 问题"),
    ]
    
    results = {}
    for name, query in search_tasks:
        print(f"搜索: {name}")
        result = unified_search(query)
        
        if result["source"] != "failed":
            output_path = f"{supplement_dir}/{name}.json"
            with open(output_path, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            results[name] = {"status": "success", "path": output_path}
            print(f"  ✅ {name}")
        else:
            results[name] = {"status": "failed"}
            print(f"  ⚠️ {name}")
    
    return {
        "total": len(search_tasks),
        "success": sum(1 for r in results.values() if r["status"] == "success"),
        "results": results
    }
```

### 3.2 Task 构建器 (core/task_builder.py)

```python
"""
Task 构建器 - 为所有 Workers 构建增强版 Task

核心功能：
1. 读取原始提示词
2. 提取数据摘要
3. 注入完整上下文
4. 生成最终 Task
"""

import os
import json
from typing import Dict, Any, List, Optional


def read_original_prompt(prompt_file: str) -> str:
    """读取原始提示词文件"""
    base_dir = "/Users/allen/.openclaw/workspace/.deepflow"
    prompt_path = os.path.join(base_dir, prompt_file)
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Warning: Could not read {prompt_file}: {e}")
        return f"# {prompt_file}\n\n执行分析任务。"


def extract_data_summary(session_id: str) -> Dict[str, str]:
    """从 Blackboard 提取数据摘要"""
    key_metrics_path = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/key_metrics.json"
    
    defaults = {
        "company_name": "未知",
        "company_code": "未知",
        "industry": "未知",
        "latest_price": "未知",
        "market_cap": "未知",
        "pe_ratio": "未知",
        "pb_ratio": "未知",
        "ps_ratio": "未知"
    }
    
    try:
        with open(key_metrics_path, 'r') as f:
            data = json.load(f)
        return {
            "company_name": data.get("company_name", defaults["company_name"]),
            "company_code": data.get("company_code", defaults["company_code"]),
            "industry": data.get("industry", defaults["industry"]),
            "latest_price": str(data.get("latest_price", defaults["latest_price"])),
            "market_cap": str(data.get("market_cap", defaults["market_cap"])),
            "pe_ratio": str(data.get("pe_ratio", defaults["pe_ratio"])),
            "pb_ratio": str(data.get("pb_ratio", defaults["pb_ratio"])),
            "ps_ratio": str(data.get("ps_ratio", defaults["ps_ratio"]))
        }
    except Exception as e:
        print(f"Warning: Could not extract data summary: {e}")
        return defaults


def extract_planner_focus(session_id: str) -> str:
    """从 Planner 输出提取研究重点"""
    planner_path = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/stages/planner_output.json"
    
    try:
        with open(planner_path, 'r') as f:
            data = json.load(f)
        
        objectives = data.get("research_plan", {}).get("objectives", [])
        if objectives:
            return "\n".join([f"- {obj}" for obj in objectives[:5]])
        
        # 尝试其他字段
        focus_areas = data.get("focus_areas", [])
        if focus_areas:
            return "\n".join([f"- {area}" for area in focus_areas[:5]])
        
        return "综合分析"
    except Exception as e:
        print(f"Warning: Could not extract planner focus: {e}")
        return "综合分析"


def build_data_manager_task(
    session_id: str,
    company_code: str,
    company_name: str
) -> str:
    """
    构建 DataManager Worker Task（包含完整 bootstrap 代码）
    """
    task = f'''你是 DataManager Agent。你的任务是执行数据采集 bootstrap。

## 环境说明
你拥有完整的 Python 执行环境，可以 import DeepFlow 核心模块。

## 执行代码

请执行以下 Python 代码完成数据采集：

```python
import sys
import os
import json

# 1. 设置路径
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

# 2. 导入模块
from data_providers.investment import register_providers
from data_manager import DataEvolutionLoop, ConfigDrivenCollector
from blackboard_manager import BlackboardManager

# 3. 注册数据源
print("注册数据源...")
register_providers()  # 注册 tushare/akshare/sina/web_fetch

# 4. 初始化采集器
config_path = "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
collector = ConfigDrivenCollector(config_path)

# 5. 初始化 Blackboard
blackboard = BlackboardManager("{session_id}")
data_loop = DataEvolutionLoop(collector, blackboard)

# 6. 设置上下文
context = {{"code": "{company_code}", "name": "{company_name}"}}

# 7. 执行 bootstrap 采集
print("开始执行 bootstrap 采集...")
data_loop.bootstrap_phase(context)
print("Bootstrap 完成！")

# 8. 验证数据
index_path = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/INDEX.json"
key_metrics_path = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data/key_metrics.json"

if os.path.exists(index_path):
    with open(index_path) as f:
        index = json.load(f)
    print(f"✅ 已采集 {{len(index)}} 个数据集")
elif os.path.exists(key_metrics_path):
    print("✅ 关键指标数据已就绪")
else:
    print("⚠️ 数据采集可能不完整")

print("DataManager 任务完成！")
```

## 输出要求
- 数据写入 blackboard/{session_id}/data/
- 必须生成 INDEX.json 或 key_metrics.json
- 返回执行结果摘要

## 错误处理
如果 bootstrap 失败：
1. 检查错误日志
2. 尝试降级方案（直接搜索）
3. 记录失败原因
'''
    return task


def build_worker_task(
    agent_role: str,
    session_id: str,
    company_code: str,
    company_name: str,
    prompt_file: str,
    output_path: str,
    input_paths: List[str],
    extra_context: Optional[Dict[str, str]] = None
) -> str:
    """
    构建通用 Worker Task（上下文注入 + 原始提示词）
    
    适用于：Planner, Researchers, Auditors, Fixer, Summarizer
    """
    # 1. 读取原始提示词
    original_prompt = read_original_prompt(prompt_file)
    
    # 2. 提取数据摘要
    data_summary = extract_data_summary(session_id)
    
    # 3. 提取研究重点（如果是 researcher 或之后阶段）
    planner_focus = ""
    if "planner" not in agent_role:
        planner_focus = extract_planner_focus(session_id)
    
    # 4. 构建输入路径描述
    input_paths_str = "\n".join([f"- {path}" for path in input_paths])
    
    # 5. 构建额外上下文
    extra_context_str = ""
    if extra_context:
        for key, value in extra_context.items():
            extra_context_str += f"- {key}: {value}\n"
    
    # 6. 组装完整 Task
    task = f'''# 🎯 任务上下文（Orchestrator 注入）

## 目标公司信息
- **股票代码**：{company_code}
- **公司名称**：{company_name}
- **所属行业**：{data_summary["industry"]}
- **最新股价**：{data_summary["latest_price"]}
- **市值**：{data_summary["market_cap"]}
- **市盈率(PE)**：{data_summary["pe_ratio"]}
- **市净率(PB)**：{data_summary["pb_ratio"]}
- **市销率(PS)**：{data_summary["ps_ratio"]}
'''
    
    # 添加研究重点（非 Planner 阶段）
    if planner_focus and planner_focus != "综合分析":
        task += f'''
## 研究重点（来自 Planner）
{planner_focus}
'''
    
    # 添加额外上下文
    if extra_context_str:
        task += f'''
## 额外上下文
{extra_context_str}
'''
    
    # 添加输入输出
    task += f'''
## 输入数据路径
{input_paths_str}

## 输出要求
- **输出文件**：{output_path}
- **格式**：JSON
- **要求**：
  - 必须包含具体数字和数据来源
  - 必须标注数据置信度
  - 必须包含质量自评分数

---

# 原始提示词（{agent_role}）

{original_prompt}
'''
    
    return task
```

### 3.3 Orchestrator 主模块 (orchestrator_agent.py)

```python
"""
DeepFlow V4.0 Orchestrator Agent
=================================

Agent 编程范式：执行 Python 代码，不是读文本指南。

执行流程：
1. [本地] 初始化
2. [本地] 统一搜索层
3. [spawn] DataManager Worker（执行 bootstrap）
4. [spawn] Planner Worker
5. [spawn] Researchers ×6（并行）
6. [spawn] Auditors ×3（并行）
7. [spawn] Fixer Worker
8. [spawn] Summarizer Worker
"""

import sys
import os
import json
import uuid
import time

# 导入核心工具
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')
from core.search_tools import run_supplement_search
from core.task_builder import (
    build_data_manager_task,
    build_worker_task
)


def generate_session_id(company_name: str, company_code: str) -> str:
    """生成 session_id"""
    code_clean = company_code.replace('.SH', '').replace('.SZ', '')
    return f"{company_name}_{code_clean}_{uuid.uuid4().hex[:8]}"


def init_blackboard(session_id: str) -> str:
    """初始化 Blackboard 目录"""
    base = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}"
    os.makedirs(f"{base}/data", exist_ok=True)
    os.makedirs(f"{base}/stages", exist_ok=True)
    return base


def save_execution_plan(session_id: str, plan: dict):
    """保存执行计划"""
    plan_path = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/execution_plan.json"
    with open(plan_path, 'w') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def run_orchestrator(
    company_code: str = "688652.SH",
    company_name: str = "京仪装备",
    industry: str = "半导体设备"
) -> dict:
    """
    Orchestrator 主执行流程
    
    注意：这个函数在 Orchestrator Agent 环境中执行，
    使用 sessions_spawn 工具创建 Workers。
    """
    print("=" * 60)
    print(f"DeepFlow V4.0 Orchestrator")
    print(f"目标: {company_name}({company_code})")
    print("=" * 60)
    
    # ==================== STEP 0: 初始化 ====================
    session_id = generate_session_id(company_name, company_code)
    blackboard_base = init_blackboard(session_id)
    
    print(f"\n[STEP 0] 初始化完成")
    print(f"  Session ID: {session_id}")
    print(f"  Blackboard: {blackboard_base}")
    
    # 保存执行计划
    execution_plan = {
        "session_id": session_id,
        "company_code": company_code,
        "company_name": company_name,
        "industry": industry,
        "version": "4.0",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_execution_plan(session_id, execution_plan)
    
    # ==================== STEP 1: DataManager Worker ====================
    print(f"\n[STEP 1] DataManager Worker（执行 bootstrap）")
    
    data_manager_task = build_data_manager_task(
        session_id=session_id,
        company_code=company_code,
        company_name=company_name
    )
    
    # 注意：这里是指导语，实际执行使用 sessions_spawn 工具
    print("  构建 DataManager Task 完成")
    print("  Task 长度:", len(data_manager_task), "字符")
    print("  ⚠️  请使用 sessions_spawn 创建 DataManager Worker")
    
    # 返回 Task 和执行状态
    return {
        "session_id": session_id,
        "company_code": company_code,
        "company_name": company_name,
        "industry": industry,
        "blackboard_base": blackboard_base,
        "steps": [
            {
                "step": 1,
                "name": "data_manager",
                "task": data_manager_task,
                "timeout": 300,
                "output_path": f"{blackboard_base}/data/INDEX.json"
            },
            # 其他步骤由调用者继续执行
        ],
        "status": "initialized"
    }


if __name__ == "__main__":
    # 读取环境变量
    code = os.environ.get('DEEPFLOW_CODE', '688652.SH')
    name = os.environ.get('DEEPFLOW_NAME', '京仪装备')
    industry = os.environ.get('DEEPFLOW_INDUSTRY', '半导体设备')
    
    result = run_orchestrator(code, name, industry)
    print("\n" + "=" * 60)
    print("初始化完成，准备执行 Workers")
    print(f"Session ID: {result['session_id']}")
```

---

## 四、数据流设计

### 4.1 文件依赖关系

```
Phase 0: 初始化
  └── 生成 session_id
  └── 创建目录结构

Phase 1: DataManager Worker
  ├── 输入: company_code, company_name (通过 Task 注入)
  ├── 执行: bootstrap_phase(context)
  └── 输出: blackboard/{session_id}/data/
      ├── INDEX.json
      ├── key_metrics.json
      └── 01_financials/, 02_market_quote/, ...

Phase 2: 统一搜索层（本地执行）
  ├── 输入: company_code, company_name, industry
  ├── 执行: run_supplement_search()
  └── 输出: blackboard/{session_id}/data/05_supplement/
      ├── 行业趋势.json
      ├── 竞品对比.json
      ├── 券商预期.json
      └── 风险因素.json

Phase 3: Planner Worker
  ├── 输入: data/key_metrics.json (上下文注入)
  ├── 读取: data/ 所有数据
  └── 输出: stages/planner_output.json
      └── research_plan.objectives[]

Phase 4: Researchers ×6（并行）
  ├── 输入: 
  │   ├── data/key_metrics.json (上下文注入)
  │   └── stages/planner_output.json (上下文注入)
  ├── 读取: data/ 相关数据
  └── 输出: stages/researcher_XXX_output.json

Phase 5: Auditors ×3（并行）
  ├── 输入: 
  │   ├── 6个 researcher 输出路径 (上下文注入)
  │   └── 审计视角 (上下文注入)
  ├── 读取: stages/researcher_*_output.json
  └── 输出: stages/auditor_XXX_output.json

Phase 6: Fixer Worker
  ├── 输入:
  │   ├── 6个 researcher 输出路径
  │   └── 3个 auditor 输出路径
  ├── 读取: 所有 researcher + auditor 输出
  └── 输出: stages/fixer_output.json

Phase 7: Summarizer Worker
  ├── 输入:
  │   ├── stages/fixer_output.json
  │   └── data/key_metrics.json
  ├── 读取: fixer_output + key_metrics
  └── 输出: 
      ├── stages/summarizer_output.json
      └── final_report.md
```

### 4.2 上下文传递链

```
Orchestrator (本地数据)
  ├── company_code, company_name (硬编码)
  ├── data_summary (从 key_metrics.json 读取)
  └── planner_focus (从 planner_output.json 读取)
      │
      ▼ 通过 Task 注入
      │
DataManager Worker
  └── 使用 company_code/name 执行 bootstrap
      │
      ▼ 写入 blackboard
      │
Planner Worker
  ├── 收到: company_code/name + data_summary
  └── 读取: data/ 制定计划
      │
      ▼ 写入 blackboard
      │
Researchers
  ├── 收到: company_code/name + data_summary + planner_focus
  └── 读取: data/ + planner_output 分析
      │
      ▼ 写入 blackboard
      │
Auditors
  ├── 收到: company_code/name + 6个 researcher 路径
  └── 读取: researcher 输出 审计
      │
      ▼ 写入 blackboard
      │
Fixer → Summarizer
  └── 逐级读取前一阶段输出
```

---

## 五、错误处理与降级策略

### 5.1 DataManager Worker 失败

```python
# 主流程
try:
    # 尝试使用 DataManager 模块
    data_manager_task = build_data_manager_task(...)
    spawn_worker("data_manager", data_manager_task)
except Exception as e:
    print(f"DataManager bootstrap 失败: {e}")
    
    # 降级方案：使用统一搜索层
    print("切换到降级方案：统一搜索层")
    result = run_supplement_search(session_id, company_code, company_name)
    
    # 生成最小化的 key_metrics.json
    minimal_data = {
        "company_name": company_name,
        "company_code": company_code,
        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "fallback_search"
    }
    save_to_blackboard(minimal_data, f"{session_id}/data/key_metrics.json")
```

### 5.2 Worker 超时失败

```python
# 对于超时 Worker，记录失败但继续执行
failed_workers = []

for worker in workers:
    try:
        result = spawn_worker(worker)
        if not result.success:
            failed_workers.append(worker.role)
            print(f"⚠️ {worker.role} 失败，继续执行")
    except TimeoutError:
        failed_workers.append(worker.role)
        print(f"⚠️ {worker.role} 超时，继续执行")

# 最终报告标注失败的 Workers
final_report["failed_workers"] = failed_workers
```

### 5.3 搜索工具不可用

```python
# 统一搜索层自动 fallback
result = unified_search(query)

if result["source"] == "failed":
    print("⚠️ 所有搜索工具都失败")
    # 使用 LLM 知识（标注为"LLM生成，未验证"）
    return {
        "source": "llm_fallback",
        "data": "基于LLM知识生成，未经验证",
        "verified": False
    }
```

---

## 六、验证与契约

### 6.1 验证清单

```python
V4_VERIFICATION_CHECKLIST = {
    "phase_0_init": {
        "session_id_generated": "检查 session_id 是否符合格式",
        "directories_created": "检查 blackboard/{session_id}/ 目录结构",
        "execution_plan_saved": "检查 execution_plan.json 是否存在"
    },
    "phase_1_data_manager": {
        "bootstrap_executed": "检查 DataManager Worker 是否执行了 Python 代码",
        "data_files_exist": "检查 data/INDEX.json 或 key_metrics.json 是否存在",
        "at_least_one_dataset": "检查是否至少采集了 1 个数据集"
    },
    "phase_2_search": {
        "supplement_dir_exists": "检查 data/05_supplement/ 是否存在",
        "at_least_one_search_result": "检查是否至少有一个搜索结果文件"
    },
    "phase_3_planner": {
        "planner_output_exists": "检查 stages/planner_output.json 是否存在",
        "has_objectives": "检查 planner_output 是否包含研究目标"
    },
    "phase_4_researchers": {
        "all_6_completed": "检查是否所有 6 个 researcher 都完成",
        "outputs_valid": "检查所有 researcher 输出是否为有效 JSON"
    },
    "phase_5_auditors": {
        "all_3_completed": "检查是否所有 3 个 auditor 都完成",
        "findings_exist": "检查 auditor 输出是否包含 findings"
    },
    "phase_6_fixer": {
        "fixer_output_exists": "检查 stages/fixer_output.json 是否存在"
    },
    "phase_7_summarizer": {
        "final_report_exists": "检查 final_report.md 是否存在",
        "report_has_conclusion": "检查报告是否包含投资结论"
    }
}
```

### 6.2 契约笼子 (cage/v4_contract.yaml)

```yaml
module: deepflow_v4
version: "4.0"
date: "2026-04-22"

architecture:
  orchestrator:
    type: agent_programming
    description: "执行 Python 代码，不是读文本指南"
    capabilities:
      - local_python_execution
      - sessions_spawn_tool
      - sessions_yield_tool
    
  data_manager_worker:
    type: code_execution_worker
    description: "执行完整的 Python bootstrap 代码"
    requirements:
      - can_import_data_manager_modules
      - executes_bootstrap_phase
      - writes_to_blackboard_data
    
  search_layer:
    type: unified_search
    description: "Orchestrator 本地执行的统一搜索层"
    priority:
      - gemini_cli
      - duckduckgo
      - tushare
      - web_fetch
    
  other_workers:
    type: context_enhanced
    description: "接收完整上下文注入，只负责分析"
    requirements:
      - company_info_injected
      - data_summary_injected
      - planner_focus_injected
      - reads_from_blackboard
      - writes_json_output

interfaces:
  orchestrator_input:
    company_code: str
    company_name: str
    industry: str
    
  orchestrator_output:
    session_id: str
    blackboard_base: str
    steps: list
    status: str
    
  data_manager_task:
    contains_python_code: true
    bootstrap_phase: true
    
  worker_task:
    contains_context_injection: true
    contains_original_prompt: true
    input_paths_specified: true
    output_path_specified: true

validation:
  pre_execution:
    - check_module_imports
    - check_blackboard_permissions
    
  during_execution:
    - verify_data_manager_bootstrap
    - verify_search_results
    - verify_worker_outputs
    
  post_execution:
    - validate_final_report
    - check_all_outputs_exist
    - score_execution_quality
```

---

## 七、实施计划

### 7.1 文件创建清单

| 序号 | 文件路径 | 状态 | 说明 |
|:---|:---|:---|:---|
| 1 | `core/__init__.py` | 新建 | 核心模块包 |
| 2 | `core/search_tools.py` | 新建 | 统一搜索层 |
| 3 | `core/task_builder.py` | 新建 | Task 构建器 |
| 4 | `core/context_extractor.py` | 新建 | 上下文提取器 |
| 5 | `orchestrator_agent.py` | 重写 | V4.0 主模块 |
| 6 | `prompts/data_manager_v4.md` | 新建 | DataManager Worker 提示词 |
| 7 | `cage/v4_contract.yaml` | 新建 | 契约文件 |
| 8 | `tests/test_v4.py` | 新建 | 验证测试 |

### 7.2 实施步骤

**Step 1: 创建核心模块 (2小时)**
```bash
# 创建目录结构
mkdir -p .deepflow/core
mkdir -p .deepflow/tests

# 创建核心模块文件
touch .deepflow/core/__init__.py
touch .deepflow/core/search_tools.py
touch .deepflow/core/task_builder.py
touch .deepflow/core/context_extractor.py
```

**Step 2: 实现统一搜索层 (1小时)**
- 实现 `gemini_search()`
- 实现 `duckduckgo_search()`
- 实现 `tushare_financial()`
- 实现 `unified_search()` 统一接口
- 实现 `run_supplement_search()` 补充搜索

**Step 3: 实现 Task 构建器 (1.5小时)**
- 实现 `read_original_prompt()`
- 实现 `extract_data_summary()`
- 实现 `extract_planner_focus()`
- 实现 `build_data_manager_task()`（含 bootstrap 代码）
- 实现 `build_worker_task()`（通用 Worker Task）

**Step 4: 重写 Orchestrator (2小时)**
- 重写 `orchestrator_agent.py`
- 删除 V3.0 文本指南内容
- 实现 Agent 编程范式
- 实现执行流程编排

**Step 5: 创建 DataManager V4 提示词 (0.5小时)**
- 基于 `build_data_manager_task()` 生成
- 包含完整的 bootstrap 代码
- 包含错误处理和降级方案

**Step 6: 验证测试 (2小时)**
- 单元测试：搜索工具
- 单元测试：Task 构建器
- 集成测试：完整流程
- 契约验证

**总计：9小时**

### 7.3 验证检查点

```python
# 验证点 1：统一搜索层
result = unified_search("京仪装备 688652 财务数据")
assert result["source"] in ["gemini", "duckduckgo", "tushare"]
assert result["data"] is not None

# 验证点 2：Task 构建器
task = build_data_manager_task("test_session", "688652.SH", "京仪装备")
assert "bootstrap_phase" in task
assert "DataEvolutionLoop" in task

# 验证点 3：完整流程
result = run_orchestrator("688652.SH", "京仪装备")
assert result["session_id"] is not None
assert result["steps"][0]["name"] == "data_manager"
assert "bootstrap" in result["steps"][0]["task"]
```

---

## 八、关联部分联动

### 8.1 与现有配置文件的联动

| 配置文件 | 联动方式 | 说明 |
|:---|:---|:---|
| `domains/investment.yaml` | 读取 | Orchestrator 读取 agents 配置 |
| `data_sources/investment.yaml` | 传入 | DataManager Worker 使用 |
| `prompts/*.md` | 读取 | Task 构建器读取原始提示词 |
| `blackboard/{session_id}/` | 写入/读取 | 所有数据流通道 |

### 8.2 与 PipelineEngine 的联动

```python
# PipelineEngine 可以调用 V4.0 Orchestrator
from orchestrator_agent import run_orchestrator

class PipelineEngineV4:
    def execute(self, domain, context):
        # 调用 V4.0 Orchestrator
        result = run_orchestrator(
            company_code=context["code"],
            company_name=context["name"]
        )
        
        # 使用 sessions_spawn 创建 Orchestrator Agent
        # 由 Orchestrator Agent 执行后续步骤
        ...
```

### 8.3 向后兼容

```python
# V3.0 版本备份
mv orchestrator_agent.py orchestrator_agent_v3.py

# V4.0 新实现
# orchestrator_agent.py (新)

# 调用者可以选择版本
def run_analysis(version="v4"):
    if version == "v4":
        from orchestrator_agent import run_orchestrator
    else:
        from orchestrator_agent_v3 import run_orchestrator
    ...
```

---

## 九、预期效果

### 9.1 质量提升

| 维度 | V3.0 | V4.0 预期 |
|:---|:---|:---|
| DataManager 数据质量 | 不稳定（文本提示）| 高（代码执行 bootstrap）|
| Workers 上下文完整性 | 部分有 | 100% 强制注入 |
| 搜索工具一致性 | Workers 各自为政 | 统一优先级策略 |
| 可调试性 | 低 | 高（代码化）|
| 可验证性 | 低 | 高（检查点机制）|

### 9.2 执行效率

| 指标 | V3.0 | V4.0 预期 |
|:---|:---|:---|
| DataManager 耗时 | ~4-5分钟 | ~3-4分钟（代码优化）|
| 搜索层耗时 | Workers 各自搜索 | ~1-2分钟（统一缓存）|
| 总流程耗时 | ~20-25分钟 | ~15-20分钟 |
| 成功率 | ~85% | ~95% |

---

## 十、决策确认

基于 bak 文件的先进设计，结合用户确认的需求，V4.0 方案的核心决策：

### ✅ 已确认

1. **DataManager Worker 执行 Python 代码**
   - Task 包含完整的 `bootstrap_phase()` 代码
   - Worker 可以 import DeepFlow 核心模块
   - 写入 blackboard/data/ 目录

2. **统一搜索层放在 Orchestrator 本地执行**
   - Orchestrator 执行 `run_supplement_search()`
   - 结果写入 blackboard/data/05_supplement/
   - Workers 只读取，不自己搜索

3. **其他 Workers 只需要上下文注入**
   - 使用 `build_worker_task()` 构建完整 Task
   - 强制注入：公司信息、数据摘要、研究重点
   - Workers 从 blackboard 读取数据，只负责分析

### 📋 实施准备

请确认以下事项后开始实施：

- [ ] 确认 V4.0 方案设计
- [ ] 确认 9 小时实施时间预算
- [ ] 确认保留 V3.0 备份
- [ ] 确认测试验证标准

**确认后开始实施。**