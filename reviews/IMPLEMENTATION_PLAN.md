# DeepFlow 架构加固 — 详细实施方案

> **基于**: 6 专家评审综合报告 (SYNTHESIS_REPORT.md)
> **日期**: 2026-06-23
> **总工期**: ~4 个工作日
> **原则**: Pydantic 为真相源，渐进式推进，每 Phase 独立可验证

---

## 全局架构变更一览

```
变更前（当前状态）:
  Prompt (Markdown) ──各自描述──→ LLM ──各自理解──→ Gate (Python) ──各自检查──→ Schema (JSON)
  3 条执行路径各自独立
  3 个状态文件各自更新

变更后（目标状态）:
  contracts.py (Pydantic) ──自动生成──→ Prompt schema 段落
                        ──自动生成──→ Gate 检查代码
                        ──自动生成──→ JSON Schema
  run_pipeline.py 为唯一执行引擎
  pipeline_state.json 为唯一状态文件
```

---

## Phase 0: 止血（今天，~1 小时）

> **目标**: 消除 P1 级问题，让管线能正确运行
> **原则**: 最小改动，不改架构

### Task 0.1: 修复 Architect Prompt ↔ Gate 契约断裂（P1-2）

**问题**: `gate_architect()` 检查 `project_type` 和 `requirements[].mapped_components`，但 prompt 的输出 schema 没有这两个字段。

**改动文件**: `domains/ship_pro/prompts/architect.md`

**具体改动**:

1. **在输出格式 JSON 模板中**（约 L220-260），添加 `project_type` 字段：

```json
{
  "_meta": { ... },
  "project_type": "web_app | data_pipeline | multi_agent | api_service | mobile_app | desktop_app | other",
  "project": { ... },
  "modules": [ ... ],
  "requirements": [
    {
      "req_id": "REQ-001",
      "description": "需求描述",
      "priority": "P0|P1|P2",
      "coverage": "covered|partial|missing",
      "mapped_components": ["COMP-001", "COMP-002"]   // ← 新增
    }
  ],
  "wp_file_mapping": { ... }   // ← 新增（gate minor check）
}
```

2. **在需求提取规则中**（约 L112-130），归一化格式增加 `mapped_components`：

```json
{
  "req_id": "REQ-001",
  "description": "需求描述",
  "priority": "P0|P1|P2",
  "coverage": "covered|partial|missing",
  "mapped_components": ["COMP-001"]  // 实现该需求的模块 ID 列表
}
```

3. **在 Few-Shot 示例中**（约 L310-420），所有 requirements 条目加上 `mapped_components`，加上 `project_type` 和 `wp_file_mapping`。

4. **在自检清单中**（约 L207），添加：
   - `□ project_type 是否已填写？`
   - `□ 每个 requirement 是否有 mapped_components？`

**验证**:
```bash
cd ~/.openclaw/workspace/.deepflow
python3 -c "
import sys; sys.path.insert(0, '.')
import core.bootstrap
from domains.ship_pro.eval.gates import gate_architect
import json

# 用修复后的 few-shot 示例数据测试
test_data = {
    'project_type': 'multi_agent',
    'modules': [{'id': 'COMP-01', 'name': 'test'}],
    'dependencies': [],
    'requirements': [{'req_id': 'REQ-001', 'mapped_components': ['COMP-01']}],
    'domain_details': {},
    'wp_file_mapping': {'REQ-001': 'file.md'}
}
result = gate_architect(test_data)
assert result['decision'] == 'PASS', f'Expected PASS, got {result[\"decision\"]}: {result[\"feedback\"]}'
print('✅ gate_architect PASS with complete data')
"
```

---

### Task 0.2: 修复 Packager Prompt ↔ Schema 断裂（P1-1）

**问题**: Packager prompt 的输出模板与 `ship_package_v3.schema.json` 有 128 个不一致。

**改动文件**: `domains/ship_pro/prompts/packager.md`

**具体改动**:

1. **删除 `_meta` 顶层字段** — prompt 中的 JSON 模板目前有 `_meta` 在顶层，schema 不允许。改为只保留 `meta`（无下划线前缀）。

2. **对齐 `meta.input_format` 枚举值**:
   - 当前 prompt: `"检测到的格式"` (自由文本)
   - Schema 要求: `"A_final_solution" | "B_flat_domain" | "C_pipeline_summary" | "D_minimal"`
   - 改动: 在 prompt 中明确列出枚举值

