# Summarizer Prompt

Create comprehensive summary of all work.

## Input
All stage outputs and findings.

## Output
Structured final report:
1. Executive summary
2. Key findings
3. Recommendations
4. Next steps

Output to: final_report.md

## Blackboard 读写（强制）
**读取**：读取所有 `{session_id}/*_output.md` 文件
**写入**：最终报告写入 `{session_id}/final_report.md`
