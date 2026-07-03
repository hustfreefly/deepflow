"""
LLM Gate Checks - AI Native 语义理解层

职责：用 LLM 判断 Agent 输出的语义合理性，而非仅检查格式。
调用时机：在 orchestrator 层（run_pipeline.py check_gate）中调用，不在 gate 函数内部。
原则：确定性优先（格式检查用代码），理解优于穷举（语义判断用 LLM）。

三层架构：
  Layer 1: 确定性检查（gates.py）— 快速过滤格式错误
  Layer 2: LLM 语义检查（本文件）— 深入理解意图
  Layer 3: 综合决策 — 合并结果

关键设计：
- Worker 零改动红线：不修改 Worker prompt，不修改输出格式
- 结构化输出：LLM 返回 JSON，可解析、可验证
- 向后兼容：无 principles 时跳过 LLM 检查
"""

import json
from typing import Optional
from pathlib import Path


def llm_check_architect_quality(blueprint: dict, principles: list) -> dict:
    """
    用 LLM 判断 Architect 输出是否合理。

    检查维度：
    1. 原则一致性：covered_by 模块的 tech stack 是否真的体现原则
    2. 需求覆盖：P0 需求是否都有组件承接
    3. 模块完整性：是否缺少关键组件（编排层、错误分析器）

    Args:
        blueprint: Architect 输出（modules, dependencies, requirements, principle_coverage 等）
        principles: 架构原则列表（从 Spec Pro 注入）

    Returns:
        {
          "decision": "PASS" | "FAIL",
          "issues": [
            {
              "type": "principle_violation" | "requirement_gap" | "missing_module" | "unreasonable_design",
              "severity": "BLOCKER" | "WARNING",
              "description": "...",
              "affected_modules": ["COMP-001"],
              "suggestion": "..."
            }
          ],
          "reasoning": "判断逻辑"
        }
    """
    # 如果没有原则，跳过 LLM 检查
    if not principles:
        return {
            "decision": "PASS",
            "issues": [],
            "reasoning": "无架构原则，跳过语义检查"
        }

    # 构建 prompt
    prompt = _build_architect_prompt(blueprint, principles)

    # 调用 LLM（这里需要注入 LLM 调用接口，暂时用占位符）
    llm_output = _call_llm(prompt)

    # 解析并验证 LLM 输出
    result = _parse_and_validate_gate_result(llm_output)

    return result


def llm_check_decomposer_quality(wp_structure: dict, blueprint: dict, principles: list) -> dict:
    """
    用 LLM 判断 Decomposer 输出是否合理。

    检查维度：
    1. 粒度合理性：每个 COMP 是否至少有 1 个 WP？职责 > 3 的 COMP 是否被拆分？
    2. 原则继承：WP 是否继承了 serving_principles？
    3. 需求覆盖：P0 需求是否被分配到具体的 WP？

    Args:
        wp_structure: Decomposer 输出（work_packages, dependency_edges）
        blueprint: Architect 输出（modules, requirements）
        principles: 架构原则列表

    Returns:
        结构化 gate 结果
    """
    if not principles:
        return {
            "decision": "PASS",
            "issues": [],
            "reasoning": "无架构原则，跳过语义检查"
        }

    prompt = _build_decomposer_prompt(wp_structure, blueprint, principles)
    llm_output = _call_llm(prompt)
    result = _parse_and_validate_gate_result(llm_output)

    return result


def llm_check_specifier_quality(specs: dict, principles: list) -> dict:
    """
    用 LLM 判断 Specifier 输出是否合理。

    检查维度：
    1. AC 可验证性：每条 AC 是否可以被自动化测试验证？
    2. 原则覆盖：每个 WP 是否至少有 1 条原则验证 AC？
    3. AC 完整性：AC 是否覆盖了 WP 的所有 responsibilities？

    Args:
        specs: Specifier 输出（work_packages）
        principles: 架构原则列表

    Returns:
        结构化 gate 结果
    """
    if not principles:
        return {
            "decision": "PASS",
            "issues": [],
            "reasoning": "无架构原则，跳过语义检查"
        }

    prompt = _build_specifier_prompt(specs, principles)
    llm_output = _call_llm(prompt)
    result = _parse_and_validate_gate_result(llm_output)

    return result