3. **对齐 `work_packages` 字段**:
   - 删除 Schema 不允许的字段: `constraints`, `related_modules`, `requirements`
   - `model_tier` 枚举对齐: `claude-opus | claude-sonnet | claude-haiku | gpt-4o | gpt-4o-mini | qwen-max | qwen-plus | auto`
   - `outputs` 从 `string[]` 改为 `object[]`，每个元素包含 `{type, path, description}`

4. **对齐 `risk_register` 字段**:
   - 添加必填字段: `title`, `likelihood`
   - 当前 risk 结构: `{id, description, severity}` → 改为 `{id, title, description, severity, likelihood, mitigation}`

5. **对齐 `quality_report` 字段**:
   - 删除 Schema 不允许的字段: `ac_verifiability_score`, `consistency_checks`, `dependency_sanity`, `issues_by_severity`
   - 改为 Schema 定义的结构: `{layer1_structural, layer2_semantic, layer3_actionable, overall_score, recommendations}`

6. **在 prompt 的 JSON 模板中完整对齐**:

```json
{
  "schema_version": "3.0.0",
  "meta": {
    "package_id": "SP-001",
    "project_name": "从 blueprint 提取",
    "generated_at": "ISO 8601",
    "generator": { "agent": "ship-pro", "model": "你的模型", "version": "3.0.0" },
    "source_session_id": "从输入获取",
    "input_format": "A_final_solution | B_flat_domain | C_pipeline_summary | D_minimal"
  },
  "project_context": { ... },
  "work_packages": [
    {
      "id": "WP-001",
      "title": "...",
      "objective": "...",
      "budget": { "tokens": 50000, "time_minutes": 30 },
      "complexity": "simple | medium | complex",
      "model_tier": "claude-opus | claude-sonnet | claude-haiku | gpt-4o | gpt-4o-mini | qwen-max | qwen-plus | auto",
      "dependencies": ["WP-000"],
      "priority": "high | medium | low",
      "context_files": ["..."],
      "outputs": [
        { "type": "file | directory | config | test | documentation", "path": "path/to/output", "description": "..." }
      ],
      "acceptance_criteria": ["AC1 文本描述", "AC2 文本描述"],
      "acceptance_tests": ["test command"],
      "retry_policy": { "on_failure": "retry | abort | skip" },
      "tags": ["..."]
    }
  ],
  "dependency_graph": { ... },
  "risk_register": [
    {
      "id": "RISK-001",
      "title": "风险标题（必填）",
      "description": "风险描述",
      "severity": "critical | high | medium | low",
      "likelihood": "very_high | high | medium | low | very_low",
      "mitigation": "缓解措施",
      "affected_wps": ["WP-001"]
    }
  ],
  "summary": { ... },
  "quality_report": {
    "layer1_structural": { "score": 85, "details": "..." },
    "layer2_semantic": { "score": 80, "details": "..." },
    "layer3_actionable": { "score": 75, "details": "..." },
    "overall_score": 80,
    "recommendations": ["..."]
  }
}
```

**验证**:
```bash
cd ~/.openclaw/workspace/.deepflow
python3 -c "
import sys, json; sys.path.insert(0, '.')
import core.bootstrap
from domains.ship_pro.schemas import load_schema  # 或直接加载
from jsonschema import Draft7Validator

# 用修复后的 prompt 模板示例数据验证
# ... (具体验证脚本)
print('✅ Packager output passes schema validation')
"
```

---

### Task 0.3: 修复 Solution Pro 状态不一致（P1-4）

**问题**: `.completed.json` 说 completed，`.stage_progress.json` 说 running。

**改动文件**: `domains/solution_pro/completion_handler.py`

**具体改动**: 在 `_write_completion_marker()` 函数中（约 L440-470），添加 `.stage_progress.json` 更新：

```python
def _write_completion_marker(session_id, status, completion_rate):
    bb = BlackboardManager(session_id=session_id)
    # ... existing code ...
    marker_path = bb.write('.completed', marker_data)

    # 新增: 同步更新 .stage_progress.json
    try:
        progress_data = bb.read('stages/.stage_progress')
        if progress_data:
            progress_data['status'] = 'completed' if status == 'completed' else 'failed'
            progress_data['completed_at'] = marker_data['completed_at']
            bb.write('stages/.stage_progress', progress_data)
    except Exception:
        pass  # 非关键路径，不阻塞主流程

    return marker_path
```

