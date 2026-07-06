# DeepFlow 代码腐化扫描报告

**日期**: 2026-06-23  
**扫描范围**: `.deepflow/` 全量 Python 代码（排除 `tests/`, `__pycache__`, `ARCHIVED/`, `venv/`）  
**Python 文件总数**: 270

---

## 总览

| 类别 | 数量 | 严重度 |
|:---|:---:|:---:|
| Bare `except:` | 5 | 🔴 P0 |
| `except Exception` 宽泛捕获 | 94 | 🟠 P1 |
| `pass` in except block（吞异常） | 48 | 🟠 P1 |
| 函数过长（>100 行） | 36 | 🟠 P1 |
| 硬编码 `/Users/` 路径 | 54 | 🔴 P0 |
| 硬编码 `.deepflow/blackboard` 路径 | 30 | 🟠 P1 |
| 重复代码块 | 1 组 | 🟡 P2 |
| 潜在死代码 | ~50+ | 🟡 P2 |
| **合计** | **~320+** | |

---

## 一、🔴 P0 — 必须立即修复

### 1.1 Bare `except:`（5 处）

无类型限定的 bare except 会捕获 `KeyboardInterrupt`、`SystemExit` 等系统异常，导致进程无法终止。

| 文件 | 行号 | 建议 |
|:---|:---:|:---|
| `core/orchestrator/orchestrator_base.py` | 277 | → `except Exception as e:` + 日志 |
| `frontend/backend/routers/status_v2.py` | 242 | → `except (ValueError, TypeError):` |
| `frontend/backend/routers/status_v2.py` | 596 | → 明确异常类型 |
| `frontend/backend/routers/status_v2.py` | 634 | → 明确异常类型 |
| `scripts/checks/check_data_manager_v4.py` | 141 | → `except Exception as e:` + 日志 |

### 1.2 硬编码 `/Users/allen/` 路径（54 处，核心代码 ~20 处）

硬编码绝对路径导致代码在其他机器/用户下完全不可用。**核心模块中必须全部替换为动态路径**。

**核心模块（P0）**:
| 文件 | 行号 | 内容摘要 | 修复方式 |
|:---|:---:|:---|:---|
| `tools/deepflow_cli.py` | 21 | `DEEPFLOW_BASE = "/Users/allen/..."` | → `Path(__file__).resolve().parent.parent` |
| `frontend/backend/routers/tasks_v2.py` | 89 | `sys.path.insert(0, '/Users/allen/...')` | → 使用 `DEEPFLOW_BASE` 环境变量 |
| `frontend/backend/routers/consumer.py` | 211 | `cd /Users/allen/...` | → 使用 `DEEPFLOW_BASE` 环境变量 |

**脚本（P1）**: `scripts/` 下约 17 个脚本硬编码了路径，包括：
- `scripts/data_collect_smic.py`（5 处）
- `scripts/checks/check_worker_completion.py`（2 处）
- `scripts/checks/check_path_fix.py`（11 处）
- `scripts/checks/check_task_enhancement.py`（7 处）
- `scripts/checks/check_data_manager_v4.py`（2 处）
- `scripts/checks/check_p0_fix.py`（5 处）
- `scripts/checks/check_p0_p1_fix.py`（4 处）
- `scripts/checks/check_prompt_refactor.py`（2 处）
- `scripts/checks/check_orchestrator_v4.py`（2 处）
- `scripts/runners/run_solution_task.py`（1 处）

**修复方式**: 统一使用 `os.path.expanduser('~')` 或环境变量 `DEEPFLOW_BASE`。

---

## 二、🟠 P1 — 本迭代内修复

### 2.1 `except Exception` 宽泛捕获（94 处）

虽然比 bare except 好，但 `except Exception` 仍然吞掉了大量不应被捕获的异常（如 `ProgrammingError`）。