# ---------------------------------------------------------------------------
# Prompt Builders
# ---------------------------------------------------------------------------

def _build_architect_prompt(blueprint: dict, principles: list) -> str:
    """构建 Architect 语义检查 prompt"""
    return f"""你是 Architect 输出的质量评审员。

## 架构原则（必须遵守）

{json.dumps(principles, indent=2, ensure_ascii=False)}

## Architect 输出

```json
{json.dumps(blueprint, indent=2, ensure_ascii=False)}
```

## 你的任务

判断 Architect 的输出是否符合架构原则。重点检查：

### 判断标准（AI Native）

用你的理解判断，不是硬编码规则：

1. **原则一致性**：检查每个原则是否被合理实现。如果某个原则被违反，判断是严重违反（FAIL）还是可以接受的权衡（PASS_WITH_WARNING）。

2. **需求覆盖**：检查 P0 需求是否被映射到模块。如果有需求未被映射，判断这个需求是否重要。

3. **模块完整性**：检查是否缺少关键组件。用你的理解判断什么是"关键组件"。

4. **职责合理性**：检查每个模块的职责是否相关。用你的理解判断，不是机械地套用规则。

## 输出格式

```json
{{
  "decision": "PASS" | "FAIL",
  "issues": [
    {{
      "type": "principle_violation" | "requirement_gap" | "missing_module" | "unreasonable_design",
      "severity": "BLOCKER" | "WARNING",
      "description": "问题描述",
      "affected_modules": ["COMP-001"],
      "suggestion": "建议的修复方案"
    }}
  ],
  "reasoning": "你的判断逻辑（为什么 PASS/FAIL）"
}}
```

## 重要约束

- 只输出 JSON，不要输出其他文本
- 如果没有问题，decision 为 "PASS"，issues 为空数组
- 每个 issue 必须有 type、severity、description、affected_modules、suggestion
- reasoning 必须清晰说明判断逻辑
"""


def _build_decomposer_prompt(wp_structure: dict, blueprint: dict, principles: list) -> str:
    """构建 Decomposer 语义检查 prompt"""
    return f"""你是 Decomposer 输出的质量评审员。

## 架构原则

{json.dumps(principles, indent=2, ensure_ascii=False)}

## Architect 输出（上游）

```json
{json.dumps(blueprint, indent=2, ensure_ascii=False)}
```

## Decomposer 输出

```json
{json.dumps(wp_structure, indent=2, ensure_ascii=False)}
```

## 你的任务

判断 Decomposer 的输出是否合理。

### 判断标准（AI Native）

用你的理解判断，不是硬编码规则：

1. **粒度合理性**：判断 WP 的粒度是否合适。用你的理解判断什么时候应该拆分，什么时候应该合并。

2. **原则继承**：检查架构原则是否被正确传递到 WP 层。

3. **需求覆盖**：检查 P0 需求是否被分配到具体的 WP。

## 输出格式

```json
{{
  "decision": "PASS" | "FAIL",
  "issues": [
    {{
      "type": "granularity_issue" | "principle_not_inherited" | "requirement_not_assigned",
      "severity": "BLOCKER" | "WARNING",
      "description": "问题描述",
      "affected_wps": ["WP-001"],
      "suggestion": "建议的修复方案"
    }}
  ],
  "reasoning": "判断逻辑"
}}
```
"""


def _build_specifier_prompt(specs: dict, principles: list) -> str:
    """构建 Specifier 语义检查 prompt"""
    return f"""你是 Specifier 输出的质量评审员。

## 架构原则

{json.dumps(principles, indent=2, ensure_ascii=False)}

## Specifier 输出

```json
{json.dumps(specs, indent=2, ensure_ascii=False)}
```

## 你的任务

判断 Specifier 的输出是否合理。

### 判断标准（AI Native）

用你的理解判断，不是硬编码规则：

1. **AC 可验证性**：判断每条 AC 是否可以被自动化测试验证。用你的理解判断什么是"可验证的 AC"。

2. **原则覆盖**：检查架构原则是否在 AC 中有体现。

3. **AC 完整性**：判断 AC 是否足够覆盖 WP 的所有职责。

## 输出格式

```json
{{
  "decision": "PASS" | "FAIL",
  "issues": [
    {{
      "type": "ac_not_verifiable" | "principle_not_covered" | "ac_incomplete",
      "severity": "BLOCKER" | "WARNING",
      "description": "问题描述",
      "affected_wps": ["WP-001"],
      "suggestion": "建议的修复方案"
    }}
  ],
  "reasoning": "判断逻辑"
}}
```
"""


