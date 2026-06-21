# DeepClaw → Research Pro 改名契约

## 契约编号
RENAME-RESEARCH-PRO-V1.0

## 契约目标
将系统中的 "DeepClaw" 统一重命名为 "Research Pro"，确保代码、文档、配置的完全一致性。

## 约束条件

### 1. 命名规范
- **用户界面**: "Research Pro"（两个词，首字母大写）
- **代码标识符**: "research_pro"（蛇形命名）
- **模块/包名**: "research_pro"
- **类名**: "ResearchPro"（驼峰命名）
- **常量**: "RESEARCH_PRO"（全大写）

### 2. 改名范围
- 所有 Python 代码文件
- 所有 Markdown 文档
- 所有 YAML 配置文件
- 目录和文件名
- 注释和文档字符串
- 测试文件
- 导入语句

### 3. 不改的内容
- 历史版本号和变更日志（保持历史记录完整性）
- Git commit messages（历史记录不可变）
- 已归档的 blackboard 数据（保持数据完整性）

## 验收标准

### 功能验收
- [ ] 所有导入语句正确
- [ ] 所有测试通过
- [ ] 所有文档链接有效
- [ ] 用户界面显示正确

### 代码验收
- [ ] `grep -r "DeepClaw\|deepclaw\|deep_claw\|DEEPCLAW"` 返回空（除历史文件）
- [ ] `grep -r "ResearchPro\|research_pro\|RESEARCH_PRO"` 返回预期文件
- [ ] 无循环依赖
- [ ] 无断裂的导入

### 文档验收
- [ ] 所有 SKILL.md 更新
- [ ] 所有 README.md 更新
- [ ] 导览页（/deepflow）更新
- [ ] 记忆文件更新

## 执行步骤

### Phase 1: 准备（5分钟）
1. 扫描所有 DeepClaw 引用
2. 生成改名清单
3. 备份关键文件

### Phase 2: 代码改名（20分钟）
1. 重命名目录和文件
2. 批量替换代码中的引用
3. 更新导入语句
4. 修复测试文件

### Phase 3: 文档改名（10分钟）
1. 更新所有 Markdown 文档
2. 更新 SKILL.md
3. 更新导览页
4. 更新记忆文件

### Phase 4: 配置改名（5分钟）
1. 更新 YAML 配置
2. 更新 JSON 配置
3. 更新 cage 契约

### Phase 5: 验证（10分钟）
1. 运行所有测试
2. 检查导入错误
3. 验证文档链接
4. 生成验证报告

## 风险缓解
- 备份所有修改的文件
- 分阶段执行，每阶段验证
- 保留回滚能力
- 记录所有变更

## 签名
- 执行者: OpenClaw Agent
- 日期: 2026-05-29
- 状态: 待执行
