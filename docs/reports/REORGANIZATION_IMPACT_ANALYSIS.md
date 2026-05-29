# 目录移动影响分析报告

> 生成时间：2026-05-30 00:15

---

## 高风险目录（移动会破坏功能）

### 1. agents/ - 🔴 高风险

**引用情况：**
- ✅ **硬编码引用**（动态生成 Python 代码）：
  - `frontend/backend/routers/tasks_v2.py:213` - 生成 webhook 任务时硬编码 `from core.agents.webhook_task_processor`
  - `frontend/backend/routers/consumer.py:74` - 生成 consumer 任务时硬编码 `from core.agents.webhook_task_processor`
  
- ✅ **Python import**：
  - `tests/test_e2e_webhook.py` - 测试文件 import
  - `cage/check_wh003.py` - 契约检查脚本 import
  
- ✅ **契约引用**：
  - `cage/frontend_phase4_cron_v1.0.yaml` - 多处路径引用
  - `cage/frontend_webhook_fix_v1.0.yaml` - 多处路径引用
  - `cage/frontend_webhook_integration_v1.0.yaml` - 多处路径引用

**影响评估：**
- 移动会破坏 webhook 任务执行
- 移动会破坏 consumer 任务执行
- 移动会破坏测试用例
- **需要更新至少 5 个文件**

**建议：**
```
方案A（推荐）：保留 agents/ 位置，加入契约白名单
方案B：移动到 core/agents/，但需要：
  1. 更新 frontend/backend/routers/tasks_v2.py 的硬编码路径
  2. 更新 frontend/backend/routers/consumer.py 的硬编码路径
  3. 更新所有 import 语句
  4. 更新所有契约文件路径
  5. 运行完整测试套件验证
```

---

### 2. data_providers/ - 🔴 高风险

**引用情况：**
- ✅ **Python import**（核心业务逻辑）：
  - `domains/investment/__init__.py` - 多次 import `from core.data_providers.investment import register_providers`
  - `core/data_manager_worker.py` - import `from core.data_providers.investment import register_providers`
  - `scripts/data_collect_smic.py` - import `from core.data_providers.investment import register_providers`
  - `ARCHIVED/v1.0_legacy/orchestrator_agent.py` - import（历史代码）
  - `core/core/core/data_providers/investment.py` 内部 import `from core.data_providers.tushare_provider import TushareProvider`

**影响评估：**
- 移动会破坏 investment 域的数据提供者注册
- 移动会破坏 data_manager 的数据采集功能
- 移动会破坏测试脚本
- **需要更新至少 4 个核心文件**

**建议：**
```
方案A（推荐）：保留 data_providers/ 位置，加入契约白名单
方案B：移动到 core/data_providers/，但需要：
  1. 更新 domains/investment/__init__.py 的所有 import
  2. 更新 core/data_manager_worker.py 的 import
  3. 更新 data_providers/ 内部的相对 import
  4. 更新所有测试脚本
  5. 运行投资域完整测试验证
```

---

### 3. data_sources/ - 🟡 中等风险

**引用情况：**
- ✅ **配置引用**：
  - `domains/investment.yaml` - `config: "config/config/config/data_sources/investment.yaml"`
  - `domains/investment/__init__.py` - 多处文档引用 `config/config/config/data_sources/investment.yaml`
  - `domains/investment/CHANGES.md` - 文档引用

**影响评估：**
- 移动会破坏 investment 域的配置加载
- **需要更新至少 1 个配置文件**

**建议：**
```
方案A（推荐）：保留 data_sources/ 位置，加入契约白名单
方案B：移动到 config/data_sources/，但需要：
  1. 更新 domains/investment.yaml 的 config 路径
  2. 更新相关文档
  3. 运行 investment 域测试验证
```

---

## 低风险目录（移动安全）

### 4. pipelines/ - 🟢 低风险

**引用情况：**
- 只有研究文档和计划文档引用
- **没有代码 import**
- **没有配置文件引用**

