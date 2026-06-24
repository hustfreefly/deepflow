# 模块过渡引导词设计 V3（专家评审终版）

## 概述

当 DeepFlow 的一个模块完成时，引导用户进入下一个模块。

## 设计原则

1. **用户友好**：避免技术术语，使用用户能感知的价值描述
2. **明确选项**：给出 2-3 个清晰的下一步选项，标记推荐项
3. **简洁信息**：维度评分默认折叠，只展示总分和等级
4. **确定性**：所有用户看到相同的引导词格式（变量填充）
5. **架构合规**：数据生成层 vs 展示渲染层分离，职责清晰

## 评审修订记录

### V3 修订（2026-06-25 专家评审后）

**UX专家反馈**：
- ✅ 修复：技术术语改为用户价值描述（"系统架构设计" → "整体设计方案"）
- ✅ 修复：维度摘要默认折叠，只展示总分
- ✅ 修复：低质量选项措辞从威胁改为建议
- ✅ 修复：Ship Pro 完成选项添加推荐标记

**技术文档专家反馈**：
- ✅ 修复：Solution Pro 维度名称（完整性、必要性、目标一致性、全局影响）
- ✅ 修复：删除不存在的 `route_recommendation.suggested_engine` 引用
- ✅ 修复：Spec Pro 维度名称统一为 5 维度（清晰度、完整度、可执行度、一致性、可行性）
- ✅ 修复：`write_auto_chain()` 函数签名与实际代码对齐
- ✅ 修复：补充完整的文件路径说明

**架构专家反馈**：
- ✅ 修复：使用 `quality.level`（S/A/B/C）而非硬编码阈值
- ✅ 修复：明确 `_handle_done_action()` 为待实现方法
- ✅ 修复：补充 auto_chain 机制的完整说明

---

## 架构设计（评审修订）

### 核心原则：数据生成 vs 展示渲染分离

```
┌─────────────────┐         ┌──────────────────┐
│  数据生成层      │  JSON   │  展示渲染层       │
│                 │ ───────> │                  │
│ - coordinator   │         │ - 主 Agent       │
│ - watcher       │         │   (读取 JSON,    │
│ - workers       │         │    渲染模板,     │
└─────────────────┘         │    展示给用户)   │
                            └──────────────────┘
```

### 实现位置（修订后）

| 过渡点 | 数据生成 | 展示渲染 | 说明 |
|--------|---------|---------|------|
| Spec Pro → Solution Pro | `round_result.json` 添加 `transition_prompt` 字段 | 主 Agent 读取后渲染 | StructureWorker 生成数据 |
| Solution Pro → Ship Pro | `.auto_chain_trigger` 添加 `transition_prompt` 字段 | 主 Agent 读取后渲染 | watcher 生成数据 |
| Ship Pro 完成 | `.completed` 添加 `transition_prompt` 字段 | 主 Agent 读取后渲染 | watcher 生成数据 |

### 质量判断（修订后）

**不再硬编码阈值 75**，改为使用 `quality.level`（S/A/B/C）：
- S/A 级 → 高质量引导词（推荐启动下游）
- B 级 → 中等引导词（提示可继续优化）
- C 级 → 低质量引导词（建议继续补充）

---

## 引导词模板

### 1. Spec Pro → Solution Pro

#### 高质量（S/A 级）

```
━━━━━━━━━━━━━━━━━━━━
✅ 需求梳理完成！

📊 质量评分：{quality_score} / 100（{quality_level}级）

📄 需求文档已生成：
   • {num_users} 个用户角色
   • {num_capabilities} 项核心能力
   • {num_constraints} 项约束条件

━━━━━━━━━━━━━━━━━━━━
🎯 下一步：方案设计

基于这份需求文档，可以启动 Solution Pro 生成完整的技术方案：
  • 整体设计方案
  • 技术路线规划  
  • 实施路径图
  • 风险与对策

预计耗时：15-30 分钟

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 启动方案设计（Solution Pro）  ← 推荐
  [2] 查看需求文档详情
  [3] 继续补充需求细节

请输入数字选择。
```

#### 中等质量（B 级）

```
━━━━━━━━━━━━━━━━━━━━
✅ 需求梳理完成

📊 质量评分：{quality_score} / 100（{quality_level}级）

💡 建议继续补充需求细节，提升评分后再进入方案设计，可获得更优的方案质量。

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 继续补充需求（推荐，可提升方案质量）
  [2] 启动方案设计（当前评分也可生成方案）
  [3] 查看需求文档详情

请输入数字选择。
```

