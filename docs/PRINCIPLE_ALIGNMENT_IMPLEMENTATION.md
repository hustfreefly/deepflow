# DeepFlow 原则对齐修复 - 实施规范

> **目标**: 修复 6 个系统级缺陷，确保架构约束从 Spec Pro 到实现全程可见、可验证  
> **方法**: 契约笼子（Pydantic schema → gate 验证 → prompt 对齐）  
> **工作量**: ~590 行代码改动  
> **验证**: 用 OpenClaw AI Native Loop 案例做回归测试  

---

## Phase 1: 契约层（Pydantic Models）

### 1.1 新建 `domains/ship_pro/contracts/principles.py`

```python
"""
架构原则与平台约束契约 — 唯一真相源

新增模型:
- ArchitecturePrinciple: 架构原则（风格约束）
- PlatformCapability: 平台能力（复用约束）
- PrincipleCoverage: 原则-组件映射
- PlatformReuseEntry: 平台能力-组件映射
- PrincipleAuditEntry: 原则审计结果
- PlatformAuditEntry: 平台审计结果
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ArchitecturePrinciple(BaseModel):
    """
    架构原则（风格约束）。
    
    例: "全LLM控制，Python不做控制流"
    """
    
    id: str = Field(description="原则ID，如 PRINCIPLE-001")
    name: str = Field(min_length=1, description="原则名称")
    type: Literal["must_do", "must_not_do", "must_have", "invariant"]
    description: str = Field(min_length=1)
    anti_patterns: list[str] = Field(
        default_factory=list,
        description="具体的反面模式描述，帮助 LLM 理解什么不该做"
    )
    verification_method: str = Field(
        default="",
        description="如何验证此原则被遵守"
    )
    severity: Literal["BLOCKER", "WARNING"] = "BLOCKER"


class PlatformCapability(BaseModel):
    """
    平台能力（复用约束）。
    
    例: "OpenClaw sessions_spawn 用于子Agent调度，禁止自建 Worker Pool"
    """
    
    platform: str = Field(description="平台名称，如 OpenClaw")
    capability: str = Field(min_length=1, description="能力名称")
    api: str = Field(description="API 调用方式")
    replaces: list[str] = Field(
        default_factory=list,
        description="该能力替代的自建组件列表"
    )
    must_use: bool = Field(
        default=True,
        description="是否必须使用（true=禁止重建）"
    )
    rationale: str = Field(
        default="",
        description="为什么必须用平台能力而非自建"
    )


class PrincipleCoverage(BaseModel):
    """
    原则-组件映射（Architect 输出）。
    
    说明哪些组件负责实现/遵守某条原则。
    """
    
    principle_id: str
    covered_by_modules: list[str] = Field(
        description="负责实现此原则的模块ID列表"
    )
    coverage_method: str = Field(
        description="如何覆盖此原则（例: COMP-001 通过 LLM API 调用实现路由决策）"
    )
    gap_analysis: str = Field(
        default="",
        description="覆盖缺口分析（如果为空表示完全覆盖）"
    )


class PlatformReuseEntry(BaseModel):
    """
    平台能力-组件映射（Architect 输出）。
    
    说明哪些组件复用了哪些平台能力。
    """
    
    platform_capability: str
    reused_by_modules: list[str] = Field(
        description="复用此平台能力的模块ID列表"
    )
    not_reused_rationale: str = Field(
        default="",
        description="如果未复用，说明原因（仅当 must_use=false 时填写）"
    )


class PrincipleAuditEntry(BaseModel):
    """
    原则审计结果（Reviewer 输出）。
    
    检查每条原则是否在 WP 中有可验证的对应。
    """
    
    principle_id: str
    principle_name: str
    wp_coverage: dict[str, str] = Field(
        description="WP覆盖情况，key=WP ID, value=覆盖状态描述"
    )
    overall_status: Literal["PASS", "FAIL", "PARTIAL"]
    action_required: str = Field(
        default="",
        description="需要采取的行动（如果 overall_status != PASS）"
    )


class PlatformAuditEntry(BaseModel):
    """
    平台审计结果（Reviewer 输出）。
    
    检查每个必须复用的平台能力是否在 WP 中被使用。
    """
    
    platform_capability: str
    api: str
    wp_status: dict[str, str] = Field(
        description="WP使用状态，key=WP ID, value=使用状态描述"
    )
    overall_status: Literal["PASS", "FAIL", "PARTIAL"]
    violation_description: str = Field(
        default="",
        description="违反描述（如果 overall_status = FAIL）"
    )


__all__ = [
    "ArchitecturePrinciple",
    "PlatformCapability",
    "PrincipleCoverage",
    "PlatformReuseEntry",
    "PrincipleAuditEntry",
    "PlatformAuditEntry",
]
```

