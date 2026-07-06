# DeepFlow 代码质量扫描报告

**扫描日期**: 2026-06-22  
**扫描范围**: `.deepflow/` 全目录（排除 `.git/`、`blackboard/`、`ARCHIVED/`）  
**扫描文件**: 205 个 Python 文件 + 22 个 Prompt Markdown 文件  

---

## 📊 总览

| 检查类别 | 发现数量 | 最高严重度 |
|:---|:---|:---|
| Python 代码质量 | 418 | P1 |
| Prompt 交叉引用 | 10 | P1 |
| 敏感信息泄露 | 9 | P0 🔴 |
| **合计** | **437** | **P0** |

### 严重度分布

| 严重度 | 数量 | 说明 |
|:---|:---|:---|
| P0 | 5 | 活跃密钥/凭证泄露（飞书 App ID + Secret） |
| P1 | 105 | 重复函数定义、硬编码路径 |
| P2 | 323 | 未使用 import、异常处理不当、过长函数 |
| P3 | 4 | 低风险信息（测试 fixture、schema 命名空间） |

---

## 🔴 一、敏感信息泄露（P0 优先修复）

**扫描范围**: 649 个文本文件（排除 `.git/`、`blackboard/`、`ARCHIVED/`、二进制文件）

### 1.1 API 密钥 / Token（P0 🔴）— 5 处

| # | 文件 | 行号 | 匹配内容（脱敏） | 说明 |
|:---|:---|:---|:---|:---|
| 1 | `core/config_loader.py` | 215 | `cli_****1ceb` | Feishu App ID 作为 `config.get_credential()` 默认值硬编码 |
| 2 | `core/config_loader.py` | 216 | `TIox****XX5g` | **Feishu App Secret** 作为默认值硬编码 |
| 3 | `frontend/backend/utils/feishu_doc.py` | 10 | `cli_****1ceb` | Feishu App ID 作为 `os.environ.get()` 默认值 |
| 4 | `frontend/backend/utils/feishu_doc.py` | 11 | `TIox****XX5g` | **Feishu App Secret** 作为 `os.environ.get()` 默认值 |
| 5 | `frontend/backend/utils/feishu_doc.py` | 12 | `ou_d****044c` | Feishu User Open ID 作为默认值 |

**风险分析**: 虽然这些凭证位于 `os.environ.get()` 或 `config.get_credential()` 的默认值位置，但它们是**真实有效的凭证**，提交到源码中意味着任何有仓库访问权限的人都能获得飞书 API 访问权限。

**修复建议**:
```python
# ❌ 当前写法（危险）:
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a917c939e1f91ceb")

# ✅ 正确写法:
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")  # 或 os.environ["FEISHU_APP_ID"]
```

### 1.2 个人信息标识（P2）— 1 处

| 文件 | 行号 | 匹配内容 |
|:---|:---|:---|
| `domains/solution_pro/SKILL.md` | 138 | `ou_d****044c`（文档模板中的 User Open ID） |

### 1.3 低风险信息（P3）— 3 处

| 文件 | 行号 | 匹配内容 | 说明 |
|:---|:---|:---|:---|
| `domains/ship_pro/schemas/ship_package_v3.schema.json` | 3 | `deepflow.local` 命名空间 | Schema $id，非真实 URL |
| `domains/ship_pro/schemas/final_result_v3.schema.json` | 3 | `deepflow.local` 命名空间 | Schema $id，非真实 URL |
| `domains/research_pro/tests/test_url_utils.py` | 38 | `http://192.168.1.1` | 测试用例中的 URL 验证 fixture |

### ✅ 未发现以下问题

- ❌ 无 `sk-*` OpenAI 风格密钥
- ❌ 无私钥 / RSA/EC 密钥
- ❌ 无数据库连接字符串凭证
- ❌ 无 GitHub/GitLab/Slack/Discord token
- ❌ 无飞书 Webhook URL（含 token）
- ❌ 无真实邮箱地址（仅 `example@email.com` 占位符）
- ❌ 无 `.env` 或 credentials 文件泄露
- ❌ 无硬编码密码

