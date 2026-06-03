# 契约：AssessGuideWorker 合并

## 声明

### 目标
将 AssessWorker（质量评分）+ QuestionWorker（问题生成）合并为 AssessGuideWorker。
- 当前：AssessWorker(60s) → QuestionWorker(90s) = 150s
- 合并后：AssessGuideWorker(120s) = 120s
- 收益：省 30s/轮

### 输入
- `spec/living_spec.json`
- `spec/quality_trajectory.json`（可选，用于判断轮次策略）
- `spec/conversation_log.json`（历史对话，用于去重）
- `stages/round_{NN-1}_questions.json`（上轮问题）
- `stages/round_{NN-1}_response.json`（上轮回答解析）

### 输出（两个独立文件）
1. `spec/quality_report.json`（同 assess.md 格式）
2. `stages/round_NN_questions.json`（同 guide.md 格式）

### 执行步骤
Phase 1: 质量评估 → 输出 quality_report.json
Phase 2: 问题生成 → 读取 Phase 1 结果 → 输出 questions.json

### 约束
- 不改变评分逻辑（7维度加权）
- 不改变提问策略（苏格拉底六类问题）
- 不改变边界检查规则（需求 vs 设计）
- 两个输出文件独立，格式与原来完全一致

### 成功标准
1. quality_report.json 格式与原 assess.md 输出一致
2. questions.json 格式与原 guide.md 输出一致
3. coordinator.py 收集阶段从 5 步减到 4 步
4. worker_fallback.py 增加 assess_guide fallback
5. 旧 prompt 文件保留（向后兼容）

## 验证项
- [ ] assess_guide.md 包含 Phase 1 + Phase 2 明确标记
- [ ] coordinator.py 中 Step 4 改为 AssessGuideWorker
- [ ] coordinator.py 中不再单独 spawn QuestionWorker（分支 C 已合并）
- [ ] worker_fallback.py 有 assess_guide case
- [ ] schemas.py 有 AssessGuideWorker schema
