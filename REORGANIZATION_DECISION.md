# DeepFlow 目录整理决策方案

> 基于实际内容分析，2026-05-30 决策

---

## 一、frontend/ 独立项目方案

### 决策
**frontend/ 作为独立项目管理，不受 DeepFlow 契约约束。**

### 理由
1. 完整独立项目：React前端 + FastAPI后端 + SQLite + Webhook
2. 有自己的 node_modules、package.json、tsconfig.json
3. 有自己的6个契约（frontend_*.yaml），已形成独立契约体系
4. DeepFlow 是后端引擎，前端设计模式完全不同

### 执行方案
```
方案：移动到 DeepFlow 同级目录

当前：.deepflow/frontend/
目标：workspace/deepflow-frontend/

契约边界：
- DeepFlow 契约（DIRECTORY_STRUCTURE_CONTRACT.md）不约束 frontend
- frontend 保留自己的契约体系（cage/frontend_*.yaml）
- 共用契约：仅 .gitignore、CHANGELOG.md 格式规范
```

---

## 二、其他目录处理方案

| 目录 | 当前内容 | 决策 | 目标位置 | 理由 |
|------|---------|------|---------|------|
| **agents/** | 2个Python脚本 | 移入 core/agents/ | core/agents/ | 后端代码，属于核心层 |
| **pipelines/** | 3个YAML配置 | 移入 config/pipelines/ | config/pipelines/ | 配置文件 |
| **data/** | 5个配置文件 | 移入 config/data/ | config/data/ | 配置文件 |
| **data_sources/** | 1个YAML配置 | 移入 config/data_sources/ | config/data_sources/ | 配置文件 |
| **data_providers/** | 2个Python文件 | 移入 core/data_providers/ | core/data_providers/ | 后端代码，属于核心层 |
| **industries/** | 2个YAML配置 | 移入 config/industries/ | config/industries/ | 配置文件 |
| **reviews/** | 5个审查文档 | 移入 docs/reviews/ | docs/reviews/ | 文档 |
| **research/** | 6个分析文档 | 移入 docs/research/ | docs/research/ | 文档 |
| **audit_reports/** | 1个审计报告 | 移入 docs/audit/ | docs/audit/ | 文档 |
| **test_results/** | 24个测试结果 | 移入 tests/results/ | tests/results/ | 测试数据 |
| **reports/** | 2个报告文档 | 移入 docs/reports/ | docs/reports/ | 文档 |
| **cron/** | 1个markdown | 移入 docs/cron/ | docs/cron/ | 文档 |
| **checkpoints/** | 空目录 | 删除 | - | 无内容 |
| **state/** | 空目录 | 删除 | - | 无内容 |
| **output/** | 空目录 | 删除 | - | 无内容 |

---

## 三、契约更新方案

### 1. DIRECTORY_STRUCTURE_CONTRACT.md 更新

新增章节：
```markdown
## 第X章 独立项目

### X.1 deepflow-frontend

frontend/ 已作为独立项目移出，不受本契约约束。

位置：workspace/deepflow-frontend/
契约：保留自己的 frontend_*.yaml 契约体系

### X.2 契约边界

- DeepFlow 契约不约束 deepflow-frontend
- 共用：.gitignore、CHANGELOG.md 格式
- 独立：目录结构、代码规范、测试规范
```

### 2. 其他契约更新

整理完成后，批量更新路径引用：
- `agents/` → `core/agents/`
- `pipelines/` → `config/pipelines/`
- `data/` → `config/data/`
- 其他路径同步更新

---

## 四、执行顺序

| 阶段 | 操作 | 时间 | 风险 |
|------|------|------|------|
| **阶段0** | 删除空目录（checkpoints/state/output） | 2分钟 | 零 |
| **阶段1** | 移动 frontend/ 到 workspace/deepflow-frontend/ | 5分钟 | 低 |
| **阶段2** | 移动文档类目录（reviews/research/audit_reports/reports/cron） | 10分钟 | 低 |
| **阶段3** | 移动配置类目录（pipelines/data/data_sources/industries） | 10分钟 | 中 |
| **阶段4** | 移动代码类目录（agents/data_providers） | 10分钟 | 中 |
| **阶段5** | 移动测试数据（test_results） | 5分钟 | 低 |
| **阶段6** | 更新 DIRECTORY_STRUCTURE_CONTRACT.md | 10分钟 | 低 |
| **阶段7** | 批量更新其他契约路径 | 20分钟 | 低 |

**总计：约70分钟**

---

## 五、回滚策略

- 阶段0-2：`git mv` 可逆
- 阶段3-5：每个阶段 commit，`git reset` 回退
- 阶段6-7：纯文本修改，`git diff` 确认

---

## 六、确认项

请确认以下决策：

- [ ] frontend/ 移出为独立项目
- [ ] 空目录直接删除
- [ ] 其他目录按表格方案处理
- [ ] 执行顺序是否合理

确认后我立即开始执行。
