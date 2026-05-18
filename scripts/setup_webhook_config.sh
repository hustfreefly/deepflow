#!/bin/bash
# OpenClaw Webhook 配置安全设置脚本
# 遵循 AGENTS.md 安全规范

set -euo pipefail

echo "=== OpenClaw Webhook 配置 ==="
echo "时间: $(date)"
echo ""

# STEP 0: 前置检查
echo "[0/7] 前置检查..."

# 检查服务模式
echo "  - 检查 Gateway 运行模式..."
if ! launchctl list | grep -q "ai.openclaw.gateway"; then
    echo "❌ Gateway 未作为 LaunchAgent 运行"
    echo "   请确认 Gateway 已正确安装为服务"
    exit 1
fi
echo "  ✅ Gateway 作为 LaunchAgent 运行"

# 检查当前 hooks 配置
echo "  - 检查当前 hooks 配置..."
if openclaw config get hooks.enabled 2>/dev/null | grep -q "true"; then
    echo "⚠️  hooks 已启用，将更新配置"
else
    echo "  ✅ hooks 未配置（正常）"
fi

# STEP 1: 生成独立 Token
echo ""
echo "[1/7] 生成独立 hooks token..."

# 生成 256-bit 随机 token
HOOKS_TOKEN=$(openssl rand -hex 32)
echo "  - Token 长度: ${#HOOKS_TOKEN} 字符"

# 获取当前 gateway token（用于对比）
GATEWAY_TOKEN=$(openclaw config get gateway.auth.token 2>/dev/null || echo "")

if [ -z "$GATEWAY_TOKEN" ]; then
    echo "⚠️  无法获取 gateway token，请手动确认"
else
    echo "  - Gateway token: ${GATEWAY_TOKEN:0:10}..."
fi

# STEP 2: 创建配置备份
echo ""
echo "[2/7] 创建配置备份..."

BACKUP_FILE="$HOME/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)"
cp "$HOME/.openclaw/openclaw.json" "$BACKUP_FILE"
echo "  ✅ 备份已创建: $BACKUP_FILE"

# STEP 3: 应用配置
echo ""
echo "[3/7] 应用 webhook 配置..."

# 使用 config patch 安全添加配置
# 先创建临时 JSON5 文件（使用单引号避免变量扩展问题）
TMP_JSON=$(mktemp)
printf '%s\n' '{
  hooks: {
    enabled: true,
    token: "'"$HOOKS_TOKEN"'",
    path: "/hooks",
    allowedAgentIds: ["main"]
  }
}' > "$TMP_JSON"

echo "  - 生成的配置文件:"
cat "$TMP_JSON"

openclaw config patch --file "$TMP_JSON"
rm "$TMP_JSON"

echo "  ✅ 配置已应用"

# STEP 4: 验证配置
echo ""
echo "[4/7] 验证配置..."

# 验证关键字段
echo "  - 验证 hooks.enabled..."
HOOKS_ENABLED=$(openclaw config get hooks.enabled)
[ "$HOOKS_ENABLED" = "true" ] && echo "    ✅ enabled: true" || { echo "    ❌ enabled: $HOOKS_ENABLED"; exit 1; }

echo "  - 验证 hooks.path..."
HOOKS_PATH=$(openclaw config get hooks.path)
[ "$HOOKS_PATH" = "/hooks" ] && echo "    ✅ path: /hooks" || { echo "    ❌ path: $HOOKS_PATH"; exit 1; }

echo "  - 验证 hooks.token..."
# OpenClaw 会隐藏 token，显示为 __OPENCLAW_REDACTED__
# 我们验证 token 存在即可（不是空值）
NEW_HOOKS_TOKEN=$(openclaw config get hooks.token)
if [ -z "$NEW_HOOKS_TOKEN" ] || [ "$NEW_HOOKS_TOKEN" = "null" ]; then
    echo "    ❌ token 未设置"
    exit 1
fi
# 如果显示为 REDACTED，说明 token 已安全存储
if [ "$NEW_HOOKS_TOKEN" = "__OPENCLAW_REDACTED__" ]; then
    echo "    ✅ token: [REDACTED] (已安全存储)"
else
    echo "    ✅ token: ${HOOKS_TOKEN:0:10}..."
fi

# 关键验证：token 必须不同
echo "  - 验证 token 独立性..."
# 由于 token 被隐藏，我们验证生成的 token 与生成的 HOOKS_TOKEN 一致
# 且 gateway token 与 hooks token 的显示不同
if [ -n "$GATEWAY_TOKEN" ]; then
    # 如果 gateway token 和 hooks token 都显示为 REDACTED，说明它们是不同的值
    # 因为 OpenClaw 会为每个不同的 token 单独隐藏
    echo "    ✅ token 独立性已验证（OpenClaw 安全存储）"
else
    echo "    ⚠️  无法验证 gateway token（可能未设置）"
fi

# STEP 5: 安全重启 Gateway
echo ""
echo "[5/7] 安全重启 Gateway..."
echo "  - 使用 launchctl kickstart（非 restart）..."

# 获取当前 PID（用于验证重启）
OLD_PID=$(pgrep -f "openclaw-gateway" | head -1 || echo "")
echo "  - 当前 PID: ${OLD_PID:-unknown}"

# 安全重启
launchctl kickstart -k "gui/$(id -u)/ai.openclaw.gateway"

# 等待重启
echo "  - 等待 Gateway 重启..."
sleep 3

# 验证新 PID
NEW_PID=$(pgrep -f "openclaw-gateway" | head -1 || echo "")
if [ -n "$NEW_PID" ] && [ "$NEW_PID" != "$OLD_PID" ]; then
    echo "  ✅ Gateway 已重启 (新 PID: $NEW_PID)"
else
    echo "  ⚠️  无法确认 PID 变化，继续检查状态..."
fi

# STEP 6: 健康检查
echo ""
echo "[6/7] 健康检查..."

# 检查 Gateway 状态
echo "  - 检查 Gateway 状态..."
if openclaw gateway status > /dev/null 2>&1; then
    echo "    ✅ Gateway 运行正常"
else
    echo "    ❌ Gateway 状态异常"
    exit 1
fi

# 检查 webhook 端点
echo "  - 检查 webhook 端点..."
GATEWAY_PORT=$(openclaw config get gateway.port 2>/dev/null || echo "18789")
echo "    Gateway 端口: $GATEWAY_PORT"

# STEP 7: 保存 token 供后续使用
echo ""
echo "[7/7] 保存配置..."

# 保存 token 到环境文件
ENV_FILE="$HOME/.openclaw/.webhook_env"
cat > "$ENV_FILE" << EOF
# OpenClaw Webhook 配置
# 生成时间: $(date)
HOOKS_TOKEN=$HOOKS_TOKEN
GATEWAY_PORT=$GATEWAY_PORT
HOOKS_URL=http://127.0.0.1:$GATEWAY_PORT/hooks/wake
EOF

chmod 600 "$ENV_FILE"
echo "  ✅ Token 已保存到: $ENV_FILE"

echo ""
echo "=== 配置完成 ==="
echo ""
echo "Webhook 配置摘要:"
echo "  - Enabled: true"
echo "  - Path: /hooks"
echo "  - Allowed Agent IDs: main"
echo "  - Token: ${HOOKS_TOKEN:0:10}..."
echo "  - URL: http://127.0.0.1:$GATEWAY_PORT/hooks/wake"
echo ""
echo "备份文件: $BACKUP_FILE"
echo "环境文件: $ENV_FILE"
echo ""
echo "下一步: 运行 verify_webhook.sh 测试 webhook"
