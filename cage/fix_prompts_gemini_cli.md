# 契约笼子：修复6个Prompt文件的Gemini CLI残留

## 状态：✅ 已完成（验证通过）

## 目标
修复6个文件中残留的 Gemini CLI 硬编码引用，统一使用 SearchEngine 接口

## 范围
- `prompts/investment/auditor.md`
- `prompts/investment/financial.md`
- `prompts/investment/market.md`
- `prompts/investment/researcher_enhanced.md`
- `prompts/investment/researcher_finance.md`
- `prompts/investment/risk.md`

## 执行记录

### 步骤1：验证当前残留位置
```bash
$ grep -n "Gemini CLI\|gemini -p" [6个文件]
结果：全部无残留
```

### 步骤2：修复执行
**无需修复** - 前序提交 `42c813b` 已完成修复

### 步骤3：验证
```bash
$ grep -l "Gemini CLI" *.md
结果：✅ 所有 Prompt 文件已无 Gemini CLI 硬编码引用
```

## 验收标准
- [x] 所有文件无 `gemini -p` 硬编码命令
- [x] 所有文件无 `Gemini CLI` 文字引用
- [x] 所有搜索相关段落使用统一接口说明
- [x] 验证：grep 无匹配

## 结论
前序提交 `42c813b` 已完成修复，本次验证确认无残留。契约完成。