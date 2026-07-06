# DeepFlow 代码健康度分类报告

**日期**: 2026-06-23  
**基于**: `code_health_scan_2026-06-23.md`  
**原则**: 绝对不改任何源码，只分类和规划

---

## FIX 清单（R2 执行）

### P0 - Bare Except

| 文件 | 行号 | 当前代码 | 修复方案 |
|:---|:---:|:---|:---|
| `core/orchestrator/orchestrator_base.py` | 277 | `except:` (在 `_load_with_fallback` 中，fallback 读取) | → `except Exception as e:` + `logger.debug()` |
| `frontend/backend/routers/status_v2.py` | 242 | `except: return 0` (浮点转换) | → `except (ValueError, TypeError): return 0` |
| `frontend/backend/routers/status_v2.py` | 596 | `except:` (subprocess.run 获取版本) | → `except (subprocess.SubprocessError, OSError):` |
| `frontend/backend/routers/status_v2.py` | 634 | `except:` (subprocess.run 获取版本，与596重复) | → `except (subprocess.SubprocessError, OSError):` |
| `scripts/checks/check_data_manager_v4.py` | 141 | `except:` (JSON 解析检查) | → `except (json.JSONDecodeError, OSError):` |

### P0 - 硬编码路径（核心模块 4 处）

| 文件 | 行号 | 当前代码 | 修复方案 |
|:---|:---:|:---|:---|
| `tools/deepflow_cli.py` | 21 | `DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"` | → `Path(__file__).resolve().parent.parent` |
| `frontend/backend/routers/tasks_v2.py` | 89 | `sys.path.insert(0, '/Users/allen/...')` (消息文本中) | → 使用 `DEEPFLOW_BASE` 环境变量或动态拼接 |
| `frontend/backend/routers/consumer.py` | 211 | `cd /Users/allen/...` (消息文本中) | → 使用 `DEEPFLOW_BASE` 环境变量或动态拼接 |
| `src/deepflow/diagnostics/fallback_extractor.py` | 79 | `Path("/Users/allen/.openclaw/workspace/.deepflow")` (默认路径) | → 删除此行（已有 `Path.home()` 动态路径在上方） |

### P0 - 硬编码路径（脚本 10 处）

| 文件 | 行号 | 当前代码 | 修复方案 |
|:---|:---:|:---|:---|
| `scripts/runners/run_solution_task.py` | 9 | `DEEPFLOW_BASE = "/Users/allen/..."` | → `os.environ.get("DEEPFLOW_BASE", str(Path(__file__).resolve().parent.parent))` |
| `scripts/data_collect_smic.py` | 29,42,102,126,207 | 5 处硬编码 blackboard 路径 | → 使用 `DEEPFLOW_BASE` 环境变量 + `Path` 拼接 |
| `scripts/v3_v4_analysis.py` | 11 | `WORKSPACE = Path("/Users/allen/...")` | → `Path.home() / ".openclaw" / "workspace"` |
| `scripts/prompt_loader.py` | 15 | `self.base_path = Path(f"/Users/allen/...")` | → `Path(__file__).resolve().parent.parent` |
| `scripts/checks/check_orchestrator_v4.py` | 14,117 | 2 处硬编码 `orchestrator_agent.py` 路径 | → 使用 `DEEPFLOW_BASE` 环境变量 |

### P1 - 吞异常（except + pass，关键路径 12 处）

