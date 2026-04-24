## STEP 3: Worker Agent 调度

**管线顺序**：
```
planner → researcher×6 → financial → auditor×3 → fixer → verifier → summarizer
```

**spawn Worker**（必须真实调用）：
```python
# Researcher（6个并行）
for role in ["finance", "tech", "market", "macro", "management", "sentiment"]:
    sessions_spawn(
        runtime="subagent",
        mode="run",
        label=f"researcher_{role}_{iteration}",
        task=build_researcher_task(role, context),  # 从prompts/workers/加载
        timeout_seconds=300,
        model="bailian/qwen3.5-plus",
        scopes=["host.exec", "fs.read"]
    )

# Auditor（3个并行）
for role in ["factual", "upside", "downside"]:
    sessions_spawn(...)
```

**收敛检测**：
每轮迭代后调用check_convergence()，未收敛继续迭代。

**最大迭代**：10轮
