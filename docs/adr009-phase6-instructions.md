# ADR-009 Phase 6: 清理防回归 — 子 Agent 指令

## 任务概述

清理残留代码，添加防回归检查，确保 MD-first 架构不会退化。

---

## 具体任务

### 1. 检查并清理双写残留

搜索 Solution Pro 中是否还有 JSON 主写入逻辑：

```bash
grep -rn "write.*\.json" domains/solution_pro/__init__.py | grep -v "shared_state\|master_state\|planning_convergence"
```

如果发现交付物（frozen_spec/final_solution/solution_document）还有 JSON 写入，删除它。

### 2. 更新测试用例

检查测试文件中是否有验证 JSON 产物的用例，改为验证 MD：

```bash
grep -rn "final_solution\.json\|frozen_spec\.json" domains/solution_pro/tests/
```

如果有，改为检查 `.md` 文件。

### 3. 添加防回归测试

在 `tests/contract/` 或 `domains/solution_pro/tests/` 中添加一个测试，确保：
- `write_stage('final_solution', md_string)` 生成 `.md` 文件
- `read_stage('final_solution')` 优先读 `.md`
- 交付物 stage 不允许 `.json` 写入

示例测试：
```python
def test_md_first_enforcement():
    """确保交付物 stage 是 MD-first"""
    bb = BlackboardManager("test_md_first")
    
    # 写入 MD
    bb.write_stage("final_solution", "# Test MD")
    
    # 验证 .md 文件存在
    assert bb._stage_path("final_solution", ".md").exists()
    
    # 验证 .json 文件不存在
    assert not bb._stage_path("final_solution", ".json").exists()
    
    # 读取应该返回 MD 内容
    content = bb.read_stage("final_solution", as_text=True)
    assert content == "# Test MD"
```

### 4. 添加 CI 检查脚本（可选）

在 `scripts/` 或 `tests/` 中添加一个脚本，检查：
- Prompt 文件中不允许引用交付物 `.json` 路径
- 代码中不允许直接写入交付物 `.json`

---

## 验证标准

- [ ] `grep -rn "frozen_spec\.json\|final_solution\.json\|solution_document\.json" domains/solution_pro/` 返回空
- [ ] 所有测试通过
- [ ] 新增防回归测试

---

## 完成后报告

1. 清理了哪些残留
2. 新增了什么测试
3. 最终验证结果