#### 低质量（C 级）

```
━━━━━━━━━━━━━━━━━━━━
⚠️ 需求梳理完成，但质量评分较低

📊 质量评分：{quality_score} / 100（{quality_level}级）

强烈建议继续补充需求细节，提升评分后再进入方案设计。

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 继续补充需求  ← 强烈推荐
  [2] 查看当前需求文档
  [3] 仍然启动方案设计（建议先补充需求）

请输入数字选择。
```

### 2. Solution Pro → Ship Pro

**Solution Pro 的 4 个评分维度**：完整性、必要性、目标一致性、全局影响

```
━━━━━━━━━━━━━━━━━━━━
✅ 方案设计完成！

📊 质量评分：{harness_score} / 100

📦 方案包含：
   • {num_reqs} 个需求项
   • {num_modules} 个模块
   • 整体设计方案 + 实施路径图

━━━━━━━━━━━━━━━━━━━━
🎯 下一步：工程实现

基于这份技术方案，可以启动 Ship Pro 生成可直接交付给开发的工作包：
  • 开发所需的文件结构
  • 测试验证标准
  • 部署上线配置

预计耗时：10-20 分钟

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 启动工程实现（Ship Pro）  ← 推荐
  [2] 查看方案详情
  [3] 调整方案某些部分

请输入数字选择。
```

### 3. Ship Pro 完成

```
━━━━━━━━━━━━━━━━━━━━
✅ 工程实现完成！

📦 工作包已生成，可直接交付给开发团队或 AI 编码助手。

📊 质量评分：{harness_score} / 100

━━━━━━━━━━━━━━━━━━━━
🎯 下一步

工作包已就绪，你可以：
  [1] 查看工作包详情  ← 推荐
  [2] 导出为 GitHub Issues（需要 gh CLI）
  [3] 生成项目脚手架代码
  [4] 下载工作包文件

━━━━━━━━━━━━━━━━━━━━

🎉 整个 DeepFlow 管线已完成！从需求 → 方案 → 工程实现，全流程闭环。
```

---

## 数据结构定义

### transition_prompt Schema

```json
{
  "template": "spec_to_solution | solution_to_ship | ship_completed",
  "variables": {
    "quality_score": 85,
    "quality_level": "A",
    "dimension_summary": "清晰度 88 | 完整度 82 | 可执行度 90 | 一致性 85 | 可行性 80",
    "num_users": 3,
    "num_capabilities": 8,
    "num_constraints": 5,
    "harness_score": 92,
    "num_reqs": 12,
    "num_modules": 5
  }
}
```

### Pydantic 模型

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class TransitionPromptVariables(BaseModel):
    """过渡引导词变量"""
    quality_score: Optional[int] = None
    quality_level: Optional[Literal["S", "A", "B", "C"]] = None
    dimension_summary: Optional[str] = None
    num_users: Optional[int] = None
    num_capabilities: Optional[int] = None
    num_constraints: Optional[int] = None
    harness_score: Optional[int] = None
    num_reqs: Optional[int] = None
    num_modules: Optional[int] = None

class TransitionPrompt(BaseModel):
    """过渡引导词数据"""
    template: Literal["spec_to_solution", "solution_to_ship", "ship_completed"]
    variables: TransitionPromptVariables
