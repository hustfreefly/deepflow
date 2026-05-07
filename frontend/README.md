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
│   └── routers/
│       └── health.py       # 健康检查 API
└── web/                     # React 前端
    ├── index.html           # HTML 入口
    ├── vite.config.ts       # Vite 配置
    ├── tailwind.config.js   # Tailwind 配置
    └── src/
        ├── main.tsx         # React 入口
        ├── App.tsx          # 主应用
        ├── index.css        # 全局样式
        └── components/
            └── Header.tsx   # 头部组件
```

## API 端点

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/health` | 健康检查 + OpenClaw 状态 |

## 开发状态

**Phase 1: Foundation** ✅
- [x] FastAPI 后端骨架
- [x] React 前端骨架
- [x] OpenClaw 状态检测
- [x] Google Material Design 风格

**Phase 2: Task Submission** ⏳
- [ ] Domain 选择界面
- [ ] 动态参数表单
- [ ] 任务提交 API

**Phase 3: Progress Visualization** ⏳
- [ ] 实时进度轮询
- [ ] Pipeline 阶段可视化
- [ ] Harness 质量分数展示

**Phase 4: Report & Export** ⏳
- [ ] Markdown 报告渲染
- [ ] 复制/下载/飞书发送
- [ ] 历史记录列表

## 约束

- 前端是 UI 层 ONLY，OpenClaw 是核心引擎
- 所有 OpenClaw 调用通过后端 FastAPI
- 单任务限制（运行中不可提交新任务）
- 本地访问 only（localhost）

## 参考

- [架构设计文档](../docs/FRONTEND_DESIGN.md)
- [需求文档](../cage/frontend_design_requirements_v1.2.md)