### 1.2 更新 `ArchitectOutput`

在 `domains/ship_pro/contracts/architect.py` 的 `ArchitectOutput` 类中添加：

```python
from .principles import (
    ArchitecturePrinciple,
    PlatformCapability,
    PrincipleCoverage,
    PlatformReuseEntry,
)


class ArchitectOutput(BaseModel):
    # ... 现有字段 ...
    
    # 新增字段（Phase 1）
    architecture_principles: list[ArchitecturePrinciple] = Field(
        default_factory=list,
        description="架构原则列表（从 Spec Pro final_result 继承）。Gate Major 必检字段。"
    )
    platform_capabilities: list[PlatformCapability] = Field(
        default_factory=list,
        description="平台能力列表（从 Spec Pro final_result 继承）。Gate Major 必检字段。"
    )
    principle_coverage: list[PrincipleCoverage] = Field(
        default_factory=list,
        description="原则-组件映射。Gate Critical 必检字段（如果 architecture_principles 非空）。"
    )
    platform_reuse_map: list[PlatformReuseEntry] = Field(
        default_factory=list,
        description="平台能力-组件映射。Gate Critical 必检字段（如果 platform_capabilities 非空）。"
    )
```

### 1.3 更新 `ReviewerOutput`

在 `domains/ship_pro/contracts/reviewer.py` 的 `ReviewerOutput` 类中添加：

```python
from .principles import PrincipleAuditEntry, PlatformAuditEntry


class ReviewerOutput(BaseModel):
    # ... 现有字段 ...
    
    # 新增字段（Phase 1）
    principle_audit: list[PrincipleAuditEntry] = Field(
        default_factory=list,
        description="原则审计结果。Gate Major 必检字段（如果输入包含 architecture_principles）。"
    )
    platform_audit: list[PlatformAuditEntry] = Field(
        default_factory=list,
        description="平台审计结果。Gate Major 必检字段（如果输入包含 platform_capabilities）。"
    )
```

---

## Phase 2: Gate 函数

### 2.1 新增 `gate_principle_alignment()`

在 `domains/ship_pro/eval/gates.py` 中添加：

```python
def gate_principle_alignment(architect_output: dict) -> dict:
    """
    Quality gate for principle alignment.
    
    检查:
    - Critical: 每条 BLOCKER 级原则都有 principle_coverage 映射
    - Critical: 每条 must_use=true 的平台能力都有 platform_reuse_map 映射
    - Major: principle_coverage 的 gap_analysis 为空（无遗漏）
    
    Args:
        architect_output: Architect 输出字典
    
    Returns:
        Gate result dict
    """
    critical = {}
    major = {}
    
    principles = architect_output.get("architecture_principles", [])
    coverage = architect_output.get("principle_coverage", [])
    capabilities = architect_output.get("platform_capabilities", [])
    reuse_map = architect_output.get("platform_reuse_map", [])
    
    # Critical 1: 每条 BLOCKER 原则都有覆盖映射
    blocker_principles = [p for p in principles if p.get("severity") == "BLOCKER"]
    covered_principle_ids = {c.get("principle_id") for c in coverage}
    
    critical["all_blockers_covered"] = all(
        p.get("id") in covered_principle_ids for p in blocker_principles
    )
    
    # Critical 2: 每条 must_use 平台能力都有复用映射
    must_use_capabilities = [c for c in capabilities if c.get("must_use", True)]
    reused_capability_names = {r.get("platform_capability") for r in reuse_map}
    
    critical["all_must_use_reused"] = all(
        c.get("capability") in reused_capability_names for c in must_use_capabilities
    )
    
    # Major 1: 覆盖缺口分析为空
    major["no_coverage_gaps"] = all(
        not c.get("gap_analysis", "").strip() for c in coverage
    )
    
    # 决策逻辑
    critical_passed = all(critical.values())
    major_passed = all(major.values())
    
    decision = "PASS"
    if not critical_passed:
        decision = "FAIL"
    elif not major_passed:
        decision = "CONDITIONAL"
    
    feedback = []
    if not critical["all_blockers_covered"]:
        missing = [p["id"] for p in blocker_principles if p["id"] not in covered_principle_ids]
        feedback.append(f"Critical: 以下 BLOCKER 原则缺少覆盖映射: {missing}")
    
    if not critical["all_must_use_reused"]:
        missing = [c["capability"] for c in must_use_capabilities if c["capability"] not in reused_capability_names]
        feedback.append(f"Critical: 以下必须复用的平台能力缺少复用映射: {missing}")
    
    if not major["no_coverage_gaps"]:
        gaps = [c["principle_id"] for c in coverage if c.get("gap_analysis", "").strip()]
        feedback.append(f"Major: 以下原则存在覆盖缺口: {gaps}")
    
    return {
        "passed": decision == "PASS",
        "decision": decision,
        "critical_results": critical,
        "major_results": major,
        "feedback": feedback,
    }
```

