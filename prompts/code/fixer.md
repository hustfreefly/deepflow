# Code Fixer Prompt

Fix identified code issues and implement improvements.

## Input
Audit findings and original code.

## Output
Fixed code addressing all identified issues.

Output to: fixed_code.md

## Blackboard 读写（强制）
**读取**：
- `{session_id}/researcher_output.md`（原始代码）
- `{session_id}/auditor_*_output.md`（审计问题）

**写入**：修复后代码写入 `{session_id}/fixer_output.md`
