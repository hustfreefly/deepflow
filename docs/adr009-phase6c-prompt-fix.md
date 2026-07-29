# ADR-009 Phase 6c: Ship Pro Prompt MD-first 修复

## 问题

`domains/ship_pro/__init__.py` 中的 Orchestrator prompt（Step 0）仍然描述 JSON-first 架构：
- Line 616: "final_solution.json 是唯一数据源，MD 是人类可读副本"
- Line 618-624: 验证脚本检查 `final_solution.json`
- Line 642: "写入 final_solution.json"
- Line 651: "write 到 final_solution.json"

这与代码的 MD-first 逻辑矛盾。Agent 会按照 prompt 指示写 JSON，导致：
1. Agent 写入 `final_solution.json`
2. 代码优先读 `final_solution.md`（不存在）
3. 代码 fallback 到 `final_solution.json`
4. 虽然能工作，但违反 ADR-009

## 修复方案

更新 prompt 为 MD-first：

```
**设计原则**: 代码只做 I/O + Schema 验证，LLM 做语义理解。final_solution.md 是真相源（ADR-009 MD-first）。

**检查**: exec 验证 final_solution.md 是否存在:

```python
exec: python3 -c "
from pathlib import Path
p = Path('{project_blackboard}/stages/final_solution.md')
if not p.exists():
    print('MISSING'); exit(1)
content = p.read_text()
# 简单检查 MD 是否包含关键 section
required_sections = ['## key_decisions', '## implementation_phases']
missing = [s for s in required_sections if s not in content]
if missing:
    print(f'INCOMPLETE: missing sections {missing}'); exit(1)
print(f'OK: MD contains required sections')
"
```

**如果 OK** → 直接进入 Step 1。

**如果 MISSING 或 INCOMPLETE** → 执行语义提取：

1. read {project_blackboard}/stages/final_solution.md（或从 Solution Pro 获取）
2. read {project_blackboard}/data/frozen_spec.md
3. **用你的语义理解能力**，从 MD + frozen_spec 中提取结构化数据
4. 必须产出的字段（字段名固定，不能自创）：
   - `key_decisions`: list of {{"decision": str, "rationale": str}}
   - `implementation_phases`: list of {{"phase": str, "description": str, "duration": str}}
   - `risk_summary`: list of {{"risk": str, "impact": str, "mitigation": str}}
   - `constraint_coverage`: {{"total": N, "covered": N, "ratio": 0-1, "details": [...]}}
   - `covered_req_ids`: list of REQ-ID strings
   - `semantic_anchors`: list of {{"name": str, "category": str, "constraint": str}}
   - `full_solution`: MD 文本（完整方案文档内容）
5. write 到 {project_blackboard}/stages/final_solution.md（MD 格式）
6. 重新执行验证脚本，确认 OK
```

## 验证标准

- [ ] prompt 中不再说 "final_solution.json 是唯一数据源"
- [ ] prompt 指示 Agent 写入 `final_solution.md`
- [ ] 测试通过
