# 契约:Summarizer 单文件输出改革

> **版本**: v1.0.0
> **日期**: 2026-06-21
> **状态**: pending

---

## 一、目标

Summarizer Worker 只写一个文件 `final_result.json`,删除 `stages/summarizer.json` 和 `final_solution.md` 的写入要求。

## 二、改动清单

| # | 文件 | 改动 | 类型 |
|:---|:---|:---|:---|
| D1 | `prompts/v1/summarizer.md` | 输出要求从“3 文件”改为“1 文件”，删除 summarizer.json 和 final_solution.md | prompt |
| D2 | `domains/solution_pro/blackboard.py` | STAGE_PATH_REGISTRY["summarizer"] 从 `stages/summarizer.json` 改为 `final_result.json` | 代码 |
| D3 | `domains/solution_pro/completion_handler.py` | 1 REQUIRED_SOLUTION_FINAL_ARTIFACTS 删除 `final_solution.md`;2 final_output 查找顺序删除 md | 代码 |
| D4 | `core/orchestrator/pipeline_orchestrator.py` | STAGE_PATHS["summarizer"] 改为 `final_result.json` | 代码 |
| D5 | `domains/solution_pro/eval/propagation_checker.py` | 删除 summarizer.json 降级逻辑,只读 final_result.json | 代码 |
| D6 | `frontend/backend/routers/status_v2.py` | 从 `final_result.json` 渲染报告,删除 md 查找 | 代码 |
| D7 | `domains/solution_pro/task_builder.py` | build_summarizer_task 输出要求从 3 文件改为 1 文件 | 代码 |
| D8 | `scripts/golden_solution_pro_dry_run.py` | 删除 summarizer.json mock + final_solution.md mock | 测试 |
| D9 | `scripts/validate_solution_pro_contract.py` | 不动(只引用 stage name,不引用文件路径) | - |
| D10 | `tests/golden/verify_golden_case.py` | 更新 final_solution.md 检查逻辑 | 测试 |

## 三、验证标准

| # | 验证项 | 方法 | 通过条件 |
|:---|:---|:---|:---|
| 2.0.0 | prompt 只要求写 1 个文件 | grep summarizer.md | 无 `summarizer.json` 和 `final_solution.md` 引用(除历史注释) |
| 2.0.0 | 代码无 summarizer.json 路径引用 | grep 全项目 | 活跃代码(非 archive)中无 `stages/summarizer.json` 字符串 |
| 2.0.0 | 代码无 final_solution.md 路径引用 | grep 全项目 | 活跃代码(非 archive)中无 `final_solution.md` 字符串 |
| 2.0.0 | final_result.json 仍是主交付 | grep 确认 | Ship Pro 消费链路不受影响 |
| 2.0.0 | 前端可渲染 | 检查 status_v2.py | 从 JSON 渲染,不报错 |
| 2.0.0 | 声明-执行对齐 | 逐条对照 D1-D10 | 每个声明项有对应改动 |

## 四、不改动清单

| 文件 | 理由 |
|:---|:---|
| `archive/` 下所有文件 | 已归档,不改 |
| `prompts_archive/` 下所有文件 | 已归档,不改 |
| `prompts_backup_20260620/` 下所有文件 | 备份,不改 |
| `scripts/checks/check_worker_completion.py` | 旧版检查脚本,不影响运行 |
| `scripts/checks/check_orchestrator_v2.py` / `v4.py` | 旧版检查脚本 |
| `scripts/pipeline_progress_notify.py` | 只引用 stage name "summarizer",不引用文件路径 |
