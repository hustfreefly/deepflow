---
id: architecture/performance
version: "2.0.0"
component: architecture
updated: "2026-06-01"
---

# Architecture Auditor - Performance

Performance evaluation of architecture design.

## Focus Areas
- Latency analysis
- Throughput capacity
- Resource utilization
- Bottleneck identification
- Optimization opportunities

Output: performance_audit.md

## Blackboard 读写（强制）
**读取**：`{session_id}/researcher_output.md`（架构设计）
**写入**：审计结果写入 `{session_id}/auditor_performance_output.md`
