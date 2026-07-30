# Agent DryRun 审计报告 — Deliver Pro V3.0.0

> **审计时间**: 2026-07-30 20:40 CST
**审计框架**: AgentDryRun V3.7（六维体检）
**执行方式**: Codex CLI 非交互式审计 + 本 Agent 逐项验证
**入口**: `.deepflow/domains/deliver_pro/__init__.py` → `run_deliver_pro()`
**审计范围**: 核心 Python 源码 + Prompt 文件 + 契约 Schema + 测试
**测试基线**: `domains/deliver_pro` 全量 pytest **338 passed** ✅ 零失败（但测试存在盲区）

---

## 综合判定: 🔴 NO_GO

| 维度 | 状态 | LLM 判断摘要 |
|------|------|-------------|
| 🔑 Prompt 主线 | 🟡 | spawn task 存在内联大段 JSON 内容，未彻底走文件引用模式 |
| 🔴 人（Agent 行为） | ✅ | 角色边界清晰，禁止行为明确 |
| 🟡 料（输入质量） | ✅ | Schema 约束较完整，但个别字段弱校验 |
| 🔵 法（编排+数据流） | 🔴 | VALIDATING 分支存在 AttributeError + 未注册 action，运行时直接崩溃 |
| 🟣 环（外部依赖） | ✅ | 无外网依赖，文件系统为唯一真相源 |
| ⚫ 系统（整车级） | 🟡 | 六维评分门控、DONE 判定、inline-task 大小均有隐患 |

---

## 架构认知图

```json
{
  "pipeline_name": "Deliver Pro V3 (Pulse 脉冲调度)",
  "stages": [
    {"name": "Entry", "agents": ["run_deliver_pro()"], "input": "project_name", "output": "pulse_config"},
    {"name": "Pulse", "agents": ["pulse_cli.py → DeliverOrchestrator.pulse()"], "input": "blackboard state", "output": "_pulse_actions.json"},
    {"name": "Worker", "agents": ["wp_runner.py 5-Phase pipeline"], "input": "WP + task", "output": "DELIVERABLE.md + MANIFEST.json"},
    {"name": "Assembly", "agents": ["smart_assembler.py (确定性代码)"], "input": "worker outputs", "output": "integrated_draft/DELIVERABLE.md"},
    {"name": "Validate", "agents": ["validate agent (LLM)"], "input": "integrated draft + plan", "output": "validation_result.json"},
    {"name": "Package", "agents": ["package agent (LLM)"], "input": "validated draft", "output": "delivery_manifest.json"},
    {"name": "Final Synthesis", "agents": ["LLM-as-Judge gate"], "input": "all WP deliverables + contract", "output": "_final_deliverable_done.json"}
  ],
  "data_flow": "Ship Pro → run_deliver_pro → pulse_cli → orchestrator.pulse() → tick() → spawn workers → assemble → validate → package → final_synthesis",
  "critical_path": ["tick() VALIDATING 分支", "phase_deriver.derive_phase()", "PulseAction 契约验证", "final batch task 构造"],
  "break_points": [
    {"location": "orchestrator.py VALIDATING 分支", "risk": "self.stages_dir 不存在 + fix_integrate 未在 PulseAction enum 注册", "cascade": "validate 返回非 PASS 时整条 WP 崩溃"},
    {"location": "phase_deriver.py derive_phase()", "risk": "manifest 内容不校验，只判存在性和文件大小", "cascade": "畸形交付物被标 DONE"},
    {"location": "ValidationVerdict.compute_verdict()", "risk": "不检查维度数量，只检查 min_score + weighted_score", "cascade": "单维度高分即可 PASS"},
    {"location": "orchestrator.py _build_*_action()", "risk": "task 字符串内含数千字符 inline JSON", "cascade": "接近/超过平台截断阈值"}
  ]
}
```

---

## 问题分级汇总