**建议：**
```
可以安全移动到 config/pipelines/
无需更新任何代码
```

---

### 5. industries/ - 🟢 低风险

**引用情况：**
- 只有文档引用
- **没有代码 import**
- **没有配置文件引用**

**建议：**
```
可以安全移动到 config/industries/
无需更新任何代码
```

---

### 6. data/ - 🟢 低风险

**引用情况：**
- `core/search_engine.py` 提到 `config/data/search_config.yaml`，但这是注释
- **没有硬编码路径**

**建议：**
```
可以安全移动到 config/data/
无需更新任何代码
```

---

### 7. 文档类目录 - 🟢 零风险

**目录列表：**
- `docs/reviews/` - 审查文档
- `docs/research/` - 研究文档
- `docs/audit_reports/` - 审计报告
- `docs/reports/` - 报告文档
- `docs/cron/` - cron 配置文档

**建议：**
```
可以安全移动到 docs/ 下
无需更新任何代码
```

---

### 8. 测试数据目录 - 🟢 低风险

**目录列表：**
- `tests/results/` - 测试结果数据

**建议：**
```
可以安全移动到 tests/results/
可能需要更新测试脚本路径
```

---

### 9. 空目录 - 🟢 零风险

**目录列表：**
- `blackboard/checkpoints/` - 空
- `blackboard/state/` - 空
- `blackboard/output/` - 空

**建议：**
```
直接删除
```

---

## 总结与建议

### 高风险目录（agents/, data_providers/）

**强烈推荐：保留位置，加入契约白名单**

理由：
1. 移动会破坏核心功能
2. 需要更新大量代码
3. 风险收益比不合理
4. 这些目录位置合理，不影响整体架构

**契约更新方案：**
```markdown
## 第X章 白名单目录

以下目录虽不在标准结构中，但因历史原因和功能需要，保留在根目录：

| 目录 | 用途 | 保留理由 |
|------|------|----------|
| agents/ | Webhook 任务处理器 | 被前端代码硬编码引用，移动会破坏功能 |
| data_providers/ | 数据提供者实现 | 被核心代码多处 import，移动风险高 |
```

---

### 中等风险目录（data_sources/）

**推荐：保留位置，加入契约白名单**

理由：
1. 移动需要更新配置路径
2. 当前位置清晰直观
3. 风险可控

---

### 低风险目录（pipelines/, industries/, data/, 文档类, 测试类）

**推荐：按原计划移动**

理由：
1. 移动安全
2. 符合契约规范
3. 不影响功能

---

## 修订后的执行计划

### 阶段 0：删除空目录（2分钟，零风险）
- 删除 `blackboard/checkpoints/`、`blackboard/state/`、`blackboard/output/`

### 阶段 1：移动低风险目录（15分钟，零风险）
- 移动 `config/pipelines/` → `config/pipelines/`
- 移动 `config/industries/` → `config/industries/`
- 移动 `config/data/` → `config/data/`
- 移动文档类目录到 `docs/`
- 移动 `tests/results/` → `tests/results/`

### 阶段 2：更新契约（10分钟）
- 在契约中添加"白名单目录"章节
- 说明 agents/、data_providers/、data_sources/ 保留在根目录的理由

### 阶段 3：批量更新路径引用（如需要，20分钟）
- 仅当决定移动中等风险目录时执行
- 更新所有受影响的代码和配置

---

## 最终建议

**采用保守方案：**

✅ **移动**：所有低风险目录（阶段 1）
❌ **保留**：agents/、data_providers/、data_sources/（加入白名单）
✅ **删除**：空目录（阶段 0）

**理由：**
1. 降低风险：避免破坏核心功能
2. 提高效率：减少 70% 的代码修改工作量
3. 保持灵活性：白名单机制允许未来需要时再移动
4. 符合实际：这些目录位置合理，不影响整体架构

**预计工作量：30分钟（原计划 70分钟）**
