# ⚠️ ARCHIVED — 这些文件未被生产代码引用

> 2026-07-15 Codex DryRun V3.4 发现: prompts/ship_pro/ 下所有文件均为死代码。
> 
> 活跃 Prompt 在 ship_orchestrator.py 中动态生成，不从此目录加载。
> 唯一活跃的 Consolidator prompt 位于: domains/ship_pro/prompts/consolidator.md
> 
> 原始文件已归档到: domains/ship_pro/_archive/prompts_ship_pro/

## 文件状态

| 文件 | 状态 | 原因 |
|------|------|------|
| ship_orchestrator.md | ❌ 死代码 | 生产 prompt 在 _build_planner_prompt() 动态生成 |
| ship_judge.md | ❌ 死代码 | 生产 prompt 在 InformationConservationGate.build_judge_prompt() 动态生成 |
| ship_fixer.md | ❌ 死代码 | 生产 prompt 在 prepare_fixer_spawn() 动态生成 |
| ship_harness.md | ❌ 死代码 | 生产 prompt 在 HarnessV3.build_judge_prompt() 动态生成 |
| ship_reviewer.md | ❌ 死代码 | 未被任何代码引用 |
