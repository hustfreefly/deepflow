# Research Pro 安全与依赖审计报告

**审计日期**: 2026-06-11  
**审计员**: DeepFlow Research Pro 安全与依赖审计员  
**审计范围**: `.deepflow/domains/research_pro/` 全部源文件 + 配置文件 + 依赖关系

---

## 总体评级: 🟢 GREEN

Research Pro 代码库在安全和开源发布方面表现优秀，**可以安全地公开发布到 GitHub**。

---

## 安全扫描结果

| 维度 | 评级 | 说明 |
|------|------|------|
| **凭证安全** | 🟢 GREEN | 无硬编码密钥，环境变量引用规范，.gitignore 完整覆盖敏感文件 |
| **代码安全** | 🟢 GREEN | 无危险操作，具备完善的 SSRF 防护、路径遍历防护、输入验证 |
| **依赖安全** | 🟡 YELLOW | 依赖声明缺失（无 requirements.txt/pyproject.toml），需补充 |
| **发布准备** | 🟢 GREEN | .gitignore 完整，无个人信息泄露，测试覆盖良好 |

---

## 详细发现

### A. 凭证安全

#### ✅ 无硬编码凭证
- **扫描结果**: 未发现硬编码的 API key、password、token、secret
- **唯一匹配**: `source_registry.py:55` 处的 `parsed.password` 是 URL 解析后的安全检查代码，非硬编码凭证

#### ✅ 环境变量引用安全
- `path_config.py` 使用 `os.environ.get('DEEPFLOW_BASE')` 获取环境变量
- 环境变量路径经过严格验证（绝对路径、无 `..` 遍历、可写检查）

#### ✅ .gitignore 完整
- 已覆盖: `.env`, `*.pem`, `*.key`, `credentials.json`, `.credentials/`, `__pycache__/`, `.idea/`, `.vscode/` 等
- 项目根目录 `.gitignore` 配置完善

#### ✅ 无日志泄露风险
- 日志输出使用结构化格式，不包含敏感信息
- 错误处理中不直接打印原始异常堆栈到用户可见输出

---

### B. 代码安全

#### ✅ 无危险操作
- **eval/exec**: 未发现使用
- **pickle**: 未发现使用
- **os.system**: 未发现使用
- **__import__**: 未发现动态导入

#### ⚠️ subprocess 使用（已安全封装）
- **位置**: `orchestrator.py:907-908`
- **用途**: 调用 `ddgs` (DuckDuckGo Search) 进行搜索
- **安全措施**:
  - 使用 `sys.executable` 确保使用当前 Python 解释器
  - 脚本内容硬编码在代码中，非外部输入
  - 参数通过 `sys.argv` 传递，非 shell 拼接
  - 设置了 `timeout=DDGS_TIMEOUT_SECONDS` (12秒)
  - `capture_output=True` 隔离输出
- **风险评级**: LOW - 已充分防护

#### ✅ SSRF 防护完善
- `safe_fetcher.py` 实现了多层 SSRF 防护:
  1. **DNS 预解析**: 在连接前解析 IP，检查是否为私有/保留地址
  2. **IP 黑名单**: 拒绝 loopback、private、link-local、multicast、reserved、unspecified 地址
  3. **URL 验证**: `_validate_safe_url()` 检查协议、主机名、userinfo
  4. **重定向验证**: 每次重定向目标都重新验证
  5. **自定义 HTTP 连接**: 使用预解析的 IP 连接，防止 DNS rebinding

#### ✅ 路径遍历防护
- `path_config.py` 实现了完整的路径安全验证:
  1. **路径解析验证**: 使用 `Path.resolve()` 后检查是否在允许基目录下
  2. **符号链接检测**: 拒绝符号链接 (`is_symlink()`)
  3. **路径长度限制**: 限制 session_id 长度 ≤255
  4. **危险字符过滤**: `_sanitize_session_id()` 过滤 `< > : " / \ | ? *` 等字符
  5. **相对路径防御**: 检查 `..` 遍历

#### ✅ 输入验证
- `orchestrator.py`: 查询长度验证 (`QUERY_MIN_LENGTH=10`, `QUERY_MAX_LENGTH=5000`)
- `source_registry.py`: URL 协议白名单 (`http/https`)
- `keyword_generator.py`: plan 结构验证（类型检查、非空检查）
- `tier_classifier.py`: 域名标准化和黑名单检查