**验证**:
```bash
# 检查上次运行的状态文件
python3 -c "
import json
bb = '/Users/allen/.openclaw/workspace/.deepflow/blackboard/开发者可观测性系统架构_architecture_790240b7'
c = json.load(open(f'{bb}/stages/.completed.json'))
p = json.load(open(f'{bb}/stages/.stage_progress.json'))
print(f'completed: {c[\"status\"]}')
print(f'progress: {p[\"status\"]}')
assert c['status'] == p['status'] or p['status'] == 'running', 'State mismatch!'
# 修复后应该一致
"
```

---

### Task 0.4: 修复 pipeline_status.json 未更新（P1-3）

**问题**: 主 Agent 手动驱动管线时，`pipeline_status.json` 不会被更新。

**改动文件**: `domains/ship_pro/scripts/run_pipeline.py`

**具体改动**: 添加一个 CLI 子命令 `update-status`，供主 Agent 在每个阶段完成后调用：

```python
# 在 CLI 部分（约 L780+）添加:
elif cmd == "update-status":
    if len(sys.argv) < 5:
        print("用法: python3 run_pipeline.py update-status <output_dir> <agent_name> <decision>")
        sys.exit(1)
    output_dir = Path(sys.argv[2])
    agent_name = sys.argv[3]
    decision = sys.argv[4]  # PASS / CONDITIONAL / FAIL
    feedback = sys.argv[5] if len(sys.argv) > 5 else ""
    _update_gate_status(output_dir, agent_name, decision, feedback)
    
    # 更新 current_agent 到下一个
    status = _load_status(output_dir)
    order = json.load(open(output_dir / "pipeline_config.json"))["execution_order"]
    current_idx = order.index(agent_name) if agent_name in order else -1
    if current_idx < len(order) - 1:
        status["current_agent"] = order[current_idx + 1]
    else:
        status["current_agent"] = None  # 全部完成
    _save_status(output_dir, status)
    print(json.dumps({"ok": True, "agent": agent_name, "decision": decision}))
```

**主 Agent 使用方式**（在 SKILL.md 中添加）:
```bash
# 每个阶段完成后执行:
python3 run_pipeline.py update-status <output_dir> architect PASS "Architect output is structurally sound."
```

**验证**:
```bash
cd ~/.openclaw/workspace/.deepflow
python3 domains/ship_pro/scripts/run_pipeline.py update-status \
  blackboard/test_session/ship_output architect PASS "test"
cat blackboard/test_session/ship_output/pipeline_status.json
```

---

## Phase 1: Pydantic 真相源（Week 1，~2 天）

> **目标**: 用 Pydantic 模型作为唯一真相源，自动生成 Prompt schema 段落、Gate 检查代码、JSON Schema
> **核心原则**: 改一处（Pydantic 模型），三处自动对齐

### Task 1.1: 安装依赖 + 创建 contracts 模块

```bash
# pydantic 2.13.4 已安装，无需额外安装
# 创建目录结构
mkdir -p domains/ship_pro/contracts/
touch domains/ship_pro/contracts/__init__.py
```

### Task 1.2: 定义 Architect 输出模型

**新建文件**: `domains/ship_pro/contracts/architect.py`

