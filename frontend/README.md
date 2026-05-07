# DeepFlow Frontend UI

> 浏览器-based 前端界面 for DeepFlow，简化任务提交、可视化分析进度、展示 Markdown 报告。

## 技术栈

| 层 | 技术 | 说明 |
|:---|:---|:---|
| 前端 | React 18 + TypeScript + Tailwind CSS | Google Material Design 风格 |
| 后端 | FastAPI (Python) | REST API，localhost:8000 |
| 通信 | HTTP + 文件轮询 | 3-5 秒进度更新 |

## 快速开始

### 1. 安装后端依赖

```bash
cd frontend/backend
pip install -r requirements.txt
```

### 2. 启动后端服务

```bash
cd frontend/backend
uvicorn main:app --reload --port 8000
```

服务启动后访问 http://localhost:8000/docs 查看 API 文档。

### 3. 安装前端依赖

```bash
cd frontend/web
npm install
```

### 4. 启动前端开发服务器

```bash
cd frontend/web
npm run dev
```

前端启动后访问 http://localhost:3000。

## 项目结构

```
frontend/
├── backend/                 # FastAPI 后端
│   ├── main.py             # 应用入口
│   ├── requirements.txt    # Python 依赖
│   ├── utils/
│   │   ├── __init__.py
│   │   └── feishu_doc.py   # 飞书文档创建 (markdown → docx)
│   └── routers/
│       ├── health.py       # 健康检查 + OpenClaw 状态
│       ├── tasks.py        # 任务创建 + 文件队列
│       └── status.py       # 状态轮询 + 报告获取 + 飞书导出
└── web/                     # React 前端
    ├── index.html           # HTML 入口 (Material Icons CDN)
    ├── vite.config.ts       # Vite 配置 (proxy: /api → :8000)
    ├── tailwind.config.js   # Tailwind + Material Design 配色
    └── src/
        ├── main.tsx         # React 入口 + BrowserRouter
        ├── App.tsx          # 首页 (Domain 选择)
        ├── index.css        # 全局样式
        ├── components/
        │   └── Header.tsx   # 头部 + 导航 + 系统状态
        └── pages/
            ├── TaskForm.tsx      # 任务表单 (Solution/Investment)
            ├── ProgressPage.tsx  # 进度轮询 + 管线可视化
            ├── ReportPage.tsx    # Markdown 报告渲染 + 导出
            └── HistoryPage.tsx   # 历史记录列表
```

## API 端点

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/health` | 健康检查 + OpenClaw 状态 |
| POST | `/api/tasks` | 创建分析任务 (文件队列) |
| GET | `/api/tasks/{session_id}` | 获取任务详情 |
| GET | `/api/status/{session_id}` | 获取管线执行状态 |
| GET | `/api/reports/{session_id}` | 获取最终报告 (markdown) |
| POST | `/api/reports/{session_id}/export` | 导出报告 (feishu/local) |
| GET | `/api/sessions` | 获取历史会话列表 |

## 开发状态

**Phase 1: Foundation** ✅
- [x] FastAPI 后端骨架 (3 routers: health/tasks/status)
- [x] React 18 + TypeScript + Tailwind CSS + Material Design
- [x] 5 页面路由 + 导航功能
- [x] OpenClaw 状态检测
- [x] TypeScript 零错误编译

**Phase 2: Task Submission** ✅
- [x] Domain 选择界面 (Solution/Investment/Coming Soon)
- [x] 动态参数表单 (Topic/Code/Constraints/Stakeholders)
- [x] 任务提交 API → 文件队列 (task_queue/)

**Phase 3: Progress Visualization** ✅
- [x] 实时进度轮询 (3 秒间隔)
- [x] Pipeline 9 阶段可视化 (含 Worker 进度)
- [x] Harness 质量分数展示 (完整性/必要性/目标一致性)
- [x] 完成自动跳转报告页

**Phase 4: Report & Export** ✅
- [x] Markdown 报告渲染 (简化版)
- [x] 复制 / 下载
- [x] **飞书发送 → 创建 docx 文档 + API 发送** (方案B)
- [x] 历史记录列表 (按 domain 筛选)

**Phase 5: Task Queue Consumer** ✅ (2026-05-08)
- [x] 后台任务队列消费机制 (`routers/consumer.py`)
- [x] 每5秒轮询 task_queue/ 目录
- [x] DeepFlow 执行桥接 (模拟/真实)
- [x] 自动启动 Consumer (FastAPI startup event)

**Phase 6: Blackboard Integration** ✅ (2026-05-08)
- [x] BlackboardBridge 状态管理 (`core/blackboard_bridge.py`)
- [x] 9阶段 Pipeline 状态追踪
- [x] Harness 质量分数记录
- [x] Report 文件生成

**Phase 7: E2E Testing** ✅ (2026-05-08)
- [x] 完整流程测试 (`tests/e2e/test_frontend_flow.py`)
- [x] 契约验证脚本 (`check_frontend_completion.py`)
- [x] 8/8 契约检查通过

**待实现：**
- [ ] 替换模拟执行为真实 DeepFlow spawn (需 Agent 环境)
- [ ] 飞书导出: markdown 列表 → 原生列表 block 格式
- [ ] 前端构建产物 + 生产部署

## 约束

- 前端是 UI 层 ONLY，OpenClaw 是核心引擎
- 所有 OpenClaw 调用通过后端 FastAPI
- 单任务限制（运行中不可提交新任务）
- 本地访问 only（localhost）

## 参考

- [架构设计文档](../docs/FRONTEND_DESIGN.md)
- [需求文档](../cage/frontend_design_requirements_v1.2.md)
