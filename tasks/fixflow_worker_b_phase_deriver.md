# FixFlow Worker B — phase_deriver.py 修复

## Phase 0: 决策门

| 问题 | 不修会怎样 | 本质 | 决策 |
|------|-----------|------|:----:|
| B1: 畸形 `delivery_manifest.json` 仍被推导为 DONE | Package Agent 输出损坏时系统误判完成，交付错误产物 | 代码（状态推导缺少校验） | ✅ 代码修 |

## Phase 1: 诊断

### B1 症状与根因
- **症状**: `phase_deriver.derive_phase()` 在 `delivery_manifest.json` 是损坏 JSON 但 `final_deliverable/` 目录有 ≥50B 文件时返回 `DONE`。
- **根因假设**: `derive_phase` 只检查文件存在和目录大小，没有解析/校验 `delivery_manifest.json` 的内容。
- **修复方向**:
  - 在 DONE 分支中，读取 `delivery_manifest.json` 并尝试解析。
  - 如果 JSON 无效或无法被 `DeliveryManifest` schema 验证，则返回 `PACKAGING`（让 package 重试）或 `VALIDATING`（回到验证阶段）。
  - 记录 warning 日志说明 manifest 损坏。
- **测试 A**: 写一个 test 构造损坏的 `delivery_manifest.json` + 非空 `final_deliverable/`，断言 `derive_phase` 不返回 `DONE`。

## Phase 2: 执行约束

- 不修改其他文件
- 保持 `derive_phase` 返回类型不变（str 常量）
- 使用现有 `_read_json` helper
- 避免循环导入（`DeliveryManifest` 可能从另一个文件导入）

## Phase 3: 验证清单

- [ ] B1 test 修复前返回 DONE / 修复后返回非 DONE
- [ ] `pytest domains/deliver_pro/tests/test_phase_deriver.py` 通过
- [ ] `ruff check domains/deliver_pro/phase_deriver.py` 无新增错误
- [ ] 输出修改摘要 + git diff
