# 实施可行性视角评审

> **评审人**: 实施可行性视角（改动风险、向后兼容、迁移成本、测试验证策略）
> **评审日期**: 2026-06-21
> **评审对象**: `blackboard_system_redesign.md` v2.0.0-draft

---

## 核心判断（一句话）

**方案方向正确，但改动清单严重不完整——实际受影响文件至少 12 个而非 5 个，且降级路径策略在 pipeline_watcher 的 cron 场景下存在断裂风险，需要补充 path_config 层改造和 watcher 兼容逻辑后才能安全实施。**

---

## 逐项评审（对应 6 个问题）

### 1. 5 个文件的改动清单是否完整？

**不完整。实际受影响文件至少 12 个。**

方案列出的 5 个文件：`blackboard.py`、`completion_handler.py`、`pipeline_watcher.py`、`run_pipeline.py`、`start_solution_pro.py`。

**遗漏的文件**（通过 grep `blackboard/` 路径引用发现）：

| # | 遗漏文件 | 引用方式 | 影响 |
|:--|:--|:--|:--|
| 1 | **`core/config/path_config.py`** | `get_blackboard_path()` 是所有路径的根，`self.blackboard_dir = self.base_dir / 'blackboard'` | 🔴 **必须改**。新结构 `projects/{slug}/runs/{ts}/` 需要 path_config 支持新的路径解析逻辑，否则所有下游都错 |
| 2 | **`domains/solution_pro/task_builder.py`** | 10+ 处硬编码 `f"{_DEEPFLOW_BASE}/blackboard/{session_id}/"` 作为 prompt 中的 `{blackboard_path}` 替换 | 🔴 **必须改**。LLM worker 收到的 prompt 里路径是错的，写文件写到旧位置 |
| 3 | **`domains/solution_pro/__init__.py`** | 状态文件初始化（`.completed`、`.cron_run_count` 等写入 `base_path/`），以及 delivery config 路径 | 🟡 必须改。状态文件要移到 `state/` 子目录 |
| 4 | **`domains/solution_pro/orchestrator_agent.py`** | `self.blackboard.base_path` 引用 + worker 输出路径拼接 | 🟡 需要适配 |
| 5 | **`domains/solution_pro/harness_check_expert.py`** | `blackboard_path / session_id / STAGE_PATH_REGISTRY["audit"]` | 🟡 路径拼接方式变了 |
| 6 | **`domains/spec_pro/coordinator.py`** | `self.base_path = os.path.join(str(_BASE_DIR), "blackboard", self.session_id)` | 🟡 Spec Pro 路径也要适配新结构 |
| 7 | **`domains/research_pro/__init__.py`** | `base_path_input = str(_path_config.base_dir / "blackboard" / session_id)` + 状态文件操作 | 🟡 Research Pro 独立存放，但路径初始化代码要改 |
| 8 | **`core/quality/entry_harness.py`** | `session_dir = _DEEPFLOW_BASE / "blackboard" / session_id` | 🟡 质量检查路径 |
| 9 | **`scripts/pipeline_progress_notify.py`** | `"progress_file": ".stage_progress.json"` 和 `"progress_file": "blackboard/.stage_progress.json"` | 🟡 状态文件路径 |
| 10 | **`frontend/backend/routers/status_v2.py`** | `BLACKBOARD_DIR = _DEEPFLOW_ROOT / _cfg["paths"]["blackboard"]` | 🟡 前端 API 要搜索新路径 |

**结论**：方案低估了改动范围。仅列出 5 个文件是因为只看了"主动改动"，没有追踪"被动受影响"的文件。建议用 `grep -rn "blackboard/" --include="*.py"` 做一次全量扫描作为改动基线。

---

### 2. "新代码走新路径，旧代码走降级路径"的策略是否可行？

**部分可行，但降级路径维护成本被严重低估。**

#### 可行的部分

- `completion_handler.py`：先查 `state/.completed`，降级查 `.completed` → 简单，成本低
- `blackboard.py` STAGE_PATH_REGISTRY：通过 `get_stage_path()` 内部判断 → 可行
- `status_v2.py`：先搜 `projects/`，降级搜 `_legacy/` → 可行

#### 不可行 / 高风险的部分

**问题 1：`task_builder.py` 的 prompt 路径替换**

`task_builder.py` 在 prompt 中注入 `{blackboard_path}` 给 LLM worker。LLM worker 用这个路径读写文件。如果新代码注入新路径（`projects/{slug}/runs/{ts}/solution/`），但 LLM worker 的 write/read 工具不支持降级逻辑，那**降级路径对 LLM worker 无效**——LLM 只会按 prompt 里的路径写。