| 文件 | 行号 | 当前代码 | 修复方案 |
|:---|:---:|:---|:---|
| `core/blackboard/blackboard_manager.py` | 144 | `except Exception:` + `pass` (在 `write_stage` 中) | → 添加 `logger.warning(f"write_stage failed: {e}")` |
| `core/blackboard/blackboard_manager.py` | 317 | `except Exception:` + `pass` (在 `copy_stage` 中) | → 添加 `logger.warning(f"copy_stage failed: {e}")` |
| `core/blackboard/blackboard_manager.py` | 408 | `except OSError:` + `pass` (在 `write` 中) | → 添加 `logger.warning(f"write failed: {e}")` |
| `core/blackboard/blackboard_manager.py` | 488 | `except OSError:` + `pass` (在 `_write_json` 中) | → 添加 `logger.warning(f"_write_json failed: {e}")` |
| `core/orchestrator/orchestrator_base.py` | 252 | `except Exception:` + `pass` (在 `load_reference` 中) | → 添加 `logger.debug(f"load_reference failed: {e}")` |
| `core/prompt_registry.py` | 273 | `except Exception:` + `pass` (在 `read_prompt` 中) | → 添加 `logger.debug(f"read_prompt failed: {e}")` |
| `core/prompt_utils.py` | 54 | `except Exception:` + `pass` (在 `read_prompt` 中) | → 添加 `logger.debug(f"read_prompt failed: {e}")` |
| `core/prompt_utils.py` | 85 | `except Exception:` + `pass` (在 `read_prompt_with_meta` 中) | → 添加 `logger.debug(f"read_prompt_with_meta failed: {e}")` |
| `domains/research_pro/__init__.py` | 305 | `except Exception:` + `pass` (在 `run_research_pro` 中) | → 添加 `logger.error(f"research_pro failed: {e}")` |
| `domains/spec_pro/merge_spec.py` | 406 | `except Exception:` + `pass` (在 `merge_spec_v6` 中) | → 添加 `logger.warning(f"merge_spec_v6 failed: {e}")` |
| `domains/spec_pro/merge_spec.py` | 473 | `except Exception:` + `pass` (在 `merge_spec` 中) | → 添加 `logger.warning(f"merge_spec failed: {e}")` |
| `frontend/backend/routers/consumer.py` | 184 | `except Exception:` + `pass` (在 `_spawn_deepflow_task` 中) | → 添加 `logger.warning(f"spawn task failed: {e}")` |

### P1 - 硬编码 blackboard 路径（核心模块 2 处）

| 文件 | 行号 | 当前代码 | 修复方案 |
|:---|:---:|:---|:---|
| `domains/ship_pro/scripts/e2e_common.py` | 69,74,79 | `"~/.openclaw/workspace/.deepflow/blackboard/..."` (3 处示例输入) | → 使用 `PathConfig` 或 `Path.home()` 动态拼接 |

---

## SKIP 清单（不修，附原因）

### SKIP-DEAD（死代码/已废弃）

| 文件 | 行号 | 原因 |
|:---|:---:|:---|
| `domains/ship_pro/test_output/gen_specifier_v312.py` | 7 | 测试输出目录中的生成脚本，非运行时代码 |
| `domains/ship_pro/test_output/generate_specifier_v313.py` | 14 | 测试输出目录中的生成脚本，非运行时代码 |
| `domains/ship_pro/test_output/v316_req_verify/blackboard/gen_blueprint.py` | 528 | 测试输出目录中的生成文件 |
| `blackboard/gen_blueprint.py` | 528 | blackboard 目录下的生成产物，非源码 |
| `scripts/checks/check_orchestrator_v2.py` | 13,82 | v2 版本检查脚本，已被 v4 替代，无引用 |
| `core/blackboard/blackboard_bridge.py` | 全文件 | `BlackboardBridge` 类无任何外部引用（仅 `check_frontend_completion.py` 字符串提及），已被 `BlackboardManager` 替代 |
| `core/agents/cron_task_checker.py` | 38-184 | 内部函数 `_format_timestamp`, `_is_task_stale`, `_mark_stale_tasks_as_failed`, `_retry_webhook_notification`, `_process_failed_webhooks`, `_generate_summary` 无外部调用者 |
| `domains/solution_pro/eval/propagation_checker.py` | 101 | 硬编码路径在 `print()` 使用示例中，非运行逻辑 |
| `src/deepflow/diagnostics/validation.py` | 69 | 硬编码路径在文档注释中，非代码 |
| `scripts/start_solution_pro.py` | 9,33 | 硬编码路径在 docstring/注释中，非运行逻辑 |

### SKIP-TEST（测试/check 脚本中的合理用法）

| 文件 | 行号 | 原因 |
|:---|:---:|:---|
| `scripts/checks/check_path_fix.py` | 31-109 (11处) | 检查脚本，功能就是检测任务字符串中是否包含硬编码路径，路径是匹配模式 |
| `scripts/checks/check_task_enhancement.py` | 49-104 | 测试 fixture 的 setup/teardown，创建临时目录后删除 |
| `scripts/checks/check_p0_fix.py` | 23-122 (5处) | 验证脚本，检查特定文件是否存在 |
| `scripts/checks/check_p0_p1_fix.py` | 15-65 (4处) | 验证脚本，检查特定文件是否存在 |
| `scripts/checks/check_prompt_refactor.py` | 19,196 | 验证脚本，检查特定配置文件 |
| `scripts/checks/check_data_manager_v4.py` | 18,233 | 验证脚本，检查特定 blackboard 数据 |
| `scripts/checks/check_worker_completion.py` | 39,170 | 验证脚本，检查特定 session 数据 |
| `scripts/checks/check_orchestrator_agent.py` | 77 | 字符串字面量（violation message），不是实际 bare except |

