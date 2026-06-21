# DeepFlow V4.0 核心决策确认

**日期**: 2026-04-22 23:11  
**状态**: 等待确认

---

## 已确认的关键决策

### 1. DataManager Worker → 执行 Python 代码 ✅

```python
# Worker 将执行真实的 bootstrap
data_loop.bootstrap_phase(context)  # 不是文本描述，是真实代码
```

**效果**：真正采集数据，不是 LLM 幻觉

### 2. 统一搜索层 → Orchestrator 本地执行 ✅

```python
# Orchestrator 本地执行搜索
results = run_supplement_search(session_id, code, name)
# 结果写入 blackboard/data/05_supplement/
```

**效果**：Workers 只读取，不自己搜索，避免重复

### 3. 其他 Workers → 只需要上下文注入 ✅

```python
# 每个 Worker 收到：
task = f"""
# 🎯 上下文注入（Orchestrator 提供）
- 股票代码: 688652.SH
- 公司名称: 京仪装备
- 最新股价: {price}
- 研究重点: {planner_focus}

# 原始提示词
{read_from(prompt_file)}
"""
```

**效果**：100% 有完整上下文，质量稳定

---

## 参考 bak 文件的核心设计

| bak 文件设计 | V4.0 实现 |
|:---|:---|
| Agent 编程范式（执行代码） | ✅ Orchestrator 执行 Python |
| DataManager bootstrap | ✅ Worker 执行 `bootstrap_phase()` |
| 统一搜索层（代码化） | ✅ `unified_search()` 函数 |
| Workers 只分析不采集 | ✅ 上下文注入 + 原始提示词 |
| Blackboard 数据流 | ✅ 强制写入/读取 |
| 收敛检测（≥2轮） | ✅ 保留 |

---

## 完整方案文档

**`.deepflow/docs/V4_IMPLEMENTATION_SPEC.md`**

包含：
1. 架构总览（执行链路图）
2. 核心模块实现（search_tools.py, task_builder.py）
3. 数据流设计（文件依赖关系）
4. 错误处理与降级策略
5. 验证与契约（checklist）
6. 实施计划（9小时，分6步）
7. 关联部分联动设计

---

## 下一步

**选项 A**：立即开始实施（预计 9 小时）  
**选项 B**：先审查方案文档，确认后再实施  
**选项 C**：先实现核心模块（搜索层 + Task构建器），快速验证

**选哪个？**