**重灾区 TOP 5**:
| 文件 | 数量 | 建议 |
|:---|:---:|:---|
| `core/cage/cage_checkpoint.py` | 7 | 分别捕获 `FileNotFoundError`, `json.JSONDecodeError`, `PermissionError` |
| `core/blackboard/blackboard_manager.py` | 8 | 分别捕获 IO/JSON 相关具体异常 |
| `core/orchestrator/orchestrator_base.py` | 4 | 区分 `TimeoutError`, `RuntimeError`, `ValueError` |
| `frontend/backend/routers/consumer.py` | 9 | HTTP handler 应区分 `HTTPException`, `ValidationError` |
| `domains/spec_pro/merge_spec.py` | 4 | 区分 `json.JSONDecodeError`, `FileNotFoundError` |

**修复模式**:
```python
# ❌ Before
except Exception as e:
    logger.warning(f"failed: {e}")

# ✅ After
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.warning(f"data issue: {e}")
except PermissionError as e:
    logger.error(f"permission denied: {e}")
    raise
```

### 2.2 `pass` in except block（48 处）

异常被完全吞掉，无任何日志/重试/传播，是排查线上问题的最大障碍。

**重灾区**:
| 文件 | 数量 |
|:---|:---:|
| `domains/spec_pro/utils.py` | 4 |
| `domains/spec_pro/merge_spec.py` | 2 |
| `core/blackboard/blackboard_manager.py` | 4 |
| `core/orchestrator/orchestrator_base.py` | 2 |
| `core/prompt_utils.py` | 3 |
| `scripts/migrate_version_headers.py` | 3 |
| `src/deepflow/events/writer_thread.py` | 3 |

**修复方式**: 至少添加 `logger.debug()` 记录异常。

### 2.3 函数过长 >100 行（36 个）

**TOP 10 超长函数**:
| 函数 | 文件 | 行数 | 建议 |
|:---|:---|:---:|:---|
| `_collecting_phase_instructions` | `domains/spec_pro/coordinator.py:977` | 263 | 拆分为子方法 |
| `check_orchestrator_agent` | `scripts/checks/check_orchestrator_agent.py:28` | 224 | 拆分为检查子步骤 |
| `get_all_tasks` | `domains/solution_pro/orchestrator_agent.py:307` | 220 | 拆分为查询+格式化 |
| `_decompose_work_packages` | `domains/ship_pro/decomposer.py:238` | 184 | 拆分为子分解逻辑 |
| `process_resume` | `projects/resumefit/src/engine.py:34` | 176 | 拆分为 pipeline 阶段 |
| `gate_specifier` | `domains/ship_pro/eval/gates.py:325` | 164 | 拆分为检查子项 |
| `build_frozen_spec` | `domains/solution_pro/frozen_spec.py:59` | 156 | 拆分为阶段方法 |
| `validate_summarizer_harness_response` | `domains/solution_pro/harness_validator.py:22` | 148 | 拆分为验证子步骤 |
| `_build_v3_round_task` | `domains/spec_pro/coordinator.py:617` | 147 | 提取模板构建逻辑 |
| `check_pipeline_engine` | `scripts/checks/check_pipeline_engine_spawn.py:28` | 146 | 拆分为检查子步骤 |

**完整列表（36 个 >100 行）**:
- `domains/solution_pro/task_builder.py`: 5 个超长函数（build_reviewer_task 144行, build_harness_final_task 142行, build_planner_task 129行, build_researcher_task 122行, build_data_collection_task 110行, build_summarizer_task 124行）
- `domains/spec_pro/coordinator.py`: 3 个（263行, 147行, 137行）
- `domains/solution_pro/orchestrator_agent.py`: 2 个（220行, 103行）
- `domains/research_pro/orchestrator.py`: 2 个（123行, 105行）
- `domains/ship_pro/eval/gates.py`: 2 个（164行, 106行）
- `projects/resumefit/src/`: 2 个（176行, 119行）

### 2.4 硬编码 `.deepflow/blackboard` 路径（30 处）

与 1.2 重叠但更具体 — 直接拼接 blackboard 子路径而非通过 `BlackboardManager` API。

**核心模块**:
- `domains/solution_pro/eval/propagation_checker.py:101`
- `domains/ship_pro/scripts/e2e_common.py:69,74,79`（使用 `~/.openclaw/...` 相对形式）
- `src/deepflow/diagnostics/validation.py:69`（文档注释中）