```python
"""
Architect Agent 输出契约 — 唯一真相源

从此模型自动生成:
1. JSON Schema (gate_packager 的 check_schema_compliance 使用)
2. Prompt 中的输出格式段落 (architect.md 的 "输出格式" 章节)
3. Gate 检查逻辑 (gate_architect 的字段检查)
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class DataSufficiency(BaseModel):
    modules: Literal["sufficient", "partial", "insufficient"]
    dependencies: Literal["sufficient", "partial", "insufficient"]
    requirements: Literal["sufficient", "partial", "insufficient"]
    risks: Literal["sufficient", "partial", "insufficient"]


class ArchitectMeta(BaseModel):
    agent: Literal["architect"] = "architect"
    input_format: Literal["A", "B", "C", "D"]
    overall_confidence: Literal["high", "medium", "low"]
    data_sufficiency: DataSufficiency
    prompt_sha: str = ""
    model_id: str = ""
    run_id: str = ""
    round: int = 0
    timestamp: str = ""


class Project(BaseModel):
    name: str
    objective: str
    problem_statement: str


class Module(BaseModel):
    id: str
    name: str
    summary: str
    responsibilities: list[str] = []
    technology_stack: list[str] = []
    is_infrastructure: bool = False


class Dependency(BaseModel):
    from_: str = Field(alias="from")
    to: str
    reason: str = ""

    class Config:
        populate_by_name = True


class Requirement(BaseModel):
    req_id: str
    description: str
    priority: Literal["P0", "P1", "P2"]
    coverage: Literal["covered", "partial", "missing"]
    mapped_components: list[str] = Field(
        default_factory=list,
        description="实现该需求的模块 ID 列表。Gate 检查此字段。"
    )


class SLAConstraint(BaseModel):
    metric: str
    target: str
    scope: str = ""


class Risk(BaseModel):
    id: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]


class ImplementationHint(BaseModel):
    phase: str
    description: str
    modules: list[str] = []


class WpFileMapping(BaseModel):
    """需求到文件的映射关系。Gate minor check 检查此字段。"""
    pass  # 灵活结构，用 dict[str, str]


class ArchitectOutput(BaseModel):
    """Architect Agent 的完整输出契约。"""
    _meta: ArchitectMeta
    project_type: str = Field(
        description="项目类型分类。Gate Major check 检查此字段。",
        examples=["web_app", "data_pipeline", "multi_agent", "api_service"]
    )
    project: Project
    modules: list[Module] = Field(min_length=1)
    dependencies: list[Dependency] = []
    domain_details: dict = {}
    sla_constraints: list[SLAConstraint] = []
    requirements: list[Requirement] = Field(min_length=1)
    risks: list[Risk] = []
    implementation_hints: list[ImplementationHint] = []
    wp_file_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="需求到文件的映射。Gate Minor check。"
    )
```

### Task 1.3: 定义 Packager 输出模型

**新建文件**: `domains/ship_pro/contracts/packager.py`

```python
"""Packager Agent 输出契约 — 替代 ship_package_v3.schema.json"""

from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field


class Generator(BaseModel):
    agent: str = "ship-pro"
    model: str
    version: str = "3.0.0"


class PackageMeta(BaseModel):
    package_id: str
    project_name: str = ""
    generated_at: str
    generator: Generator
    source_session_id: str
    input_format: Literal["A_final_solution", "B_flat_domain", "C_pipeline_summary", "D_minimal"]
    tags: list[str] = []


class ArchitectureInfo(BaseModel):
    style: str = ""
    components: list[dict] = []
    layers: list[str] = []


class RequirementsCoverage(BaseModel):
    total: int
    covered: int
    coverage_rate: float


class ProjectContext(BaseModel):
    problem_statement: str
    solution_overview: str
    architecture: ArchitectureInfo
    requirements_coverage: RequirementsCoverage
    constraints: list[str] = []
    known_gaps: list[str] = []


class Budget(BaseModel):
    tokens: int
    time_minutes: int
    max_retries: int = 3


class OutputArtifact(BaseModel):
    type: Literal["file", "directory", "api_endpoint", "database_migration", "config", "test", "documentation"]
    path: str
    description: str = ""


class RetryPolicy(BaseModel):
    on_failure: Literal["retry", "abort", "skip"] = "retry"


class WorkPackage(BaseModel):
    id: str
    title: str
    objective: str
    budget: Budget
    complexity: Literal["simple", "medium", "complex"]
    model_tier: Literal[
        "claude-opus", "claude-sonnet", "claude-haiku",
        "gpt-4o", "gpt-4o-mini",
        "qwen-max", "qwen-plus", "auto"
    ] = "auto"
    dependencies: list[str] = []
    priority: Literal["high", "medium", "low"]
    context_files: list[str] = []
    outputs: list[OutputArtifact] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    acceptance_tests: list[str] = []
    retry_policy: RetryPolicy = RetryPolicy()
    requires_human_approval: bool = False
    tags: list[str] = []


class DependencyGraph(BaseModel):
    execution_order: list[str]
    parallel_groups: list[list[str]] = []
    critical_path: list[str] = []
    edges: list[dict] = []


class RiskRegisterItem(BaseModel):
    id: str
    title: str
    description: str = ""
    severity: Literal["critical", "high", "medium", "low"]
    likelihood: Literal["very_high", "high", "medium", "low", "very_low"]
    mitigation: str = ""
    affected_wps: list[str] = []


class ComplexityDistribution(BaseModel):
    trivial: int = 0
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class PackageSummary(BaseModel):
    total_wps: int
    estimated_effort: str = ""
    total_token_budget: int
    total_time_minutes: int
    parallel_time_minutes: int = 0
    complexity_distribution: ComplexityDistribution
    narrative: str = ""
    immediate_next_steps: list[str] = []


class QualityLayer(BaseModel):
    score: int
    details: str = ""


class QualityReport(BaseModel):
    layer1_structural: QualityLayer = QualityLayer(score=0)
    layer2_semantic: QualityLayer = QualityLayer(score=0)
    layer3_actionable: QualityLayer = QualityLayer(score=0)
    overall_score: int = 0
    recommendations: list[str] = []


class ShipPackage(BaseModel):
    """Ship Pro 最终交付物契约。"""
    schema_version: str = "3.0.0"
    meta: PackageMeta
    project_context: ProjectContext
    work_packages: list[WorkPackage] = Field(min_length=1)
    dependency_graph: DependencyGraph
    risk_register: list[RiskRegisterItem] = []
    summary: PackageSummary
    quality_report: QualityReport = QualityReport()
```

