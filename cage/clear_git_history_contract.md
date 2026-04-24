# 清空 Git 历史记录

## 目标
移除 Git 历史记录中残留的敏感信息（Tushare Token），创建一个干净的初始提交。

## 根因
data/credentials.yaml 曾在 Git 历史中存在（提交 15901ab 等），包含真实 Tushare Token。即使已从当前工作区移除，历史提交中仍可追溯到该凭证。

## 方案
采用 `git checkout --orphan` 创建孤立分支，保留当前代码但清空历史：

1. 备份当前代码到临时目录
2. 删除 .git 目录
3. 重新初始化 git
4. 添加所有文件（除 .gitignore 排除的）
5. 提交为干净的初始提交

## 影响
- ✅ 代码完全保留
- ✅ 敏感信息从历史中清除
- ❌ 所有提交历史丢失（无法恢复）
- ❌ Git log 将只显示一条提交

## 替代方案（不采用）
- git filter-branch：复杂，可能遗漏
- BFG Repo-Cleaner：需要额外工具

## 验收标准
- [ ] git log 只显示一条提交
- [ ] credentials.yaml 不在历史中
- [ ] 所有代码文件完整保留
- [ ] .gitignore 规则生效
