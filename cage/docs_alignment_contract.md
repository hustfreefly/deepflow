# 文档对齐与版本号统一（契约笼子）

## 目标
统一 DeepFlow 所有文档的架构描述和版本号，消除冲突。

## 根因分析
- README.md：描述为"投资研究自动化管线"（专用工具定位）
- SKILL.md：描述为"深度研究自动化管线"（模糊定位）
- V1_BLUEPRINT.md：V1.0 版本，仍在根目录
- DEVELOPMENT_RULES.md：V1.0 版本
- docs/V4_*.md：V4.0 版本
- CHANGELOG.md：0.1.0 版本
- 实际代码：混合 V1/V3/V4 设计，版本混乱

## 统一策略

### 版本号规则
- **对外版本号**：0.1.0（与 CHANGELOG 一致）
- **内部代号**：V4.0（表示第四次架构迭代）
- **文档标注**：0.1.0 (V4.0 代号)

### 定位统一
所有文档统一描述为：
> "基于通用多 Agent 协作框架的垂直场景适配，当前重点适配投资分析场景"

### 需要修改的文档清单

| 文档 | 当前版本 | 目标版本 | 关键修改 |
|:---|:---:|:---:|:---|
| README.md | - | 0.1.0 | 定位描述、版本号、项目结构 |
| SKILL.md | - | 0.1.0 | 定位描述、触发方式 |
| CHANGELOG.md | 0.1.0 | 0.1.0 | 确认无误，添加 V4.0 代号说明 |
| DEVELOPMENT_RULES.md | V1.0 | 0.1.0 | 版本号、添加架构说明引用 |
| CODING_STANDARDS.md | - | 0.1.0 | 版本号 |
| docs/ARCHITECTURE.md | 1.0 | 0.1.0 | 版本号统一 |
| docs/V4_ARCHITECTURE_PLAN.md | V4.0 | 0.1.0 | 添加版本说明，标记为历史 |
| docs/V4_FINAL_DESIGN.md | 4.0 | 0.1.0 | 添加版本说明，标记为历史 |
| docs/V4_COMPLETE_SPEC.md | V4.0 | 0.1.0 | 添加版本说明，标记为历史 |
| docs/configuration.md | - | 0.1.0 | 版本号 |
| docs/STANDARD_EXECUTION.md | - | 0.1.0 | 版本号 |
| docs/QUICKSTART.md | - | 0.1.0 | 版本号、定位描述 |
| PROTOCOLS_README.md | DeepFlow.0 | 0.1.0 | 版本号统一 |
| PROTOCOLS.md | V3.0 | 0.1.0 | 版本号、标记为历史 |
| V1_BLUEPRINT.md | V1.0 | - | 移动到 ARCHIVED/ |

## 验收标准
- [ ] 所有文档版本号统一为 0.1.0
- [ ] 所有文档定位描述一致（通用框架 + 投资适配）
- [ ] README.md 明确引用 ARCHITECTURE.md
- [ ] V1_BLUEPRINT.md 移动到 ARCHIVED/
- [ ] 无版本号冲突文档留在根目录

## 执行步骤
1. 修改 README.md（版本号、定位、结构）
2. 修改 SKILL.md（版本号、定位）
3. 确认 CHANGELOG.md（添加 V4.0 代号说明）
4. 修改 DEVELOPMENT_RULES.md（版本号）
5. 修改 CODING_STANDARDS.md（版本号）
6. 修改 docs/V4_*.md（版本说明、历史标记）
7. 修改 docs/其他文档（版本号）
8. 修改 PROTOCOLS 文档（版本号）
9. 移动 V1_BLUEPRINT.md 到 ARCHIVED/
10. Git 提交