### Task 1.4: 创建代码生成器

**新建文件**: `domains/ship_pro/contracts/generator.py`

```python
"""
从 Pydantic 模型自动生成:
1. JSON Schema → schemas/ 目录
2. Prompt schema 段落 → 嵌入 prompt 文件
3. Gate 字段检查清单 → 嵌入 gate 代码
"""

import json
from pathlib import Path
from pydantic import BaseModel


def generate_json_schema(model_class: type[BaseModel], output_path: str) -> None:
    """从 Pydantic 模型生成 JSON Schema 文件"""
    schema = model_class.model_json_schema()
    Path(output_path).write_text(json.dumps(schema, indent=2, ensure_ascii=False))
    print(f"✅ Generated JSON Schema: {output_path}")


def generate_prompt_section(model_class: type[BaseModel]) -> str:
    """从 Pydantic 模型生成 Prompt 中的输出格式段落"""
    schema = model_class.model_json_schema()
    # 提取 required 字段和类型
    lines = ["## 输出格式（自动生成，禁止手动修改）", ""]
    lines.append("```json")
    lines.append(json.dumps(schema, indent=2, ensure_ascii=False))
    lines.append("```")
    return "\n".join(lines)


def generate_gate_field_list(model_class: type[BaseModel]) -> list[str]:
    """从 Pydantic 模型提取 Gate 应检查的字段列表"""
    schema = model_class.model_json_schema()
    required = schema.get("required", [])
    properties = list(schema.get("properties", {}).keys())
    return sorted(set(required + properties))


# CLI 入口
if __name__ == "__main__":
    from domains.ship_pro.contracts.architect import ArchitectOutput
    from domains.ship_pro.contracts.packager import ShipPackage

    base = Path(__file__).parent.parent

    # 1. 生成 JSON Schema
    generate_json_schema(
        ShipPackage,
        str(base / "schemas" / "ship_package_v3.schema.json")
    )

    # 2. 打印 Gate 字段清单
    print(f"Architect fields: {generate_gate_field_list(ArchitectOutput)}")
    print(f"Packager fields: {generate_gate_field_list(ShipPackage)}")
```

### Task 1.5: 重构 Gate 使用 Pydantic 验证

**改动文件**: `domains/ship_pro/eval/gates.py`

**核心改动**: `gate_architect()` 和 `gate_packager()` 使用 Pydantic 验证替代手动 `.get()` 检查。

```python
# gate_architect 重构示例
def gate_architect(blueprint: dict) -> dict:
    from domains.ship_pro.contracts.architect import ArchitectOutput
    from pydantic import ValidationError

    critical = {}
    major = {}
    minor = {}

    # Critical: 基本结构
    try:
        validated = ArchitectOutput(**blueprint)
        critical["schema_valid"] = True
    except ValidationError as e:
        critical["schema_valid"] = False
        # 分析哪些字段缺失
        missing = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]
        critical["missing_fields"] = missing
        return _make_result(False, "FAIL", critical, major, minor,
                           f"Architect Gate FAIL: Schema invalid. Missing: {missing}")

    # Critical: modules 非空
    critical["modules_non_empty"] = len(validated.modules) > 0

    # Critical: 无环依赖
    # ... (保留现有 _check_acyclic 逻辑)

    # Major: project_type 存在 (Pydantic 已验证，这里只检查非空)
    major["project_type_exists"] = bool(validated.project_type)

    # Major: requirements 有 mapped_components
    mapped_count = sum(1 for r in validated.requirements if r.mapped_components)
    major["requirements_mapped"] = mapped_count == len(validated.requirements)

    # Minor
    minor["wp_file_mapping_exists"] = bool(validated.wp_file_mapping)
    minor["domain_details_non_empty"] = bool(validated.domain_details)

    # Decision
    critical_failures = [k for k, v in critical.items() if not v]
    major_failures = [k for k, v in major.items() if not v]

    if critical_failures:
        decision = "FAIL"
        passed = False
    elif len(major_failures) > len(major) * 0.5:
        decision = "CONDITIONAL"
        passed = True
    else:
        decision = "PASS"
        passed = True

    # ... feedback 生成 ...
    return _make_result(passed, decision, critical, major, minor, feedback)
