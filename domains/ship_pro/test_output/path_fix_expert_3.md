# 路径传递问题评估 — 工程架构视角

> 评估者：path_fix_expert_3（系统架构视角）
> 时间：2026-06-20

---

## 1. 忠礼方案覆盖范围评估

忠礼的方案是在 `prepare_pipeline` 中预计算绝对路径，通过 `.replace()` 注入到 orchestrator prompt。

| ENOENT 类别 | 次数 | 忠礼方案是否解决 |
|:---|:---:|:---|
| Worker prompt 路径猜测 | 12 | ✅ **部分解决** — 注入 `{prompts_dir}` 后，orchestrator 不再需要拼 `../prompts/` |
| 文档路径猜测（contracts/docs） | 8 | ❌ **不解决** — 这些路径在 Worker prompt 中以相对名引用，Worker 不知道 blackboard 绝对路径 |
| 竞态条件（文件未写完） | 4 | ❌ **不解决** — 需要写入端做原子操作或读取端加重试 |
| 状态文件不存在 | 6 | ❌ **不解决** — `prepare_pipeline` 已经初始化了 `.cron_run_count` 等文件，但 orchestrator 在 Step 0 之前就去读 `.stage_progress.json`，属于时序问题 |

**结论**：忠礼方案解决 ~40% 的问题（12/30 次 ENOENT），且只覆盖第 1 类。剩余 18 次错误需要额外修复。

---

## 2. 推荐的 P0 修复清单（最小改动集）

### Fix-1：扩展 prepare_pipeline 的变量注入（解决第 1+2 类，20 次 ENOENT）

**文件**：`domains/ship_pro/scripts/run_pipeline.py` → `prepare_pipeline()` 函数（L253-265）

**改动**：在 `.replace()` 链中增加 `{prompts_dir}` 和 `{deepflow_root}`：

```python
prompts_dir = str((Path(__file__).parent.parent / "prompts").resolve())
deepflow_root = str(Path(__file__).resolve().parent.parent.parent.parent)

orchestrator_prompt = (
    orchestrator_prompt
    .replace("{base_path}", base_path)
    .replace("{prompts_dir}", prompts_dir)          # 新增
    .replace("{deepflow_root}", deepflow_root)       # 新增
    .replace("{session_id}", session_id)
    .replace("{input_path}", str(input_p.resolve()))
)
```

**同时修改** `ship_orchestrator.md` L90：将 `{base_path}/../prompts/` 改为 `{prompts_dir}/`。

**对 Worker 路径问题的解决**：在 orchestrator 构建 Worker task prompt 时（模板 L114），已经注入了 `blackboard_dir: {base_path}`。问题是 orchestrator LLM 有时忽略这个注入。解决方案：在 Worker prompt 文件（`architect.md` 等）中增加占位符 `{blackboard_dir}`，由 `prepare_pipeline` 或 orchestrator 在构建 task 时替换为绝对路径。

### Fix-2：状态文件时序保护（解决第 4 类，6 次 ENOENT）

**文件**：`domains/ship_pro/prompts/ship_orchestrator.md` → Step 0 区域

**改动**：在 orchestrator prompt 的 Step 0 中明确：

> "在读取 `.stage_progress.json` 之前，先检查文件是否存在。如果不存在，视为首次运行，从 Stage 1 开始。"

这是 prompt 层面的修复（零代码改动），因为 `prepare_pipeline` 已经初始化了该文件（L250-251），问题出在 orchestrator 读文件时可能早于初始化完成（spawn 时 race）。

### Fix-3：原子写入 + 读取重试（解决第 3 类，4 次 ENOENT）

**文件**：`domains/ship_pro/prompts/ship_orchestrator.md` → 验证逻辑区域

**改动**：在 orchestrator 验证 Worker 输出的指令中增加：

> "读取输出文件后，验证 JSON 可解析且非空。如果文件为空或 JSON 解析失败，等待 3 秒后重试，最多重试 2 次。"

这是最小改动方案。更彻底的方案是让 Worker 先写 `.tmp` 再 `rename`（原子操作），但需要修改所有 Worker prompt 的输出指令。

---

## 3. 关于文件名不一致

经代码审查，**文件名不一致（连字符 vs 下划线）在当前代码中不是实际问题**。所有 Worker prompt 和 orchestrator prompt 统一使用下划线命名（`architect_output.json`）。orchestrator.md L127 已显式强调"下划线，不是连字符"。这个问题已被之前的修复覆盖。

---

## 4. 两套 Blackboard 的长期建议

Solution Pro 的 `BlackboardManager`（有 `STAGE_PATH_REGISTRY`）是正确方向。Ship Pro 应该迁移到同一模式，但**不是 P0**。

**最小迁移路径**：在 `domains/ship_pro/` 下创建 `blackboard.py`，定义 `SHIP_STAGE_REGISTRY`（5 个 Worker 的输出路径），让 `prepare_pipeline` 初始化 `BlackboardManager` 实例并传入 `spawn_params`。Worker 通过 registry 获取绝对路径，不再依赖 prompt 注入。

**建议时机**：等 P0 修复稳定运行一周后再做迁移，避免同时改动路径逻辑和架构。

---

## 总结

| 优先级 | 修复项 | 覆盖 ENOENT | 改动量 |
|:---:|:---|:---:|:---|
| P0 | Fix-1：扩展变量注入 | 20 次 | ~10 行代码 + prompt 模板 |
| P0 | Fix-2：状态文件时序保护 | 6 次 | prompt 文字修改 |
| P1 | Fix-3：读取重试逻辑 | 4 次 | prompt 文字修改 |
| P2 | BlackboardManager 迁移 | 架构统一 | 新文件 + 重构 |

忠礼的方案方向正确，但需要扩展覆盖范围才能解决全部 30 次 ENOENT。