#### ✅ 并发安全
- 使用 `threading.RLock()` 保护共享状态
- 原子文件写入（先写 `.tmp` 再 `os.replace`）
- ThreadPoolExecutor 有最大工作线程限制 (`MODE_C_MAX_WORKERS=8`)

---

### C. 依赖安全

#### ⚠️ 依赖声明缺失
- **问题**: 未发现 `requirements.txt`、`pyproject.toml`、`setup.py` 或 `Pipfile`
- **影响**: 用户无法直接安装依赖，可能导致运行时错误
- **必需依赖** (通过代码分析推断):
  ```
  # Core (Python 标准库)
  - json, os, sys, re, hashlib, socket, ssl, ipaddress
  - pathlib, threading, datetime, time, copy, subprocess
  - tempfile, warnings, stat, platform, unittest
  - http.client, urllib.parse, concurrent.futures

  # External (需安装)
  - duckduckgo-search (ddgs)  # 搜索功能
  ```

#### ✅ 依赖安全性评估
- **duckduckgo-search**: 知名开源库，用于 DuckDuckGo 搜索，无已知安全问题
- **标准库依赖**: 全部使用 Python 标准库，无外部依赖风险

#### ✅ 无绝对路径泄露
- 代码中使用 `Path(__file__).resolve().parent` 推导路径
- 无硬编码的 `/Users/`、`/home/`、`C:\` 绝对路径

---

### D. 发布准备

#### ✅ .gitignore 完整
```
# 敏感文件
.env, *.pem, *.key, credentials.json, .credentials/

# Python
__pycache__/, *.py[cod], *.egg-info/

# 虚拟环境
venv/, .venv/, env/

# IDE
.idea/, .vscode/, .DS_Store

# 测试/覆盖率
.pytest_cache/, .coverage/
```

#### ✅ 无个人信息泄露
- 无作者邮箱、用户名、个人路径
- 代码注释使用通用描述

#### ⚠️ LICENSE 文件缺失
- **问题**: 未发现 LICENSE 文件
- **建议**: 建议添加 MIT/Apache-2.0 开源许可证

#### ✅ 测试覆盖
- 测试文件完整: `test_safe_fetcher.py`, `test_source_registry.py`, `test_citation_verifier.py`, `test_keyword_generator.py`, `test_tier_classifier.py`, `test_orchestrator.py`
- 使用标准 `unittest` 框架
- 包含 SSRF、路径遍历、并发安全等安全相关测试

---

## 必须修复清单（发布前必改）

### P1-重要
1. **添加依赖声明文件**
   - 创建 `requirements.txt` 或 `pyproject.toml`
   - 内容:
     ```
     duckduckgo-search>=3.0.0
     ```

2. **添加 LICENSE 文件**
   - 建议 MIT 许可证
   - 或根据项目要求选择 Apache-2.0/GPL 等

### P2-建议
3. **添加 README.md**
   - 项目简介
   - 安装说明
   - 使用示例
   - 安全声明

4. **添加 SECURITY.md** (可选)
   - 安全漏洞报告流程
   - 安全更新策略

---

## 安全特性亮点

### 1. SSRF 防护 (safe_fetcher.py)
- DNS 预解析 + IP 黑名单
- 重定向链验证
- 响应大小限制 (512KB)
- 连接超时控制 (10秒)

### 2. 路径安全 (path_config.py)
- 路径遍历防护
- 符号链接检测
- 权限验证 (Unix)
- 原子文件写入

### 3. 输入验证
- 查询长度限制
- URL 协议白名单
- 域名黑名单
- 内容哈希验证

### 4. 并发安全
- RLock 保护共享状态
- ThreadPoolExecutor 限制
- 原子文件操作

---

## 结论

Research Pro 代码库**可以安全地公开发布到 GitHub**。代码具备良好的安全实践，包括完善的 SSRF 防护、路径遍历防护、输入验证和并发安全控制。

**发布前必须完成**:
1. 添加 `requirements.txt` 或 `pyproject.toml`
2. 添加 LICENSE 文件

**发布前建议完成**:
3. 添加 README.md
4. 添加 SECURITY.md (如需要)

---

*审计完成时间: 2026-06-11*  
*审计工具: grep, find, cat, Python 代码静态分析*