### 2.2 新增 `gate_platform_coverage()`

```python
def gate_platform_coverage(specifier_output: dict, architect_output: dict) -> dict:
    """
    Quality gate for platform capability coverage in WPs.
    
    检查:
    - Critical: 每个 must_use=true 的平台能力至少在 1 个 WP 的 acceptance_criteria 中有对应
    - Major: 每个 implementation_source=openclaw_native 的 COMP 对应的 WP 不包含自建代码 AC
    
    Args:
        specifier_output: Specifier 输出字典（包含 WPs）
        architect_output: Architect 输出字典（包含 platform_reuse_map）
    
    Returns:
        Gate result dict
    """
    critical = {}
    major = {}
    
    capabilities = architect_output.get("platform_capabilities", [])
    reuse_map = architect_output.get("platform_reuse_map", [])
    wps = specifier_output.get("work_packages", [])
    
    # Critical 1: 每个 must_use 能力在 AC 中有对应
    must_use_capabilities = [c for c in capabilities if c.get("must_use", True)]
    
    # 提取所有 AC 文本
    all_ac_text = " ".join([
        " ".join(wp.get("acceptance_criteria", [])) for wp in wps
    ])
    
    critical["must_use_in_ac"] = all(
        c.get("api", "").lower() in all_ac_text.lower() or 
        c.get("capability", "").lower() in all_ac_text.lower()
        for c in must_use_capabilities
    )
    
    # Major 1: openclaw_native COMP 对应的 WP 无自建代码 AC
    # （这个检查较复杂，暂时简化为检查 AC 中是否提到"自建"关键词）
    major["no_self_built_for_native"] = "自建" not in all_ac_text and "重新实现" not in all_ac_text
    
    # 决策逻辑
    critical_passed = all(critical.values())
    major_passed = all(major.values())
    
    decision = "PASS"
    if not critical_passed:
        decision = "FAIL"
    elif not major_passed:
        decision = "CONDITIONAL"
    
    feedback = []
    if not critical["must_use_in_ac"]:
        feedback.append("Critical: 部分必须复用的平台能力在 WP 的 acceptance_criteria 中未体现")
    
    if not major["no_self_built_for_native"]:
        feedback.append("Major: 检测到'自建'或'重新实现'关键词，可能违反平台复用原则")
    
    return {
        "passed": decision == "PASS",
        "decision": decision,
        "critical_results": critical,
        "major_results": major,
        "feedback": feedback,
    }
```

### 2.3 更新 `gate_architect()`

在现有 `gate_architect()` 函数中添加对新字段的检查：

