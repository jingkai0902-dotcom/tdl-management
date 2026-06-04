# 安全与运维改动 PR 拆分和 Review Brief - 2026-05-31

## 一、建议拆分

当前改动建议拆成两个 PR，不建议混成一个大 PR。

### PR-Ops：后台状态锚点与 intake worker 可观测性

目标：

1. 增加 runtime state 基础设施。
2. 让 intake worker 写 heartbeat / started / success / failure。
3. 让生产检查能发现 worker 假活和队列卡死。

文件范围：

- `.gitignore`
- `.env.example`
- `README.md`
- `app/config.py`
- `app/runtime_state.py`
- `app/workers/intake_queue.py`
- `scripts/tdl-prod-check.sh`
- `tests/test_runtime_state.py`
- `tests/test_intake_queue_worker.py`
- `logs/2026-05-31-系统安全性检查与PR-Ops记录.md`

主要行为变化：

1. 本地默认状态目录为 `runtime_state/`，已加入 `.gitignore`。
2. 可通过 `RUNTIME_STATE_DIR` 指定生产状态目录。
3. intake worker 空轮询会刷新 heartbeat。
4. intake worker 处理 item 时会记录 started / success / failure。
5. `tdl-prod-check.sh` 新增三类检查：
   - intake worker state 文件存在。
   - intake worker heartbeat 不超过 120 秒。
   - intake queue 中不存在 processing 超过 10 分钟或 failed 达到 max attempts 的项。

不做：

1. 不新增数据库表。
2. 不接 Prometheus / Grafana。
3. 不改变 intake queue 状态机。
4. 不改变 LLM 调用或钉钉发送。

Claude review 重点：

1. `runtime_state` 写入失败是否确实不会影响主业务。
2. 错误摘要脱敏是否足够保守。
3. `tdl-prod-check.sh` 的 stale / exhausted SQL 是否能在生产 PostgreSQL 正常运行。
4. heartbeat 120 秒阈值是否会误报。
5. 状态文件路径是否会被 systemd hardening 阻断。

验收命令：

```bash
bash -n scripts/tdl-prod-check.sh
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_runtime_state.py tests/test_intake_queue_worker.py tests/test_intake_queue_service.py
```

生产部署前置：

1. 确认生产 `RUNTIME_STATE_DIR` 是否显式设置。
2. 部署后等待 intake worker 至少空轮询一次，再跑 `scripts/tdl-prod-check.sh`。

## 二、PR-Sec：内部 API 保护、外部入口 allowlist 与部署 hardening

目标：

1. 给内部写入、调试、运维 API 加统一 internal key。
2. Nginx 模板从整体代理改成显式 allowlist。
3. systemd 服务增加基础 hardening。
4. 修复卡片回调异常日志打印完整 payload 的问题。

文件范围：

- `.env.example`
- `README.md`
- `app/config.py`
- `app/api/auth.py`
- `app/api/tdl_crud.py`
- `app/api/dingtalk_webhook.py`
- `app/api/meetings.py`
- `app/api/reminders.py`
- `app/api/reports.py`
- `app/integrations/dingtalk_stream_bot.py`
- `deploy/nginx-tdl.conf`
- `deploy/tdl-backend.service`
- `deploy/tdl-stream-bot.service`
- `deploy/tdl-intake-worker.service`
- `deploy/tdl-pilot-metrics.service`
- `tests/test_api_auth.py`
- `tests/test_api_auth_routes.py`
- `design/37-公网入口与API认证边界方案-2026-05-31.md`
- `logs/2026-05-31-系统安全性检查与PR-Ops记录.md`

主要行为变化：

1. 新增 `INTERNAL_API_KEY`。
2. 生产环境下，以下路由需要 `X-TDL-Internal-Key`：
   - `/tdls`
   - `/dingtalk/*`
   - `/meetings/*`
   - `/reminders/*`
   - `/reports/*`
3. `APP_ENV=development` 且未配置 key 时允许本地测试继续运行。
4. Nginx 模板只允许：
   - `/tdl/`
   - `/tdl/entry`
   - `/tdl/health`
   - `/tdl/calendar/auth/start`
   - `/tdl/calendar/auth/callback`
   其他 `/tdl/` 默认 `403`。
5. systemd 服务增加 `NoNewPrivileges`、`PrivateTmp`、`ProtectSystem=strict`、`ProtectHome`、`ReadWritePaths=/opt/bots/tdl/backend`、`RestrictSUIDSGID`。

不做：

1. 不做完整用户登录。
2. 不做工作台正式权限。
3. 不做钉钉 SSO。
4. 不做 token 数据库加密迁移。
5. 不部署生产。

Claude review 重点：

1. internal key 是否会误伤现有脚本、测试入口或未来受控调用。
2. 哪些路由还应保护，哪些例外不该保护。
3. Nginx allowlist 是否会影响现有工作通知入口和日历授权。
4. `/calendar/auth/start` 暂时公网保留是否可接受。
5. systemd hardening 是否可能阻断 `.env`、`.venv`、runtime_state 或 daily pilot metrics 写入。

验收命令：

```bash
bash -n deploy/deploy.sh deploy/smoke-test.sh scripts/tdl-deploy-prod.sh
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_api_auth.py tests/test_api_auth_routes.py tests/test_dingtalk_api.py tests/test_meetings_api.py tests/test_reminders_api.py tests/test_reports_api.py
```

生产部署前置：

1. Frank 确认生成并写入生产 `INTERNAL_API_KEY`。
2. 确认当前公网路径只依赖 Nginx allowlist 中的入口。
3. 部署后必须验证内部 API 公网拒绝、内部带 key 可访问。

## 三、当前共同验证

已执行：

```bash
bash -n scripts/tdl-prod-check.sh deploy/deploy.sh deploy/smoke-test.sh scripts/tdl-deploy-prod.sh
PYTHONPATH=. .venv/bin/python -m pytest -q
```

结果：

```text
312 passed in 0.79s
```

另执行：

```bash
.venv/bin/python -m pip_audit -r requirements.txt
```

结果：

```text
No known vulnerabilities found
```

## 四、合并和部署建议

推荐顺序：

1. 先 review 并合并 PR-Ops。
2. 部署 PR-Ops，确认 intake worker runtime state 正常产生。
3. 再 review PR-Sec。
4. PR-Sec 部署前先配置 `INTERNAL_API_KEY`。
5. 部署 PR-Sec 后立刻做公网路径验证。

不建议：

1. 不把 PR-Ops 和 PR-Sec 混成一个 PR。
2. 不在未配置 `INTERNAL_API_KEY` 时部署 PR-Sec 到生产。
3. 不在没有公网路径验证时扩大试用。

## 五、Claude Review 处理记录

已处理：

1. `deploy/nginx-tdl.conf` 增加 `location = /tdl { return 301 /tdl/; }`，避免无尾斜杠 `/tdl` 被 catch-all 拒绝。
2. `app/runtime_state.py` 增加 `Authorization: Bearer ...` 脱敏，并用测试覆盖 `accessToken`、`apiKey`、Bearer token。
3. `tests/test_api_auth_routes.py` 将 `/calendar/auth/start` 纳入公共入口依赖检查。

保留待确认：

1. `/calendar/auth/start` 是否继续公网放行，取决于日历授权流程是否继续使用；若继续使用，后续应补一次性 nonce 或内部签名。
2. workbench 路由当前仍依赖 feature gate 和 Nginx allowlist，不在本次 PR-Sec 内改变页面入口策略。
3. `PROCESSING_STALE_MINUTES = 10` 暂作为运维检查阈值，生产观察后再决定是否参数化。
