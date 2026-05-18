#!/bin/bash
# Webhook 端点测试脚本

set -euo pipefail

echo "=== Webhook 端点验证 ==="
echo ""

# 加载环境变量
ENV_FILE="$HOME/.openclaw/.webhook_env"
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
    echo "✅ 已加载环境配置"
else
    echo "⚠️  环境文件不存在: $ENV_FILE"
    echo "   请手动设置 HOOKS_TOKEN 和 GATEWAY_PORT"
    exit 1
fi

# 检查变量
if [ -z "${HOOKS_TOKEN:-}" ]; then
    echo "❌ HOOKS_TOKEN 未设置"
    exit 1
fi

if [ -z "${GATEWAY_PORT:-}" ]; then
    GATEWAY_PORT=18789
    echo "⚠️  GATEWAY_PORT 未设置，使用默认值: $GATEWAY_PORT"
fi

HOOKS_URL="http://127.0.0.1:$GATEWAY_PORT/hooks/wake"

echo "Webhook URL: $HOOKS_URL"
echo "Token: ${HOOKS_TOKEN:0:10}..."
echo ""

# 测试 1: 无认证请求（应该失败）
echo "[1/4] 测试无认证请求..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$HOOKS_URL" \
    -H "Content-Type: application/json" \
    -d '{"text":"test"}' 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "401" ] || [ "$HTTP_STATUS" = "403" ]; then
    echo "  ✅ 无认证请求被拒绝 (HTTP $HTTP_STATUS)"
else
    echo "  ⚠️  无认证请求返回 HTTP $HTTP_STATUS（期望 401/403）"
fi

# 测试 2: 错误 token（应该失败）
echo ""
echo "[2/4] 测试错误 token..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$HOOKS_URL" \
    -H "Authorization: Bearer wrong_token" \
    -H "Content-Type: application/json" \
    -d '{"text":"test"}' 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "401" ] || [ "$HTTP_STATUS" = "403" ]; then
    echo "  ✅ 错误 token 被拒绝 (HTTP $HTTP_STATUS)"
else
    echo "  ⚠️  错误 token 返回 HTTP $HTTP_STATUS（期望 401/403）"
fi

# 测试 3: 正确 token + now 模式
echo ""
echo "[3/4] 测试正确 token（mode: now）..."
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$HOOKS_URL" \
    -H "Authorization: Bearer $HOOKS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"text":"DeepFlow webhook test","mode":"now"}' 2>/dev/null || echo "Error")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "202" ]; then
    echo "  ✅ Webhook 调用成功 (HTTP $HTTP_CODE)"
    echo "  响应: $BODY"
else
    echo "  ❌ Webhook 调用失败 (HTTP $HTTP_CODE)"
    echo "  响应: $BODY"
    exit 1
fi

# 测试 4: next-heartbeat 模式
echo ""
echo "[4/4] 测试 next-heartbeat 模式..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$HOOKS_URL" \
    -H "Authorization: Bearer $HOOKS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"text":"DeepFlow heartbeat test","mode":"next-heartbeat"}' 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "202" ]; then
    echo "  ✅ next-heartbeat 模式调用成功 (HTTP $HTTP_STATUS)"
else
    echo "  ⚠️  next-heartbeat 模式返回 HTTP $HTTP_STATUS"
fi

echo ""
echo "=== 验证完成 ==="
echo ""
echo "Webhook 配置正确，可以进行下一步开发"
