# Ship Pro 归档文件

本目录存放已废弃的旧版本文件，保留供追溯参考。

## 目录结构

```
_archive/
├── v6/                          # V6 版本遗留
│   ├── fix_all.py               # 一次性修复脚本
│   ├── FIX_SUMMARY.md           # V6 Dry Run 修复总结
│   ├── IMPLEMENTATION_GUIDE.md  # V6 实现指南
│   ├── run_ship_pro.py          # V6 独立 CLI（已被 __init__.py::run_ship_pro 替代）
│   └── agent/                   # V6 Agent 层（已被 V8.2 Orchestrator 替代）
│       ├── __init__.py
│       └── ship_agent.py
├── v7/                          # V7 版本遗留
│   ├── V7_DECISIONS.md          # V7 架构决策文档
│   └── dry_run.py               # V7 Dry Run（已被 AgentDryRun Skill 替代）
├── prompts/                     # 已内嵌到代码的旧 Prompt 模板
│   ├── agent.md                 # V6 Agent prompt
│   ├── pipeline_runner.md       # V8 PipelineRunner prompt（已被 Orchestrator 替代）
│   └── worker_base.md           # V6 Worker prompt（已被代码内 _build_single_worker_prompt 替代）
└── sessions/                    # 旧 E2E 测试 session 数据
    ├── ship_v7_e2e_20260704_120504/
    ├── ship_v7_fix_20260704_141357/
    ├── ship_v7_fix_20260704_141406/
    ├── ship_v7_rerun_20260704_161141/
    └── ship_v8_e2e_20260704_220457/
```

## 当前版本

- **V8.2** — 见 `../__init__.py`, `../SKILL.md`, `../docs/V8_DECISIONS.md`
- 归档时间: 2026-07-04