```python
def gate_architect(blueprint: dict) -> dict:
    # ... 现有检查 ...
    
    # 新增 Major 检查（Phase 2）
    major["architecture_principles_present"] = (
        isinstance(blueprint.get("architecture_principles"), list) and 
        len(blueprint.get("architecture_principles", [])) > 0
    )
    
    major["platform_capabilities_present"] = (
        isinstance(blueprint.get("platform_capabilities"), list) and 
        len(blueprint.get("platform_capabilities", [])) > 0
    )
    
    # 新增 Critical 检查（如果原则/平台非空）
    if blueprint.get("architecture_principles"):
        critical["principle_coverage_present"] = (
            isinstance(blueprint.get("principle_coverage"), list) and 
            len(blueprint.get("principle_coverage", [])) > 0
        )
    
    if blueprint.get("platform_capabilities"):
        critical["platform_reuse_map_present"] = (
            isinstance(blueprint.get("platform_reuse_map"), list) and 
            len(blueprint.get("platform_reuse_map", [])) > 0
        )
    
    # ... 更新决策逻辑 ...
```

### 2.4 更新 `gate_reviewer()`

在现有 `gate_reviewer()` 函数中添加对新字段的检查：

```python
def gate_reviewer(review_output: dict) -> dict:
    # ... 现有检查 ...
    
    # 新增 Major 检查（Phase 2）
    major["principle_audit_present"] = isinstance(review_output.get("principle_audit"), list)
    major["platform_audit_present"] = isinstance(review_output.get("platform_audit"), list)
    
    # 新增 Critical 检查（如果有原则审计且存在 FAIL）
    principle_audit = review_output.get("principle_audit", [])
    if principle_audit:
        critical["no_principle_failures"] = all(
            entry.get("overall_status") != "FAIL" for entry in principle_audit
        )
    
    platform_audit = review_output.get("platform_audit", [])
    if platform_audit:
        critical["no_platform_failures"] = all(
            entry.get("overall_status") != "FAIL" for entry in platform_audit
        )
    
    # ... 更新决策逻辑 ...
```

---

## Phase 3: Prompt 更新

### 3.1 更新 Architect Prompt

在 `domains/ship_pro/prompts/architect.md` 的"输入格式"章节后添加：

```markdown
## 架构原则与平台约束（从 Spec Pro 继承）

如果输入中包含 `architecture_principles` 和 `platform_capabilities`，你必须在输出中包含对应的映射。

### 输出要求

在你的 JSON 输出中，必须包含以下字段：

```json
{
  "architecture_principles": [
    {
      "id": "PRINCIPLE-001",
      "name": "全 LLM 控制",
      "type": "must_do",
      "description": "所有决策模块必须由 LLM 驱动，Python 仅做执行器",
      "anti_patterns": ["硬编码 if/else 决策逻辑", "固定映射表替代 LLM 路由"],
      "verification_method": "代码中不得出现非 LLM 的决策逻辑",
      "severity": "BLOCKER"
    }
  ],
  "platform_capabilities": [
    {
      "platform": "OpenClaw",
      "capability": "子 Agent 调度",
      "api": "sessions_spawn(runtime='subagent', mode='run')",
      "replaces": ["自建 Worker Pool", "自建优先级队列"],
      "must_use": true,
      "rationale": "OpenClaw 已有完整的子Agent管理能力"
    }
  ],
  "principle_coverage": [
    {
      "principle_id": "PRINCIPLE-001",
      "covered_by_modules": ["COMP-001", "COMP-005"],
      "coverage_method": "COMP-001 通过 LLM API 调用实现路由决策，COMP-005 通过 LLM 实现目标分解",
      "gap_analysis": ""
    }
  ],
  "platform_reuse_map": [
    {
      "platform_capability": "子 Agent 调度",
      "reused_by_modules": ["COMP-001"],
      "not_reused_rationale": ""
    }
  ]
}
```

### 验证规则

- 每条 `severity=BLOCKER` 的原则必须在 `principle_coverage` 中有对应条目
- 每条 `must_use=true` 的平台能力必须在 `platform_reuse_map` 中有对应条目
- 如果 `gap_analysis` 非空，说明存在覆盖缺口，需要在 `implementation_hints` 中说明如何填补
```

### 3.2 更新 Decomposer Prompt

在 `domains/ship_pro/prompts/decomposer.md` 的"输出格式"章节添加：

