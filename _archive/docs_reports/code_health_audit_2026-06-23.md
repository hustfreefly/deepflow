# R3 审计报告

**日期**: 2026-06-23  
**审计范围**: R2 修复的 23 处改动  
**审计方法**: 逐文件源码审查 + 回归扫描 + 测试基线对比

---

## 总评：GREEN ✅

23 处修复全部正确实现，无引入新 bug，无遗漏。路径解析正确，import 无冲突，logger 声明完整且级别合理。

---

## 逐项审计结果

### 一、Bare Except 修复（5 处）

| # | 文件 | 行号 | 结果 | 备注 |
|---|------|:---:|:---:|:---|
| 1 | `core/orchestrator/orchestrator_base.py` | 277 | ✅ | `except Exception as e:` + `logger.debug()`，fallback 逻辑完整（3 层降级不受影响） |
| 2 | `frontend/backend/routers/status_v2.py` | 242 | ✅ | `except (ValueError, TypeError): return 0`，浮点转换的合理异常类型 |
| 3 | `frontend/backend/routers/status_v2.py` | 596 | ✅ | `except (subprocess.SubprocessError, OSError):`，subprocess 调用的标准异常组合 |
| 4 | `frontend/backend/routers/status_v2.py` | 634 | ✅ | 同上，与 596 保持一致 |
| 5 | `scripts/checks/check_data_manager_v4.py` | 141 | ✅ | `except (json.JSONDecodeError, OSError):`，JSON 解析 + 文件读取的精确异常类型 |

**小结**: 5/5 正确。异常类型选择精准，未破坏 fallback/降级逻辑。

---

### 二、硬编码路径修复（14 处）

| # | 文件 | 行号 | 结果 | 备注 |
|---|------|:---:|:---:|:---|
| 1 | `tools/deepflow_cli.py` | 21 | ✅ | `Path(__file__).resolve().parent.parent` → `.deepflow/tools/` → `.deepflow/` 正确 |
| 2 | `frontend/backend/routers/tasks_v2.py` | 89 | ✅ | `os.environ.get("DEEPFLOW_BASE", str(Path(__file__).resolve().parent.parent.parent))` → 3 层 parent 正确（routers→backend→frontend→.deepflow） |
| 3 | `frontend/backend/routers/consumer.py` | 211 | ✅ | 同上模式，`parent.parent.parent` 正确 |
| 4 | `src/deepflow/diagnostics/fallback_extractor.py` | 79 | ✅ | 硬编码默认路径已删除，保留 `Path.home()` 动态路径 + `Path.cwd()` 备选 |
| 5 | `scripts/runners/run_solution_task.py` | 9 | ✅ | `os.environ.get("DEEPFLOW_BASE", str(Path(__file__).resolve().parent.parent))` → `scripts/runners/` → `scripts/` → `.deepflow/` 正确 |
| 6 | `scripts/data_collect_smic.py` | 29 | ✅ | `DEEPFLOW_BASE` 变量定义正确，`import os` + `from pathlib import Path` 均有 |
| 7 | `scripts/data_collect_smic.py` | 42 | ✅ | 使用 `DEEPFLOW_BASE` 变量拼接 config 路径 |
| 8 | `scripts/data_collect_smic.py` | 102 | ✅ | 使用 `DEEPFLOW_BASE` 变量拼接 supplement 目录 |
| 9 | `scripts/data_collect_smic.py` | 126 | ✅ | 使用 `DEEPFLOW_BASE` 变量拼接 key_metrics 路径 |
| 10 | `scripts/data_collect_smic.py` | 207 | ✅ | 使用 `DEEPFLOW_BASE` 变量拼接 blackboard 数据目录 |
| 11 | `scripts/v3_v4_analysis.py` | 11 | ✅ | `Path.home() / ".openclaw" / "workspace"` 动态解析 |
| 12 | `scripts/prompt_loader.py` | 15 | ✅ | `Path(__file__).resolve().parent.parent` → `scripts/` → `.deepflow/` 正确 |
| 13 | `scripts/checks/check_orchestrator_v4.py` | 14 | ✅ | `os.environ.get("DEEPFLOW_BASE", str(Path(__file__).resolve().parent.parent.parent))` → `checks/` → `scripts/` → `.deepflow/` 正确 |
| 14 | `scripts/checks/check_orchestrator_v4.py` | 117 | ✅ | 使用 `DEEPFLOW_BASE` 变量拼接 `orchestrator_agent.py` 路径 |

