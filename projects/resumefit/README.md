# ResumeFit — 智能简历生成系统

> 输入基础简历 + 目标 JD → 输出定制化简历（PDF + 可编辑 Word）

**版本**: v1.1-Lite | **创建**: 2026-06-01 | **位置**: `.deepflow/projects/resumefit/`

---

## 🎯 核心能力

输入基础简历和职位描述（JD），系统自动：

1. **解析 JD** — 提取硬约束/软性要求/关键词
2. **优化简历** — 关键词注入、段落重排序、措辞专业化
3. **事实校验** — 确保不造假（公司/时间/学历 100% 保留）
4. **输出双格式** — PDF（投递用）+ Word（可编辑）

---

## 🚀 快速使用

```
/resumefit
```

或者：
```
ResumeFit：帮我生成一份针对XX岗位的简历
```

**所需输入**：
- 基础简历（文本或文件路径）
- 目标 JD（文本、文件路径或截图）

**可选**：
- 公司信息（名称、行业、技术栈）
- 优化强度：conservative / standard（默认）/ aggressive

---

## 📐 架构

```
主Agent (Orchestrator)
  │
  ├─→ Step 1: 收集输入
  ├─→ Step 2: OCR 处理（JD 为图片/PDF 时）
  ├─→ Step 3: LLM 调用（JD解析 + 内容优化）
  ├─→ Step 4: 事实锚点校验（程序化）
  ├─→ Step 5: PDF 渲染（WeasyPrint）
  ├─→ Step 5b: Word 渲染（python-docx）
  ├─→ Step 6: 质量报告（6维评分）
  └─→ Step 7: 输出结果（PDF + Word + 质量报告）
```

---

## 📁 目录结构

```
resumefit/
├── README.md              ← 本文件
├── DEVELOPMENT_PLAN.md    ← 开发计划
├── src/
│   ├── __init__.py
│   ├── interfaces.py          # 数据结构定义（Request/Response/Error）
│   ├── pdf_renderer.py        # PDF 渲染（WeasyPrint）
│   ├── docx_renderer.py       # Word 渲染（python-docx）
│   ├── anchor_validator.py    # 事实锚点校验
│   ├── ocr_helper.py          # 图片/PDF OCR
│   └── quality.py             # 6维质量评分
├── prompts/               ← LLM prompt 模板
├── data/                  ← 测试数据
├── templates/             ← HTML/PDF 模板
└── tests/                 ← 单元测试
```

---

## ⚙️ 配置

### 三档优化强度

| 强度 | 保真度 | 变更范围 |
|------|--------|----------|
| conservative | ≥ 95% | 仅措辞微调 |
| standard | ≥ 90% | 措辞 + 关键词注入 + 排序 |
| aggressive | ≥ 85% | 深度重写 + 重排序 |

### 质量阈值

| 指标 | 阈值 |
|------|------|
| JD 匹配度 | ≥ 75 |
| ATS 兼容性 | ≥ 85 |
| AI 筛选通过率 | ≥ 70 |
| 自然度（AI 痕迹） | ≥ 70 |

---

## 🛡️ 安全机制

**事实锚点保护**（不可变更）：
- 公司名称、职位名称、入职/离职时间
- 学历信息、量化数据

**内容删除检测**：
- 原文技术术语 100% 保留
- 原文动作动词 100% 保留
- 原文项目/产品名称 100% 保留

**高风险变更告警**：
- 新增公司/项目/技能实体需用户确认

---

## 📤 输出

| 格式 | 用途 | 说明 |
|------|------|------|
| PDF | 投递 | ATS 兼容，纯文本可提取 |
| Word (.docx) | 编辑 | 可在 Word/WPS/Google Docs 中修改 |
| 质量报告 | 参考 | 6维评分 + 变更日志 + 改进建议 |

---

## 🧪 测试

```bash
cd .deepflow/projects/resumefit
python3 -m pytest tests/ -v
```

---

## 📖 相关文档

- [开发计划](DEVELOPMENT_PLAN.md) — 完整开发路线图
- [Skill 文档](../../../skills/resumefit/SKILL.md) — OpenClaw Skill 配置
- [接口契约](src/interfaces.py) — 数据结构定义

---

## 🔄 状态

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 0: 项目基础 | ✅ 完成 | 项目骨架 + 接口契约 |
| Phase 1: 核心 MVP | 🔄 开发中 | JD 解析 + 内容优化 + 双格式输出 |
| Phase 2: 质量保障 | ⏳ 待启动 | 事实校验 + 质量报告 |
| Phase 3: 智能增强 | ⏳ 待启动 | 语义匹配 + AI 痕迹监控 |
| Phase 4: 测试部署 | ⏳ 待启动 | 端到端验证 + 文档 |

---

*2026-06-01 | OpenClaw DeepFlow 项目*
