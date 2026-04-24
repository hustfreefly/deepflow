# Label 命名规则

## 强制规则

所有 `sessions_spawn` 调用**必须设置 label 参数**，以便在 OpenClaw 控制台识别。

```python
# ✅ 正确示例
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="planner",                    # ← 控制台显示的名称
    task="规划师：制定长川科技(300604.SZ)研究计划",
    timeout_seconds=120,
)

# ❌ 错误示例（没有 label）
sessions_spawn(
    runtime="subagent",
    mode="run",
    task="...",  # 没有 label → 控制台显示 UUID
)
```

---

## 标准 Label 列表

| Worker 角色 | Label 值 | 说明 |
|------------|---------|------|
| planner | `"planner"` | 规划师 |
| researcher_finance | `"researcher_finance"` | 财务研究员 |
| researcher_tech | `"researcher_tech"` | 技术研究员 |
| researcher_market | `"researcher_market"` | 市场研究员 |
| researcher_macro_chain | `"researcher_macro_chain"` | 宏观/政策/产业链研究员 |
| researcher_management | `"researcher_management"` | 管理层/治理研究员 |
| researcher_sentiment | `"researcher_sentiment"` | 舆情/事件驱动研究员 |
| financial | `"financial"` | 财务分析师 |
| market | `"market"` | 市场分析师 |
| risk | `"risk"` | 风险评估师 |
| auditor_factual | `"auditor_factual"` | 事实审计员 |
| auditor_upside | `"auditor_upside"` | 上行风险审计员 |
| auditor_downside | `"auditor_downside"` | 下行风险审计员 |
| fixer | `"fixer"` | 修复师 |
| verifier | `"verifier"` | 验证师 |
| summarizer | `"summarizer"` | 汇总师 |

---

## Label 格式规范

### 基础格式
```
{role}
```

### 带迭代轮次（可选）
```
{role}_{iteration}
```

示例：
- `"researcher_finance_1"` - 第 1 轮财务研究
- `"researcher_finance_2"` - 第 2 轮财务研究

### ❌ 禁止的 Label 格式

| 禁止格式 | 原因 |
|---------|------|
| UUID（如 `"a1b2c3d4"`） | 无法识别角色 |
| 空字符串 | 无意义 |
| 包含特殊字符（如 `"researcher/finance"`） | 可能导致解析错误 |
| 超过 50 字符 | 过长影响可读性 |

---

## 最佳实践

1. **保持一致性**：同一角色的 label 前缀必须一致
2. **简洁明了**：使用下划线分隔，避免空格和特殊字符
3. **可追溯**：多轮迭代时附加轮次编号
