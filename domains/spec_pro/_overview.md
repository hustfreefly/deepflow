---
id: spec_pro/overview
version: "2.3.0"
component: spec_pro
role: documentation
updated: "2026-06-02"
---

# Spec Pro — 需求收集与梳理引擎

## 职责
通过苏格拉底式对话引导用户完善需求，输出 Living Spec 供下游消费。

## 入口
- Orchestrator: `coordinator.py` → `SpecProCoordinator`
- CLI API: `spec_pro_api.py` → `main()`

## 代码索引
| 文件 | 职责 |
|------|------|
| coordinator.py | 主协调器（6 轮苏格拉底对话） |
| models.py | 数据模型（LivingSpec, QualityLevel, DialogState） |
| merge_spec.py | Spec 合并（增量合并用户确认） |
| utils.py | 工具函数 |
| worker_fallback.py | Worker 回退（子 Agent 失败时降级） |
| process_guard.py | 进程守护 |
| spec_pro_api.py | CLI 接口（init/next_round/status 等） |

## Prompts
| 文件 | 用途 |
|------|------|
| prompts/orchestrator.md | 主编排 prompt |
| prompts/guide.md | 引导问题生成 |
| prompts/assess.md | 质量评估 |
| prompts/structure.md | 结构化输出 |
| prompts/parse.md | 用户输入解析 |
| prompts/harness.md | 质量门禁 |
| prompts/parse_response.md | 响应解析 |

## 配置
| 文件 | 用途 |
|------|------|
| config/spec_pro_v2.0.yaml | 活跃契约（v2.0） |

## 测试
| 位置 | 说明 |
|------|------|
| tests/ | 域内测试（待补充） |