→ 降级策略对"代码路径"可行，对"LLM 消费路径"不可行。

**问题 2：`pipeline_watcher.py` 的 cron 场景**

cron watcher 是由 launchd/cron 定期触发的独立进程。旧项目的 cron job 指向旧的 `base_path`（如 `blackboard/DeepFlow_xxx/`）。新代码改了路径后：
- 旧 cron job 仍然指向旧路径 → 旧路径的文件还在 → 旧 watcher 还能跑 → **没问题**
- 但如果旧项目重跑了 Solution Pro（新代码），新代码写到 `projects/{slug}/runs/{ts}/`，旧 watcher 不知道新路径 → **watcher 失效**

→ 降级策略要求 watcher 同时监控新旧两个路径，或者旧项目永远不用新代码跑。

**问题 3：降级路径的维护成本是永久性的**

每次改路径相关代码，都要同时维护新旧两条路径的逻辑。这不是一次性成本，是**每次改动的永久税**。按当前代码活跃度（5+ 文件涉及路径），预计维护成本为每个 PR 多 15-30 分钟。

**建议**：
- 降级路径保留，但设一个明确的过期时间（如 3 个月后删除降级逻辑）
- 或者更激进：旧项目直接不跑新代码，新代码只用于新项目。这样降级路径只需在 path_config 层做，不需要每个文件都做

---

### 3. 旧项目（`_legacy/`）的 cron watcher 找不到状态文件，会发生什么？

**两种场景，两种结果：**

#### 场景 A：旧项目不再重跑（最可能）

旧项目的 cron job 仍然存在，指向 `blackboard/{old_session_id}/`。状态文件（`.completed`、`.cron_run_count`）还在原位置。

- watcher 正常运行 → 读到 `.completed` status=completed → 输出 "已完成" → `should_remove_cron=true` → 自动移除 cron job
- **结论：没问题，自然消亡**

#### 场景 B：旧项目用新代码重跑（风险场景）

新代码写到 `projects/{slug}/runs/{ts}/`，旧 cron job 指向 `blackboard/{old_session_id}/`。

- watcher 读旧路径 → 旧路径没有新的 `.stage_progress.json` → watcher 认为 orchestrator 已死 → 触发 circuit_break
- 或者旧路径的 `.completed` 是上一次运行的（过期数据）→ watcher 读到过期 completed → 时间戳校验失败（`ts < run_start_at`）→ 返回 None → watcher 继续等 → 超时 → circuit_break
- **结论：watcher 误报，用户收到错误通知**

**处理方案**：
1. **最简单**：旧项目重跑时，先清理旧 cron job（`crontab -l | grep old_session_id`），再用新路径注册新 cron
2. **更健壮**：`pipeline_watcher.py` 加一个 fallback 逻辑——如果 `base_path` 下没有 `.stage_progress.json`，检查 `projects/` 下是否有对应 slug 的新 run
3. **推荐**：方案 1。方案 2 增加了 watcher 复杂度，而旧项目重跑的频率很低（16 个真实项目），手动清理 cron 的成本可接受

---

### 4. 改动顺序应该是什么？

**依赖关系图**：

```
path_config.py (基础层)
    ↓
blackboard.py (路径注册表)
    ↓
task_builder.py (prompt 路径注入) ← orchestrator_agent.py (调用)
    ↓
__init__.py (Solution Pro 入口，session_id 生成)
    ↓
start_solution_pro.py (启动脚本)
    ↓
completion_handler.py (完成检查)
    ↓
pipeline_watcher.py (cron 监控)
    ↓
run_pipeline.py (Ship Pro)
    ↓
status_v2.py (前端)
```

**推荐改动顺序（6 步，每步可独立验证）**：

| 步骤 | 文件 | 理由 |
|:--|:--|:--|
| **Step 1** | `core/config/path_config.py` | 基础层。新增 `get_project_run_path(slug, run_id)` 方法，不改现有 `get_blackboard_path()`。零风险 |
| **Step 2** | `domains/solution_pro/blackboard.py` | STAGE_PATH_REGISTRY 适配。新增 `get_stage_path_v2()` 方法，旧方法保留。通过 `BlackboardManager.__init__` 的参数判断用新还是旧 |
| **Step 3** | `domains/solution_pro/task_builder.py` + `orchestrator_agent.py` | prompt 路径注入。这是 LLM worker 的唯一路径来源，必须跟 Step 2 同步 |
| **Step 4** | `domains/solution_pro/__init__.py` + `start_solution_pro.py` | session_id 生成逻辑改为 `{slug}/runs/{timestamp}`。这是入口改动，改完后新跑的项目走新路径 |
| **Step 5** | `completion_handler.py` + `pipeline_watcher.py` + `pipeline_progress_notify.py` | 状态文件路径 + 降级逻辑。必须在 Step 4 之后，因为要先有新路径才能写降级 |
| **Step 6** | `run_pipeline.py` + `status_v2.py` + `coordinator.py` + `research_pro/__init__.py` | Ship Pro 去套娃 + 前端适配 + 其他域适配。独立于主链路，可以并行改 |

