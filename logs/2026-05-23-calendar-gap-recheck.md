# Calendar Gap 复查 — 2026-05-23

## 背景

2026-05-22 首次 pilot metrics 显示日历事件生成率只有 50.0%（9/18），主要来自早期权限缺失、旧授权码、测试任务和 reminder method 参数问题。

PR #126 已修复 `Unknown reminder method`，后续又清理了 pilot attention backlog 和 draft 残留。本次复查确认当前 open TDL 是否仍有日历缺口。

## 生产复查

生产执行：

```bash
.venv/bin/python scripts/diagnose-pilot-calendar-gaps.py
```

结果：

```text
# Pilot Calendar Gaps

- Missing calendar events: 0
```

同时导出 2026-05-23 周累计指标：

```text
Calendar event generation rate | N/A (0/0) | >= 90%
Open TDL status mix | active 0 / attention 0 / snoozed 0 | diagnostic
```

## 结论

当前没有 open TDL 缺少 `calendar_event_id`。

日历事件生成率显示 `N/A (0/0)` 的原因是当前 open TDL 分母为 0，不是日历同步失败。后续判断日历能力，应看新增真实 active TDL 是否能正常写入日历，而不是继续按 2026-05-22 的历史缺口判断。