### SKIP（注释/docstring/示例中的路径，非代码）

| 文件 | 行号 | 原因 |
|:---|:---:|:---|
| `scripts/start_solution_pro.py` | 9 | docstring 中的使用示例 |
| `scripts/start_solution_pro.py` | 33 | 注释（已提示应使用 `os.path.expanduser`） |
| `domains/ship_pro/scripts/e2e_common.py` | 69,74,79 | 示例输入数据中的路径（`~/.openclaw/...` 形式，已有 `~` 展开） |
| `domains/solution_pro/eval/test_v6_improvements.py` | 175 | print 示例中的路径 |

---

## DEFER 清单（值得修但需更大重构）

### P1 - except Exception 宽泛捕获（94 处，非 pass）

**说明**: 这些 `except Exception as e:` 至少记录了错误（非静默吞掉），但异常类型过于宽泛。逐个细化需要理解每个上下文的业务语义，建议按模块分批进行。

**TOP 5 重灾区（建议优先细化）**:

| 文件 | 数量 | 建议细化方向 |
|:---|:---:|:---|
| `core/cage/cage_checkpoint.py` | 7 | → `FileNotFoundError`, `json.JSONDecodeError`, `PermissionError` |
| `core/blackboard/blackboard_manager.py` | 8 | → IO/JSON 相关具体异常 |
| `core/orchestrator/orchestrator_base.py` | 4 | → `TimeoutError`, `RuntimeError`, `ValueError` |
| `frontend/backend/routers/consumer.py` | 9 | → `HTTPException`, `ValidationError` |
| `domains/spec_pro/merge_spec.py` | 4 | → `json.JSONDecodeError`, `FileNotFoundError` |

**完整分布（94 处）**:
- `core/` 模块: ~25 处
- `domains/` 模块: ~30 处
- `frontend/` 模块: ~15 处
- `scripts/` 模块: ~15 处
- `projects/` 模块: ~9 处

### P1 - except + pass（已有具体异常类型，非关键路径 20+ 处）

**说明**: 这些 except 块已使用具体异常类型（如 `JSONDecodeError`, `OSError`），`pass` 是合理的优雅降级（如读取可选数据文件失败时静默跳过）。建议统一添加 `logger.debug()` 但不紧急。

| 文件 | 行号 | 异常类型 | 原因 |
|:---|:---:|:---|:---|
| `core/config/path_config.py` | 176 | `FileNotFoundError` | 路径验证，已有具体类型 |
| `core/config/path_config.py` | 288 | `OSError, FileNotFoundError` | 缓存清理，已有具体类型 |
| `core/agents/webhook_task_processor.py` | 47 | `ImportError` | 可选依赖导入，合理降级 |
| `core/orchestrator/pipeline_orchestrator.py` | 614 | `JSONDecodeError, OSError` | worker 等待，已有具体类型 |
| `domains/solution_pro/progress_tracker.py` | 75 | `ImportError, FileNotFoundError, ...` | 进度追踪，已有具体类型 |
| `domains/solution_pro/task_builder.py` | 1006 | `FileNotFoundError` | fixer 审计，已有具体类型 |
| `domains/spec_pro/models.py` | 26 | `Exception` | 版本读取，非关键 |
| `domains/spec_pro/utils.py` | 84,107,143,200 | `JSONDecodeError, OSError` | 数据读取优雅降级 |
| `domains/spec_pro/worker_fallback.py` | 122,138 | `JSONDecodeError, OSError` | 数据追加优雅降级 |
| `domains/spec_pro/process_guard.py` | 114 | `JSONDecodeError, OSError` | 进程守卫 |
| `domains/spec_pro/update_conversation_log.py` | 54,63 | `FileNotFoundError, JSONDecodeError` | 日志更新 |
| `domains/research_pro/source_registry.py` | 172 | `OSError` | 注册表备份 |
| `frontend/backend/routers/status.py` | 106 | `Exception` | 只读列表 |
| `frontend/backend/routers/status_v2.py` | 289 | `JSONDecodeError, IOError` | 已有具体类型 |
| `frontend/backend/routers/upload.py` | 47 | `OSError` | 清理旧上传 |
| `projects/resumefit/src/ocr_helper.py` | 117,123 | `ImportError` | 可选 OCR 依赖 |
| `scripts/e2e_monitor.py` | 207,428 | `Exception` / 具体 | 监控脚本 |
| `scripts/migrate_version_headers.py` | 124,211,256 | `Exception` | 迁移脚本 |
| `src/deepflow/events/emitter.py` | 148 | `queue.Empty` | 队列空是正常情况 |
| `src/deepflow/events/writer_thread.py` | 210,310,346 | `Empty` / `Exception` | 写入线程 |
| `src/deepflow/diagnostics/validation.py` | 258,551 | 具体类型 | 诊断验证 |
| `scripts/pipeline_watcher.py` | 20 | `ValueError, TypeError` | 已有具体类型 |

