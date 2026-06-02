# Solution Pro E2E Golden Case

> 版本: 1.0 | 创建: 2026-06-02 | 适配: Solution Pro V4.3

## 概述

Golden Case 是 Solution Pro 管线的**标准端到端测试用例**，用于验证固定 10 阶段管线的完整性和正确性。

## 案例: AI智能客服系统

- **Topic**: 设计一个企业级AI智能客服系统，支持多轮对话、意图识别、知识库检索和人工坐席无缝转接
- **Type**: architecture
- **Mode**: standard
- **6 个约束**: 10万+日对话、99.9%可用性、<2秒响应、中英双语、CRM集成、GDPR合规
- **4 个利益相关者**: 技术团队、产品团队、客服运营、合规部门

## 文件清单

| 文件 | 用途 |
|------|------|
| `golden_case_001.json` | 测试用例定义（输入 + 预期输出 + 验证标准） |
| `run_golden_e2e.py` | 启动器（生成执行计划，不执行管线） |
| `verify_golden_case.py` | 验证脚本（40+ 项检查，exit code 0/1/2） |
| `README.md` | 本文件 |

## 执行流程

### 1. 生成执行计划（Python）

```bash
cd ~/.openclaw/workspace/.deepflow
python3 tests/golden/run_golden_e2e.py
```

产出: `blackboard/<session_id>/execution_plan.json` + `tasks.json` + `data/frozen_spec.json`

### 2. 主Agent 执行管线（OpenClaw）

主Agent 读取 session_id，按 SKILL.md 执行 Step 2-6（清理→spawn→cron→yield）

### 3. 验证结果

```bash
python3 tests/golden/verify_golden_case.py <session_id>
```

## 验证项（40+ 项）

| 类别 | 数量 | 说明 |
|------|------|------|
| 基础设施 | 4 | blackboard目录、核心文件存在性 |
| 执行计划 | 12 | 10阶段完整性、并行阶段配置 |
| Frozen Spec | 7 | 需求数量、P0存在性、REQ-ID格式 |
| 阶段输出 | 16 | 每个阶段的输出文件+字段+状态 |
| 全局产物 | 5 | control_contract、traceability_matrix、.completed |
| 最终报告 | 5 | final_solution.md存在性+章节覆盖 |
| REQ-ID追踪 | 3+ | P0需求在追踪矩阵中的覆盖 |

### 退出码

| 码 | 含义 | 条件 |
|----|------|------|
| 0 | ✅ PASS | 全部通过 |
| 1 | ⚠️ PARTIAL | 有 FAIL 但通过率 ≥ 70% |
| 2 | ❌ FAIL | 关键断言失败或通过率 < 70% |

## 10 阶段管线

```
Phase 1:  Data Collection  ─── web搜索，行业调研
Phase 2:  Planning         ─── 架构蓝图，专家映射 → 刷新 control_contract
Phase 3:  Reviewers (×3)   ─── 技术/业务/风险评审 [并行]
Phase 4:  Research (×3)    ─── NLP/RAG/高可用调研 [并行]
Phase 5:  Consolidator     ─── 合并结果，消除矛盾
Phase 6:  Audit            ─── 交叉验证诚实性
Phase 7:  Fix              ─── 基于审计修复
Phase 8:  Fixer Expert     ─── 深度修复
Phase 9:  Harness Final    ─── 4维质量门禁
Phase 10: Summarizer       ─── 生成 final_solution.md
```

## 预期耗时

- 执行计划生成: < 5 秒
- 管线执行: 30-60 分钟
- 验证脚本: < 2 秒