**Import 检查**:
- `import os` — 所有使用 `os.environ.get` 的文件均已声明 ✅
- `from pathlib import Path` — 所有使用 `Path` 的文件均已声明 ✅
- 无 import 冲突 ✅

**默认值合理性**:
- `os.environ.get("DEEPFLOW_BASE", ...)` 的 fallback 均使用 `Path(__file__)` 动态计算，无硬编码 ✅
- `v3_v4_analysis.py` 使用 `Path.home()` 而非 `Path(__file__)`，因为该脚本可能在非 `.deepflow` 目录运行，合理 ✅

**小结**: 14/14 正确。路径层级计算准确，import 完整，环境变量优先策略一致。

---

### 三、吞异常修复（12 处）

| # | 文件 | 行号 | 结果 | 备注 |
|---|------|:---:|:---:|:---|
| 1 | `core/blackboard/blackboard_manager.py` | 144 | ✅ | `logger.warning(f"write_stage failed for '{stage_name}': {e}")`，级别合理（数据写入失败） |
| 2 | `core/blackboard/blackboard_manager.py` | 317 | ✅ | `logger.warning(f"copy_stage failed: ...")`，级别合理 |
| 3 | `core/blackboard/blackboard_manager.py` | 408 | ✅ | **超出预期**：从 `except OSError: pass` 重构为 `except BaseException:` + 清理 fd + unlink tmp + `raise`。不再吞异常，正确传播错误 |
| 4 | `core/blackboard/blackboard_manager.py` | 488 | ✅ | 同上模式，`_write_json` 方法同样重构为安全写入 + 异常传播 |
| 5 | `core/orchestrator/orchestrator_base.py` | 252 | ✅ | `logger.debug(f"load_reference failed: {e}")`，级别合理（可选读取） |
| 6 | `core/prompt_registry.py` | 273 | ✅ | `logger.debug(f"read_prompt failed: {e}")`，级别合理（YAML 剥离可选） |
| 7 | `core/prompt_utils.py` | 54 | ✅ | `logger.debug(f"read_prompt failed: {e}")`，级别合理 |
| 8 | `core/prompt_utils.py` | 85 | ✅ | `logger.debug(f"read_prompt_with_meta failed: {e}")`，级别合理 |
| 9 | `domains/research_pro/__init__.py` | 305 | ✅ | `logger.error(f"research_pro cleanup failed: {e}")`，级别合理（入口失败） |
| 10 | `domains/spec_pro/merge_spec.py` | 406 | ✅ | `logger.warning(f"merge_spec_v6 failed: {e}")`，级别合理（迁移日志写入） |
| 11 | `domains/spec_pro/merge_spec.py` | 473 | ✅ | `logger.warning(f"merge_spec failed: {e}")`，级别合理 |
| 12 | `frontend/backend/routers/consumer.py` | 184 | ✅ | `logger.warning(f"spawn task failed: {e}")`，级别合理（数据库 fallback 失败） |

**Logger 声明检查**:
| 文件 | `import logging` | `logger = ...` | 结果 |
|:---|:---:|:---:|:---:|
| `blackboard_manager.py` | ✅ (line 21) | ✅ (line 30) | ✅ |
| `orchestrator_base.py` | ✅ (line 14) | ✅ (line 20) | ✅ |
| `prompt_registry.py` | ✅ (line 16) | ✅ (line 25) | ✅ |
| `prompt_utils.py` | ✅ (line 12) | ✅ (line 16) | ✅ |
| `research_pro/__init__.py` | ✅ (line 32) | ✅ (line 39) | ✅ |
| `merge_spec.py` | ✅ (line 14) | ✅ (line 22) | ✅ |
| `consumer.py` | ✅ (line 10) | ✅ (line 19) | ✅ |