```markdown
## 原则继承（从 Architect 继承）

每个 WP 必须包含 `serving_principles` 字段，说明该 WP 服务于哪些架构原则。

```json
{
  "id": "WP-001",
  "title": "...",
  "serving_principles": [
    {
      "principle_id": "PRINCIPLE-001",
      "obligation": "必须通过 LLM API 实现路由决策，不得使用硬编码映射",
      "anti_patterns_to_avoid": ["DEFAULT_ROUTES = {...}", "if 'simple' in ..."]
    }
  ]
}
```
```

### 3.3 更新 Specifier Prompt

在 `domains/ship_pro/prompts/specifier.md` 的"acceptance_criteria 格式"章节添加：

```markdown
## 原则验证 AC

如果 WP 包含 `serving_principles`，必须为每条原则生成至少 1 条原则验证 AC。

**格式**:
```
Given 原则 <principle_id>, When 审查 WP-XXX 的实现代码, Then <验证条件>
```

**示例**:
```
Given 原则 PRINCIPLE-001（全LLM控制）, When 审查 WP-001 的实现代码, Then 不存在硬编码的路由映射表（如 DEFAULT_ROUTES），所有路由决策通过 LLM API 调用完成
```
```

### 3.4 更新 Reviewer Prompt

在 `domains/ship_pro/prompts/reviewer.md` 的"输出格式"章节添加：

```markdown
## 原则与平台审计（新增）

你的输出必须包含 `principle_audit` 和 `platform_audit` 字段。

### principle_audit 格式

```json
{
  "principle_audit": [
    {
      "principle_id": "PRINCIPLE-001",
      "principle_name": "全 LLM 控制",
      "wp_coverage": {
        "WP-001": "❌ AC 只验证了路由正确性，未验证是否通过 LLM 实现",
        "WP-008": "✅ AC 明确要求通过 LLM 实现目标分解"
      },
      "overall_status": "FAIL",
      "action_required": "为 WP-001 增加原则验证 AC"
    }
  ]
}
```

### platform_audit 格式

```json
{
  "platform_audit": [
    {
      "platform_capability": "子 Agent 调度",
      "api": "sessions_spawn",
      "wp_status": {
        "WP-001": "⚠️ 提到 sessions_spawn 但未在 AC 中验证调用"
      },
      "overall_status": "PARTIAL",
      "violation_description": ""
    }
  ]
}
```

### 验证规则

- 每条 `severity=BLOCKER` 的原则必须在 `principle_audit` 中有对应条目
- 每条 `must_use=true` 的平台能力必须在 `platform_audit` 中有对应条目
- 如果 `overall_status=FAIL`，必须在 `issues` 中添加对应问题
```

---

## Phase 4: 验证

### 4.1 回归测试脚本

创建 `domains/ship_pro/eval/test_principle_alignment.py`:

