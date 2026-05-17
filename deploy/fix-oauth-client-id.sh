#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 修复 OAuth ClientID 错配问题
# 场景：.env 里的 DINGTALK_OAUTH_CLIENT_ID 和 DINGTALK_APP_KEY
#       指向了不同的钉钉应用，导致用户授权拿不到 Contact.User.Read
# 修复：清掉 DINGTALK_OAUTH_CLIENT_ID / DINGTALK_OAUTH_CLIENT_SECRET，
#       让系统回退使用 DINGTALK_APP_KEY（机器人同一应用）
# ============================================================

APP_DIR="/opt/bots/tdl/backend"

if [[ ! -d "$APP_DIR" ]]; then
    echo "ERROR: $APP_DIR 不存在"
    exit 1
fi

cd "$APP_DIR"

# 备份
BACKUP="$APP_DIR/.env.backup.$(date +%Y%m%d-%H%M%S)"
cp .env "$BACKUP"
echo "已备份 .env → $BACKUP"

# 检查是否有问题值
CURRENT_CLIENT_ID=$(grep "^DINGTALK_OAUTH_CLIENT_ID=" .env | cut -d= -f2 || true)
CURRENT_APP_KEY=$(grep "^DINGTALK_APP_KEY=" .env | cut -d= -f2 || true)

if [[ -z "$CURRENT_CLIENT_ID" ]]; then
    echo "DINGTALK_OAUTH_CLIENT_ID 已经是空的，不需要修复"
else
    if [[ "$CURRENT_CLIENT_ID" = "$CURRENT_APP_KEY" ]]; then
        echo "DINGTALK_OAUTH_CLIENT_ID 和 DINGTALK_APP_KEY 相同，清空以消除冗余配置"
    else
        echo "⚠️  发现错配："
        echo "   DINGTALK_OAUTH_CLIENT_ID = $CURRENT_CLIENT_ID"
        echo "   DINGTALK_APP_KEY         = $CURRENT_APP_KEY"
        echo "   两者指向不同的应用，这是权限报错的根因！"
    fi

    # 清空这两个字段
    sed -i.bak 's/^DINGTALK_OAUTH_CLIENT_ID=.*/DINGTALK_OAUTH_CLIENT_ID=/' .env
    sed -i.bak 's/^DINGTALK_OAUTH_CLIENT_SECRET=.*/DINGTALK_OAUTH_CLIENT_SECRET=/' .env
    rm -f .env.bak
    echo "已清空 DINGTALK_OAUTH_CLIENT_ID 和 DINGTALK_OAUTH_CLIENT_SECRET"
fi

# 重启服务
echo ""
echo "重启服务..."
systemctl restart tdl-backend.service
systemctl restart tdl-stream-bot.service
sleep 3

echo ""
echo "服务状态："
systemctl status tdl-backend.service --no-pager -l | head -5
echo "---"
systemctl status tdl-stream-bot.service --no-pager -l | head -5

# 检查健康
PUBLIC_BASE_URL=$(grep "^PUBLIC_BASE_URL=" .env | cut -d= -f2 || echo "")
HEALTH_URL="${PUBLIC_BASE_URL}/health"
echo ""
echo "健康检查 $HEALTH_URL ..."
if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    echo "✅ 服务正常"
else
    echo "❌ 健康检查失败，请检查日志: journalctl -u tdl-backend.service -n 50"
fi

# 打印荆少巍的日历授权链接
USER_ID="0617564550-1513038363"
AUTH_URL="${PUBLIC_BASE_URL}/calendar/auth/start?user_id=${USER_ID}"

echo ""
echo "============================================"
echo "  荆少巍的日历授权链接："
echo "  $AUTH_URL"
echo ""
echo "  在浏览器打开这个链接，重新授权一次即可。"
echo "============================================"