**修复方式**: 统一通过 `BlackboardManager.get_session_dir(session_id)` 获取路径。

---

## 三、🟡 P2 — 计划修复

### 3.1 重复代码（1 组明确重复）

| 函数 | 文件 | 行数 | 说明 |
|:---|:---|:---:|:---|
| `get_session_stages` (v1) | `frontend/backend/routers/status_v2.py:308` | 46 | 与下方版本几乎相同 |
| `get_session_stages` (v2) | `frontend/backend/routers/status_v2.py:467` | 46 | 应合并为一个函数 |

**修复**: 删除重复版本，保留一个并提取为公共方法。

### 3.2 潜在死代码（~50+ 处）

通过 AST 分析函数定义 vs 引用，以下函数/类在代码库中**仅有定义无引用**（排除动态调用、测试、__init__ 导出）：

**core/ 模块**:
| 函数/类 | 文件 | 行号 | 备注 |
|:---|:---|:---:|:---|
| `BlackboardBridge` 全部方法 | `core/blackboard/blackboard_bridge.py` | 全文件 | 可能已被 `BlackboardManager` 替代 |
| `_format_timestamp` | `core/agents/cron_task_checker.py:38` | | 仅内部使用但无调用者 |
| `_is_task_stale` | `core/agents/cron_task_checker.py:47` | | 同上 |
| `_mark_stale_tasks_as_failed` | `core/agents/cron_task_checker.py:60` | | 同上 |
| `_retry_webhook_notification` | `core/agents/cron_task_checker.py:82` | | 同上 |
| `_process_failed_webhooks` | `core/agents/cron_task_checker.py:147` | | 同上 |
| `_generate_summary` | `core/agents/cron_task_checker.py:184` | | 同上 |
| `set_spawn_fn` / `_cli_spawn_fn` | `core/agents/webhook_task_processor.py` | 30, 56 | |
| `generate_session_id` / `generate_run_id` | `core/blackboard/session_id.py` | 29, 76 | 可能被外部动态调用 |
| `retry_config` / `output_schema` / `max_concurrency` | `core/cage/cage_loader.py` | 65, 70, 103 | property 方法，可能通过属性访问 |

**scripts/ 模块**:
| 函数 | 文件 | 行号 |
|:---|:---|:---:|
| `find_all_sessions` | `blackboard_recover_all.py:15` | |
| `extract_blackboard_writes` | `blackboard_recover_all.py:30` | |

> ⚠️ 注意：AST 静态分析对动态调用（`getattr`, `importlib`, `eval`）有误报。以上列表需人工确认后再删除。

---

## 四、修复优先级建议

### 本迭代必做（P0，~25 处）
1. **5 个 bare except** → 改为具体异常类型（30 min）
2. **核心模块硬编码路径** → `tools/deepflow_cli.py`, `frontend/` 路由中 3 处（1 h）

### 本迭代计划做（P1，~210 处）
3. **48 个 pass-in-except** → 至少加 `logger.debug()`（2 h）
4. **94 个 except Exception** → 逐步细化异常类型（4 h）
5. **36 个超长函数** → 优先拆分 TOP 10（4 h）
6. **脚本硬编码路径** → 统一使用 `DEEPFLOW_BASE` 环境变量（2 h）

### 下一迭代（P2，~100 处）
7. 合并重复代码（30 min）
8. 清理确认后的死代码（2 h）

---

## 五、统计摘要

```
总问题数:          ~320+
  P0 (紧急):       ~25   (8%)
  P1 (重要):       ~210  (65%)
  P2 (改进):       ~85   (27%)

预计修复工时:      ~15 h
  P0:              ~1.5 h
  P1:              ~12 h
  P2:              ~2.5 h
```

---

*报告生成时间: 2026-06-23 08:08 CST*  
*扫描工具: grep + Python AST 分析*  
*扫描范围: .deepflow/ 全量 .py 文件（排除 tests/, __pycache__/, ARCHIVED/, venv/）*