**关键依赖**：Step 1-3 必须先完成再改 Step 4。否则新 session_id 格式下 task_builder 注入的路径是错的，LLM worker 写文件到错误位置。

---

### 5. 如何验证改动正确性？需要写哪些测试？

#### 验证策略：三层验证

**Layer 1：单元测试（路径解析）**

```python
# test_path_config.py
def test_new_project_path():
    """新项目路径解析正确"""
    path = config.get_project_run_path("deepflow-observability", "20260621_104400")
    assert path == base_dir / "blackboard/projects/deepflow-observability/runs/20260621_104400"

def test_legacy_path_fallback():
    """旧 session_id 降级到旧路径"""
    path = config.get_blackboard_path("DeepFlow_xxx_architecture_1a43ee1f")
    assert path == base_dir / "blackboard/DeepFlow_xxx_architecture_1a43ee1f"

def test_slug_conflict_resolution():
    """slug 冲突时加 hash 后缀"""
    slug1 = config.generate_slug("DeepFlow 可观测性")
    slug2 = config.generate_slug("DeepFlow 可观测性")  # 同 topic
    assert slug1 != slug2  # 第二个加 hash
```

**Layer 2：集成测试（端到端路径链路）**

```python
# test_blackboard_path_integration.py
def test_solution_pro_creates_correct_structure():
    """Solution Pro 跑完后，文件在新路径正确位置"""
    # 跑一个最小 Solution Pro（mock LLM）
    result = run_solution_pro(topic="test", ...)
    run_path = Path(result["run_path"])
    assert (run_path / "solution/stages/planning.json").exists()
    assert (run_path / "solution/final_result.json").exists()

def test_ship_pro_no_nesting():
    """Ship Pro 不再创建 blackboard/ 子目录"""
    result = prepare_pipeline(input_path, output_dir)
    bb_dir = Path(result["blackboard_dir"])
    assert bb_dir.name != "blackboard"  # 不套娃
    assert (bb_dir / "stages/architect_output.json").exists()

def test_legacy_project_still_readable():
    """旧项目数据仍可被 completion_handler 读取"""
    status = check_orchestrator_completion("old_session_id", domain="solution")
    assert status["status"] in ("completed", "partial")
```

**Layer 3：Golden 测试（现有测试适配）**

现有 `tests/golden/` 和 `tests/integration/test_watcher_contract.py` 需要更新路径断言。建议：
- 新增 golden case 用新路径结构
- 旧 golden case 保留，标记为 `legacy`，验证降级路径

#### 必须写的测试（最小集）

| 测试 | 验证什么 | 优先级 |
|:--|:--|:--|
| `test_slug_generation` | slug 生成 + 冲突处理 | P0 |
| `test_new_path_resolution` | 新路径解析正确 | P0 |
| `test_legacy_fallback` | 旧路径降级正确 | P0 |
| `test_ship_pro_no_nesting` | Ship Pro 不套娃 | P0 |
| `test_watcher_with_new_path` | watcher 在新路径下正常工作 | P1 |
| `test_watcher_with_legacy_path` | watcher 在旧路径下降级工作 | P1 |
| `test_task_builder_prompt_path` | prompt 中注入的路径正确 | P1 |
| `test_completion_handler_both_paths` | completion_handler 新旧路径都能检查 | P1 |

---

### 6. 你发现了什么风险？

#### 风险 1：`path_config.py` 是单点故障（🔴 高）

所有路径解析都经过 `PathConfig.get_blackboard_path()`。如果新逻辑有 bug，**所有域都受影响**。

**缓解**：Step 1 的 `path_config.py` 改动必须有 100% 测试覆盖，且新旧路径走不同的方法（不改现有方法签名）。

#### 风险 2：LLM worker 路径注入断裂（🔴 高）

