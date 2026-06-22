# DeepFlow Wiki

> 系统架构、数据流、测试覆盖的完整知识库  
> 版本：1.0.0 | 最后更新：2026-06-22

---

## 📚 文档索引

| 文档 | 内容 | 适合谁看 |
|:---|:---|:---|
| [1-系统总览.md](1-系统总览.md) | 三域全景图 + 数据流 + 快速导航 | 新人入门、全局理解 |
| [2-域详解.md](2-域详解.md) | 每个域的完整工作流程 + 关键组件 | 开发者、调试者 |
| [3-Blackboard结构.md](3-Blackboard结构.md) | 文件组织规范 + 核心文件格式 | 开发者、数据恢复 |
| [4-Prompt注册表.md](4-Prompt注册表.md) | 70+ Prompt 模板清单 + 调用关系 | Prompt 工程师、调试者 |
| [5-测试覆盖地图.md](5-测试覆盖地图.md) | 10 个测试套件 + 211+ 测试用例 | 测试工程师、质量保证 |
| [6-恢复手册.md](6-恢复手册.md) | 数据丢失后的完整恢复指南 | 运维、灾难恢复 |

---

## 🎯 快速查询

### "我想了解..."

| 问题 | 看哪个文档 |
|:---|:---|
| DeepFlow 是什么？ | 1-系统总览.md |
| Spec Pro 怎么工作？ | 2-域详解.md → 1. Spec Pro |
| LivingSpec 长什么样？ | 3-Blackboard结构.md → 核心文件格式 |
| 某个 prompt 被谁调用？ | 4-Prompt注册表.md → 对应域 |
| 怎么运行测试？ | 5-测试覆盖地图.md → 一键运行 |
| 数据丢了怎么恢复？ | 6-恢复手册.md |
| merge_spec 的签名？ | 2-域详解.md → 1.2 merge_spec.py |
| Harness V2 评估什么？ | 2-域详解.md → 1.3 Harness V2 |
| Solution Pro 有几个阶段？ | 2-域详解.md → 2. 10 阶段管线 |
| Ship Pro 质量门控？ | 2-域详解.md → 3. 质量门控 |

---

## 🔧 常用命令

### 运行所有测试
```bash
cd /Users/allen/.openclaw/workspace/.deepflow
PYTHONPATH=. python3 -c "
import subprocess, sys, os
tests = [
    'tests/test_path_config.py',
    'tests/test_prompt_registry.py', 
    'tests/test_e2e_living_spec_v2.py',
    'tests/test_spec_pro_full.py',
    'tests/contract/test_quality_gate.py',
    'tests/e2e_solution_test.py',
]
for path in tests:
    r = subprocess.run([sys.executable, path], capture_output=True, timeout=60,
                      env={**os.environ, 'PYTHONPATH': '.'})
    status = '✅' if r.returncode == 0 else '❌'
    print(f'{status} {path}')
"
```

### 恢复 Blackboard 数据
```bash
python3 blackboard_recover_all.py
```

### 检查关键函数
```bash
PYTHONPATH=. python3 -c "
from domains.spec_pro.merge_spec import merge_conversation_digest
from domains.spec_pro.eval.harness import run_harness_v2
from domains.solution.spec_context import build_conversation_digest_for_prompt
print('✅ 关键函数存在')
"
```

---

## 📊 系统状态 (2026-06-22)

| 指标 | 值 |
|:---|:---|
| 代码文件 | 183 个 Python |
| Prompt 模板 | 70+ 个 |
| 测试套件 | 10 个 |
| 测试用例 | 211+ 个 |
| 测试通过率 | 9/10 (90%) |
| Blackboard 案例 | 88 个 |
| 数据恢复完整性 | 617/617 (100%) |

---

## 🗺️ 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Spec Pro (需求规格域)                                       │
│  ─────────────────────                                       │
│  Coordinator → ResponseWorker → merge_spec → Harness V2    │
│                                                              │
│  输出: LivingSpec (需求规格)                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Solution Pro (解决方案域)                                   │
│  ─────────────────────────                                   │
│  10 阶段管线:                                               │
│  Planner → Reviewer → Fixer → Researcher → Consolidator   │
│  → Auditor → Fixer → Harness → Fixer → Summarizer          │
│                                                              │
│  输出: final_result.json (技术方案)                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Ship Pro (工程交付域)                                       │
│  ─────────────────────                                       │
│  Architect → Specifier → Decomposer → Packager → Reviewer  │
│                                                              │
│  输出: ship_package.json (工程包)                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 数据流

```
用户对话
   ↓
ResponseWorker 提取需求
   ↓
merge_spec.py → LivingSpec
   ↓
Harness V2 评估 → PASS?
   ↓ (是)
Solution Pro 10 阶段管线
   ↓
final_result.json
   ↓
Ship Pro 5 Agent 流水线
   ↓
ship_package.json
```

---

## 📝 更新日志

### 2026-06-22 (v1.0.0)
- ✅ 创建 Wiki 结构
- ✅ 编写 6 个核心文档
- ✅ 覆盖 4 个域的完整工作流程
- ✅ 记录 70+ Prompt 模板
- ✅ 记录 10 个测试套件
- ✅ 编写恢复手册

---

## 🤝 贡献指南

### 添加新文档
1. 在 `wiki/` 目录创建 `.md` 文件
2. 命名规范: `{序号}-{标题}.md`
3. 更新本 README 的索引表

### 更新现有文档
1. 修改对应 `.md` 文件
2. 更新 `最后更新` 日期
3. 提交 Git: `git commit -m "docs: update wiki/2-域详解.md"`

---

## 📞 支持

遇到问题？

1. 查阅 Wiki 文档
2. 运行测试套件验证
3. 检查 Blackboard 结构
4. 查看 Session 日志

**核心原则**: 
- 代码在 `domains/{domain}/`
- Prompt 在 `domains/{domain}/prompts/`
- 测试在 `tests/` 或 `domains/{domain}/eval/`
- 数据在 `blackboard/`