### P1 - 函数过长 >100 行（36 个）

**全部标记为 DEFER**。拆分函数是重构任务，不是 bug 修复，需要单独任务逐个处理。

**TOP 10（建议优先拆分）**:

| 函数 | 文件 | 行数 |
|:---|:---|:---:|
| `_collecting_phase_instructions` | `domains/spec_pro/coordinator.py:977` | 263 |
| `check_orchestrator_agent` | `scripts/checks/check_orchestrator_agent.py:28` | 224 |
| `get_all_tasks` | `domains/solution_pro/orchestrator_agent.py:307` | 220 |
| `_decompose_work_packages` | `domains/ship_pro/decomposer.py:238` | 184 |
| `process_resume` | `projects/resumefit/src/engine.py:34` | 176 |
| `gate_specifier` | `domains/ship_pro/eval/gates.py:325` | 164 |
| `build_frozen_spec` | `domains/solution_pro/frozen_spec.py:59` | 156 |
| `validate_summarizer_harness_response` | `domains/solution_pro/harness_validator.py:22` | 148 |
| `_build_v3_round_task` | `domains/spec_pro/coordinator.py:617` | 147 |
| `check_pipeline_engine` | `scripts/checks/check_pipeline_engine_spawn.py:28` | 146 |

**其余 26 个 >100 行函数**: 见扫描报告完整列表。

---

## 统计

| 分类 | 数量 | 说明 |
|:---|:---:|:---|
| **FIX** | **23 处** | R2 执行修复 |
| ├─ P0 Bare Except | 5 | 改为具体异常类型 + logging |
| ├─ P0 硬编码路径（核心模块） | 4 | 替换为动态路径 |
| ├─ P0 硬编码路径（脚本） | 10 | 替换为环境变量/Path |
| ├─ P1 吞异常（关键路径） | 12 | 添加 logger.warning/debug |
| └─ P1 硬编码 blackboard 路径 | 2 | 替换为 PathConfig |
| **SKIP** | **~30 处** | 不修 |
| ├─ SKIP-DEAD | ~10 | 死代码/已废弃/生成产物 |
| ├─ SKIP-TEST | ~16 | 测试/check 脚本中的合理用法 |
| └─ SKIP（注释/示例） | ~4 | 非代码 |
| **DEFER** | **~270 处** | 值得修但需更大重构 |
| ├─ except Exception 宽泛捕获 | 94 | 需按模块分批细化 |
| ├─ except + pass（非关键路径） | ~20 | 已有具体类型，建议加 debug log |
| ├─ 函数过长 | 36 | 需拆分重构 |
| └─ 其余 except Exception（非 pass） | ~120 | 低优先级 |

---

## R2 修复优先级建议

### 第一批：P0 核心模块（~1.5h）
1. 5 个 bare except → 具体异常类型
2. 4 个核心模块硬编码路径 → 动态路径

### 第二批：P1 吞异常关键路径（~1h）
3. 12 个 except+pass → 添加 logger

### 第三批：P0 脚本路径（~1h）
4. 10 个脚本硬编码路径 → 环境变量

### 第四批：P1 blackboard 路径（~0.5h）
5. 2 个 e2e_common.py 路径 → PathConfig

**R2 总预计工时: ~4h**

---

*分类时间: 2026-06-23 08:21 CST*  
*分类方法: grep + AST 分析 + 上下文人工审查*