```

---

## 实现代码

### 1. Spec Pro 引导词生成

**位置**：`domains/spec_pro/prompts/structure.md`（StructureWorker prompt）

在 `action = "done"` 的输出中添加 `transition_prompt` 字段：

```json
{
  "action": "done",
  "summary_text": "📋 需求收集摘要\n...",
  "quality": {
    "overall_score": 82,
    "level": "A"
  },
  "transition_prompt": {
    "template": "spec_to_solution",
    "variables": {
      "quality_score": 82,
      "quality_level": "A",
      "dimension_summary": "清晰度 88 | 完整度 82 | 可执行度 90",
      "num_users": 3,
      "num_capabilities": 8,
      "num_constraints": 5
    }
  },
  ...
}
```

### 2. Solution Pro 引导词生成

**位置**：`scripts/pipeline_watcher.py` → `write_auto_chain()`

```python
def write_auto_chain(config: Dict, base_path: Path, completion: Dict) -> Optional[str]:
    """Write .auto_chain_trigger with transition_prompt data."""
    ac = config.get("auto_chain", {})
    next_pl = ac.get("next_pipeline")
    if not next_pl:
        return None
    
    # 构建引导词变量
    prompt_variables = {}
    if config["pipeline_id"] == "solution_pro" and next_pl == "ship_pro":
        # 读取 harness 评分
        harness_data = _read_json(base_path / "stages" / "harness_final.json")
        if harness_data:
            prompt_variables["harness_score"] = harness_data.get("overall_score", 0)
            dimensions = harness_data.get("dimensions", [])
            prompt_variables["dimension_summary"] = " | ".join(
                [f"{d['name']} {d['score']}" for d in dimensions]
            )
        
        # 读取 final_result.json 统计
        final_data = _read_json(base_path / "stages" / "final_result.json")
        if final_data:
            prompt_variables["num_reqs"] = len(final_data.get("requirements", []))
            prompt_variables["num_modules"] = len(final_data.get("modules", []))
    
    # 写入触发文件（包含引导词数据）
    trigger = {
        "source_pipeline": config["pipeline_id"],
        "completed_at": completion.get("completed_at", ""),
        "base_path": str(base_path),
        "transition_prompt": {
            "template": "solution_to_ship",
            "variables": prompt_variables
        }
    }
    atomic_write(base_path / ac.get("trigger_file", ".auto_chain_trigger"), 
                 json.dumps(trigger, ensure_ascii=False))
    
    return next_pl
```

### 3. 主 Agent 渲染引导词

**位置**：主 Agent 读取 `transition_prompt` 后，根据 `template` 渲染对应模板

```python
def render_transition_prompt(prompt_data: Dict) -> str:
    """渲染过渡引导词"""
    template = prompt_data["template"]
    vars = prompt_data["variables"]
    
    if template == "spec_to_solution":
        level = vars.get("quality_level", "C")
        if level in ["S", "A"]:
            # 高质量模板
            return f"""
━━━━━━━━━━━━━━━━━━━━
✅ 需求梳理完成！

📊 质量评分：{vars['quality_score']} / 100（{level}级）
   {vars['dimension_summary']}

📄 需求文档已生成：
   • {vars['num_users']} 个用户角色
   • {vars['num_capabilities']} 项核心能力
   • {vars['num_constraints']} 项约束条件

━━━━━━━━━━━━━━━━━━━━
🎯 下一步：方案设计

基于这份需求文档，可以启动 Solution Pro 生成完整的技术方案：
  • 系统架构设计
  • 技术选型建议  
  • 实施路线图
  • 风险评估

预计耗时：15-30 分钟

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 启动方案设计（Solution Pro）  ← 推荐
  [2] 查看需求文档详情
  [3] 继续补充需求细节

请输入数字选择。
"""
        elif level == "B":
            # 中等质量模板
            ...
        else:
            # 低质量模板
            ...
    
    elif template == "solution_to_ship":
        # Solution Pro → Ship Pro 模板
        ...
    
    elif template == "ship_completed":
        # Ship Pro 完成模板
        ...
```

---

## 评审修订总结

| 问题 | 原方案 | 修订后 |
|------|--------|--------|
| watcher 内 print() | 直接 print 引导词 | 写入 `.auto_chain_trigger` 的 `transition_prompt` 字段，主 Agent 渲染 |
| "10秒自动启动" | 虚假承诺 | 删除，改为用户主动选择 |
| coordinator 职责越界 | 在 coordinator 添加 `_handle_done_action()` | 引导词数据由 StructureWorker 生成，写入 `round_result.json` |
| 阈值硬编码 75 | `quality_score >= 75` | 使用 `quality_level`（S/A/B/C）判断 |
| Ship Pro 终点指引不足 | 只有查看/下载/编码 | 增加导出 GitHub Issues、生成脚手架等选项 |
| 数据 vs 展示分离 | 混合 | 数据生成层（worker/watcher）vs 展示渲染层（主 Agent） |

---

## 待实现清单

- [ ] 修改 `domains/spec_pro/prompts/structure.md`：`action="done"` 时生成 `transition_prompt`
- [ ] 修改 `scripts/pipeline_watcher.py`：`write_auto_chain()` 生成 `transition_prompt` 数据
- [ ] 添加 Pydantic 模型：`TransitionPrompt` + `TransitionPromptVariables`
- [ ] 主 Agent 渲染逻辑：读取 `transition_prompt` → 根据 template 渲染
- [ ] 编写单元测试
- [ ] 端到端测试验证
