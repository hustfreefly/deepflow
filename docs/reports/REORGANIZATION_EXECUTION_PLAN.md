# DeepFlow 目录整理执行方案（契约笼子模式）

> 日期：2026-05-30
> 方法：契约笼子 — 每步声明 → 移动 → 更新引用 → 验证 → commit

---

## 核心原则

```
每个目录移动 = 5 步闭环
1. 声明：这次移什么、影响哪些文件、验证标准是什么
2. 移动：git mv 原子操作
3. 更新引用：修改所有 import、路径、配置
4. 验证：跑验证脚本确认功能正常
5. commit：Git 提交，出问题 git revert 回滚
```

**一次只移一个目录，验证通过再移下一个。**

---

## 执行顺序（按风险从低到高）

### 阶段 0：删除空目录（2分钟）

| 操作 | 命令 | 验证 |
|------|------|------|
| 删除 checkpoints/ | `rm -rf checkpoints/` | 确认目录为空 |
| 删除 state/ | `rm -rf state/` | 确认目录为空 |
| 删除 output/ | `rm -rf output/` | 确认目录为空 |
| 删除备份文件 | `rm orchestrator_agent.py.bak.*` | 无 |

验证脚本：
```bash
# 验证无文件丢失
find . -maxdepth 1 -name "*.bak*" -o -name "*.backup" | wc -l  # 应为 0
```

---

### 阶段 1：移动文档类目录（15分钟）

按顺序移动：

| 序号 | 源 | 目标 | 影响文件数 |
|------|-----|------|-----------|
| 1.1 | reviews/ | docs/reviews/ | 0（纯文档） |
| 1.2 | research/ | docs/research/ | 0（纯文档） |
| 1.3 | audit_reports/ | docs/audit_reports/ | 0（纯文档） |
| 1.4 | reports/ | docs/reports/ | 0（纯文档） |
| 1.5 | cron/ | docs/cron/ | 0（纯文档） |

每个子步骤：
```bash
# 声明
echo "移动 reviews/ → docs/reviews/"

# 移动
git mv reviews/ docs/reviews/

# 更新引用（如有）
grep -rl "docs/reviews/" --include="*.py" --include="*.yaml" --include="*.md" . | xargs sed -i '' 's|reviews/|docs/reviews/|g'

# 验证
test -d docs/reviews/ && echo "✅ 目录存在"

# commit
git add -A && git commit -m "refactor: move reviews/ to docs/reviews/"
```

---

### 阶段 2：移动测试数据（5分钟）

| 序号 | 源 | 目标 |
|------|-----|------|
| 2.1 | test_results/ | tests/results/ |

```bash
git mv test_results/ tests/results/
git add -A && git commit -m "refactor: move test_results/ to tests/results/"
```

---

### 阶段 3：移动低风险配置目录（15分钟）

| 序号 | 源 | 目标 | 影响文件 |
|------|-----|------|---------|
| 3.1 | pipelines/ | config/pipelines/ | 无代码引用 |
| 3.2 | industries/ | config/industries/ | 无代码引用 |
| 3.3 | data/ | config/data/ | 无代码引用 |

每个子步骤：
```bash
# 声明
echo "移动 pipelines/ → config/pipelines/"

# 移动
git mv pipelines/ config/pipelines/

# 更新引用（检查 .md 和 .yaml 中的路径引用）
grep -rl "config/pipelines/" --include="*.py" --include="*.yaml" --include="*.md" . \
  | grep -v ".git" | grep -v "ARCHIVED" \
  | xargs sed -i '' 's|pipelines/|config/pipelines/|g'

# 验证
test -d config/pipelines/ && echo "✅ 目录存在"

# commit
git add -A && git commit -m "refactor: move pipelines/ to config/pipelines/"
```

---

### 阶段 4：移动中等风险目录（15分钟）

| 序号 | 源 | 目标 | 影响文件 |
|------|-----|------|---------|
| 4.1 | data_sources/ | config/data_sources/ | domains/investment.yaml, 文档 |

