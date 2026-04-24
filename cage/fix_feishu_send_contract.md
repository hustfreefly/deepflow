# 契约笼子：修复飞书发送方式 + 配置化 + 路径硬编码

## 目标
1. 修复飞书发送方式：MD 报告应创建飞书文档发送链接，而非本地路径
2. 发报告配置化：目标用户、发送方式应可配置
3. 修复所有 Prompt 中的硬编码绝对路径

## 问题确认

### 问题1：飞书发送方式错误
当前 send_reporter.md：
```
**完整报告**: {blackboard_base_path}/final_report.md  ← 手机打不开
```

正确做法（TOOLS.md）：
- MD 文件 → 飞书 API 创建文档 → 发送文档链接
- 用户手机点击链接即可查看

### 问题2：发送目标硬编码
当前 send_reporter.md：
```
用户 OpenID: ou_d55068472a52a0f34ff72c3b6930044c  ← 硬编码
```

应改为配置化：
```yaml
output:
  feishu:
    enabled: true
    target_open_id: "${FEISHU_USER_OPEN_ID}"
```

### 问题3：所有 Prompt 硬编码绝对路径
```python
sys.path.insert(0, "/Users/allen/.openclaw/workspace/.deepflow")  ← 硬编码
```

应使用：
```python
sys.path.insert(0, "{{deepflow_base}}")  ← 模板变量
```

## 修复范围

### 修改文件
- data/search_config.yaml - 添加飞书发送配置
- prompts/investment/send_reporter.md - 修复发送方式
- prompts/investment/*.md - 修复硬编码路径（使用 {{deepflow_base}}）
- core/task_builder.py - 添加 deepflow_base 模板变量

### 验证清单
- [ ] search_config.yaml 包含飞书配置
- [ ] send_reporter.md 使用飞书文档 API
- [ ] 所有 Prompt 无硬编码绝对路径
- [ ] 语法验证通过
- [ ] Git 提交

## 实施步骤
1. 修改 search_config.yaml 添加 output.feishu 配置
2. 重写 send_reporter.md 使用 feishu_doc API
3. 批量替换所有 Prompt 中的硬编码路径
4. 修改 task_builder.py 注入 deepflow_base 变量
5. 验证并提交