---

## 🟡 二、Python 代码质量

**扫描范围**: 183 个 Python 文件（排除 `.git/`、`blackboard/`、`ARCHIVED/`）  
**扫描工具**: Python AST 解析 + 正则匹配

### 2.1 未使用的 Import（P2）— 151 处

共 151 处 `import` 语句导入了模块/类型但在文件中未被引用。高频重灾区：

| 文件 | 数量 | 典型未使用 import |
|:---|:---|:---|
| `core/orchestrator/orchestrator_base.py` | 5 | `os`, `copy`, `asdict`, `TypeVar`, `Generic` |
| `domains/solution_pro/orchestrator_agent.py` | 6 | `os`, `glob`, `List`, `Dict`, `Any`, `Callable` |
| `domains/solution_pro/task_builder.py` | 2 | `os`, `read_prompt_with_vars` |
| `scripts/checks/` (多个文件) | 25+ | `os`, `json`, `ast`, `List`, `Tuple`, `Mock` |
| `tests/` (多个文件) | 30+ | `Path`, `json`, `time`, `subprocess`, `List`, `Dict` |
| `core/cage/` (多个文件) | 8 | `os`, `json`, `Optional`, `Tuple` |

**影响**: 增加启动时间、降低可读性、可能隐藏循环依赖。  
**修复建议**: 运行 `ruff check --select F401 --fix` 或 `autoflake --remove-all-unused-imports` 自动清理。

### 2.2 重复函数定义（P1）— 37 处

同一文件中同名函数被定义多次，后者覆盖前者：

| 文件 | 函数名 | 定义行号 | 次数 |
|:---|:---|:---|:---|
| `core/orchestrator/orchestrator_base.py` | `from_dict()` | 79, 96, 108, 123, 140 | **5次** |
| `core/orchestrator/orchestrator_base.py` | `__init__()` | 195, 300, 355, 456 | **4次** |
| `frontend/backend/routers/status_v2.py` | `get_session_stages()` | 308, 357, 414, 467, 516 | **5次** |
| `domains/research_pro/tests/test_safe_fetcher.py` | 多个 mock 方法 | 多处 | 6组重复 |
| `scripts/pipeline_watcher.py` | `__init__()` | 55, 70, 81, 116, 139 | **5次** |
| `core/quality/observability.py` | `__init__()` / `reset()` | 多处 | 3组重复 |
| `domains/research_pro/safe_fetcher.py` | `__init__()` / `connect()` | 多处 | 3+2次 |
| `core/config_loader.py` | `get_tushare_token()` / `get_gemini_api_key()` | 167/201, 177/206 | 各2次 |
| `core/cage/cage_checkpoint.py` | `to_dict()` / `from_dict()` | 43/59, 47/68 | 各2次 |
| `core/checkpoint_manager.py` | `to_dict()` / `from_dict()` | 33/52, 37/56 | 各2次 |

**影响**: 🔴 **严重** — 后面的定义覆盖前面的，可能导致运行时逻辑错误。  
**修复建议**: 审查每个重复定义，删除废弃版本，保留正确实现。

### 2.3 硬编码路径（P1）— 58 处

代码中直接拼接 `/Users/allen/.openclaw/workspace/.deepflow/...` 绝对路径：

| 文件/目录 | 数量 | 说明 |
|:---|:---|:---|
| `scripts/checks/` | 35 | 检查脚本大量硬编码项目根路径 |
| `scripts/data_collect_smic.py` | 6 | 数据采集脚本硬编码 blackboard 路径 |
| `scripts/runners/` | 3 | 运行脚本硬编码项目根路径 |
| `scripts/prompt_loader.py` | 1 | prompt 加载器硬编码路径 |
| `scripts/v3_v4_analysis.py` | 1 | 分析脚本硬编码路径 |
| `tools/deepflow_cli.py` | 1 | CLI 工具硬编码路径 |
| `frontend/backend/routers/tasks_v2.py` | 1 | 路由中硬编码路径 |

