# 深度清理方案（Phase 3）

## 扫描发现的主要问题

### 问题1：根目录存在大量V3时代遗留文件（🔴 严重）

当前V4核心代码在 `core/` 目录，但根目录仍有15个Python文件，大部分是V3旧模块：

| 文件 | 类型 | 判断 | 原因 |
|:---|:---|:---:|:---|
| `pipeline_engine.py` | V3 PipelineEngine | 🔴 旧版 | V4已移除PipelineEngine |
| `coordinator.py` | V3 Coordinator | 🔴 旧版 | V4用Master Agent替代 |
| `config_loader.py` | V3 ConfigLoader | 🔴 旧版 | V4配置方式已变 |
| `data_manager.py` | V3 DataManager | 🔴 旧版 | V4核心在`core/data_manager_worker.py` |
| `blackboard_manager.py` | V3 BlackboardManager | 🔴 旧版 | V4核心在`core/blackboard_manager.py` |
| `quality_gate.py` | V3 QualityGate | 🔴 旧版 | V4用契约笼子替代 |
| `resilience_manager.py` | V3 ResilienceManager | 🔴 旧版 | V4未使用 |
| `observability.py` | V3 Observability | 🔴 旧版 | V4未使用 |
| `protocols.py` | V3 Protocols | 🔴 旧版 | V4用`PROTOCOLS.md`替代 |
| `data_collection_task.py` | V3 任务定义 | 🔴 旧版 | V4用Task Builder替代 |
| `init_smic.py` | 特定会话脚本 | 🟡 临时 | 中芯国际测试脚本 |
| `init_session.py` | 旧版初始化 | 🟡 临时 | 功能已合并到Master Agent |
| `check_pipeline_engine_fix.py` | 旧版检查 | 🔴 旧版 | PipelineEngine已移除 |

### 问题2：根目录存在孤立的旧版模块（🔴 严重）

这些模块在V4中完全没有被使用，但文件仍然存在：
- `domains/investment/orchestrator.py` - 旧版orchestrator
- `domains/investment/cage_orchestrator.py` - 早期实验

### 问题3：tests/ 目录内容可能过时（🟡 中）

`tests/` 下的测试用例可能是为V3编写的，需要确认是否能在V4运行。

### 问题4：config/ 目录配置过时（🟡 中）

`config/` 下的5个YAML文件是V3时代的配置，V4可能不再需要。

---

## 清理方案

### 保守方案（推荐）

**删除确认过时的文件：**
1. 根目录V3遗留文件（保留`__init__.py`和`orchestrator_agent.py`）
2. `domains/investment/orchestrator.py`（与根目录orchestrator重复）
3. `domains/investment/cage_orchestrator.py`（实验文件）

**保留待确认文件：**
- `tests/` - 需要评估是否可用
- `config/` - 需要评估是否过时

### 彻底方案

删除所有确认不用的文件，包括：
- 所有V3根目录文件
- 过时的tests/
- 过时的config/

---

## 验证计划

清理后需要验证：
1. V4核心代码能否正常导入
2. 是否有import错误（因为删除了被依赖的文件）
3. Git提交是否干净

---

## 建议

**推荐保守方案**，因为：
1. 这些V3文件确实不再使用（V4核心在core/）
2. 已创建双重备份，可以恢复
3. 清理后仓库更干净，避免混淆

**但需要先验证**：这些根目录文件是否真的没有import关系。
