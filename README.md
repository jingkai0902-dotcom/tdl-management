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
- `DINGTALK_OAUTH_SCOPE`（默认 `openid Contact.User.Read Calendar.Event.Read Calendar.Event.Write`）
- `DINGTALK_OAUTH_REDIRECT_URI`

如果需要互动卡，再补：

- `DINGTALK_TDL_CARD_TEMPLATE_ID`

提醒端互动卡模板需要在钉钉卡片搭建器中暴露这些变量：

- `msgTitle`
- `staticMsgContent`
- `button1Text` / `button1ActionId` / `button1Visible`
- `button2Text` / `button2ActionId` / `button2Visible`
- `button3Text` / `button3ActionId` / `button3Visible`
- `button4Text` / `button4ActionId` / `button4Visible`

按钮动作需要在模板中固定枚举，点击请求参数传 `actionId=${buttonNActionId}`；显示控制绑定对应的 `buttonNVisible`。

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

本地协作时，优先使用仓库内的确定性脚本，避免重复手拼命令：

```bash
bash scripts/tdl-prod-check.sh
bash scripts/tdl-deploy-prod.sh
bash scripts/check-meeting-baseline.sh
```

`scripts/tdl-prod-check.sh` 会检查 backend、Stream bot、intake worker、
pilot metrics timer、API health、钉钉卡片模板配置和互动卡片强制开关。

`scripts/tdl-deploy-prod.sh` 会保留生产机上由 timer 自动追加的
`励步英语资料库/励步5月月度会/daily-pilot-metrics.md`，避免部署时用本地模板覆盖生产记录。

`scripts/check-meeting-baseline.sh` 会用当前 DeepSeek baseline 跑会议
gold set evaluator，并开启 gate violations、false confirmed、fabricated dates
和 deep processing errors 四个 strict 挡板。

日历生成率低于目标时，可运行：

```bash
python scripts/diagnose-pilot-calendar-gaps.py
```

该脚本只读数据库，列出 open TDL 中缺少 `calendar_event_id` 的任务及最近一次日历审计归因。

草稿确认率低或忽略率高时，可运行：

```bash
python scripts/diagnose-pilot-draft-outcomes.py --date 2026-05-22
```

该脚本只读数据库，按周累计列出草稿的确认、忽略、未处理状态，以及缺失字段和最近动作。

准备单个钉钉按钮真实端验证卡时，先 dry-run：

```bash
python scripts/prepare-button-validation-card.py \
  --scenario d4-owner \
  --run-id button-validation-YYYYMMDD
```

确认场景和接收人无误后再加 `--send`。验证结束后按 run id 清理：

```bash
python scripts/prepare-button-validation-card.py \
  --cleanup-run-id button-validation-YYYYMMDD
python scripts/prepare-button-validation-card.py \
  --cleanup-run-id button-validation-YYYYMMDD \
  --execute-cleanup
```

需要提醒某个试点成员开通日历授权时，先 dry-run 预览：

```bash
python scripts/send-calendar-auth-reminder.py --user-id <dingtalk_user_id>
```

确认收件人无误后再加 `--send` 发送工作通知。

## Smoke Test

```bash
bash deploy/smoke-test.sh
```

等价手工检查：

```bash
systemctl status tdl-backend.service --no-pager
systemctl status tdl-stream-bot.service --no-pager
systemctl status tdl-intake-worker.service --no-pager
systemctl status tdl-pilot-metrics.timer --no-pager
curl -fsS http://127.0.0.1:8010/health
```

随后在钉钉里给机器人发一条简单消息，确认有回复。
