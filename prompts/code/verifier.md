# Code Verifier Prompt

Verify the correctness of code fixes and improvements.

## Input
- Fixed code
- Original audit findings (P0/P1/P2 issues)
- Test results (if available)

## Output
Verification report:
1. Each issue addressed (✓ fixed / ✗ not fixed / ⚠ partially fixed)
2. New issues introduced by fixes
3. Test pass rate
4. Final quality score (0-100)
5. Approval status (PASS / REVISE / REJECT)

Output to: code_verification_report.md

## Blackboard 读写（强制）
**读取**：`{session_id}/fixer_output.md`（修复后代码）
**写入**：验证报告写入 `{session_id}/verifier_output.md`
- 评分 0-100，明确通过/失败
