# Pilot Metrics 首次读数与日历缺口诊断 — 2026-05-22

## 背景

本记录用于补充 `design/23-日常TDL试点验收闭环-2026-05-18.md` 中的日常指标闭环。

2026-05-22 23:19 CST 时，生产 `tdl-pilot-metrics.timer` 尚未到 23:50 自动导出时间。为提前判断试点状态，手动在生产环境只读执行：

```bash
.venv/bin/python scripts/export-daily-pilot-metrics.py --date 2026-05-22
```

## 指标读数

时间窗口：

```text
2026-05-18T00:00:00+08:00 -> 2026-05-23T00:00:00+08:00
```

| Metric | Value | Target | 初步判断 |
|---|---:|---:|---|
| Weekly active users | 2 | >= 2 | 达标 |
| TDL closure rate | 61.5% (8/13) | >= 60% | 刚好达标 |
| AI draft confirmation rate | N/A (0/0) | >= 70% | 当前统计源暂无 diff 记录 |
| Calendar event generation rate | 50.0% (9/18) | >= 90% | 未达标 |
| Average response time | N/A | < 5s | 当前统计源暂无 async intake 记录 |
| Draft ignore rate | N/A (0/0) | < 20% | 当前统计源暂无 diff 记录 |

## 结论

短期可用性信号：

- 周活跃用户达到 2 人，符合 Frank + 李珍试点范围。
- 本周闭环率 61.5%，略高于 60% 目标。

主要缺口：

- 日历事件生成率只有 50%，明显低于 90% 目标。
- 草稿确认率、平均响应时间、忽略率当前为 N/A，说明相关数据源尚未形成可解释读数。

## 日历缺口诊断

已新增并部署只读脚本：

```bash
.venv/bin/python scripts/diagnose-pilot-calendar-gaps.py
```

生产执行结果显示 open TDL 中共有 9 条缺少 `calendar_event_id`：

| Reason | Count | 解释 |
|---|---:|---|
| app_calendar_scope_missing_at_attempt | 4 | 5 月 16 日应用尚未开通日历创建权限时失败的历史任务 |
| invalid_calendar_user_identifier | 1 | 手工联调时使用了不能被日历 API 解析的 userId |
| invalid_or_expired_auth_code | 1 | 旧授权码刷新失败 |
| no_calendar_attempt | 1 | live_test 任务没有日历审计记录 |
| missing_user_authorization | 1 | 李珍账号缺少日历授权 |
| calendar_payload_reminder_method_rejected | 1 | 钉钉日历 API 拒绝当前 reminder method 参数 |

## 处理建议

1. 不把日历生成率低简单归因成当前主链路故障；其中多数是早期权限/联调历史残留。
2. 不立即批量重试创建日历事件，避免对历史测试任务和真实用户产生意外日历写入。
3. 下一步应先确认：
   - 生产日历权限当前是否已完整开通。
   - 李珍是否需要完成一次日历授权。
   - `Unknown reminder method` 是否仍会影响新创建任务。
4. 若后续要修复历史缺口，应先做显式 allowlist 的单条重试脚本，而不是全量 backfill。
