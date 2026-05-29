# ResearchPro 自驱开发指令

## 目标
按 `cage/research_pro_v1.0.yaml` 契约，从 Step 2 到 Step 15 自动迭代完成全部开发。

## 工作目录
`/Users/allen/.openclaw/workspace/.deepflow`

## 开发流程（每步重复）

1. **读取契约** — 读 `cage/research_pro_v1.0.yaml` 中当前 step 的定义
2. **开发实现** — 严格按照契约的 interface/data/behavior 定义编写代码
3. **自检 gates** — 执行契约中定义的所有 gates
4. **写 checkpoint** — 写入 `blackboard/research_pro_checkpoints/step_{N}.json`
5. **自动进入下一步**

## Step 列表

| Step | 名称 | 产出文件 |
|------|------|----------|
| 2 | 配置文件 | `skills/deep-research/config/*.json` (3个文件) |
| 3 | Source Registry | `skills/deep-research/lib/source_registry.py` |
| 4 | Citation Verifier | `skills/deep-research/lib/citation_verifier.py` |
| 5 | Tier Classifier | `skills/deep-research/lib/tier_classifier.py` |
| 6 | Keyword Generator | `skills/deep-research/lib/keyword_generator.py` |
| 7 | Orchestrator | `skills/deep-research/lib/orchestrator.py` |
| 8 | Prompt-规划 | `skills/deep-research/prompts/planning.md` |
| 9 | Prompt-搜索 | `skills/deep-research/prompts/search.md` |
| 10 | Prompt-引用验证 | `skills/deep-research/prompts/citation_verify.md` |
| 11 | Prompt-金融分析 | `skills/deep-research/prompts/finance_analysis.md` |
| 12 | SKILL.md | `skills/deep-research/SKILL.md` |
| 13 | E2E 快速模式 | 测试报告 |
| 14 | E2E 标准模式 | 测试报告 |
| 15 | Harness 验证 | 测试报告 |

## Checkpoint 格式

```json
{
  "step": 2,
  "name": "配置文件",
  "status": "done|failed",
  "gates_passed": ["gate1", "gate2"],
  "gates_failed": [],
  "files_created": ["skills/deep-research/config/tier_domains.json"],
  "timestamp": "ISO8601",
  "notes": "..."
}
```

## 关键约束

1. **每步必须读契约** — 不要凭记忆，每步开始时重新读 `cage/research_pro_v1.0.yaml`
2. **红线不可违反** — 7 条 RED-DC-xxx 红线必须全部满足
3. **gate 必须全部通过** — 任何一个 gate 失败就修复后重试
4. **先目录后文件** — 先 `mkdir -p` 创建目录结构
5. **Python 模块必须可 import** — 每个 .py 文件写完后立即 `python3 -c "import ..."` 验证
6. **测试文件同步写** — Python 模块写完同时写对应的测试文件
7. **自动迭代** — 一步完成后立即开始下一步，不等待人工确认

## 目录结构（先创建）

```
skills/deep-research/
├── SKILL.md
├── lib/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── source_registry.py
│   ├── citation_verifier.py
│   ├── tier_classifier.py
│   └── keyword_generator.py
├── prompts/
│   ├── planning.md
│   ├── search.md
│   ├── citation_verify.md
│   └── finance_analysis.md
├── config/
│   ├── tier_domains.json
│   ├── time_budgets.json
│   └── completion_criteria.json
└── templates/
    ├── fast_report.md
    └── standard_report.md

tests/research_pro/
├── __init__.py
├── test_source_registry.py
├── test_citation_verifier.py
├── test_tier_classifier.py
├── test_keyword_generator.py
├── test_orchestrator.py
└── test_e2e.py

blackboard/research_pro_checkpoints/
└── step_{N}.json
```
