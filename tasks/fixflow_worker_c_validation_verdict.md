# FixFlow Worker C — validation_verdict.py 修复

## Phase 0: 决策门

| 问题 | 不修会怎样 | 本质 | 决策 |
|------|-----------|------|:----:|
| C1: 单维度高分即可通过六维质量门 | 验证维度缺失时仍 PASS，质量缺陷漏过 | 代码（评分聚合逻辑） | ✅ 代码修 |

## Phase 1: 诊断

### C1 症状与根因
- **症状**: `ValidationVerdict(scores={'completeness': {'score': 5, 'weight': 1.0}}, weighted_score=5.0)` 返回 `verdict='PASS'`。
- **根因假设**: `compute_verdict()` 只检查 `weighted_score` 和 `min_score`，没有检查是否包含全部六个维度。
- **修复方向**:
  - 定义 `REQUIRED_DIMENSIONS = {"completeness", "correctness", "credibility", "actionability", "consistency", "professionalism"}`。
  - 在 `compute_verdict()` 中：
    - 如果缺失维度，返回 `FAIL` 或 `CONDITIONAL`（建议 FAIL，因为维度不完整本身就是契约违反）。
    - 或者缺失维度按最低分（1 分）补齐后再计算 weighted_score。
  - 推荐策略：缺失维度 > 0 时直接返回 `FAIL`，因为这是六维体检的设计要求。
- **测试 A**: 写一个 test 构造单维度 / 少维度 ValidationVerdict，断言 compute_verdict 返回 `FAIL`；六维完整且均 ≥3 时返回 `PASS`。

## Phase 2: 执行约束

- 不修改 `ValidationVerdict` 的字段定义（只改 `compute_verdict` / `compute_weighted_score` 行为）
- 保持向后兼容：现有六维完整的 verdict 计算结果不变
- 更新 docstring 说明维度完整性要求

## Phase 3: 验证清单

- [ ] C1 test 修复前单维度 PASS / 修复后 FAIL
- [ ] `pytest domains/deliver_pro/tests/test_validation_verdict.py` 通过（如果存在，否则新建或跑相关 tests）
- [ ] `ruff check domains/deliver_pro/contracts/validation_verdict.py` 无新增错误
- [ ] 输出修改摘要 + git diff
