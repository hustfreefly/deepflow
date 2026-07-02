## 🔴 执行铁律（契约笼子 — 所有子 Agent 必须遵守）

1. **声称 ≠ 完成，证据 = 完成** — 写完 stage 后必须等待父 Agent exec 验证，不能自行声明"完成"
2. **只写指定 stage** — 不修改任何其他 stage，不写完成信号（`*_completed`）
3. **MUST 约束不可妥协** — planning_convergence 中标记为 MUST 的约束是硬约束，任何情况下不能违反或弱化
4. **语义判断用 LLM，确定性穷举用 Python** — 不混用。分类/匹配/评估 → LLM；字段检查/格式验证/计数 → Python
5. **不修改上游输出** — 只能读取和写入自己的 stage，不能修改 Planning/Research 模块的产出
6. **完成后只写指定 stage** — 不生成额外文件，不写 summary/README/完成报告到 Blackboard 以外的位置
7. **不能 web_search** — 基于已有知识工作，不搜索新信息（除非 prompt 明确要求）
