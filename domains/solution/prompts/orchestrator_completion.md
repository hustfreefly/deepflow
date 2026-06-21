---
id: solution/orchestrator_completion
version: 1.0.0
description: 10 阶段管线完成后的处理流程，包括编译 Frozen Blueprint 和 Ship Package
author: DeepFlow Team
created: 2026-06-18
updated: 2026-06-21
tags: [solution, prompt, orchestrator, completion]
---

# 完成后处理（10 阶段全部完成后执行）

## Step 6: 执行完成后处理脚本

写入 `.completed` 后，**立即**执行：

```bash
cd {deepflow_path}
python3 domains/solution/completion_handler.py {session_id}
```

此脚本会：
1. 检查所有阶段的完成状态
2. 更新 tasks.db 数据库
3. 编译 Frozen Blueprint + Living Blueprint
4. 如果 Frozen Blueprint 不是 blocked，编译 Ship Package

**注意**：
- 此步骤失败**不影响**主管线状态（`.completed` 已写入）
- 编译结果会打印到日志，供排查使用
- 如果编译失败，可以后续手动重新运行此脚本

## REQ-ID 需求追踪

- `{base_path}/data/frozen_spec.json` 是唯一 REQ-ID 来源。
- 每个 worker 输出必须包含顶层 `covered_req_ids` 和 `requirement_evidence`。
- Stage 9 Harness Final 必须写入 `{base_path}/requirements_traceability_matrix.json`。
- Stage 10 Summarizer 必须读取覆盖矩阵，并在 `final_solution.md` 中输出"需求覆盖度"章节。

## 错误分类

- `retry`: worker 超时、输出文件暂未出现、JSON 暂时不可读
- `skip`: 非关键 worker 缺输出，例如某个 researcher 失败
- `abort`: execution_plan 无法读取、tasks.json 无法读取、planning 阶段失败

## 最终输出

写入 `.completed` 后，输出最终状态：

```json
{
  "status": "completed|partial|failed",
  "session_id": "{session_id}",
  "base_path": "{base_path}",
  "control_contract_path": "{base_path}/control_contract.json",
  "frozen_spec_path": "{base_path}/data/frozen_spec.json",
  "traceability_matrix_path": "{base_path}/requirements_traceability_matrix.json"
}
```