```

### Task 1.6: 更新测试

**改动文件**: `domains/ship_pro/eval/test_gates.py`

添加基于 Pydantic 模型的测试：

```python
def test_architect_contract_from_pydantic():
    """验证 ArchitectOutput Pydantic 模型与 gate_architect 一致"""
    from domains.ship_pro.contracts.architect import ArchitectOutput
    
    # 1. 有效数据应该通过
    valid = ArchitectOutput(
        _meta={...},
        project_type="web_app",
        project={...},
        modules=[...],
        requirements=[Requirement(req_id="REQ-001", mapped_components=["COMP-01"], ...)]
    )
    result = gate_architect(valid.model_dump(by_alias=True))
    assert result["decision"] == "PASS"

    # 2. 缺少 project_type 应该 CONDITIONAL
    data = valid.model_dump(by_alias=True)
    del data["project_type"]
    result = gate_architect(data)
    assert result["decision"] in ("CONDITIONAL", "FAIL")

def test_packager_contract_schema_match():
    """验证 ShipPackage Pydantic 模型生成的 Schema 与 JSON Schema 文件一致"""
    from domains.ship_pro.contracts.packager import ShipPackage
    import json
    
    generated = ShipPackage.model_json_schema()
    stored = json.load(open("schemas/ship_package_v3.schema.json"))
    
    # 比较 required 字段
    assert set(generated["required"]) == set(stored["required"])
```

---

## Phase 2: 执行引擎化（Week 2，~1 天）

> **目标**: 消灭 3 条执行路径，统一为 `run_pipeline.py` CLI

### Task 2.1: 合并 orchestrator.py 到 run_pipeline.py

**改动**:
- `orchestrator.py` 的 `detect_format()` 和 `load_prompt()` 功能已在 `run_pipeline.py` 中存在
- 废弃 `orchestrator.py`，在其头部添加 deprecation 警告
- 所有调用 `orchestrator.py` 的地方改为 `run_pipeline.py`

### Task 2.2: 更新 SKILL.md

**改动文件**: `domains/ship_pro/SKILL.md`

将 V2 流程（Pre-Scanner → Compiler → Reviewer）标记为 `deprecated`，只保留 V3 流程描述，且改为 CLI-only：

```markdown
## 执行流程（V3）

主 Agent 只需调用 `run_pipeline.py` CLI：

1. `python3 run_pipeline.py prepare <input> <output_dir>` — 准备管线
2. 循环直到所有阶段完成：
   a. `python3 run_pipeline.py task <agent> <output_dir>` — 获取 Agent 任务
   b. `sessions_spawn(task=<task_content>)` — 执行 Agent
   c. `python3 run_pipeline.py gate <agent> <output_dir>` — 运行质量门禁
   d. `python3 run_pipeline.py update-status <output_dir> <agent> <decision>` — 更新状态
3. `python3 run_pipeline.py validate <output_dir>` — 最终验证
```

### Task 2.3: 添加 Cron Watcher 自动设置

在 `run_pipeline.py prepare` 阶段自动生成 Cron Watcher 配置，确保管线进度可追踪。

---

## Phase 3: 状态单一化（Week 3，~半天）

> **目标**: 合并所有状态文件为 1 个 `pipeline_state.json`

### Task 3.1: 定义统一状态模型

**新建文件**: `domains/ship_pro/contracts/pipeline_state.py`

```python
from pydantic import BaseModel
from typing import Literal

class AgentState(BaseModel):
    state: Literal["pending", "running", "gate_pass", "gate_conditional", "gate_fail", "skipped", "done"]
    retry_count: int = 0
    gate_decision: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