| # | 维度 | 问题 | 分级 | 分类 | 修复方向 | 状态 |
|---|------|------|------|------|----------|:----:|
| 1 | 🔵法 | `orchestrator.py` VALIDATING 分支访问不存在的 `self.stages_dir` | 🔴 BLOCKER | 运行时崩溃 | 改为 `self._wp_dir(wp_id) / "stages" / "validation_result.json"` | 待修 |
| 2 | 🔵法 | VALIDATING 分支返回 `action="fix_integrate"`，但 `PulseAction` enum 未注册该值 | 🔴 BLOCKER | 契约违例 | 在 `PulseAction.action` 枚举中加入 `"fix_integrate"`，或改为 `"spawn_workers"` + 特殊标记 | 待修 |
| 3 | ⚫系统 | `phase_deriver.derive_phase()` 对 `delivery_manifest.json` 内容不校验，畸形 JSON 仍返回 `DONE` | 🟡 技术债 | 状态推导不严 | 读取并校验 manifest JSON 结构，损坏时返回 `PACKAGING` 或 `VALIDATING` | 待修 |
| 4 | ⚫系统 | `ValidationVerdict.compute_verdict()` 不检查维度数量，单维度高分即可 PASS | 🟡 技术债 | 评分门控过松 | 增加最少维度数检查（如 ≥4 个有效维度） | 待修 |
| 5 | 🔑主线 | `_build_infer_contract_action` / `_build_final_synthesis_action` / `_build_run_final_gate_action` 的 task 字符串分别为 3673 / 5619 / 7912 字符，内含大量 inline JSON | 🟡 技术债 | spawn task 过大 | 把 living_spec / contract / synthesis 摘要先写入 blackboard 文件，task 只给文件路径 | 待修 |
| 6 | 🟡料 | ruff 静态检查报 86 个 lint 错误（多为未使用 import / 变量） | ℹ️ 建议 | 代码整洁度 | 批量清理（低风险） | 可选 |

---

## 详细审计结果

### 1. 🔴 BLOCKER #1：VALIDATING 分支访问 `self.stages_dir` 导致 AttributeError

**证据**：

```python
# domains/deliver_pro/orchestrator.py:606-615（VALIDATING 分支）
if verdict != "PASS":
    import json
    verdict_path = self.stages_dir / "validate" / "validation_result.json"  # ❌
    if verdict_path.exists():
        ...
```

验证：

```python
>>> from domains.deliver_pro.orchestrator import DeliverOrchestrator
>>> o = DeliverOrchestrator.__new__(DeliverOrchestrator)
>>> hasattr(o, 'stages_dir')
False
```

**根因**：`DeliverOrchestrator` 没有 `stages_dir` 属性，该属性只存在于 `DeliverWPRunner` / `DeliverRunner`。`DeliverOrchestrator` 应该使用 `self._wp_dir(wp_id) / "stages" / "validation_result.json"`。

**影响**：只要 validate agent 返回 CONDITIONAL / FAIL，进入该分支就会立刻抛出 `AttributeError`，对应 WP 在该 pulse  tick 中无法进入 fix loop 或 package_failed，流程中断。

**修复方向**：

```python
verdict_path = self._wp_dir(wp_id) / "stages" / "validation_result.json"
```

---

### 2. 🔴 BLOCKER #2：`fix_integrate` action 未在 `PulseAction` 枚举中注册

**证据**：

```python
# domains/deliver_pro/orchestrator.py:616
return {"wp_id": wp_id, "action": "fix_integrate", "spawn_params": fix_params, "error": None}
```

```python
# domains/deliver_pro/contracts/pulse_report.py:25
action: Literal[
    "analyze", "spawn_workers", "validate", "package", "package_failed",
    "infer_deliverable_contract", "final_synthesis", "run_final_gate",
]
```

验证：

```python
>>> from domains.deliver_pro.contracts.pulse_report import PulseAction
>>> PulseAction(wp_id='WP-001', action='fix_integrate', task='x', label='y')
ValidationError: Input should be 'analyze', 'spawn_workers', 'validate', 'package', ...
```

