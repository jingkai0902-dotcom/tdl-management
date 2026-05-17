# TDL 管理交互系统

## 运行方式

这个仓库在生产环境需要两个常驻进程：

- `tdl-backend.service`：FastAPI、APScheduler、HTTP API
- `tdl-stream-bot.service`：钉钉 Stream 机器人长连接，负责收消息和卡片回调

只启动后端、不启动 Stream bot，系统能跑 API，但收不到钉钉消息。

## 本地开发

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
PYTHONPATH=. .venv/bin/alembic upgrade head
PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload
```

另开一个终端启动钉钉 Stream bot：

```bash
PYTHONPATH=. .venv/bin/python -m app.integrations.dingtalk_stream_bot
```

测试：

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

## 必要环境变量

至少需要配置：

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `DINGTALK_APP_KEY`
- `DINGTALK_APP_SECRET`
- `DINGTALK_AGENT_ID`
- `PUBLIC_BASE_URL`
- `DINGTALK_OAUTH_SCOPE`（默认 `openid Contact.User.Read Calendar.Event.Write`）
- `DINGTALK_OAUTH_REDIRECT_URI`

如果需要互动卡，再补：

- `DINGTALK_TDL_CARD_TEMPLATE_ID`

## 生产目录

- 代码目录：`/opt/bots/tdl/backend`
- 后端端口：`127.0.0.1:8010`
- 运行用户：默认 `tdl`
- systemd：
  - `tdl-backend.service`
  - `tdl-stream-bot.service`

## 首次部署

在 ECS 上准备目录和代码后：

```bash
cd /opt/bots/tdl/backend
cp .env.example .env
# 填好 .env
bash deploy/deploy.sh
```

如果服务器默认 `python3` 仍是系统自带版本，可显式指定 Python 3.11：

```bash
PYTHON_BIN=python3.11 bash deploy/deploy.sh
```

部署脚本默认创建并使用专用系统用户 `tdl`。如目标服务器已经有既定服务用户，可显式指定：

```bash
SERVICE_USER=<existing-user> bash deploy/deploy.sh
```

如果需要通过 Nginx 暴露 API，可把 [deploy/nginx-tdl.conf](deploy/nginx-tdl.conf) 合并到目标站点配置中，再执行：

```bash
NGINX_SITE=/etc/nginx/sites-enabled/<site-name> bash deploy/deploy.sh
```

钉钉机器人消息使用 Stream 模式，本身不依赖公网 webhook。  
但个人日历授权回调需要公网 HTTPS 地址，因此如果要启用日历同步，需要让 `/tdl/calendar/auth/callback` 可从外网访问。

## 更新部署

```bash
cd /opt/bots/tdl/backend
git pull
bash deploy/deploy.sh
```

## Smoke Test

```bash
bash deploy/smoke-test.sh
```

等价手工检查：

```bash
systemctl status tdl-backend.service --no-pager
systemctl status tdl-stream-bot.service --no-pager
curl -fsS http://127.0.0.1:8010/health
```

随后在钉钉里给机器人发一条简单消息，确认有回复。
