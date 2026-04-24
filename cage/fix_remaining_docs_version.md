# 修复遗漏文档版本号

## 目标
修复 5 个遗漏文档的版本号问题

## 问题清单

| 文档 | 问题 | 修复方式 |
|:---|:---|:---|
| PROTOCOLS.md | 标题 V3.0，之前修改未生效 | 重新修改 |
| PROTOCOLS_README.md | 版本 DeepFlow.0，之前修改未生效 | 重新修改 |
| SYSTEM_PROMPT.md | 版本 1.1（系统提示词） | 添加历史标记，标注为 V1.0 时期产物 |
| docs/STANDARD_EXECUTION.md | 版本 V1.0 | 添加 0.1.0 标注 |
| docs/FULL_REHEARSAL_REPORT.md | 版本 1.0 | 添加 0.1.0 标注 |

## 修复策略
- PROTOCOLS/PROTOCOLS_README: 直接修改版本号
- SYSTEM_PROMPT: 保留原版本（1.1 是系统提示词内部版本），添加文档级 0.1.0 标注
- STANDARD_EXECUTION/FULL_REHEARSAL: 添加版本说明行（保留原版本作为历史记录）