**影响**：即使 BLOCKER #1 被修复，当 `verdict != "PASS"` 且 `loop_decision == "fix"` 时，返回的 action 会在 `PulseReport.model_validate()` 处失败，导致 `_pulse_actions.json` 写入失败，整次 pulse 崩溃。

**修复方向**：

方案 A（推荐）：在 `PulseAction.action` 枚举中加入 `"fix_integrate"`。

方案 B： orchestrator 不再返回 `fix_integrate`，而是返回 `spawn_workers` + 在 `task`/`label` 中携带修复标记，由 wp_runner 识别。

---

### 3. 🟡 技术债 #1：畸形 `delivery_manifest.json` 仍被推导为 `DONE`

**证据**：

```python
# domains/deliver_pro/phase_deriver.py:213-217
manifest_file = stages_dir / "delivery_manifest.json"
final_dir = stages_dir / "final_deliverable"
if manifest_file.exists() and final_dir.exists():
    if _has_substantial_file(final_dir):
        return PHASE_DONE
```

验证：

```python
>>> from domains.deliver_pro.phase_deriver import derive_phase
>>> (stages/'delivery_manifest.json').write_text('{malformed json')
>>> (final/'junk.txt').write_text('x'*50)
>>> derive_phase(wp)
'DONE'
```

**根因**：`derive_phase` 只检查 manifest 文件是否存在 + 交付目录是否有 ≥50B 的文件，不解析/校验 manifest 内容。

**影响**：package agent 写入损坏的 JSON 后，系统会错误地认为 WP 已完成，下游 final synthesis 可能基于空/坏数据运行。

**修复方向**：

```python
if manifest_file.exists() and final_dir.exists():
    manifest_data = _read_json(manifest_file)
    if not isinstance(manifest_data, dict):
        return PHASE_PACKAGING  # 或 VALIDATING，取决于上下文
    if _has_substantial_file(final_dir):
        return PHASE_DONE
```

---

### 4. 🟡 技术债 #2：单维度高分即可通过“六维”质量门

**证据**：

```python
# domains/deliver_pro/contracts/validation_verdict.py:91-101
@classmethod
def compute_verdict(cls, weighted_score: float, scores: dict[str, ScoreDimension]) -> str:
    min_score = min(s.score for s in scores.values()) if scores else 0
    if weighted_score >= 3.5 and min_score >= 3:
        return "PASS"
    elif weighted_score >= 3.0 and min_score >= 2:
        return "CONDITIONAL"
    else:
        return "FAIL"
```

验证：

```python
>>> v = ValidationVerdict.model_validate({
...     'round': 1, 'verdict': 'PASS',
...     'scores': {'completeness': {'score': 5, 'weight': 1.0}},
...     'weighted_score': 5.0
... })
>>> v.compute_verdict(v.weighted_score, v.scores)
'PASS'
```

**根因**：`compute_verdict` 不检查 `scores` 中是否包含全部六个预期维度，也不检查维度数量。

**影响**：LLM Judge 可以只给一个维度打高分就通过验证，违背“六维体检”设计意图。

**修复方向**：

```python
REQUIRED_DIMENSIONS = {"completeness", "correctness", "credibility", "actionability", "consistency", "professionalism"}
if len(scores) < len(REQUIRED_DIMENSIONS) or not REQUIRED_DIMENSIONS.issubset(scores):
    return "FAIL"  # 或 "CONDITIONAL"
```

---

### 5. 🟡 技术债 #3：最终 batch 级 task 字符串过大

**证据**：

| Action | task 长度 | 内容特征 |
|--------|----------|----------|
| `infer_deliverable_contract` | 3673 字符 | 内含 `living_spec` / `contract` JSON 摘要 |
| `final_synthesis` | 5619 字符 | 内含 `spec_summary` / `contract_summary` 摘要 |
| `run_final_gate` | 7912 字符 | 内含 `contract_summary` + `synthesis_text` 前 10000 字符 |

