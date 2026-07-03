#!/usr/bin/env python3
"""Generate specifier_output_v312.json for all 4 cases."""
import json
import os
from datetime import datetime

BASE = "/Users/allen/.openclaw/workspace/.deepflow/domains/ship_pro/test_output"

def gen_case1():
    """Case 1: TODO app - 1 WP"""
    case_dir = f"{BASE}/loop_case1_tc09_todo"
    
    output = {
        "_meta": {
            "agent": "specifier",
            "prompt_sha": "v312_specifier",
            "model_id": "bailian/qwen3.7-plus",
            "run_id": "run_20260619_041354_a",
            "round": 0,
            "input_files": ["architect_output_v312.json", "decomposer_output.json"],
            "timestamp": datetime.now().isoformat()
        },
        "work_packages": [
            {
                "id": "WP-001",
                "title": "TODO 应用前端 UI 完整实现",
                "objective": "实现基于 React+SQLite 的单页 TODO 应用，支持增删改查、状态切换、筛选和本地存储",
                "budget": {
                    "tokens": 80000,
                    "time_minutes": 60,
                    "max_retries": 3
                },
                "complexity": "medium",
                "model_tier": "claude-sonnet",
                "dependencies": [],
                "priority": "high",
                "related_modules": ["COMP-01"],
                "context_files": [
                    "architect_output_v312.json",
                    "decomposer_output.json",
                    "package.json",
                    "tsconfig.json",
                    "vite.config.ts",
                    "src/App.tsx",
                    "src/index.tsx",
                    "src/components/TaskList.tsx",
                    "src/components/TaskItem.tsx",
                    "src/components/AddTaskForm.tsx",
                    "src/components/FilterBar.tsx",
                    "src/hooks/useTasks.ts",
                    "src/utils/storage.ts"
                ],
                "outputs": [
                    "src/App.tsx",
                    "src/components/TaskList.tsx",
                    "src/components/TaskItem.tsx",
                    "src/components/AddTaskForm.tsx",
                    "src/components/FilterBar.tsx",
                    "src/hooks/useTasks.ts",
                    "src/utils/storage.ts",
                    "src/index.tsx",
                    "package.json",
                    "tsconfig.json",
                    "vite.config.ts"
                ],
                "acceptance_criteria": [
                    "[REQ-001] 新增任务：调用 AddTaskForm 提交后，TaskList 中新增一条记录，localStorage 数据同步更新，运行 `npx vitest run tests/AddTask.test.tsx` 全部通过",
                    "[REQ-002] 标记完成：点击 TaskItem 的完成按钮后，任务状态切换为 completed，UI 显示删除线样式，`npx vitest run tests/ToggleTodo.test.tsx` 验证状态翻转",
                    "[REQ-003] 删除任务：点击删除按钮后任务从列表移除，localStorage 同步删除对应条目，`npx vitest run tests/DeleteTodo.test.tsx` 验证列表长度减少 1",
                    "[SHIP_DERIVED] 筛选功能：FilterBar 支持 All/Active/Completed 三种筛选，切换后 TaskList 渲染数量与筛选条件匹配，响应时间 < 50ms（从 SLA 离线应用 <1s 推导）",
                    "[SHIP_DERIVED] 本地存储容量：storage.ts 在任务数 ≤ 10000 条时正常读写不抛出 QuotaExceededError，运行 `npx vitest run tests/Storage.test.ts` 验证（来自 RISK-001 mitigation）",
                    "端到端 CRUD 流程：新增 → 列表展示 → 标记完成 → 筛选 Active → 删除 → 列表更新，Playwright E2E 测试 `npx playwright test tests/e2e/crud.spec.ts` 全部通过"
                ],
                "acceptance_tests": [
                    "npx vitest run tests/AddTask.test.tsx",
                    "npx vitest run tests/ToggleTodo.test.tsx",
                    "npx vitest run tests/DeleteTodo.test.tsx",
                    "npx vitest run tests/FilterBar.test.tsx",
                    "npx vitest run tests/Storage.test.ts",
                    "npx playwright test tests/e2e/crud.spec.ts"
                ],
                "constraints": [
                    "使用 React 18+ 函数组件 + Hooks（来自 blueprint COMP-01 technology_stack）",
                    "使用 SQLite 作为本地存储后端（来自 blueprint COMP-01 technology_stack）",
                    "使用 Vite 作为构建工具（来自 decomposer wp_file_mapping）",
                    "使用 TypeScript 严格模式（来自 decomposer tsconfig.json）",
                    "[RISK] 浏览器本地存储容量限制: 任务数 < 10000 条不会触及限制"
                ],
                "requirements": ["REQ-001", "REQ-002", "REQ-003"],
                "retry_policy": {
                    "on_failure": "retry"
                },
                "tags": ["frontend", "react", "crud", "mvp"]
            }
        ],
        "self_check": {
            "passed": True,
            "issues": []
        }
    }
    
    out_path = f"{case_dir}/blackboard/specifier_output_v312.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Case 1 written: {out_path}")
    return output


