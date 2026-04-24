# Verifier Prompt

Verify the quality and correctness of fixes and improvements.

## Input
Fixed code/content and original audit findings.

## Output
Verification report:
1. Issues addressed (✓/✗)
2. New issues introduced
3. Quality score
4. Final approval status

## Blackboard 读写（强制）
**读取**：`{session_id}/fixer_output.md`（修复后内容）
**写入**：验证报告写入 `{session_id}/verifier_output.md`
- 评分 0-100，明确通过/失败结论