```python
"""
原则对齐回归测试 — 使用 OpenClaw AI Native Loop 案例

测试目标:
1. Spec Pro final_result 包含 architecture_principles 和 platform_capabilities
2. Ship Pro Architect 输出包含 principle_coverage 和 platform_reuse_map
3. gate_principle_alignment 能检测出原则未覆盖
4. gate_platform_coverage 能检测出平台能力未复用
5. Reviewer 输出包含 principle_audit 和 platform_audit
"""

import json
from pathlib import Path

from domains.ship_pro.contracts.architect import ArchitectOutput
from domains.ship_pro.contracts.reviewer import ReviewerOutput
from domains.ship_pro.contracts.principles import (
    ArchitecturePrinciple,
    PlatformCapability,
    PrincipleCoverage,
    PlatformReuseEntry,
    PrincipleAuditEntry,
    PlatformAuditEntry,
)
from domains.ship_pro.eval.gates import (
    gate_architect,
    gate_reviewer,
    gate_principle_alignment,
    gate_platform_coverage,
)


def test_architect_contract_with_principles():
    """测试 Architect 契约包含原则字段"""
    
    architect_data = {
        "_meta": {
            "agent": "architect",
            "input_format": "A",
            "overall_confidence": "high",
            "data_sufficiency": {
                "modules": "sufficient",
                "dependencies": "sufficient",
                "requirements": "sufficient",
                "risks": "sufficient",
            },
        },
        "project_type": "multi_agent",
        "project": {
            "name": "Test Project",
            "objective": "Test objective",
            "problem_statement": "Test problem",
        },
        "modules": [
            {
                "id": "COMP-001",
                "name": "Test Module",
                "summary": "Test summary",
                "responsibilities": ["resp1"],
                "technology_stack": ["tech1"],
                "is_infrastructure": True,
            }
        ],
        "dependencies": [],
        "requirements": [
            {
                "req_id": "REQ-001",
                "description": "Test requirement",
                "priority": "P0",
                "coverage": "covered",
                "mapped_components": ["COMP-001"],
            }
        ],
        # 新增字段
        "architecture_principles": [
            {
                "id": "PRINCIPLE-001",
                "name": "全 LLM 控制",
                "type": "must_do",
                "description": "所有决策模块必须由 LLM 驱动",
                "anti_patterns": ["硬编码 if/else"],
                "verification_method": "代码审查",
                "severity": "BLOCKER",
            }
        ],
        "platform_capabilities": [
            {
                "platform": "OpenClaw",
                "capability": "子 Agent 调度",
                "api": "sessions_spawn",
                "replaces": ["自建 Worker Pool"],
                "must_use": True,
                "rationale": "OpenClaw 已有能力",
            }
        ],
        "principle_coverage": [
            {
                "principle_id": "PRINCIPLE-001",
                "covered_by_modules": ["COMP-001"],
                "coverage_method": "通过 LLM API 实现",
                "gap_analysis": "",
            }
        ],
        "platform_reuse_map": [
            {
                "platform_capability": "子 Agent 调度",
                "reused_by_modules": ["COMP-001"],
                "not_reused_rationale": "",
            }
        ],
    }
    
    # 测试 Pydantic 验证
    validated = ArchitectOutput(**architect_data)
    assert len(validated.architecture_principles) == 1
    assert validated.architecture_principles[0].id == "PRINCIPLE-001"
    assert len(validated.platform_capabilities) == 1
    assert len(validated.principle_coverage) == 1
    assert len(validated.platform_reuse_map) == 1


def test_gate_principle_alignment_pass():
    """测试 gate_principle_alignment 通过场景"""
    
    architect_output = {
        "architecture_principles": [
            {
                "id": "PRINCIPLE-001",
                "name": "Test Principle",
                "type": "must_do",
                "description": "Test",
                "anti_patterns": [],
                "verification_method": "Test",
                "severity": "BLOCKER",
            }
        ],
        "platform_capabilities": [
            {
                "platform": "OpenClaw",
                "capability": "Test Capability",
                "api": "test_api",
                "replaces": [],
                "must_use": True,
                "rationale": "Test",
            }
        ],
        "principle_coverage": [
            {
                "principle_id": "PRINCIPLE-001",
                "covered_by_modules": ["COMP-001"],
                "coverage_method": "Test",
                "gap_analysis": "",
            }
        ],
        "platform_reuse_map": [
            {
                "platform_capability": "Test Capability",
                "reused_by_modules": ["COMP-001"],
                "not_reused_rationale": "",
            }
        ],
    }
    
    result = gate_principle_alignment(architect_output)
    assert result["passed"] is True
    assert result["decision"] == "PASS"


def test_gate_principle_alignment_fail():
    """测试 gate_principle_alignment 失败场景（原则未覆盖）"""
    
    architect_output = {
        "architecture_principles": [
            {
                "id": "PRINCIPLE-001",
                "name": "Test Principle",
                "type": "must_do",
                "description": "Test",
                "anti_patterns": [],
                "verification_method": "Test",
                "severity": "BLOCKER",
            }
        ],
        "platform_capabilities": [],
        "principle_coverage": [],  # 缺失！
        "platform_reuse_map": [],
    }
    
    result = gate_principle_alignment(architect_output)
    assert result["passed"] is False
    assert result["decision"] == "FAIL"
    assert not result["critical_results"]["all_blockers_covered"]


def test_gate_platform_coverage_fail():
    """测试 gate_platform_coverage 失败场景（平台能力未在 AC 中体现）"""
    
    specifier_output = {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "Test WP",
                "acceptance_criteria": [
                    "Given X, When Y, Then Z"  # 未提到 OpenClaw API
                ],
            }
        ]
    }
    
    architect_output = {
        "platform_capabilities": [
            {
                "platform": "OpenClaw",
                "capability": "子 Agent 调度",
                "api": "sessions_spawn",
                "replaces": [],
                "must_use": True,
                "rationale": "Test",
            }
        ],
        "platform_reuse_map": [],
    }
    
    result = gate_platform_coverage(specifier_output, architect_output)
    assert result["passed"] is False
    assert result["decision"] == "FAIL"
    assert not result["critical_results"]["must_use_in_ac"]


def test_reviewer_contract_with_audit():
    """测试 Reviewer 契约包含审计字段"""
    
    reviewer_data = {
        "verdict": "PASS_WITH_CONDITIONS",
        "issues": [],
        "quality_metrics": {
            "ac_verifiability_score": 85.0,
            "coverage_rate": 0.9,
            "dependency_sanity": "ok",
        },
        "summary": "Test summary",
        "round": 1,
        # 新增字段
        "principle_audit": [
            {
                "principle_id": "PRINCIPLE-001",
                "principle_name": "Test Principle",
                "wp_coverage": {"WP-001": "✅ PASS"},
                "overall_status": "PASS",
                "action_required": "",
            }
        ],
        "platform_audit": [
            {
                "platform_capability": "Test Capability",
                "api": "test_api",
                "wp_status": {"WP-001": "✅ PASS"},
                "overall_status": "PASS",
                "violation_description": "",
            }
        ],
    }
    
    # 测试 Pydantic 验证
    validated = ReviewerOutput(**reviewer_data)
    assert len(validated.principle_audit) == 1
    assert validated.principle_audit[0].overall_status == "PASS"
    assert len(validated.platform_audit) == 1


if __name__ == "__main__":
    test_architect_contract_with_principles()
    print("✅ test_architect_contract_with_principles passed")
    
    test_gate_principle_alignment_pass()
    print("✅ test_gate_principle_alignment_pass passed")
    
    test_gate_principle_alignment_fail()
    print("✅ test_gate_principle_alignment_fail passed")
    
    test_gate_platform_coverage_fail()
    print("✅ test_gate_platform_coverage_fail passed")
    
    test_reviewer_contract_with_audit()
    print("✅ test_reviewer_contract_with_audit passed")
    
    print("\n🎉 All tests passed!")
```