# ---------------------------------------------------------------------------
# LLM Caller (占位符，需要注入真实 LLM 调用)
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> str:
    """
    调用 LLM 并返回输出。

    使用注入的 LLM caller，如果未注入则使用默认 caller。
    """
    from domains.ship_pro.eval.llm_caller import get_default_caller
    
    caller = get_default_caller()
    return caller.call(prompt)


# ---------------------------------------------------------------------------
# Result Parser & Validator
# ---------------------------------------------------------------------------

def _parse_and_validate_gate_result(llm_output: str) -> dict:
    """
    解析并验证 LLM 输出的 gate 结果。

    验证规则：
    - 必须是合法 JSON
    - 必须有 decision 字段（PASS/FAIL）
    - 必须有 issues 字段（数组）
    - 每个 issue 必须有 type、severity、description、affected_modules/wps、suggestion
    """
    try:
        result = json.loads(llm_output)
    except json.JSONDecodeError as e:
        return {
            "decision": "FAIL",
            "issues": [{
                "type": "llm_output_invalid",
                "severity": "BLOCKER",
                "description": f"LLM 输出不是合法 JSON: {str(e)}",
                "affected_modules": [],
                "suggestion": "检查 LLM 输出格式"
            }],
            "reasoning": "LLM 输出解析失败"
        }

    # 验证必要字段
    if "decision" not in result or result["decision"] not in ("PASS", "FAIL"):
        result["decision"] = "FAIL"
        result.setdefault("issues", []).append({
            "type": "llm_output_invalid",
            "severity": "BLOCKER",
            "description": "LLM 输出缺少 decision 字段或值无效",
            "affected_modules": [],
            "suggestion": "检查 LLM 输出格式"
        })

    if "issues" not in result or not isinstance(result["issues"], list):
        result["issues"] = []

    if "reasoning" not in result:
        result["reasoning"] = "无 reasoning"

    return result


# ---------------------------------------------------------------------------
# Result Merger
# ---------------------------------------------------------------------------

def merge_gate_results(deterministic: dict, semantic: dict) -> dict:
    """
    合并确定性检查和 LLM 语义检查的结果。

    决策逻辑：
    - 如果任一为 FAIL → FAIL
    - 如果任一为 CONDITIONAL → CONDITIONAL
    - 否则 → PASS

    Args:
        deterministic: 确定性检查结果（来自 gates.py）
        semantic: LLM 语义检查结果（来自本文件）

    Returns:
        合并后的 gate 结果
    """
    # 提取决策
    det_decision = deterministic.get("decision", "PASS")
    sem_decision = semantic.get("decision", "PASS")

    # 合并决策
    if det_decision == "FAIL" or sem_decision == "FAIL":
        final_decision = "FAIL"
    elif det_decision == "CONDITIONAL" or sem_decision == "CONDITIONAL":
        final_decision = "CONDITIONAL"
    else:
        final_decision = "PASS"

    # 合并 issues
    all_issues = []

    # 确定性检查的 issues（从 critical_results 提取）
    for key, passed in deterministic.get("critical_results", {}).items():
        if not passed:
            all_issues.append({
                "type": "deterministic_check",
                "severity": "BLOCKER",
                "description": f"确定性检查失败: {key}",
                "affected_modules": [],
                "suggestion": deterministic.get("feedback", "")
            })

    # LLM 语义检查的 issues
    all_issues.extend(semantic.get("issues", []))

    # 合并 feedback
    feedback_parts = []
    if deterministic.get("feedback"):
        feedback_parts.append(f"[确定性] {deterministic['feedback']}")
    if semantic.get("reasoning"):
        feedback_parts.append(f"[语义] {semantic['reasoning']}")

    return {
        "passed": final_decision == "PASS",
        "decision": final_decision,
        "critical_results": deterministic.get("critical_results", {}),
        "major_results": deterministic.get("major_results", {}),
        "minor_results": deterministic.get("minor_results", {}),
        "llm_issues": semantic.get("issues", []),
        "feedback": " | ".join(feedback_parts) if feedback_parts else "无反馈",
    }