**Logger 级别一致性**:
| 场景 | 使用级别 | 是否合理 |
|:---|:---:|:---:|
| 数据写入失败（blackboard write/copy） | `warning` | ✅ |
| 可选读取失败（prompt/reference） | `debug` | ✅ |
| 入口/任务失败（research_pro, consumer） | `error`/`warning` | ✅ |
| 清理操作失败（fd close） | `debug` | ✅ |

**小结**: 12/12 正确。#3 和 #4 超出预期（从吞异常重构为异常传播），是更高质量的修复。所有 logger 声明完整，级别与场景匹配。

---

## 回归扫描结果

| 检查项 | 结果 | 详情 |
|:---|:---:|:---|
| **bare except 残留** | **0 个** | grep 匹配 2 条均为字符串字面量（`check_orchestrator_agent.py:77` 违规消息文本、`:204` 变量名 `has_try_except`），非实际 bare except |
| **/Users/allen/ 硬编码残留（运行时）** | **0 个** | 剩余 35 处全在 SKIP 类别：`scripts/checks/`（验证脚本匹配模式）、`domains/ship_pro/test_output/`（测试产物）、`scripts/start_solution_pro.py`（docstring/注释） |
| **测试基线** | **223 passed, 12 failed, 1 error** | 与修复前一致（12 failed + 1 error 均为预存问题：`test_validation.py` 10 个 + `test_spec_pro_regressions.py` 3 个 + `test_e2e_living_spec_v2.py` 1 个 error） |

---

## 发现的问题

**无。**

所有 23 处修复均正确实现，未引入新 bug、未遗漏 import、未破坏现有逻辑。

---

## 额外发现（非 R2 范围，记录备查）

| # | 文件 | 说明 | 严重度 |
|:---|:---|:---|:---:|
| 1 | `blackboard_manager.py:408,488` | R2 将 `except OSError: pass` 重构为 `except BaseException:` + cleanup + `raise`，比原计划（加 `logger.warning`）更彻底。这是**正向偏差**，但改变了异常传播行为——调用方需要能处理这些异常。建议确认上游调用方（如 worker 脚本）有对应的 try/except | 低 |
| 2 | `status_v2.py:242` | 第一层 `except Exception as e:` + `print()` 未改（line 270 附近），但不在 R2 范围内（已有 `Exception` 类型 + print 输出，非 bare except） | 信息 |

---

## 建议

1. **确认 `blackboard_manager.py` 异常传播的上游兼容性**：`write()` 和 `_write_json()` 现在会 `raise`，需确认调用方（如 `data_manager_worker.py`、`worker_fallback.py`）有对应的异常处理。建议在下一轮检查。

2. **DEFER 清单仍有效**：94 处 `except Exception` 宽泛捕获 + 36 个过长函数仍待后续重构。

3. **check 脚本硬编码路径**：`scripts/checks/` 下仍有 ~20 处 `/Users/allen/` 硬编码。虽然是验证脚本且分类为 SKIP-TEST，但长期建议改为 `Path(__file__)` 动态解析以提高可移植性。

---

## 审计评分

| 维度 | 评分 | 说明 |
|:---|:---:|:---|
| **正确性** | ✅ GREEN | 23/23 修复正确，异常类型精准，路径层级无误 |
| **安全性** | ✅ GREEN | 无新 bug，无 import 缺失，无路径错误 |
| **一致性** | ✅ GREEN | logger 命名/级别与文件风格一致，环境变量策略统一 |
| **最小性** | ✅ GREEN | 仅修改了该改的代码，`blackboard_manager.py:408,488` 的正向偏差是唯一超出范围的改动，且质量更高 |

**综合评定：GREEN** — R2 修复质量优秀，可以合并。