### 4.2 运行验证

```bash
cd /Users/allen/.openclaw/workspace/.deepflow
python -m pytest domains/ship_pro/eval/test_principle_alignment.py -v
```

---

## 执行计划

| 阶段 | 任务 | 工作量 | 验证 |
|------|------|--------|------|
| **Phase 1** | 创建 `principles.py`，更新 `architect.py` 和 `reviewer.py` | ~150 行 | Pydantic 验证通过 |
| **Phase 2** | 添加 gate 函数，更新现有 gate | ~200 行 | gate 测试通过 |
| **Phase 3** | 更新 4 个 prompt 模板 | ~100 行 | prompt 格式正确 |
| **Phase 4** | 创建并运行回归测试 | ~140 行 | 所有测试通过 |

**总计**: ~590 行代码，预计 2-3 小时完成。

---

## 成功标准

1. ✅ `ArchitectOutput` Pydantic 验证通过（包含新字段）
2. ✅ `ReviewerOutput` Pydantic 验证通过（包含新字段）
3. ✅ `gate_principle_alignment()` 能检测出原则未覆盖（FAIL 场景）
4. ✅ `gate_platform_coverage()` 能检测出平台能力未复用（FAIL 场景）
5. ✅ 回归测试全部通过（5/5）
6. ✅ 用 OpenClaw AI Native Loop 案例验证：如果重跑 Ship Pro，gate 会拒绝通过（因为原 Architect 输出缺少 `principle_coverage`）

---

*契约笼子方法：Pydantic schema → gate 验证 → prompt 对齐 → 回归测试。*
*不是修个案，是升级管线结构。*