代码位置：

```python
# domains/deliver_pro/orchestrator.py:1700-1748
spec_summary = json.dumps(living_spec, ensure_ascii=False)[:3000]
contract_summary = json.dumps(contract, ensure_ascii=False)[:2000]
...
task = (
    f"You are a Final Synthesis Agent.\n"
    f"..."
    f"living_spec (truncated):\n{spec_summary}\n\n"
    f"contract (truncated):\n{contract_summary}\n\n"
)
```

**根因**：虽然 task 里包含文件路径，但仍把大量 JSON 摘要直接 inline 到 task 字符串中，不符合 AgentDryRun V3.7 §9.1 的“文件引用模式”。

**影响**：task 接近/超过 500 字符警告线、2000 字符阻断线，存在平台截断风险。

**修复方向**：

1. 在 action 构建前把摘要写入 blackboard 文件，例如：
   - `blackboard/{project}/data/_dryrun_living_spec_summary.json`
   - `blackboard/{project}/data/_dryrun_contract_summary.json`
   - `blackboard/{project}/final_synthesis/_synthesis_text_for_gate.md`
2. task 字符串只包含角色说明 + 文件路径 + 输出要求，控制在 300-500 字符以内。

---

### 6. ℹ️ 建议：ruff 静态检查 86 个 lint 错误

**证据**：

```bash
$ ruff check domains/deliver_pro --output-format=concise
Found 86 errors.
```

错误类型分布：
- `F401`：未使用的 import（大量）
- `F541`：无占位符的 f-string
- `F841`：赋值但未使用的局部变量
- `F811`：`verify_package_output` 重复定义 3 次
- `E741`：歧义变量名 `l`

**影响**：这些大多不影响运行时，但会降低代码可维护性，隐藏真正的问题。

**修复方向**：低风险批量清理。特别注意 `wp_runner.py` 中 `verify_package_output` 被重复定义 3 次，需要确认保留正确版本。

---

## 修复优先级建议

| 优先级 | 问题 | 理由 |
|--------|------|------|
| P0 | BLOCKER #1 + #2 | 直接造成运行时崩溃，必须一起修 |
| P1 | 技术债 #1（畸形 manifest） | 导致错误终态，数据质量风险 |
| P2 | 技术债 #2（六维门控） | 影响验证语义正确性 |
| P3 | 技术债 #3（task 大小） | 可运行但截断风险随数据量增长 |
| P4 | 建议 lint 清理 | 代码整洁，可延后 |

---

## 验证清单（修复后必做）

- [ ] 构造 `validation_result.json` verdict=FAIL，确认 VALIDATING 分支不抛 `AttributeError`
- [ ] 构造 `validation_result.json` verdict=FAIL + `has_fixable=True`，确认 `fix_integrate` action 能写入 `_pulse_actions.json`
- [ ] 构造损坏的 `delivery_manifest.json` + 非空 final_deliverable，确认 `derive_phase` 不返回 `DONE`
- [ ] 构造单维度 ValidationVerdict，确认 `compute_verdict` 返回 `FAIL` 或 `CONDITIONAL`
- [ ] 测量 infer/synthesis/gate 三个 task 字符串长度，确认均 < 500 字符（或至少 < 2000）
- [ ] `pytest domains/deliver_pro` 全绿
- [ ] `ruff check domains/deliver_pro` 剩余错误数下降

---

## 审计结论

Deliver Pro V3 在架构层面（Pulse 调度、文件系统真相源、契约笼子）已经比较成熟，全量测试也通过了。但 Codex 定向探针暴露出 **2 个运行时 BLOCKER** 和 **3 个系统级技术债**，这些问题都被现有测试盲区覆盖。建议先修 P0 BLOCKER，再按优先级逐条修复。

**综合判定：🔴 NO_GO（修复 BLOCKER 后可重新评估为 CONDITIONAL）**
