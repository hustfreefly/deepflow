# Solution Pro Schema Contract

> **Version**: 4.3.0 | **Last Updated**: 2026-06-02  
> **Single Source of Truth**: All JSON schema definitions for Solution Pro

This document defines the complete JSON schema for Solution Pro stage outputs, harness checks, and control contracts. **All other documents must reference this file, not duplicate schema definitions.**

---

## Table of Contents

1. [Stage Output Schema](#stage-output-schema)
2. [Harness Check Schema](#harness-check-schema)
3. [Exempt Stages](#exempt-stages)
4. [REQ-ID Format](#req-id-format)
5. [Control Contract Schema](#control-contract-schema)
6. [Validation Rules](#validation-rules)

---

## Stage Output Schema

### Three-Layer Architecture

```
┌─────────────────────────────────────┐
│  Core Layer (Required)              │  All stages must have these fields
├─────────────────────────────────────┤
│  Standard Layer (Optional)          │  Non-exempt stages must have harness_check
├─────────────────────────────────────┤
│  Metadata Layer (Optional)          │  Additional tracking info
└─────────────────────────────────────┘
```

### Core Layer (Required for ALL stages)

Every stage output **must** include these fields:

```json
{
  "status": "completed",
  "stage": "<stage_name>",
  "covered_req_ids": ["REQ-001", "REQ-002"]
}
```

**Field Definitions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | ✅ | Stage completion status: `"completed"`, `"failed"`, or `"skipped"` |
| `stage` | string | ✅ | Stage name (e.g., `"planning"`, `"consolidator"`, `"reviewer_technical"`) |
| `covered_req_ids` | array | ✅ | List of REQ-IDs covered by this stage (format: `REQ-\d+`) |

### Standard Layer (Required for non-exempt stages)

Non-exempt stages **must** include `harness_check`:

```json
{
  "status": "completed",
  "stage": "consolidator",
  "covered_req_ids": ["REQ-001"],
  "harness_check": {
    "completeness": {
      "score": 0.9,
      "level": "high",
      "reasoning": "All key components are covered"
    },
    "necessity": {
      "score": 0.85,
      "level": "high",
      "reasoning": "No redundant components identified"
    },
    "alignment": {
      "score": 0.95,
      "level": "high",
      "reasoning": "Output directly addresses original requirements"
    },
    "global_impact": {
      "score": 0.8,
      "level": "high",
      "reasoning": "Minimal negative impact on other stages"
    },
    "overall_score": 0.875,
    "decision": "PASS",
    "improvements": []
  }
}
```

**`harness_check` Field Definitions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `completeness` | object | ✅ | Coverage assessment (0-1 score) |
| `necessity` | object | ✅ | Redundancy assessment (0-1 score) |
| `alignment` | object | ✅ | Goal alignment assessment (0-1 score) |
| `global_impact` | object | ✅ | Cross-stage impact assessment (0-1 score) |
| `overall_score` | number | ✅ | Weighted average: `0.3*C + 0.2*N + 0.3*A + 0.2*G` |
| `decision` | string | ✅ | Quality gate decision (see [Decision Values](#decision-values)) |
| `improvements` | array | ✅ | List of suggested improvements (can be empty) |

**Score Object Structure:**

```json
{
  "score": 0.9,
  "level": "high",
  "reasoning": "Brief explanation"
}
```

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `score` | number | 0.0 - 1.0 | Numeric score |
| `level` | string | `"high"`, `"medium"`, `"low"` | Qualitative level |
| `reasoning` | string | - | Brief justification |

**Decision Values:**

| Value | Description |
|-------|-------------|
| `PASS` | Quality gate passed, no issues |
| `PASS_WITH_CONDITIONS` | Passed with minor conditions |
| `WARNING` | Warning issued, but acceptable |
| `CRITICAL_WARNING` | Serious warning, review recommended |
| `BLOCK_RECOMMENDATION` | Recommend blocking this output |

### Metadata Layer (Optional)

Additional tracking fields (not validated):

```json
{
  "session_id": "session_abc123",
  "timestamp": "2026-06-02T10:30:00Z",
  "duration_seconds": 45,
  "model": "qwen3.6-plus"
}
```

---

## Harness Check Schema

### Complete Example

```json
{
  "harness_check": {
    "completeness": {
      "score": 0.9,
      "level": "high",
      "reasoning": "All 7 requirements are addressed with clear evidence"
    },
    "necessity": {
      "score": 0.85,
      "level": "high",
      "reasoning": "No redundant analysis; each section serves a distinct purpose"
    },
    "alignment": {
      "score": 0.95,
      "level": "high",
      "reasoning": "Output structure directly mirrors the original problem statement"
    },
    "global_impact": {
      "score": 0.8,
      "level": "high",
      "reasoning": "No conflicts with previous stages; recommendations are consistent"
    },
    "overall_score": 0.875,
    "decision": "PASS",
    "improvements": [
      "Consider adding cost estimation for implementation",
      "Include risk mitigation timeline"
    ]
  }
}
```

### Scoring Weights

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Completeness | 30% | Most important: did we cover everything? |
| Alignment | 30% | Equally important: did we solve the right problem? |
| Necessity | 20% | Less critical: avoid redundancy |
| Global Impact | 20% | Less critical: minimize cross-stage conflicts |

**Formula:**
```
overall_score = 0.3 * completeness + 0.2 * necessity + 0.3 * alignment + 0.2 * global_impact
```

---

## Exempt Stages

### Definition

**Exempt stages** are stages that only require the Core Layer. They do **not** require `harness_check`.

### List of Exempt Stages

```python
HARNESS_EXEMPT_STAGES = frozenset([
    "data_collection",
    "planning",
    "summarizer"
])
```

### Rationale

| Stage | Why Exempt? |
|-------|-------------|
| `data_collection` | Pure information gathering, no analysis to evaluate |
| `planning` | Meta-stage that orchestrates others, not a deliverable |
| `summarizer` | Aggregation stage, quality depends on inputs not its own work |

### Validation Behavior

For exempt stages, `validate_stage_output()` only checks:
- ✅ `status` field exists
- ✅ `stage` field exists
- ✅ `covered_req_ids` field exists and is a non-empty array

For non-exempt stages, additionally checks:
- ✅ `harness_check` field exists
- ✅ All four dimensions exist with valid scores (0-1)
- ✅ `decision` field is one of the allowed values

---

## REQ-ID Format

### Pattern

```
REQ-\d+
```

**Examples:**
- ✅ `REQ-001`
- ✅ `REQ-042`
- ❌ `req-001` (lowercase)
- ❌ `REQ001` (missing hyphen)
- ❌ `REQ-` (no digits)

### Validation

```python
import re

def is_valid_req_id(req_id: str) -> bool:
    return bool(re.match(r'^REQ-\d+$', req_id))
```

### Usage in `covered_req_ids`

```json
{
  "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003"]
}
```

**Rules:**
- Must be an array (even if empty)
- Each element must match the `REQ-\d+` pattern
- Duplicates are allowed but discouraged
- Empty array `[]` is valid (stage covers no requirements)

---

## Control Contract Schema

### Purpose

The control contract is generated after the Planning stage to:
1. Map planner-generated experts to fixed research slots
2. Inject Layer 2 constraints into subsequent worker prompts
3. Define acceptance criteria for the final output

### Structure

```json
{
  "version": "1.0",
  "generated_at": "2026-06-02T10:30:00Z",
  "source": {
    "planning_stage": "stages/planning.json",
    "frozen_spec": "data/frozen_spec.json"
  },
  "research_workers": [
    {
      "id": "expert_1",
      "planner_expert_id": "performance_expert",
      "name": "性能优化专家",
      "angle": "系统性能调优",
      "reason": "Ensures system meets performance requirements",
      "expected_output_path": "stages/research_expert_1.json",
      "worker_role": "researcher_expert_1"
    },
    {
      "id": "expert_2",
      "planner_expert_id": "security_expert",
      "name": "安全专家",
      "angle": "系统安全设计",
      "reason": "Ensures system security and compliance",
      "expected_output_path": "stages/research_expert_2.json",
      "worker_role": "researcher_expert_2"
    },
    {
      "id": "expert_3",
      "planner_expert_id": "architecture_expert",
      "name": "架构专家",
      "angle": "系统架构设计",
      "reason": "Ensures robust system architecture",
      "expected_output_path": "stages/research_expert_3.json",
      "worker_role": "researcher_expert_3"
    }
  ],
  "layer2_constraints": {
    "reviewer_technical": [
      "Verify performance requirements are met",
      "Check security implementation"
    ],
    "reviewer_business": [
      "Validate business value proposition"
    ]
  },
  "audit_strategy": "standard",
  "frozen_spec_path": "data/frozen_spec.json",
  "traceability_matrix_path": "requirements_traceability_matrix.json",
  "acceptance_criteria": [
    "REQ-001: System handles 100k daily conversations",
    "REQ-002: Response time < 2 seconds"
  ],
  "warnings": []
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Schema version |
| `generated_at` | string | ISO 8601 timestamp |
| `research_workers` | array | Fixed 3 research slots (always `expert_1`, `expert_2`, `expert_3`) |
| `layer2_constraints` | object | Constraints injected into worker prompts |
| `audit_strategy` | string | Audit intensity: `"skip"`, `"standard"`, `"strict"` |
| `acceptance_criteria` | array | Final acceptance criteria (from frozen spec) |

---

## Validation Rules

### `validate_stage_output()` Function

**Location:** `domains/solution/task_builder.py`

**Signature:**
```python
def validate_stage_output(output: dict, stage_name: str) -> tuple[bool, str]
```

**Returns:**
- `(True, "")` if validation passes
- `(False, "error message")` if validation fails

### Validation Logic

```python
def validate_stage_output(output: dict, stage_name: str) -> tuple[bool, str]:
    # 1. Check Core Layer (all stages)
    for field in ["status", "stage", "covered_req_ids"]:
        if field not in output:
            return False, f"Missing required field: {field}"
    
    if not isinstance(output["covered_req_ids"], list):
        return False, "covered_req_ids must be an array"
    
    # 2. Check REQ-ID format
    import re
    for req_id in output["covered_req_ids"]:
        if not re.match(r'^REQ-\d+$', req_id):
            return False, f"Invalid REQ-ID format: {req_id}"
    
    # 3. Check Standard Layer (non-exempt stages only)
    if stage_name not in HARNESS_EXEMPT_STAGES:
        if "harness_check" not in output:
            return False, "Non-exempt stage missing harness_check"
        
        hc = output["harness_check"]
        for dim in ["completeness", "necessity", "alignment", "global_impact"]:
            if dim not in hc:
                return False, f"harness_check missing dimension: {dim}"
            if not (0 <= hc[dim]["score"] <= 1):
                return False, f"Invalid score for {dim}: {hc[dim]['score']}"
        
        valid_decisions = ["PASS", "PASS_WITH_CONDITIONS", "WARNING", 
                          "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]
        if hc["decision"] not in valid_decisions:
            return False, f"Invalid decision: {hc['decision']}"
    
    return True, ""
```

### Runtime Integration

**Location:** `domains/solution/completion_handler.py`

**Behavior:**
- Automatically called after each stage completes
- If validation fails, stage status is downgraded to `"partial"`
- Schema errors are recorded in the `.schema_errors` field of the completion result

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 4.3.0 | 2026-06-02 | Added `PASS_WITH_CONDITIONS` decision value; Fixed exempt stage validation |
| 4.2.0 | 2026-06-01 | Introduced three-layer schema architecture |
| 4.1.0 | 2026-05-30 | Added `HARNESS_EXEMPT_STAGES` |
| 4.0.0 | 2026-05-25 | Initial schema definition |

---

## Related Documents

- [README.md](../../domains/solution/README.md) - Solution Pro overview
- [SKILL.md](../../domains/solution/SKILL.md) - Agent execution steps
- [_overview.md](../../domains/solution/_overview.md) - Code file index
- [CHANGELOG.md](../../CHANGELOG.md) - Full version history

---

**Maintainer:** DeepFlow Solution Pro Team  
**Last Reviewed:** 2026-06-02