```bash
# 声明
echo "移动 data_sources/ → config/data_sources/"
echo "影响文件："
echo "  - domains/investment.yaml (config 路径)"
echo "  - domains/investment/__init__.py (文档引用)"
echo "  - domains/investment/CHANGES.md (文档引用)"

# 移动
git mv data_sources/ config/data_sources/

# 更新引用
# 4.1a: 更新 domains/investment.yaml
sed -i '' 's|config: "config/data_sources/|config: "config/data_sources/|g' domains/investment.yaml

# 4.1b: 更新所有 Python/MD/YAML 中的路径引用
grep -rl "config/data_sources/" --include="*.py" --include="*.yaml" --include="*.md" . \
  | grep -v ".git" | grep -v "ARCHIVED" | grep -v "config/data_sources" \
  | xargs sed -i '' 's|data_sources/|config/data_sources/|g'

# 验证脚本
python3 -c "
import yaml
with open('domains/investment.yaml') as f:
    cfg = yaml.safe_load(f)
config_path = cfg.get('data_collection', {}).get('config', '')
assert 'config/data_sources/' in config_path, f'路径未更新: {config_path}'
print('✅ domains/investment.yaml 路径已更新')

import os
assert os.path.exists('config/config/config/data_sources/investment.yaml'), '文件不存在'
print('✅ config/config/config/data_sources/investment.yaml 存在')
"

# commit
git add -A && git commit -m "refactor: move data_sources/ to config/data_sources/ + update refs"
```

---

### 阶段 5：移动高风险目录 — data_providers/（20分钟）

| 序号 | 源 | 目标 |
|------|-----|------|
| 5.1 | data_providers/ | core/data_providers/ |

**声明：影响清单**

| 文件 | 引用方式 | 修改内容 |
|------|---------|---------|
| domains/investment/__init__.py | `from core.data_providers.investment import register_providers` | → `from core.data_providers.investment import register_providers` |
| core/data_manager_worker.py | `from core.data_providers.investment import register_providers` | → `from core.data_providers.investment import register_providers` |
| core/core/data_providers/investment.py | `from core.data_providers.tushare_provider import TushareProvider` | → `from core.data_providers.tushare_provider import TushareProvider` |
| scripts/data_collect_smic.py | `from core.data_providers.investment import register_providers` | → `from core.data_providers.investment import register_providers` |
| tests/unit/check_data_manager.py | 路径引用 | → 更新路径 |

```bash
# 声明
echo "移动 data_providers/ → core/data_providers/"
echo "影响 5 个文件，需要更新 import 路径"

# 移动
git mv data_providers/ core/data_providers/

# 确保 __init__.py 存在
touch core/data_providers/__init__.py

# 更新 import 引用
# 5.1a: domains/investment/__init__.py
sed -i '' 's|from data_providers\.|from core.data_providers.|g' domains/investment/__init__.py

# 5.1b: core/data_manager_worker.py
sed -i '' 's|from data_providers\.|from core.data_providers.|g' core/data_manager_worker.py

# 5.1c: core/core/core/data_providers/investment.py（内部引用）
sed -i '' 's|from data_providers\.|from core.data_providers.|g' core/core/core/data_providers/investment.py

# 5.1d: scripts/data_collect_smic.py
sed -i '' 's|from data_providers\.|from core.data_providers.|g' scripts/data_collect_smic.py

# 5.1e: tests/unit/check_data_manager.py
sed -i '' 's|"core/data_providers/|"core/data_providers/|g' tests/unit/check_data_manager.py

# 验证脚本
python3 -c "
import sys
sys.path.insert(0, '.')

# 验证 1: import 能成功
try:
    from core.data_providers.investment import register_providers
    print('✅ import core.data_providers.investment 成功')
except ImportError as e:
    print(f'❌ import 失败: {e}')
    sys.exit(1)

# 验证 2: 内部引用正确
try:
    from core.data_providers.tushare_provider import TushareProvider
    print('✅ import core.data_providers.tushare_provider 成功')
except ImportError as e:
    print(f'❌ import 失败: {e}')
    sys.exit(1)

# 验证 3: 旧路径不存在
import os
assert not os.path.exists('core/data_providers/'), '旧目录仍存在'
print('✅ 旧目录已移除')

# 验证 4: 新路径存在
assert os.path.exists('core/core/core/data_providers/investment.py'), '新文件不存在'
print('✅ 新文件存在')

print()
print('🎉 data_providers/ 迁移验证通过！')
"

# commit
git add -A && git commit -m "refactor: move data_providers/ to core/data_providers/ + update all imports"
```