**影响**: 换机器/换用户后所有路径失效，无法移植。  
**修复建议**: 统一使用 `path_config.py` 中的 `get_project_root()` 等函数，或 `Path(__file__).parent` 相对定位。

### 2.4 异常处理不当（P2）— 132 处

#### Bare `except:` — 5 处

| 文件 | 行号 |
|:---|:---|
| `core/orchestrator/orchestrator_base.py` | 277 |
| `frontend/backend/routers/status_v2.py` | 242, 596, 634 |
| `scripts/checks/check_data_manager_v4.py` | 141 |

#### 过宽 `except Exception:` 静默吞错（无 raise 无 log）— 127 处

高频文件：

| 文件 | 数量 |
|:---|:---|
| `core/cage/cage_checkpoint.py` | 7 |
| `core/cage/cage_loader.py` | 4 |
| `core/cage/cage_validator.py` | 4 |
| `core/checkpoint_manager.py` | 3 |
| `core/orchestrator/orchestrator_base.py` | 3 |
| `frontend/backend/routers/consumer.py` | 8 |
| `scripts/checks/` (多个文件) | 35+ |
| `tests/smoke_solution_pro.py` | 8 |

**影响**: 异常被静默吞掉，导致问题难以排查，故障传播不可见。  
**修复建议**:
- Bare `except:` → `except Exception as e:` + `logger.error(...)`
- 静默 `except Exception:` → 至少添加 `logger.warning(f"...: {e}")` 或 `raise`

### 2.5 过长函数 >100 行（P2）— 40 处

| 文件 | 函数名 | 行数 |
|:---|:---|:---|
| `domains/ship_pro/test_output/gen_specifier_v312.py` | `gen_case2()` | **493** |
| `domains/ship_pro/test_output/gen_specifier_v312.py` | `gen_case3()` | 350 |
| `domains/ship_pro/test_output/gen_specifier_v312.py` | `gen_case4()` | 337 |
| `domains/spec_pro/coordinator.py` | `_collecting_phase_instructions()` | 257 |
| `domains/solution_pro/orchestrator_agent.py` | `get_all_tasks()` | 224 |
| `scripts/checks/check_orchestrator_agent.py` | `check_orchestrator_agent()` | 224 |
| `tests/unit/test_e2e_production.py` | `run_e2e_test()` | 203 |
| `tests/e2e_solution_test.py` | `_generate_mock_output()` | 175 |
| `domains/ship_pro/decomposer.py` | `_decompose_work_packages()` | 184 |
| `domains/solution_pro/frozen_spec.py` | `build_frozen_spec()` | 156 |
| `domains/ship_pro/eval/gates.py` | `gate_specifier()` | 164 |
| `domains/solution_pro/task_builder.py` | 6 个函数 >100 行 | 110-144 |
| `domains/solution_pro/harness_validator.py` | `validate_summarizer_harness_response()` | 148 |
| `domains/spec_pro/coordinator.py` | `_build_v3_round_task()` | 145 |
| `scripts/checks/check_pipeline_engine_spawn.py` | `check_pipeline_engine()` | 146 |
| `core/orchestrator/pipeline_orchestrator.py` | `run_pipeline()` | 144 |

**修复建议**: 拆分为更小的子函数，每个函数职责单一。测试输出文件可忽略。

---

## 🔵 三、Prompt 文件交叉引用

### 3.1 断裂引用（P1）— 8 处

全部位于 `prompts/system/pipeline_engine_orchestrator.md`：

| 行号 | 引用路径 | 状态 |
|:---|:---|:---|
| 36 | `/Users/allen/.openclaw/workspace/.deepflow/prompts/data_manager_agent.md` | ❌ 绝对路径错误，实际在 `system/data_manager_agent.md` |
| 46 | `prompts/investment_planner.md` | ❌ 文件不存在 |
| 50 | `prompts/investment_researcher_finance.md` | ❌ 文件不存在 |
| 51 | `prompts/investment_researcher_tech.md` | ❌ 文件不存在 |
| 52 | `prompts/investment_researcher_market.md` | ❌ 文件不存在 |
| 53 | `prompts/investment_researcher_macro_chain.md` | ❌ 文件不存在 |
| 54 | `prompts/investment_researcher_management.md` | ❌ 文件不存在 |
| 55 | `prompts/investment_researcher_sentiment.md` | ❌ 文件不存在 |

