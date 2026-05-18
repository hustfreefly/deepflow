# DeepFlow Frontend UI v2.0

> 浏览器-based 前端界面 for DeepFlow，支持 Webhook 自动触发、SQLite 任务队列、实时状态追踪。

## 技术栈

| 层 | 技术 | 说明 |
|:---|:---|:---|
| 前端 | React 18 + TypeScript + Tailwind CSS | Google Material Design 风格 |
| 后端 | FastAPI (Python) | REST API，localhost:8000 |
| 通信 | HTTP + Webhook + SQLite | Webhook 自动触发，SQLite 持久化 |

## 新特性 (v2.0)

### Webhook 自动触发
- 任务提交后自动调用 OpenClaw Webhook (`POST /hooks/wake`)
- 主 Agent 收到通知后自动启动 DeepFlow 执行
- 无需手动轮询或 Consumer 进程

### SQLite 任务队列
- 持久化任务存储（替代文件队列）
- 支持任务重试（Webhook 失败自动标记）
- 任务状态追踪：pending → running → completed/failed

### 增强状态 API
- 从 Blackboard 实时读取执行状态
- 9 阶段 Pipeline 可视化
- Harness 质量分数展示

## 快速开始

### 1. 配置 OpenClaw Webhook

```bash
# 运行配置脚本
cd ../scripts
./setup_webhook_config.sh

# 验证配置
./verify_webhook.sh
```

### 2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 启动后端服务

```bash
cd backend
uvicorn main:app --reload --port 8000
```

服务启动后访问 http://localhost:8000/docs 查看 API 文档。

### 4. 安装前端依赖

```bash
cd web
npm install
```

### 5. 启动前端开发服务器

```bash
cd web
npm run dev
```

前端启动后访问 http://localhost:3000。

## 项目结构

```
frontend/
├── backend/                 # FastAPI 后端
│   ├── main.py             # 应用入口（v1 + v2 路由）
│   ├── requirements.txt    # Python 依赖
│   ├── data/               # SQLite 数据库
│   │   └── tasks.db       # 任务队列数据库
│   ├── routers/
│   │   ├── health.py      # 健康检查
│   │   ├── tasks.py       # v1: 文件队列（兼容）
│   │   ├── status.py      # v1: 文件状态（兼容）
│   │   ├── tasks_v2.py    # v2: SQLite + Webhook ⭐
│   │   ├── status_v2.py   # v2: Blackboard 状态 ⭐
│   │   └── consumer.py    # 任务队列 Consumer（备用）
│   ├── database.py         # SQLite 数据库模型 ⭐
│   └── utils/
│       └── feishu_doc.py  # 飞书文档创建
└── web/                     # React 前端（v1 兼容）
    ├── src/
    │   ├── api/            # API 客户端（需更新为 v2）
    │   └── ...
    └── ...
```

## API 端点

### v2 API (Webhook 集成)

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/api/v2/tasks` | 创建任务 + Webhook 通知 |
| GET | `/api/v2/tasks/{session_id}` | 获取任务详情 |
| GET | `/api/v2/tasks` | 列出所有任务 |
| GET | `/api/v2/status/{session_id}` | 从 Blackboard 获取状态 |
| GET | `/api/v2/report/{session_id}` | 从 Blackboard 获取报告 |

### v1 API (兼容)

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/health` | 健康检查 + OpenClaw 状态 |
| POST | `/api/tasks` | 创建任务（文件队列） |
| GET | `/api/tasks/{session_id}` | 获取任务详情 |
| GET | `/api/status/{session_id}` | 获取执行状态 |
| GET | `/api/reports/{session_id}` | 获取最终报告 |

## Webhook 流程

```
用户提交任务 → FastAPI 接收 → 写入 SQLite → 调用 Webhook
                                                    ↓
                                              OpenClaw Gateway
                                                    ↓
                                               主 Agent 接收
                                                    ↓
                                         webhook_task_processor
                                                    ↓
                                              sessions_spawn
                                                    ↓
                                              DeepFlow 执行
                                                    ↓
                                              写入 Blackboard
                                                    ↓
                                              前端轮询获取
```

## 配置

### 环境变量

```bash
# ~/.openclaw/.webhook_env
HOOKS_TOKEN=ff3382...aefe
GATEWAY_PORT=18789
HOOKS_URL=http://127.0.0.1:18789/hooks/wake
```

### OpenClaw Webhook 配置

```json
{
  "hooks": {
    "enabled": true,
    "token": "ff3382...aefe",
    "path": "/hooks",
    "allowedAgentIds": ["main"]
  }
}
```

## 开发状态

### Phase 1: Webhook 配置 ✅
- [x] OpenClaw Webhook 配置脚本
- [x] Token 生成与验证
- [x] Gateway 重启流程

### Phase 2: FastAPI Webhook 集成 ✅
- [x] SQLite 数据库 (`database.py`)
- [x] 任务提交 API (`tasks_v2.py`)
- [x] Webhook 调用（带重试）
- [x] 状态查询 API (`status_v2.py`)

### Phase 3: 主 Agent 处理器 ✅
- [x] Webhook 任务处理器 (`webhook_task_processor.py`)
- [x] spawn_fn 注入模式
- [x] DeepFlow 任务构建

### Phase 4: Cron Job 兜底 ⏭️
- [ ] Cron Job 配置脚本
- [ ] 失败任务重试机制

### Phase 5: 前端更新 ⏭️
- [ ] 更新 API 客户端为 v2
- [ ] 实时状态推送（可选）

## 迁移指南 (v1 → v2)

### 后端

1. 启动后端时会自动创建 SQLite 数据库
2. v1 API 保持兼容，v2 API 并行运行
3. Consumer 可作为 Webhook 备用方案

### 前端

1. 将 API 调用从 `/api/tasks` 改为 `/api/v2/tasks`
2. 状态查询从文件轮询改为 Blackboard 读取
3. 可选：添加 WebSocket 实时推送

## 调试

### 检查 Webhook 配置

```bash
openclaw config get hooks.enabled
openclaw config get hooks.path
openclaw config get hooks.token
```

### 测试 Webhook

```bash
curl -X POST http://127.0.0.1:18789/hooks/wake \
  -H "Authorization: Bearer $HOOKS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"test","mode":"now"}'
```

### 查看任务队列

```bash
sqlite3 ~/.openclaw/workspace/.deepflow/frontend/data/tasks.db \
  "SELECT * FROM tasks ORDER BY created_at DESC;"
```

## 参考

- [架构设计文档](../docs/FRONTEND_DESIGN.md)
- [Webhook 集成契约](../cage/frontend_webhook_integration_v1.0.yaml)
- [标准执行模式](../docs/STANDARD_EXECUTION.md)
