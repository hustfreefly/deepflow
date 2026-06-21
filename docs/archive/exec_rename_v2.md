# DeepClaw → Research Pro 执行契约 V2

## 契约编号
EXEC-RENAME-RESEARCH-PRO-V2.0

## 影响范围摘要
- **总匹配**: 165 处
- **影响文件**: 29 个
- **主要变体**: DeepClaw (108), deepclaw (47), deep_claw (3), DEEPCLAW (3)

## 执行分类

### 类别 A: 必须修改（代码+文档）
**文件数**: 18  
**匹配数**: 120+

1. **核心代码** (8个文件)
   - `.deepflow/skills/deep-research/lib/orchestrator.py` (10处)
   - `.deepflow/skills/deep-research/lib/citation_verifier.py` (4处)
   - `.deepflow/skills/deep-research/lib/tier_classifier.py` (2处)
   - `.deepflow/skills/deep-research/lib/keyword_generator.py` (2处)
   - `.deepflow/skills/deep-research/lib/source_registry.py` (2处)
   - `.deepflow/tests/deepclaw/test_orchestrator.py` (37处)
   - `.deepflow/tests/deepclaw/test_citation_verifier.py` (2处)
   - `.deepflow/tests/deepclaw/test_source_registry.py` (2处)
   - `.deepflow/tests/deepclaw/test_keyword_generator.py` (2处)
   - `.deepflow/tests/deepclaw/test_tier_classifier.py` (2处)
   - `.deepflow/tests/e2e/run_real_e2e.py` (6处)

2. **文档** (5个文件)
   - `.deepflow/skills/deep-research/SKILL.md` (4处)
   - `skills/deepflow/SKILL.md` (3处)
   - `.deepflow/cage/deepclaw_dev_instructions.md` (7处)
   - `.deepflow/tests/unit/validate_deepflow_navigator.py` (2处)
   - `.deepflow/cage/deepclaw_v1.0.yaml` (9处)

### 类别 B: 不修改（历史/记忆数据）
**文件数**: 5  
**匹配数**: 40+

1. **记忆系统** (2个文件)
   - `memory/.dreams/short-term-recall.json` (22处) - 历史记录
   - `memory/.dreams/session-corpus/2026-05-29.txt` (16处) - 会话历史

2. **Blackboard 归档** (2个目录)
   - `.deepflow/blackboard/deepclaw_checkpoints/` - 已归档数据
   - `.deepflow/blackboard/deepclaw_tao_law/` - 已归档数据

3. **本契约文件** (1个文件)
   - `.deepflow/cage/rename_deepclaw_to_research_pro.md` (7处) - 契约本身

## 改名映射表

| 原文 | 替换为 | 场景 |
|------|--------|------|
| `DeepClaw` | `ResearchPro` | 类名、标题 |
| `deepclaw` | `research_pro` | 模块名、变量 |
| `deep_claw` | `research_pro` | 蛇形命名 |
| `DEEPCLAW` | `RESEARCH_PRO` | 常量 |
| `Deep Claw` | `Research Pro` | 显示文本 |
| `deep claw` | `research pro` | 显示文本 |

## 执行步骤

### Step 1: 备份关键文件
```bash
cp -r .deepflow/skills/deep-research .deepflow/skills/deep-research.backup
cp -r .deepflow/tests/deepclaw .deepflow/tests/deepclaw.backup
cp -r .deepflow/cage .deepflow/cage.backup
```

### Step 2: 重命名目录
```bash
mv .deepflow/tests/deepclaw .deepflow/tests/research_pro
```

### Step 3: 批量替换代码（按优先级）
1. Python 代码文件（使用 sed）
2. Markdown 文档
3. YAML 配置

### Step 4: 验证
- 运行所有测试
- 检查导入语句
- 验证文档链接

## 验收标准
- [ ] `grep -r "DeepClaw\|deepclaw" --include="*.py" --include="*.md" --include="*.yaml"` 在类别 A 文件中返回空
- [ ] 所有 Python 测试通过
- [ ] 所有文档链接有效
- [ ] 导览页显示正确

## 风险控制
- 备份完成后才执行
- 分步骤执行，每步验证
- 保留回滚能力（备份目录）
- 不修改历史数据

## 执行签名
- 执行者: OpenClaw Agent
- 日期: 2026-05-29
- 状态: 待执行
