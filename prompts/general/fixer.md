# General Fixer Prompt

Fix identified issues in general research and analysis content.

## Input
- Audit findings with identified issues
- Original content/documents
- Issue priority list (P0/P1/P2)

## Output
Revised content addressing all identified issues:
1. Summary of issues fixed
2. Updated content sections
3. Rationale for changes
4. Quality improvement assessment

## Blackboard 读写（强制）
**读取**：
- `{session_id}/researcher_output.md`（原始内容）
- `{session_id}/auditor_output.md`（问题清单）

**写入**：修复后内容写入 `{session_id}/fixer_output.md`
- 标注修复部分，保持原有结构