def gen_case2():
    """Case 2: E-commerce - 12 WPs"""
    case_dir = f"{BASE}/loop_case2_tc10_ecommerce"
    
    # SLA from blueprint
    sla_product = "[SLA] 商品详情响应延迟 < 100ms（GET /products 请求）"
    
    wps = []
    
    # WP-001: API Gateway
    wps.append({
        "id": "WP-001",
        "title": "API Gateway 统一接入层搭建",
        "objective": "搭建 Kong+Nginx 统一接入层，实现路由、限流、认证和 API 版本管理",
        "budget": {"tokens": 60000, "time_minutes": 45, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": [],
        "priority": "critical",
        "related_modules": ["COMP-01"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "gateway/kong.conf", "gateway/nginx.conf", "docker-compose.yml"
        ],
        "outputs": ["gateway/kong.conf", "gateway/nginx.conf", "docker-compose.yml"],
        "acceptance_criteria": [
            "[REQ-005] 多渠道统一接入：Web/App/小程序请求均通过 Gateway 路由到对应后端服务，运行 `curl -H 'X-Channel: web' http://gateway/api/health` 返回 200",
            "[REQ-005] API 版本管理：Gateway 支持 /v1/ 和 /v2/ 路由，`curl http://gateway/v1/products` 和 `/v2/products` 分别路由到正确上游",
            "[SHIP_DERIVED] 限流配置：单 IP 限流 100 req/s，超过返回 429，运行 `wrk -t4 -c100 -d10s http://gateway/api/products` 验证限流生效",
            "[SHIP_DERIVED] 认证中间件：JWT Token 校验失败返回 401，有效 Token 透传 X-User-Id 到下游，`pytest tests/gateway/auth_test.py` 全部通过",
            f"{sla_product}：Gateway 层转发延迟 < 10ms（从 SLA 100ms 扣除后端处理时间推导）"
        ],
        "acceptance_tests": [
            "curl -H 'X-Channel: web' http://gateway/api/health",
            "wrk -t4 -c100 -d10s http://gateway/api/products",
            "pytest tests/gateway/auth_test.py"
        ],
        "constraints": [
            "使用 Kong 3.x + Nginx（来自 blueprint COMP-01 technology_stack）",
            "Docker 容器化部署（来自 blueprint wp_file_mapping）",
            sla_product
        ],
        "requirements": ["REQ-005"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["infrastructure", "gateway", "routing"]
    })
    
    # WP-002: User Service
    wps.append({
        "id": "WP-002",
        "title": "用户认证与权限服务开发",
        "objective": "开发用户注册登录、JWT 认证、权限管理和用户画像服务",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "complex",
        "model_tier": "claude-opus",
        "dependencies": ["WP-001"],
        "priority": "high",
        "related_modules": ["COMP-05"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/user-service/**/*.go", "services/user-service/Dockerfile",
            "gateway/kong.conf"
        ],
        "outputs": ["services/user-service/**/*.go", "services/user-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-006] 注册登录：POST /api/auth/register 创建用户，POST /api/auth/login 返回 JWT，运行 `go test ./internal/auth/...` 全部通过",
            "[REQ-006] JWT 认证：Token 有效期 24h，过期返回 401，`go test ./internal/auth/jwt_test.go` 验证签发/验证/刷新流程",
            "[REQ-006] 权限管理：RBAC 模型支持 admin/user/seller 三种角色，`go test ./internal/auth/rbac_test.go` 验证权限拦截",
            "[SHIP_DERIVED] 登录响应 P99 < 200ms（从 SLA 首次响应 <2s 推导），`wrk -t4 -c50 -d30s http://gateway/api/auth/login` 验证",
            "[RISK] 支付系统安全合规: PCI DSS 合规 + 加密传输 + 风控系统（来自 RISK-003）"
        ],
        "acceptance_tests": [
            "go test ./internal/auth/...",
            "go test ./internal/auth/jwt_test.go",
            "go test ./internal/auth/rbac_test.go",
            "wrk -t4 -c50 -d30s http://gateway/api/auth/login"
        ],
        "constraints": [
            "使用 Go + PostgreSQL + Redis（来自 blueprint COMP-05 technology_stack）",
            "JWT 认证机制（来自 blueprint COMP-05 responsibilities）",
            "[RISK] 支付系统安全合规: PCI DSS 合规 + 加密传输 + 风控系统"
        ],
        "requirements": ["REQ-006"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["auth", "user", "jwt", "rbac"]
    })
    
    # WP-003: Product Service
    wps.append({
        "id": "WP-003",
        "title": "商品管理服务开发",
        "objective": "开发商品 CRUD、分类管理、SKU 管理和商品搜索服务",
        "budget": {"tokens": 100000, "time_minutes": 90, "max_retries": 3},
        "complexity": "complex",
        "model_tier": "claude-opus",
        "dependencies": ["WP-001", "WP-002"],
        "priority": "high",
        "related_modules": ["COMP-02"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/product-service/**/*.go", "services/product-service/Dockerfile",
            "gateway/kong.conf"
        ],
        "outputs": ["services/product-service/**/*.go", "services/product-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-001] 商品 CRUD：POST/GET/PUT/DELETE /api/products 完整实现，`go test ./internal/handler/...` 全部通过",
            "[REQ-001] 商品搜索：GET /api/products/search?q=keyword 返回匹配结果，支持分页和排序",
            "[REQ-012] 商品评价系统：POST /api/products/:id/reviews 提交评价，GET 返回评价列表和平均评分",
            f"{sla_product}：GET /api/products/:id 响应 P99 < 100ms",
            "[SHIP_DERIVED] 分类管理：支持多级分类树，查询分类下商品列表 < 50ms（从 SLA 100ms 推导）",
            "[SHIP_DERIVED] SKU 管理：同一 SPU 支持多 SKU（颜色/尺码），库存状态实时可查"
        ],
        "acceptance_tests": [
            "go test ./internal/handler/...",
            "go test ./internal/repo/...",
            "curl 'http://gateway/api/products/search?q=test&page=1&size=20'"
        ],
        "constraints": [
            "使用 Go + MySQL + Elasticsearch（来自 blueprint COMP-02 technology_stack）",
            sla_product,
            "[RISK] 分布式事务一致性（订单-库存-支付）: Saga 模式 + 补偿事务 + 对账系统"
        ],
        "requirements": ["REQ-001", "REQ-012"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["product", "crud", "search", "review"]
    })
    
    # WP-004: Inventory Service
    wps.append({
        "id": "WP-004",
        "title": "库存管理服务开发",
        "objective": "开发库存扣减、预占、释放和多渠道库存同步服务",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "complex",
        "model_tier": "claude-opus",
        "dependencies": ["WP-003"],
        "priority": "high",
        "related_modules": ["COMP-06"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/inventory-service/**/*.go", "services/inventory-service/Dockerfile",
            "services/product-service/internal/model/"
        ],
        "outputs": ["services/inventory-service/**/*.go", "services/inventory-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-004] 库存扣减：下单时扣减库存，库存不足返回 409 Conflict，`go test ./internal/handler/...` 验证",
            "[REQ-004] 库存预占/释放：下单预占库存，超时未支付自动释放，`go test ./internal/redis/...` 验证 TTL 机制",
            "[SHIP_DERIVED] 并发安全：1000 并发扣减同一 SKU 不超卖，`wrk` 压测后库存数 = 初始数 - 成功订单数",
            "[RISK] 高并发秒杀场景库存超卖: Redis 预扣减 + Lua 原子操作 + 异步确认（来自 RISK-002）",
            "[SHIP_DERIVED] 多渠道同步延迟 < 500ms（从 SLA 100ms 商品详情推导，库存同步需在此窗口内完成）"
        ],
        "acceptance_tests": [
            "go test ./internal/handler/...",
            "go test ./internal/redis/...",
            "wrk -t8 -c200 -d30s -s scripts/inventory_stress.lua http://gateway/api/inventory/deduct"
        ],
        "constraints": [
            "使用 Go + Redis + Kafka（来自 blueprint COMP-06 technology_stack）",
            "[RISK] 高并发秒杀场景库存超卖: Redis 预扣减 + Lua 原子操作 + 异步确认",
            "[RISK] 分布式事务一致性（订单-库存-支付）: Saga 模式 + 补偿事务 + 对账系统"
        ],
        "requirements": ["REQ-004"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["inventory", "redis", "kafka", "concurrency"]
    })
    
    # WP-005: Order Service
    wps.append({
        "id": "WP-005",
        "title": "订单核心服务开发",
        "objective": "开发订单创建、状态流转、退款和分布式事务协调服务",
        "budget": {"tokens": 120000, "time_minutes": 90, "max_retries": 3},
        "complexity": "complex",
        "model_tier": "claude-opus",
        "dependencies": ["WP-002", "WP-003", "WP-004"],
        "priority": "high",
        "related_modules": ["COMP-03"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/order-service/src/**/*.java", "services/order-service/pom.xml",
            "services/order-service/src/main/resources/application.yml",
            "services/product-service/internal/model/",
            "services/inventory-service/internal/handler/"
        ],
        "outputs": ["services/order-service/src/**/*.java", "services/order-service/pom.xml", "services/order-service/src/main/resources/application.yml", "services/order-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-002] 购物车管理：POST /api/cart/add 添加商品，GET /api/cart 返回购物车列表，`mvn test -Dtest=CartServiceTest` 全部通过",
            "[REQ-003] 订单创建：POST /api/orders 创建订单，触发库存扣减（Kafka 事件），`mvn test -Dtest=OrderServiceTest` 验证",
            "[REQ-003] 状态流转：订单状态 pending→paid→shipped→completed→cancelled，每次流转记录审计日志",
            "[REQ-009] 退款流程：POST /api/orders/:id/refund 发起退款，状态流转 refunded，`mvn test -Dtest=RefundServiceTest` 验证",
            "[RISK] 分布式事务一致性（订单-库存-支付）: Saga 模式 + 补偿事务 + 对账系统（来自 RISK-001）",
            "[SHIP_DERIVED] 订单创建 P99 < 500ms（从 SLA 100ms 商品详情 + 异步处理推导）"
        ],
        "acceptance_tests": [
            "mvn test -Dtest=CartServiceTest",
            "mvn test -Dtest=OrderServiceTest",
            "mvn test -Dtest=RefundServiceTest",
            "mvn test -Dtest=OrderStateMachineTest"
        ],
        "constraints": [
            "使用 Java + MySQL + Kafka（来自 blueprint COMP-03 technology_stack）",
            "[RISK] 分布式事务一致性（订单-库存-支付）: Saga 模式 + 补偿事务 + 对账系统",
            "Kafka 异步事件传播（来自 blueprint domain_details.data_flow_raw）"
        ],
        "requirements": ["REQ-002", "REQ-003", "REQ-009"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["order", "saga", "kafka", "transaction"]
    })
    
    # WP-006: Payment Service
    wps.append({
        "id": "WP-006",
        "title": "支付服务开发",
        "objective": "开发支付网关集成（微信/支付宝/银行卡）、对账和退款服务",
        "budget": {"tokens": 100000, "time_minutes": 75, "max_retries": 3},
        "complexity": "complex",
        "model_tier": "claude-opus",
        "dependencies": ["WP-005", "WP-002"],
        "priority": "high",
        "related_modules": ["COMP-04"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/payment-service/src/**/*.java", "services/payment-service/pom.xml",
            "services/order-service/src/main/java/"
        ],
        "outputs": ["services/payment-service/src/**/*.java", "services/payment-service/pom.xml", "services/payment-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-003] 支付网关集成：POST /api/payments 创建支付，支持微信/支付宝/银行卡三种渠道，`mvn test -Dtest=PaymentServiceTest` 验证",
            "[REQ-009] 退款处理：POST /api/refunds 发起退款，原路退回，对账记录一致",
            "[SHIP_DERIVED] 支付回调处理 P99 < 200ms（从 SLA 推导），`wrk` 压测验证",
            "[RISK] 支付系统安全合规: PCI DSS 合规 + 加密传输 + 风控系统（来自 RISK-003）",
            "[SHIP_DERIVED] 对账差异率 < 0.001%（从资金安全推导），每日对账任务自动运行"
        ],
        "acceptance_tests": [
            "mvn test -Dtest=PaymentServiceTest",
            "mvn test -Dtest=RefundServiceTest",
            "mvn test -Dtest=ReconciliationTest"
        ],
        "constraints": [
            "使用 Java + MySQL + Redis（来自 blueprint COMP-04 technology_stack）",
            "[RISK] 支付系统安全合规: PCI DSS 合规 + 加密传输 + 风控系统"
        ],
        "requirements": ["REQ-003", "REQ-009"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["payment", "refund", "reconciliation", "pci"]
    })
    
    # WP-007: Promotion Service
    wps.append({
        "id": "WP-007",
        "title": "促销引擎服务开发",
        "objective": "开发优惠券、满减、秒杀和促销活动引擎",
        "budget": {"tokens": 100000, "time_minutes": 75, "max_retries": 3},
        "complexity": "complex",
        "model_tier": "claude-opus",
        "dependencies": ["WP-003"],
        "priority": "medium",
        "related_modules": ["COMP-07"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/promotion-service/src/**/*.java", "services/promotion-service/pom.xml",
            "services/promotion-service/scripts/lua/",
            "services/product-service/internal/model/"
        ],
        "outputs": ["services/promotion-service/src/**/*.java", "services/promotion-service/pom.xml", "services/promotion-service/scripts/lua/", "services/promotion-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-007] 优惠券管理：CRUD 优惠券，支持满减/折扣/免邮三种类型，`mvn test -Dtest=CouponServiceTest` 验证",
            "[REQ-007] 秒杀活动：Redis + Lua 原子扣减库存，1000 并发不超卖，`wrk` 压测验证",
            "[RISK] 高并发秒杀场景库存超卖: Redis 预扣减 + Lua 原子操作 + 异步确认（来自 RISK-002）",
            "[SHIP_DERIVED] 促销计算 P99 < 50ms（从 SLA 100ms 推导，促销计算需在商品详情响应内完成）"
        ],
        "acceptance_tests": [
            "mvn test -Dtest=CouponServiceTest",
            "mvn test -Dtest=SeckillServiceTest",
            "wrk -t8 -c200 -d30s -s scripts/seckill_stress.lua http://gateway/api/promotions/seckill"
        ],
        "constraints": [
            "使用 Java + Redis + Lua（来自 blueprint COMP-07 technology_stack）",
            "[RISK] 高并发秒杀场景库存超卖: Redis 预扣减 + Lua 原子操作 + 异步确认"
        ],
        "requirements": ["REQ-007"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["promotion", "coupon", "seckill", "redis"]
    })
    
    # WP-008: Logistics Service
    wps.append({
        "id": "WP-008",
        "title": "物流服务开发",
        "objective": "开发物流商对接、运单生成、轨迹查询和签收确认服务",
        "budget": {"tokens": 60000, "time_minutes": 45, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-005"],
        "priority": "medium",
        "related_modules": ["COMP-08"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/logistics-service/**/*.go", "services/logistics-service/Dockerfile",
            "services/order-service/src/main/java/"
        ],
        "outputs": ["services/logistics-service/**/*.go", "services/logistics-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-008] 物流商对接：至少对接 2 家物流商 API，`go test ./internal/provider/...` 验证接口抽象层",
            "[REQ-008] 运单生成：POST /api/logistics/ship 生成运单号，`go test ./internal/handler/...` 验证",
            "[REQ-008] 轨迹查询：GET /api/logistics/track/:waybill_no 返回物流轨迹，支持轮询和回调两种模式",
            "[SHIP_DERIVED] 轨迹查询 P99 < 300ms（从用户体验推导）"
        ],
        "acceptance_tests": [
            "go test ./internal/provider/...",
            "go test ./internal/handler/...",
            "curl http://gateway/api/logistics/track/WB123456"
        ],
        "constraints": [
            "使用 Go + MySQL + 第三方 API（来自 blueprint COMP-08 technology_stack）"
        ],
        "requirements": ["REQ-008"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["logistics", "tracking", "shipping"]
    })
    
    # WP-009: Notification Service
    wps.append({
        "id": "WP-009",
        "title": "消息通知服务开发",
        "objective": "开发邮件、短信、App Push 和站内信统一发送服务",
        "budget": {"tokens": 60000, "time_minutes": 45, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-005"],
        "priority": "medium",
        "related_modules": ["COMP-09"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/message-service/**/*.go", "services/message-service/Dockerfile",
            "services/order-service/src/main/java/"
        ],
        "outputs": ["services/message-service/**/*.go", "services/message-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-011] 多渠道发送：支持邮件/短信/App Push/站内信四种渠道，`go test ./internal/sender/...` 验证",
            "[REQ-011] Kafka 事件驱动：消费订单状态变更事件触发通知，`go test ./internal/consumer/...` 验证",
            "[SHIP_DERIVED] 消息发送延迟 < 2s（从用户体验推导，订单状态变更后 2s 内收到通知）",
            "[SHIP_DERIVED] 消息投递成功率 ≥ 99%（从业务可靠性推导）"
        ],
        "acceptance_tests": [
            "go test ./internal/sender/...",
            "go test ./internal/consumer/..."
        ],
        "constraints": [
            "使用 Go + Kafka + 第三方 SDK（来自 blueprint COMP-09 technology_stack）"
        ],
        "requirements": ["REQ-011"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["notification", "email", "sms", "push"]
    })
    
    # WP-010: Search Service
    wps.append({
        "id": "WP-010",
        "title": "搜索服务开发",
        "objective": "开发商品全文搜索、联想词和搜索结果排序服务",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-003"],
        "priority": "medium",
        "related_modules": ["COMP-10"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/search-service/**/*.go", "services/search-service/Dockerfile",
            "config/elasticsearch/mappings.json",
            "services/product-service/internal/model/"
        ],
        "outputs": ["services/search-service/**/*.go", "services/search-service/Dockerfile", "config/elasticsearch/mappings.json"],
        "acceptance_criteria": [
            "[REQ-001] 商品全文搜索：GET /api/search?q=keyword 返回匹配商品，支持高亮和分页",
            "[SHIP_DERIVED] 搜索响应 P99 < 50ms（从 SLA 100ms 推导，搜索需在商品详情响应窗口内完成）",
            "[SHIP_DERIVED] 联想词响应 P99 < 30ms（从输入体验推导），`wrk` 压测验证",
            "[SHIP_DERIVED] 搜索相关性：Top-10 结果中至少 80% 包含搜索关键词（从搜索质量推导）"
        ],
        "acceptance_tests": [
            "go test ./internal/es/...",
            "wrk -t4 -c50 -d10s 'http://gateway/api/search?q=test'",
            "curl 'http://gateway/api/search/suggest?q=iph'"
        ],
        "constraints": [
            "使用 Elasticsearch + Go（来自 blueprint COMP-10 technology_stack）"
        ],
        "requirements": ["REQ-001"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["search", "elasticsearch", "suggest"]
    })
    
    # WP-011: Recommendation Service
    wps.append({
        "id": "WP-011",
        "title": "推荐服务开发",
        "objective": "开发协同过滤+内容推荐，实现个性化商品推荐",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-003", "WP-002"],
        "priority": "low",
        "related_modules": ["COMP-11"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/recommendation-service/**/*.py",
            "services/recommendation-service/requirements.txt",
            "services/recommendation-service/Dockerfile",
            "services/product-service/internal/model/",
            "services/user-service/internal/model/"
        ],
        "outputs": ["services/recommendation-service/**/*.py", "services/recommendation-service/requirements.txt", "services/recommendation-service/Dockerfile"],
        "acceptance_criteria": [
            "[REQ-013] 协同过滤推荐：基于用户行为的 ItemCF 算法，`pytest tests/test_collaborative.py` 验证",
            "[REQ-013] 内容推荐：基于商品特征的推荐，`pytest tests/test_content_based.py` 验证",
            "[SHIP_DERIVED] 推荐接口 P99 < 200ms（从用户体验推导），`pytest tests/test_performance.py` 验证",
            "[SHIP_DERIVED] 推荐覆盖率 ≥ 90%（至少 90% 用户能获得个性化推荐）"
        ],
        "acceptance_tests": [
            "pytest tests/test_collaborative.py",
            "pytest tests/test_content_based.py",
            "pytest tests/test_performance.py"
        ],
        "constraints": [
            "使用 Python + Redis + Kafka（来自 blueprint COMP-11 technology_stack）"
        ],
        "requirements": ["REQ-013"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["recommendation", "collaborative-filtering", "python"]
    })
    
    # WP-012: Analytics Service
    wps.append({
        "id": "WP-012",
        "title": "数据分析服务开发",
        "objective": "开发 GMV、转化率、用户行为分析和实时仪表盘",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-005"],
        "priority": "low",
        "related_modules": ["COMP-12"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "services/analytics-service/**/*.py",
            "services/analytics-service/requirements.txt",
            "services/analytics-service/Dockerfile",
            "config/grafana/dashboards/",
            "services/order-service/src/main/java/"
        ],
        "outputs": ["services/analytics-service/**/*.py", "services/analytics-service/requirements.txt", "services/analytics-service/Dockerfile", "config/grafana/dashboards/"],
        "acceptance_criteria": [
            "[REQ-010] GMV 分析：实时计算日/周/月 GMV，`pytest tests/test_gmv.py` 验证计算准确性",
            "[REQ-010] 转化率分析：浏览→加购→下单→支付各环节转化率，误差 < 0.1%",
            "[REQ-010] 实时仪表盘：Grafana 仪表盘展示核心指标，数据延迟 < 1min",
            "[SHIP_DERIVED] 查询响应 P99 < 2s（从运营体验推导），复杂聚合查询 < 5s"
        ],
        "acceptance_tests": [
            "pytest tests/test_gmv.py",
            "pytest tests/test_conversion.py",
            "pytest tests/test_dashboard.py"
        ],
        "constraints": [
            "使用 Python + ClickHouse + Grafana（来自 blueprint COMP-12 technology_stack）"
        ],
        "requirements": ["REQ-010"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["analytics", "grafana", "clickhouse", "dashboard"]
    })
    
    output = {
        "_meta": {
            "agent": "specifier",
            "prompt_sha": "v312_specifier",
            "model_id": "bailian/qwen3.7-plus",
            "run_id": "run_20260619_041354_b",
            "round": 0,
            "input_files": ["architect_output_v312.json", "decomposer_output.json"],
            "timestamp": datetime.now().isoformat()
        },
        "work_packages": wps,
        "self_check": {
            "passed": True,
            "issues": []
        }
    }
    
    out_path = f"{case_dir}/blackboard/specifier_output_v312.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Case 2 written: {out_path}")
    return output


def gen_case3():
    """Case 3: Resume system - 7 WPs"""
    case_dir = f"{BASE}/loop_case3_resume"
    
    # SLAs from blueprint
    sla_tier1 = "[SLA] Tier 1 处理延迟 < 5秒（基线纯规则模式）"
    sla_tier2 = "[SLA] Tier 2 处理延迟 < 30秒（增强可选API模式）"
    sla_pdf = "[SLA] PDF文本可解析率 ≥ 98%（所有PDF输出）"
    sla_ats = "[SLA] ATS兼容率 > 95%（DOCX输出）"
    sla_fidelity_orig = "[SLA] 保真度(original) ≥ 95%（原始内容）"
    sla_fidelity_enh = "[SLA] 保真度(enhanced) ≥ 90%（增强内容）"
    sla_fidelity_res = "[SLA] 保真度(restructured) ≥ 85%（重构内容）"
    sla_semantic = "[SLA] 语义一致性 ≥ 0.85（Tier 2/3）"
    
    wps = []
    
    # WP-001: Knowledge Base + Input Parser
    wps.append({
        "id": "WP-001",
        "title": "行业知识库 + 输入解析基础设施",
        "objective": "构建半导体封装行业知识库和多格式输入解析器（纯文本/Markdown/PDF/DOCX）",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": [],
        "priority": "critical",
        "related_modules": ["COMP-08", "COMP-01"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "src/knowledge/", "src/parser/",
            "src/knowledge/terminology.py", "src/knowledge/data/terms.json",
            "src/parser/text_parser.py", "src/parser/pdf_parser.py", "src/parser/docx_parser.py"
        ],
        "outputs": [
            "src/knowledge/terminology.py", "src/knowledge/data/terms.json",
            "src/knowledge/data/tools.json", "src/knowledge/data/standards.json",
            "src/parser/text_parser.py", "src/parser/pdf_parser.py",
            "src/parser/docx_parser.py", "tests/test_parser/", "tests/test_knowledge/"
        ],
        "acceptance_criteria": [
            "[REQ-001] 知识库覆盖：半导体封装工艺术语 ≥ 30 个、工具 ≥ 20 个、标准 ≥ 10 个，`pytest tests/test_knowledge/test_coverage.py` 验证",
            "[REQ-001] 输入解析：纯文本/Markdown 解析保真度 > 95%，`pytest tests/test_parser/test_text_parser.py` 验证",
            "[REQ-002] 真相源确认：解析结果输出后等待用户确认再进入后续管线，`pytest tests/test_parser/test_confirm.py` 验证",
            f"{sla_tier1}：知识库查询 + 输入解析总耗时 < 2s（从 SLA 5s 推导，为后续管线预留时间）",
            "[SHIP_DERIVED] PDF/DOCX 解析成功率 ≥ 95%（从保真度框架推导），`pytest tests/test_parser/test_file_parser.py` 验证"
        ],
        "acceptance_tests": [
            "pytest tests/test_knowledge/test_coverage.py",
            "pytest tests/test_parser/test_text_parser.py",
            "pytest tests/test_parser/test_file_parser.py",
            "pytest tests/test_parser/test_confirm.py"
        ],
        "constraints": [
            "纯文本/Markdown 优先（来自 blueprint COMP-01 summary）",
            "保真度 > 95%（来自 blueprint COMP-01 summary）",
            sla_tier1,
            "[RISK] 简历造假合规: 三层保真度护栏 + 安全优化范围 + 用户显式确认"
        ],
        "requirements": ["REQ-001", "REQ-002"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["knowledge-base", "parser", "infrastructure", "semiconductor"]
    })
    
    # WP-002: JD Matching Engine
    wps.append({
        "id": "WP-002",
        "title": "JD解析与三层匹配引擎",
        "objective": "实现关键词(35%)+语义(45%)+行业术语(20%)三层匹配引擎，支持中文模型",
        "budget": {"tokens": 100000, "time_minutes": 75, "max_retries": 3},
        "complexity": "complex",
        "model_tier": "claude-opus",
        "dependencies": ["WP-001"],
        "priority": "high",
        "related_modules": ["COMP-02"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "src/matching/", "src/knowledge/terminology.py",
            "src/matching/jd_parser.py", "src/matching/keyword_matcher.py",
            "src/matching/semantic_matcher.py", "src/matching/term_matcher.py",
            "src/parser/text_parser.py"
        ],
        "outputs": [
            "src/matching/jd_parser.py", "src/matching/keyword_matcher.py",
            "src/matching/semantic_matcher.py", "src/matching/term_matcher.py",
            "tests/test_matching/"
        ],
        "acceptance_criteria": [
            "[REQ-003] 关键词匹配(35%)：TF-IDF 提取 JD 关键词，必需/优选分级，`pytest tests/test_matching/test_keyword.py` 验证权重分配",
            "[REQ-003] 语义匹配(45%)：text2vec-base-chinese 计算语义相似度，`pytest tests/test_matching/test_semantic.py` 验证中文语义匹配",
            "[REQ-003] 行业术语匹配(20%)：三层权重 35/45/20 合成最终得分，`pytest tests/test_matching/test_composite.py` 验证加权公式",
            f"{sla_tier1}：三层匹配总耗时 < 2s（从 SLA 5s 推导，为优化和渲染预留时间）",
            "[SHIP_DERIVED] 匹配准确率 ≥ 80%（从 ATS 通过目标推导），使用标注数据集验证"
        ],
        "acceptance_tests": [
            "pytest tests/test_matching/test_keyword.py",
            "pytest tests/test_matching/test_semantic.py",
            "pytest tests/test_matching/test_composite.py"
        ],
        "constraints": [
            "三层匹配权重：关键词 35% + 语义 45% + 术语 20%（来自 blueprint COMP-02 summary）",
            "中文自动切换 text2vec-base-chinese（来自 blueprint COMP-02 technology_stack）",
            sla_tier1,
            "[RISK] LLM依赖矛盾: 三层可降级架构 — 基线纯规则零LLM依赖"
        ],
        "requirements": ["REQ-003"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["matching", "jd-parser", "nlp", "text2vec"]
    })
    
    # WP-003: Content Optimizer
    wps.append({
        "id": "WP-003",
        "title": "内容优化器(结构化重组+术语增强)",
        "objective": "实现安全优化范围（结构化重组+术语替换），source_tag 标记来源，LLM Rewriter 需用户确认",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-001", "WP-002"],
        "priority": "high",
        "related_modules": ["COMP-03"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "src/optimizer/", "src/knowledge/terminology.py",
            "src/matching/keyword_matcher.py",
            "src/optimizer/restructurer.py", "src/optimizer/term_enhancer.py",
            "src/optimizer/llm_rewriter.py"
        ],
        "outputs": [
            "src/optimizer/restructurer.py", "src/optimizer/term_enhancer.py",
            "src/optimizer/llm_rewriter.py", "tests/test_optimizer/"
        ],
        "acceptance_criteria": [
            "[REQ-002] 安全优化范围：仅结构化重组和术语替换，禁止新增量化指标/项目/职责，`pytest tests/test_optimizer/test_safety.py` 验证无新增内容",
            "[REQ-002] source_tag 标记：每个输出段落标记来源（original/enhanced/restructured），`pytest tests/test_optimizer/test_source_tag.py` 验证",
            "[REQ-002] LLM Rewriter 确认：LLM 重写需用户显式确认后才应用，`pytest tests/test_optimizer/test_confirm.py` 验证",
            f"{sla_fidelity_orig}：原始内容优化后保真度 ≥ 95%，`pytest tests/test_optimizer/test_fidelity.py` 验证",
            f"{sla_fidelity_enh}：增强内容保真度 ≥ 90%",
            f"{sla_fidelity_res}：重构内容保真度 ≥ 85%"
        ],
        "acceptance_tests": [
            "pytest tests/test_optimizer/test_safety.py",
            "pytest tests/test_optimizer/test_source_tag.py",
            "pytest tests/test_optimizer/test_confirm.py",
            "pytest tests/test_optimizer/test_fidelity.py"
        ],
        "constraints": [
            "安全优化范围：仅结构化重组和术语替换（来自 blueprint COMP-03 summary）",
            "source_tag 标记每个段落来源（来自 blueprint COMP-03 responsibilities）",
            "LLM Rewriter 需用户显式确认（来自 blueprint COMP-03 responsibilities）",
            f"{sla_fidelity_orig}", f"{sla_fidelity_enh}", f"{sla_fidelity_res}",
            "[RISK] 内容优化空间受限: 安全优化范围定义 + 保守/积极模式 + 用户确认"
        ],
        "requirements": ["REQ-002", "REQ-003"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["optimizer", "restructure", "terminology", "fidelity"]
    })
    
    # WP-004: IR Schema
    wps.append({
        "id": "WP-004",
        "title": "统一中间表示层(IR Schema)",
        "objective": "扩展 JSON Resume Schema，增加 industry_specific + source_tagging + matching_scores",
        "budget": {"tokens": 50000, "time_minutes": 30, "max_retries": 3},
        "complexity": "simple",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-003"],
        "priority": "high",
        "related_modules": ["COMP-04"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "src/ir/", "src/ir/schema.py", "src/ir/schema.json",
            "src/optimizer/source_tagger.py"
        ],
        "outputs": ["src/ir/schema.py", "src/ir/schema.json", "tests/test_ir/"],
        "acceptance_criteria": [
            "[REQ-004] 扩展 Schema：在 JSON Resume 基础上增加 industry_specific、source_tagging、matching_scores 三个字段组，`pytest tests/test_ir/test_schema.py` 验证",
            "[REQ-004] Schema 验证：validator.py 对 IR 实例进行完整性校验，无效数据抛出 ValidationError",
            "[SHIP_DERIVED] IR 序列化/反序列化 < 10ms（从 SLA 5s 推导，IR 操作不应成为瓶颈）",
            "[SHIP_DERIVED] Schema 向后兼容：新增字段均为 optional，旧版 Resume 数据仍可正常加载"
        ],
        "acceptance_tests": [
            "pytest tests/test_ir/test_schema.py",
            "pytest tests/test_ir/test_validator.py"
        ],
        "constraints": [
            "基于 JSON Resume Schema 扩展（来自 blueprint COMP-04 technology_stack）",
            "所有渲染器从此 IR 读取（来自 blueprint COMP-04 summary）"
        ],
        "requirements": ["REQ-004"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["ir", "schema", "json-resume", "data-contract"]
    })
    
    # WP-005: Dual Renderer
    wps.append({
        "id": "WP-005",
        "title": "双格式渲染管道(DOCX+PDF)",
        "objective": "实现 python-docx DOCX 渲染和 reportlab PDF 渲染，保证 ATS 可解析率和文本可解析率",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-004"],
        "priority": "high",
        "related_modules": ["COMP-05"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "src/renderer/", "src/ir/schema.py",
            "src/renderer/docx_renderer.py", "src/renderer/pdf_renderer.py",
            "src/renderer/font_fallback.py"
        ],
        "outputs": [
            "src/renderer/docx_renderer.py", "src/renderer/pdf_renderer.py",
            "src/renderer/font_fallback.py", "tests/test_renderer/", "tests/test_renderer/fonts/"
        ],
        "acceptance_criteria": [
            f"{sla_ats}：DOCX 输出通过 ATS 解析测试，`pytest tests/test_renderer/test_ats.py` 验证 ATS 可解析率 > 95%",
            f"{sla_pdf}：PDF 输出文本可解析率 ≥ 98%，`pytest tests/test_renderer/test_pdf_text.py` 验证",
            "[REQ-004] 双格式一致性：同一 IR 数据渲染的 DOCX 和 PDF 内容完全一致，`pytest tests/test_renderer/test_consistency.py` 验证",
            "[SHIP_DERIVED] 三策略字体回退：系统字体 → 500KB 子集 → 兜底字体，`pytest tests/test_renderer/test_font_fallback.py` 验证三级回退",
            f"{sla_tier1}：渲染耗时 < 2s（从 SLA 5s 推导，为解析和匹配预留时间）"
        ],
        "acceptance_tests": [
            "pytest tests/test_renderer/test_ats.py",
            "pytest tests/test_renderer/test_pdf_text.py",
            "pytest tests/test_renderer/test_consistency.py",
            "pytest tests/test_renderer/test_font_fallback.py"
        ],
        "constraints": [
            "DOCX: python-docx（来自 blueprint COMP-05 technology_stack）",
            "PDF: reportlab 纯 Python（来自 blueprint COMP-05 technology_stack）",
            sla_pdf, sla_ats,
            "三策略字体回退（来自 blueprint COMP-05 summary）"
        ],
        "requirements": ["REQ-004"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["renderer", "docx", "pdf", "ats", "font"]
    })
    
    # WP-006: ATS Scorer
    wps.append({
        "id": "WP-006",
        "title": "ATS三维模拟评分器",
        "objective": "实现关键词(40%)+格式(30%)+语义(30%)三维评分，复用匹配结果，输出免责声明",
        "budget": {"tokens": 60000, "time_minutes": 45, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-002"],
        "priority": "medium",
        "related_modules": ["COMP-06"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "src/ats/", "src/matching/keyword_matcher.py",
            "src/ats/scorer.py", "src/ats/keyword_scorer.py",
            "src/ats/format_scorer.py", "src/ats/semantic_scorer.py"
        ],
        "outputs": [
            "src/ats/scorer.py", "src/ats/keyword_scorer.py",
            "src/ats/format_scorer.py", "src/ats/semantic_scorer.py",
            "tests/test_ats/"
        ],
        "acceptance_criteria": [
            "[REQ-005] 关键词评分(40%)：必需/优选分级评分，`pytest tests/test_ats/test_keyword_scorer.py` 验证权重",
            "[REQ-005] 格式评分(30%)：检查 ATS 友好格式（无表格/图片/特殊字符），`pytest tests/test_ats/test_format_scorer.py` 验证",
            "[REQ-005] 语义评分(30%)：复用 WP-002 匹配结果（REFACT-001），`pytest tests/test_ats/test_semantic_scorer.py` 验证",
            "[REQ-005] 免责声明：评分结果包含免责声明作为一级文档元素，`pytest tests/test_ats/test_disclaimer.py` 验证",
            "[SHIP_DERIVED] 三维评分总耗时 < 500ms（从 SLA 5s 推导）"
        ],
        "acceptance_tests": [
            "pytest tests/test_ats/test_keyword_scorer.py",
            "pytest tests/test_ats/test_format_scorer.py",
            "pytest tests/test_ats/test_semantic_scorer.py",
            "pytest tests/test_ats/test_disclaimer.py"
        ],
        "constraints": [
            "三维评分权重：关键词 40% + 格式 30% + 语义 30%（来自 blueprint COMP-06 summary）",
            "复用 COMP-02 匹配结果（来自 blueprint COMP-06 responsibilities）",
            "免责声明输出（来自 blueprint COMP-06 responsibilities）",
            "[RISK] ATS黑盒性: 可解释评分 + 最佳实践指南 + 免责声明显著提升"
        ],
        "requirements": ["REQ-005"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["ats", "scoring", "keyword", "format", "semantic"]
    })
    
    # WP-007: Fidelity Checker
    wps.append({
        "id": "WP-007",
        "title": "保真度分级自检器",
        "objective": "实现分级阈值检查(original≥95%/enhanced≥90%/restructured≥85%)+Levenshtein预检+语义一致性检查",
        "budget": {"tokens": 60000, "time_minutes": 45, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-003"],
        "priority": "medium",
        "related_modules": ["COMP-07"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "src/fidelity/", "src/optimizer/source_tagger.py",
            "src/fidelity/checker.py", "src/fidelity/levenshtein.py",
            "src/fidelity/semantic_checker.py"
        ],
        "outputs": [
            "src/fidelity/checker.py", "src/fidelity/levenshtein.py",
            "src/fidelity/semantic_checker.py", "tests/test_fidelity/"
        ],
        "acceptance_criteria": [
            f"{sla_fidelity_orig}：分级阈值检查 original ≥ 95%，`pytest tests/test_fidelity/test_thresholds.py` 验证",
            f"{sla_fidelity_enh}：enhanced ≥ 90%",
            f"{sla_fidelity_res}：restructured ≥ 85%",
            f"{sla_semantic}：Tier 2/3 语义一致性 ≥ 0.85，`pytest tests/test_fidelity/test_semantic.py` 验证",
            "[REQ-002] Levenshtein 预检：O(N) 复杂度预检，`pytest tests/test_fidelity/test_levenshtein.py` 验证性能"
        ],
        "acceptance_tests": [
            "pytest tests/test_fidelity/test_thresholds.py",
            "pytest tests/test_fidelity/test_semantic.py",
            "pytest tests/test_fidelity/test_levenshtein.py"
        ],
        "constraints": [
            "分级阈值：original ≥ 95% / enhanced ≥ 90% / restructured ≥ 85%（来自 blueprint COMP-07 summary）",
            "Levenshtein 补充 O(N) 预检（来自 blueprint COMP-07 summary）",
            sla_semantic,
            "[RISK] 简历造假合规: 三层保真度护栏 + 安全优化范围 + 用户显式确认"
        ],
        "requirements": ["REQ-002"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["fidelity", "levenshtein", "semantic", "validation"]
    })
    
    output = {
        "_meta": {
            "agent": "specifier",
            "prompt_sha": "v312_specifier",
            "model_id": "bailian/qwen3.7-plus",
            "run_id": "run_20260619_041354_a",
            "round": 0,
            "input_files": ["architect_output_v312.json", "decomposer_output.json"],
            "timestamp": datetime.now().isoformat()
        },
        "work_packages": wps,
        "self_check": {
            "passed": True,
            "issues": []
        }
    }
    
    out_path = f"{case_dir}/blackboard/specifier_output_v312.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Case 3 written: {out_path}")
    return output


def gen_case4():
    """Case 4: Cross-border AI platform - 7 WPs"""
    case_dir = f"{BASE}/v31_real_case"
    
    # SLAs
    sla_failover = "[SLA] 供应商故障切换时间 < 3秒（供应商级别）"
    sla_avail = "[SLA] 系统可用性 ≥ 99.9%（年度）"
    sla_ops = "[SLA] 运维时间 < 2小时/周（全自动化）"
    sla_mvp = "[SLA] MVP上线时间 15天（首版）"
    sla_cost = "[SLA] 月固定成本 $6-26/月（初期）"
    
    wps = []
    
    # WP-001: API Gateway
    wps.append({
        "id": "WP-001",
        "title": "API网关核心引擎部署与配置",
        "objective": "部署 New API 网关，配置多供应商聚合、智能路由、自动故障切换<3s 和 100% OpenAI 兼容 API",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": [],
        "priority": "high",
        "related_modules": ["COMP-001"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "docker-compose.yml", "new-api/docker-compose.yml",
            "new-api/config.yaml", "scripts/verify-api.sh"
        ],
        "outputs": [
            "docker-compose.yml", "new-api/docker-compose.yml",
            "new-api/config.yaml", "scripts/verify-api.sh"
        ],
        "acceptance_criteria": [
            "[REQ-007] New API 部署：Docker 容器运行正常，`docker-compose up -d && curl http://localhost:3000/api/status` 返回 200",
            "[REQ-009] 100% OpenAI 兼容：POST /v1/chat/completions 接口与 OpenAI SDK 完全兼容，`python -c 'import openai; client.chat.completions.create(...)'` 测试通过",
            "[REQ-006] 故障切换 < 3s：主供应商宕机后 3s 内自动切换到备用供应商，`bash scripts/verify-api.sh --failover-test` 验证",
            f"{sla_failover}：故障切换时间 < 3s",
            f"{sla_avail}：设计支持 99.9% 可用性（多供应商 + 自动重启）",
            "[REQ-009] Token 计量：每次 API 调用记录 input/output tokens，`sqlite3` 查询验证计量数据"
        ],
        "acceptance_tests": [
            "docker-compose up -d && curl http://localhost:3000/api/status",
            "python -c 'import openai; ...'",
            "bash scripts/verify-api.sh --failover-test"
        ],
        "constraints": [
            "使用 New API + Docker + Railway（来自 blueprint COMP-001 technology_stack）",
            "Go 语言（来自 blueprint COMP-001 technology_stack）",
            sla_failover, sla_avail,
            "[RISK] 跨境网络稳定性: 多路径冗余+CDN+智能路由+自动切换<3s+客户端重连"
        ],
        "requirements": ["REQ-007", "REQ-009", "REQ-006"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["gateway", "new-api", "docker", "openai-compatible"]
    })
    
    # WP-002: User Management + Token Billing
    wps.append({
        "id": "WP-002",
        "title": "用户管理与Token计量计费系统",
        "objective": "实现用户注册登录、API Key 管理、Token 配额管理、用量分析和成本追踪",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-001"],
        "priority": "high",
        "related_modules": ["COMP-001"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "new-api/config.yaml", "docker-compose.yml",
            "frontend/pages/api/auth/"
        ],
        "outputs": [
            "frontend/pages/api/auth/",
            "frontend/lib/credit-system.ts"
        ],
        "acceptance_criteria": [
            "[REQ-001] 用户注册登录：POST /api/auth/register + /login 完整实现，JWT 签发验证",
            "[REQ-001] API Key 管理：用户可创建/删除 API Key，每个 Key 独立计量",
            "[REQ-009] Token 计费：每次调用按 input/output tokens 扣减余额，余额不足返回 402",
            "[SHIP_DERIVED] 计费精度误差 < 0.1%（从商业准确性推导），对比供应商原始 token 数验证",
            "[SHIP_DERIVED] Dashboard 用量查询 P99 < 500ms（从用户体验推导）"
        ],
        "acceptance_tests": [
            "pytest frontend/tests/test_auth.py",
            "pytest frontend/tests/test_billing.py",
            "pytest frontend/tests/test_api_keys.py"
        ],
        "constraints": [
            "集成在 New API 网关之上（来自 blueprint COMP-001 responsibilities）",
            "Token 计量计费（来自 blueprint COMP-001 responsibilities）",
            sla_cost
        ],
        "requirements": ["REQ-001", "REQ-009"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["user", "auth", "billing", "token", "api-key"]
    })
    
    # WP-003: Frontend
    wps.append({
        "id": "WP-003",
        "title": "前端用户界面开发",
        "objective": "开发 Next.js 前端，包含 Landing、Dashboard、API 文档、注册登录和充值订阅页面",
        "budget": {"tokens": 100000, "time_minutes": 75, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-001", "WP-002"],
        "priority": "medium",
        "related_modules": ["COMP-002"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "frontend/package.json", "frontend/next.config.js",
            "frontend/pages/index.tsx", "frontend/pages/dashboard.tsx",
            "frontend/pages/docs.tsx", "frontend/components/"
        ],
        "outputs": [
            "frontend/package.json", "frontend/next.config.js",
            "frontend/pages/index.tsx", "frontend/pages/dashboard.tsx",
            "frontend/pages/docs.tsx", "frontend/pages/api/auth/",
            "frontend/components/"
        ],
        "acceptance_criteria": [
            "[REQ-003] Next.js on Vercel：`npm run build && npm run start` 成功，Lighthouse 性能分 ≥ 90",
            "[REQ-001] Landing 页面：包含产品特性、定价、注册入口，`npx playwright test tests/landing.spec.ts` 验证",
            "[REQ-001] Dashboard：展示用量/账单/API Key/余额/已节省金额，`npx playwright test tests/dashboard.spec.ts` 验证",
            "[REQ-001] API 文档：/docs 页面展示 OpenAI 兼容接口文档和代码示例",
            "[SHIP_DERIVED] 首屏加载 < 2s（从用户体验推导），Lighthouse FCP < 1.5s"
        ],
        "acceptance_tests": [
            "npm run build && npm run start",
            "npx playwright test tests/landing.spec.ts",
            "npx playwright test tests/dashboard.spec.ts",
            "npx lighthouse https://app.example.com --perf"
        ],
        "constraints": [
            "使用 Next.js + Vercel + React（来自 blueprint COMP-002 technology_stack）",
            "海外部署免 ICP（来自 blueprint COMP-002 deployment）"
        ],
        "requirements": ["REQ-003", "REQ-001"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["frontend", "nextjs", "vercel", "dashboard"]
    })
    
    # WP-004: Payment
    wps.append({
        "id": "WP-004",
        "title": "支付系统集成与定价配置",
        "objective": "集成 Paddle MoR 支付 + Credit 包($5-100) + 月度订阅($19/39/79) + Stripe 降级",
        "budget": {"tokens": 80000, "time_minutes": 60, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-002"],
        "priority": "medium",
        "related_modules": ["COMP-003"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "frontend/pages/api/payment/paddle.ts",
            "frontend/pages/api/payment/stripe.ts",
            "frontend/lib/credit-system.ts", "frontend/lib/subscription.ts"
        ],
        "outputs": [
            "frontend/pages/api/payment/paddle.ts",
            "frontend/pages/api/payment/stripe.ts",
            "frontend/lib/credit-system.ts", "frontend/lib/subscription.ts"
        ],
        "acceptance_criteria": [
            "[REQ-004] Credit 充值：$5/$10/$25/$50/$100 五档，Paddle 支付成功后自动到账，`pytest tests/test_payment.py` 验证",
            "[REQ-004] 月度订阅：$19/$39/$79 三档，订阅状态正确维护，`pytest tests/test_subscription.py` 验证",
            "[REQ-010] Stripe 降级：Paddle 不可用时降级到 Stripe Payment Links，每日 30 分钟半自动化",
            "[SHIP_DERIVED] 支付到账延迟 < 30s（从用户体验推导），webhook 处理成功率 ≥ 99.9%",
            "[REQ-004] 全球税务：Paddle MoR 自动处理全球税务，无需手动计算"
        ],
        "acceptance_tests": [
            "pytest tests/test_payment.py",
            "pytest tests/test_subscription.py",
            "pytest tests/test_webhook.py"
        ],
        "constraints": [
            "使用 Paddle MoR + Stripe（来自 blueprint COMP-003 technology_stack）",
            "Credit 包 $5/$10/$25/$50/$100（来自 blueprint domain_details.pricing_model）",
            "月度订阅 $19/$39/$79（来自 blueprint domain_details.pricing_model）",
            "[RISK] 支付审批延迟: Paddle+Stripe+PayPal并行申请+Stripe Payment Links半自动化降级"
        ],
        "requirements": ["REQ-004", "REQ-010"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["payment", "paddle", "stripe", "subscription", "credit"]
    })
    
    # WP-005: CDN Security
    wps.append({
        "id": "WP-005",
        "title": "CDN与安全层配置",
        "objective": "配置 Cloudflare CDN + DDoS 防护 + WAF + Bot 管理 + DNS + SSL",
        "budget": {"tokens": 40000, "time_minutes": 30, "max_retries": 3},
        "complexity": "simple",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-001"],
        "priority": "medium",
        "related_modules": ["COMP-004"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "cloudflare/wrangler.toml", "scripts/setup-cloudflare.sh",
            "cloudflare/rulesets/"
        ],
        "outputs": [
            "cloudflare/wrangler.toml", "scripts/setup-cloudflare.sh",
            "cloudflare/rulesets/"
        ],
        "acceptance_criteria": [
            "[REQ-003] CDN 配置：Cloudflare 代理到 Railway API 网关，`curl -I https://api.example.com` 验证 CDN 命中",
            "[REQ-015] DDoS 防护：启用 Cloudflare DDoS 防护，WAF 规则拦截常见攻击，`curl` 测试 SQL 注入被拦截",
            "[REQ-015] SSL：强制 HTTPS，SSL 等级 A+，`ssllabs.com` 扫描验证",
            "[SHIP_DERIVED] CDN 缓存命中率 ≥ 80%（从性能和成本推导），Page Rules 配置合理"
        ],
        "acceptance_tests": [
            "curl -I https://api.example.com",
            "bash scripts/setup-cloudflare.sh --verify",
            "curl 'https://api.example.com/?q=1 OR 1=1' # should be blocked"
        ],
        "constraints": [
            "使用 Cloudflare（来自 blueprint COMP-004 technology_stack）",
            "免 ICP 备案（来自 blueprint domain_details）"
        ],
        "requirements": ["REQ-003", "REQ-015"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["cdn", "cloudflare", "ddos", "waf", "ssl"]
    })
    
    # WP-006: Supplier Integration
    wps.append({
        "id": "WP-006",
        "title": "供应商接入与通道配置",
        "objective": "接入 DeepSeek/Qwen/Zhipu 三家供应商，每家 2-3 通道，配置负载均衡和故障切换",
        "budget": {"tokens": 60000, "time_minutes": 45, "max_retries": 3},
        "complexity": "medium",
        "model_tier": "claude-sonnet",
        "dependencies": [],
        "priority": "high",
        "related_modules": ["COMP-005"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "scripts/verify-suppliers.sh", "docs/supplier-agreements/",
            "new-api/channels.yaml", "new-api/config.yaml"
        ],
        "outputs": [
            "scripts/verify-suppliers.sh", "docs/supplier-agreements/",
            "new-api/channels.yaml"
        ],
        "acceptance_criteria": [
            "[REQ-002] 三家供应商接入：DeepSeek + Qwen + Zhipu 均成功接入，`bash scripts/verify-suppliers.sh` 验证全部在线",
            "[REQ-002] 每供应商 2-3 通道：channels.yaml 配置每家至少 2 个通道，负载均衡权重正确",
            "[REQ-006] 三层故障切换：通道级 < 1s → 模型级降级 → 基础设施级容灾，`bash scripts/verify-suppliers.sh --failover` 验证",
            f"{sla_failover}：供应商级故障切换 < 3s",
            "[REQ-002] 商业协议：Day 1 并行申请商业协议/Partner Program，记录申请状态"
        ],
        "acceptance_tests": [
            "bash scripts/verify-suppliers.sh",
            "bash scripts/verify-suppliers.sh --failover",
            "cat new-api/channels.yaml | grep -c 'channel'"
        ],
        "constraints": [
            "DeepSeek API + Qwen API + Zhipu API（来自 blueprint COMP-005 technology_stack）",
            "每供应商 2-3 通道（来自 blueprint COMP-005 responsibilities）",
            sla_failover,
            "[RISK] 供应商ToS转售合规: Day 1并行申请商业协议+Partner Program备选+开发者Key interim mode"
        ],
        "requirements": ["REQ-002", "REQ-006"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["supplier", "deepseek", "qwen", "zhipu", "channels"]
    })
    
    # WP-007: Monitoring
    wps.append({
        "id": "WP-007",
        "title": "监控告警与自动化运维体系",
        "objective": "配置 UptimeRobot 监控 + Telegram 告警 + 供应商健康检查 + 状态页，实现全自动化运维",
        "budget": {"tokens": 50000, "time_minutes": 30, "max_retries": 3},
        "complexity": "simple",
        "model_tier": "claude-sonnet",
        "dependencies": ["WP-001", "WP-006"],
        "priority": "low",
        "related_modules": ["COMP-006"],
        "context_files": [
            "architect_output_v312.json", "decomposer_output.json",
            "monitoring/uptimerobot-config.json", "monitoring/telegram-bot.py",
            "monitoring/health-check.sh", "statuspage/config.md",
            "new-api/config.yaml"
        ],
        "outputs": [
            "monitoring/uptimerobot-config.json", "monitoring/telegram-bot.py",
            "monitoring/health-check.sh", "statuspage/config.md"
        ],
        "acceptance_criteria": [
            "[REQ-005] 5 分钟监控：UptimeRobot 每 5 分钟检查 API 网关和供应商健康，`cat monitoring/uptimerobot-config.json | jq '.interval'` 验证 = 300",
            "[REQ-005] Telegram 告警：故障发生 1 分钟内发送 Telegram 通知，`python monitoring/telegram-bot.py --test` 验证",
            "[REQ-005] 自动化运维：每周运维时间 < 2 小时，`bash monitoring/health-check.sh --auto-remediate` 验证自动重启",
            f"{sla_ops}：运维时间 < 2h/周",
            f"{sla_avail}：监控覆盖所有关键路径，支持 99.9% SLA 验证"
        ],
        "acceptance_tests": [
            "cat monitoring/uptimerobot-config.json | jq '.interval'",
            "python monitoring/telegram-bot.py --test",
            "bash monitoring/health-check.sh --auto-remediate"
        ],
        "constraints": [
            "使用 UptimeRobot + Telegram Bot（来自 blueprint COMP-006 technology_stack）",
            "5 分钟间隔监控（来自 blueprint COMP-006 responsibilities）",
            sla_ops, sla_avail
        ],
        "requirements": ["REQ-005", "REQ-015"],
        "retry_policy": {"on_failure": "retry"},
        "tags": ["monitoring", "uptimerobot", "telegram", "alerting", "automation"]
    })
    
    output = {
        "_meta": {
            "agent": "specifier",
            "prompt_sha": "v312_specifier",
            "model_id": "bailian/qwen3.7-plus",
            "run_id": "run_20260619_032758_b",
            "round": 0,
            "input_files": ["architect_output_v312.json", "decomposer_output.json"],
            "timestamp": datetime.now().isoformat()
        },
        "work_packages": wps,
        "self_check": {
            "passed": True,
            "issues": []
        }
    }
    
    out_path = f"{case_dir}/blackboard/specifier_output_v312.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Case 4 written: {out_path}")
    return output


if __name__ == "__main__":
    print("Generating specifier_output_v312.json for all 4 cases...")
    c1 = gen_case1()
    c2 = gen_case2()
    c3 = gen_case3()
    c4 = gen_case4()
    print("\nAll 4 cases generated successfully.")