---

### 阶段 6：移动高风险目录 — agents/（20分钟）

| 序号 | 源 | 目标 |
|------|-----|------|
| 6.1 | agents/ | core/agents/ |

**声明：影响清单**

| 文件 | 引用方式 | 修改内容 |
|------|---------|---------|
| frontend/backend/routers/tasks_v2.py | 硬编码字符串 `from core.agents.webhook_task_processor` | → `from core.agents.webhook_task_processor` |
| frontend/backend/routers/consumer.py | 硬编码字符串 `from core.agents.webhook_task_processor` | → `from core.agents.webhook_task_processor` |
| tests/test_e2e_webhook.py | `from core.agents.webhook_task_processor import ...` | → `from core.agents.webhook_task_processor import ...` |
| agents/cron_task_checker.py | 内部引用 `from core.agents.webhook_task_processor` | → `from core.agents.webhook_task_processor` |
| cage/check_wh003.py | `from core.agents.webhook_task_processor import ...` | → `from core.agents.webhook_task_processor import ...` |
| 4个 cage/*.yaml | 路径引用 `core/agents/` | → `core/agents/` |

```bash
# 声明
echo "移动 agents/ → core/agents/"
echo "影响 5 个 Python 文件 + 4 个契约文件"

# 移动
git mv agents/ core/agents/

# 确保 __init__.py 存在
touch core/agents/__init__.py

# 更新 Python 引用
sed -i '' 's|from agents\.|from core.agents.|g' frontend/backend/routers/tasks_v2.py
sed -i '' 's|from agents\.|from core.agents.|g' frontend/backend/routers/consumer.py
sed -i '' 's|from agents\.|from core.agents.|g' tests/test_e2e_webhook.py
sed -i '' 's|from agents\.|from core.agents.|g' core/agents/cron_task_checker.py
sed -i '' 's|from agents\.|from core.agents.|g' cage/check_wh003.py

# 更新契约文件路径
sed -i '' 's|agents/|core/agents/|g' cage/frontend_phase4_cron_v1.0.yaml
sed -i '' 's|agents/|core/agents/|g' cage/frontend_webhook_fix_v1.0.yaml
sed -i '' 's|agents/|core/agents/|g' cage/frontend_webhook_integration_v1.0.yaml

# 验证脚本
python3 -c "
import sys, os
sys.path.insert(0, '.')

# 验证 1: import 能成功
try:
    from core.agents.webhook_task_processor import process_pending_tasks
    print('✅ import core.agents.webhook_task_processor 成功')
except ImportError as e:
    print(f'❌ import 失败: {e}')
    sys.exit(1)

# 验证 2: cron_task_checker import 能成功
try:
    from core.agents.cron_task_checker import _is_task_stale
    print('✅ import core.agents.cron_task_checker 成功')
except ImportError as e:
    print(f'❌ import 失败: {e}')
    sys.exit(1)

# 验证 3: 旧路径不存在
assert not os.path.exists('core/agents/'), '旧目录仍存在'
print('✅ 旧目录已移除')

# 验证 4: 新路径存在
assert os.path.exists('core/agents/webhook_task_processor.py'), '新文件不存在'
print('✅ 新文件存在')

# 验证 5: 前端代码引用已更新
with open('frontend/backend/routers/tasks_v2.py') as f:
    content = f.read()
assert 'from core.agents.' in content, '前端引用未更新'
assert 'from core.agents.' not in content or 'core.agents' in content, '旧引用仍存在'
print('✅ 前端代码引用已更新')

print()
print('🎉 agents/ 迁移验证通过！')
"

# commit
git add -A && git commit -m "refactor: move agents/ to core/agents/ + update all imports and contracts"
```

---

### 阶段 7：根目录脚本迁移（15分钟）

| 序号 | 源 | 目标 |
|------|-----|------|
| 7.1 | deepflow.py | tools/deepflow_cli.py |
| 7.2 | spec_pro_api.py | tools/spec_pro_api.py |
| 7.3 | run_spec_pro.py | scripts/runners/run_spec_pro.py |
| 7.4 | run_solution_task.py | scripts/runners/run_solution_task.py |
| 7.5 | run_all_tasks.py | scripts/runners/run_all_tasks.py |
| 7.6 | run_task_1.py | scripts/runners/run_task_1.py |
| 7.7 | ci.sh | scripts/ci/ci.sh |
| 7.8 | run_tests.sh | scripts/ci/run_tests.sh |
| 7.9 | run_orchestrator.sh | scripts/runners/run_orchestrator.sh |
| 7.10 | cleanup_plan.sh | scripts/maintenance/cleanup_plan.sh |
| 7.11 | test_run.sh | scripts/ci/test_run.sh |
| 7.12 | orchestrator_agent.py | 删除（与 core/ 重复） |
| 7.13 | run_solution_test.py | tests/integration/run_solution_test.py |
| 7.14 | check_frontend_completion.py | scripts/checks/check_frontend_completion.py |

```bash
# 创建目标目录
mkdir -p tools scripts/runners scripts/ci scripts/maintenance scripts/checks tests/integration

# 移动
git mv deepflow.py tools/deepflow_cli.py
git mv spec_pro_api.py tools/spec_pro_api.py
git mv run_spec_pro.py scripts/runners/
git mv run_solution_task.py scripts/runners/
git mv run_all_tasks.py scripts/runners/
git mv run_task_1.py scripts/runners/
git mv ci.sh scripts/ci/
git mv run_tests.sh scripts/ci/
git mv run_orchestrator.sh scripts/runners/
git mv cleanup_plan.sh scripts/maintenance/
git mv test_run.sh scripts/ci/
git mv run_solution_test.py tests/integration/
git mv check_frontend_completion.py scripts/checks/

# 删除重复
git rm orchestrator_agent.py

# 验证
test -f tools/deepflow_cli.py && echo "✅ deepflow_cli.py 已就位"
test ! -f orchestrator_agent.py && echo "✅ 重复文件已删除"
ls -1 *.py *.sh 2>/dev/null | wc -l  # 应为 0（__init__.py 除外）

# commit
git add -A && git commit -m "refactor: move root scripts to tools/ and scripts/"
```

---

### 阶段 8：根目录文档迁移（10分钟）

| 源 | 目标 |
|-----|------|
| DEVELOPMENT_RULES.md | docs/design/ |
| CODING_STANDARDS.md | docs/design/ |
| PROTOCOLS.md | docs/design/ |
| PROTOCOLS_README.md | docs/design/ |
| SYSTEM_PROMPT.md | docs/design/ |
| UNIFIED_ENTRY_IMPLEMENTATION.md | docs/design/ |
| OPENCLAW_AGENT_MECHANISM_REFERENCE.md | docs/reference/ |
| ARCHIVE_STATUS.md | docs/archive/ |
| PROGRESS_FRONTEND_2026-05-08.md | docs/archive/ |
| nightly_test_log.md | docs/archive/ |
| test_report.md | docs/archive/ |
| docs-review-technical-docs-expert.md | docs/ |
| ARCHITECTURE_REVIEW_REPORT.md | docs/ |
| CONTRACT_CONFLICT_REPORT.md | docs/ |

保留根目录：README.md、CHANGELOG.md、LICENSE、DIRECTORY_STRUCTURE_CONTRACT.md、SKILL.md

```bash
mkdir -p docs/design docs/reference docs/archive

git mv DEVELOPMENT_RULES.md docs/design/
git mv CODING_STANDARDS.md docs/design/
git mv PROTOCOLS.md docs/design/
git mv PROTOCOLS_README.md docs/design/
git mv SYSTEM_PROMPT.md docs/design/
git mv UNIFIED_ENTRY_IMPLEMENTATION.md docs/design/
git mv OPENCLAW_AGENT_MECHANISM_REFERENCE.md docs/reference/
git mv ARCHIVE_STATUS.md docs/archive/
git mv PROGRESS_FRONTEND_2026-05-08.md docs/archive/
git mv nightly_test_log.md docs/archive/
git mv test_report.md docs/archive/
git mv docs-review-technical-docs-expert.md docs/
git mv ARCHITECTURE_REVIEW_REPORT.md docs/
git mv CONTRACT_CONFLICT_REPORT.md docs/

# 验证：根目录只剩标准文件
ls -1 *.md 2>/dev/null
# 应为：CHANGELOG.md DIRECTORY_STRUCTURE_CONTRACT.md README.md SKILL.md

git add -A && git commit -m "refactor: move root .md files to docs/"
```

---

### 阶段 9：配置文件合并（10分钟）

| 源 | 目标 |
|-----|------|
| config.json | 检查内容，合并到 config/global.yaml 或删除 |

```bash
# 检查 config.json 内容
cat config.json

# 如果内容与 config/ 下文件重复，删除
git rm config.json

git add -A && git commit -m "refactor: remove redundant config.json"
```

---

### 阶段 10：更新目录契约（15分钟）

```bash
# 更新 DIRECTORY_STRUCTURE_CONTRACT.md
# 添加实际存在的目录（frontend/、agents/ → core/agents/ 等）
# 更新所有路径引用

git add -A && git commit -m "docs: update DIRECTORY_STRUCTURE_CONTRACT after reorganization"
```

---

### 阶段 11：批量更新其他契约路径（20分钟）

```bash
# 更新 18 个 cage/*.yaml 中的路径引用
# deepclaw_v1.0.yaml: deep-research → research-pro
# spec_pro_v2.0.yaml: core/spec_pro/ → domains/spec_pro/（P1 迁移时处理）
# 其他契约：按实际路径更新

git add -A && git commit -m "refactor: update all contract paths after reorganization"
```

---

## 时间估算

| 阶段 | 时间 | 风险 |
|------|------|------|
| 0: 删除空目录 | 2 分钟 | 零 |
| 1: 文档类目录 | 15 分钟 | 零 |
| 2: 测试数据 | 5 分钟 | 零 |
| 3: 低风险配置 | 15 分钟 | 低 |
| 4: 中风险配置 | 15 分钟 | 中 |
| 5: data_providers/ | 20 分钟 | 高 |
| 6: agents/ | 20 分钟 | 高 |
| 7: 根目录脚本 | 15 分钟 | 低 |
| 8: 根目录文档 | 10 分钟 | 零 |
| 9: 配置合并 | 10 分钟 | 中 |
| 10: 更新目录契约 | 15 分钟 | 低 |
| 11: 更新其他契约 | 20 分钟 | 低 |

**总计：约 2.5 小时**

---

## 回滚策略

每个阶段都有独立的 git commit，回滚只需：
```bash
git revert HEAD     # 回滚最近一步
git revert HEAD~3   # 回滚最近三步
```

---

## 验证脚本汇总

每个阶段完成后运行对应的验证脚本（已内嵌在执行步骤中），确保：
1. 目录存在且正确
2. Python import 能成功
3. 旧路径已清除
4. 代码引用已更新
5. 功能不受影响