**修复建议**:
1. 行 36：改为相对路径 `system/data_manager_agent.md`
2. 行 46-55：创建投资分析域 prompt 文件，或移除占位引用

### 3.2 孤立 Prompt 文件（信息性）— 3 处

| 文件 | 说明 |
|:---|:---|
| `system/deepflow_navigator.md` | 独立入口/引导文件 |
| `system/report_extractor.md` | 独立研究报告解析器 |
| `system/pipeline_engine_orchestrator.md` | 顶层编排器（预期孤立） |

### 3.3 YAML Frontmatter ✅

所有 22 个 prompt 文件的 `version` 和 `component` 字段一致，无冲突。

### 3.4 过时引用 ✅

未发现对 `_v2`、`_v3`、`_deprecated`、`pipeline_orchestrator_v6.md` 等过时文件的引用。

---

## 📋 修复优先级

### 🔴 P0 — 立即修复（今天）

| # | 问题 | 涉及文件 | 工作量 |
|:---|:---|:---|:---|
| 1 | Feishu App ID + Secret 硬编码（5处） | `core/config_loader.py`, `frontend/backend/utils/feishu_doc.py` | 0.5h |

### 🟡 P1 — 尽快修复（本周内）

| # | 问题 | 数量 | 涉及文件 | 工作量 |
|:---|:---|:---|:---|:---|
| 2 | 重复函数定义 | 37处 | `orchestrator_base.py`, `status_v2.py`, `pipeline_watcher.py` 等 | 2h |
| 3 | 硬编码绝对路径 | 58处 | `scripts/checks/`, `scripts/runners/`, `tools/` | 2h |
| 4 | 断裂的 prompt 引用 | 8处 | `prompts/system/pipeline_engine_orchestrator.md` | 0.5h |

### 🟢 P2 — 计划修复（下周）

| # | 问题 | 数量 | 工作量 |
|:---|:---|:---|:---|
| 5 | 未使用的 import | 151处 | 0.5h（`ruff --fix` 自动清理） |
| 6 | 异常处理不当 | 132处 | 4h |
| 7 | 过长函数 | 40处 | 6h |

### ⚪ P3 — 低优先级

| # | 问题 | 数量 | 工作量 |
|:---|:---|:---|:---|
| 8 | 文档模板中的 User Open ID | 1处 | 5min |
| 9 | Schema 命名空间 / 测试 fixture | 3处 | 无需修复 |

---

## 📈 质量评估

| 维度 | 评分 | 说明 |
|:---|:---|:---|
| 安全性 | 🔴 4/10 | 飞书 App Secret 硬编码在源码中，需立即移除 |
| 代码正确性 | 🔴 4/10 | 37 处重复函数定义，后者覆盖前者，运行时行为不可预测 |
| 异常处理 | ⚠️ 5/10 | 132 处静默吞错，严重影响可观测性和故障排查 |
| 可移植性 | ⚠️ 5/10 | 58 处硬编码绝对路径，换环境即失效 |
| 代码整洁度 | ⚠️ 6/10 | 151 处未使用 import，40 处过长函数 |
| 配置管理 | ✅ 7/10 | path_config.py 体系存在但未被广泛采用 |
| Prompt 管理 | ✅ 8/10 | YAML 一致性好，8 处断裂引用需修复 |

**综合评分**: 4.7/10 — 需要立即关注凭证安全和重复定义问题。

---

*报告生成时间: 2026-06-22 02:15 GMT+8*  
*扫描范围: 183 Python 文件 + 22 Prompt 文件 + 649 文本文件（敏感信息扫描）*  
*扫描工具: Python AST 解析 + grep regex + 手动验证*