class PipelineState(BaseModel):
    run_id: str
    session_id: str
    status: Literal["preparing", "running", "completed", "failed"]
    current_agent: str | None = None
    agents: dict[str, AgentState]
    started_at: str
    completed_at: str | None = None
```

### Task 3.2: 统一状态更新入口

所有状态变更必须通过 `run_pipeline.py update-status` CLI，禁止直接写状态文件。

### Task 3.3: Solution Pro 同步

`completion_handler.py` 的状态更新也改为写入统一的 `pipeline_state.json`。

---

## 验证计划

### Phase 0 验证（止血后）

```bash
# 1. Gate 测试
cd ~/.openclaw/workspace/.deepflow
python3 -m pytest domains/ship_pro/eval/test_gates.py -v

# 2. Schema 验证
python3 -c "
import json
from jsonschema import Draft7Validator
pkg = json.load(open('blackboard/<session>/ship_output/blackboard/ship_package'))
schema = json.load(open('domains/ship_pro/schemas/ship_package_v3.schema.json'))
errors = list(Draft7Validator(schema).iter_errors(pkg))
print(f'Schema errors: {len(errors)}')
assert len(errors) == 0, f'Still {len(errors)} errors!'
"

# 3. 状态一致性
python3 -c "
import json
bb = 'blackboard/<session>'
c = json.load(open(f'{bb}/stages/.completed.json'))
p = json.load(open(f'{bb}/stages/.stage_progress.json'))
assert c['status'] == p['status'], 'State mismatch!'
print('✅ State consistent')
"
```

### Phase 1 验证（Pydantic 真相源）

```bash
# 1. Pydantic → JSON Schema 一致性
python3 domains/ship_pro/contracts/generator.py
# 对比生成的 schema 与存储的 schema

# 2. Pydantic → Gate 一致性
python3 -m pytest domains/ship_pro/eval/test_gates.py -v -k "contract"

# 3. 端到端验证
# 用真实 Solution Pro 输出跑完整 Ship Pro 管线
# 验证 0 Schema 错误 + 0 Gate CONDITIONAL
```

### Phase 2 验证（执行引擎）

```bash
# 验证只有 run_pipeline.py 一个入口
grep -rn "sessions_spawn.*ship" domains/ship_pro/SKILL.md
# 应该只看到 run_pipeline.py CLI 调用
```

### Phase 3 验证（状态单一化）

```bash
# 验证只有 1 个状态文件
find blackboard/<session> -name "*status*" -o -name "*progress*" -o -name "*completed*" | wc -l
# 应该 = 1 (pipeline_state.json)
```

---

## 风险与缓解

| 风险 | 概率 | 缓解 |
|------|:---:|------|
| LLM 不遵守 Pydantic 定义的 Schema | 中 | 配合 JSON mode + gate 自动重试 |
| 重构引入新 bug | 中 | 每 Phase 独立验证，可回滚 |
| Phase 1 工作量大 | 中 | 先做 architect + packager 两个核心模型 |
| pydantic 版本兼容 | 低 | 已验证 2.13.4 可用 |

---

## 文件变更清单

| Phase | 文件 | 操作 | 预估行数 |
|:---:|------|------|:---:|
| 0.1 | `prompts/architect.md` | 修改 | +15 |
| 0.2 | `prompts/packager.md` | 修改 | +30 / -10 |
| 0.3 | `solution_pro/completion_handler.py` | 修改 | +10 |
| 0.4 | `scripts/run_pipeline.py` | 修改 | +20 |
| 1.2 | `contracts/architect.py` | 新建 | ~80 |
| 1.3 | `contracts/packager.py` | 新建 | ~120 |
| 1.4 | `contracts/generator.py` | 新建 | ~60 |
| 1.5 | `eval/gates.py` | 修改 | +40 / -20 |
| 1.6 | `eval/test_gates.py` | 修改 | +60 |
| 2.1 | `scripts/orchestrator.py` | 废弃 | -210 |
| 2.2 | `SKILL.md` | 修改 | +20 / -50 |
| 3.1 | `contracts/pipeline_state.py` | 新建 | ~30 |
| 3.2 | `scripts/run_pipeline.py` | 修改 | +15 |
| **总计** | | | **~480 新增 / ~80 删除** |

---

*Generated: 2026-06-23 18:50 | Based on 6-expert review synthesis*