`task_builder.py` 在 prompt 中注入 `{blackboard_path}`。LLM worker 用这个路径写文件。如果注入的路径跟 `BlackboardManager` 的实际路径不一致，**worker 写到错误位置，completion_handler 找不到文件**。

这是最容易出现且最难调试的问题——因为 LLM worker 的行为不 deterministic，路径错误可能表现为"偶尔成功偶尔失败"。

**缓解**：在 `task_builder.py` 和 `BlackboardManager` 之间加一个断言——`BlackboardManager` 初始化后，把实际路径回传给 `task_builder`，`task_builder` 注入的路径必须跟实际路径一致。

#### 风险 3：`pipeline_watcher.py` 的 `_resolve_base_path` 自动修正逻辑（🟡 中）

当前 `pipeline_watcher.py` 有一个自动修正逻辑（line 300+）：如果 `base_path` 下没有状态文件，尝试 `base_path / "blackboard/"`。这个逻辑是为 Ship Pro 套娃设计的。新结构下去套娃后，这个自动修正逻辑可能误判。

**缓解**：Step 5 改 `pipeline_watcher.py` 时，明确标记新旧两种 base_path 格式，自动修正逻辑只针对旧格式生效。

#### 风险 4：`research_pro/__init__.py` 的状态文件清理逻辑（🟡 中）

`research_pro/__init__.py` line 299 有 `for old_file in [".completed", ".cron_run_count", ".notified_stages.json"]` 的清理逻辑。如果状态文件移到 `state/` 子目录，清理逻辑也要改。但 Research Pro 独立存放，不在 `projects/` 下，需要单独处理。

**缓解**：Research Pro 的改动放在 Step 6，独立验证。

#### 风险 5：测试文件中的路径硬编码（🟡 中）

`tests/integration/test_watcher_contract.py`、`tests/golden/verify_golden_case.py` 等测试文件中硬编码了 `.completed`、`.cron_run_count` 等路径。改状态文件路径后，这些测试全部需要更新。

**缓解**：先跑一遍现有测试，记录哪些 fail，作为改动基线。

#### 风险 6：降级路径的"半新半旧"状态（🟠 中低）

在改动过程中（Step 4 完成后、Step 5 未完成前），可能出现：新代码写到新路径，但 completion_handler 还没加降级逻辑 → 检查完成状态时找不到文件。

**缓解**：Step 4 和 Step 5 应该在同一个 PR 中完成，或者 Step 4 改动时同时加临时的降级逻辑。

---

## 具体建议

### 改动顺序总结

```
Step 1: path_config.py（基础层，零风险）
    ↓
Step 2: blackboard.py（路径注册表，新增 v2 方法）
    ↓
Step 3: task_builder.py + orchestrator_agent.py（prompt 路径）
    ↓
Step 4: __init__.py + start_solution_pro.py（入口，session_id 改造）
  + Step 5: completion_handler.py + pipeline_watcher.py（降级逻辑）
  ↑ 这两步必须在同一个 PR
    ↓
Step 6: run_pipeline.py + status_v2.py + coordinator.py + research_pro（独立改动）
```

### 测试策略总结

1. **先写路径解析测试**（Step 1 之前）：确保新旧路径解析正确
2. **每步改完跑现有测试**：记录 fail 数量变化
3. **Step 4+5 完成后跑集成测试**：端到端验证 Solution Pro → Ship Pro 链路
4. **最终回归**：所有现有 golden test + 新增测试全部通过

### 关键建议

1. **不要每个文件都做降级逻辑**。只在 `path_config.py` 层做一次性降级判断（根据 session_id 格式判断走新路径还是旧路径），下游文件不需要关心降级。这样降级成本从"每个文件"降到"一个文件"。

2. **`task_builder.py` 的路径注入必须从 `BlackboardManager.base_path` 获取**，不能自己拼接。这是防止 LLM worker 路径断裂的唯一保证。

3. **旧项目的 cron job 不需要特殊处理**。它们会自然消亡（完成后自动移除 cron）。如果旧项目要重跑，手动清理旧 cron 即可。

4. **状态文件移到 `state/` 子目录的收益不够大**。8 个状态文件散在根目录确实不干净，但移动它们需要改 10+ 个文件的路径引用。建议 Phase 2 不做这个改动，留到 Phase 3 统一处理。先解决 P1（版本隔离）和 P2（套娃），P3（状态文件散落）可以等。

---

*评审完成。核心结论：改动清单需扩充到 12 个文件，降级策略应在 path_config 层统一处理而非分散到每个文件，Step 4 和 Step 5 必须同 PR。*
