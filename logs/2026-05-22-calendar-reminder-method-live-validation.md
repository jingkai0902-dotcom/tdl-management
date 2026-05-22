# 钉钉日历提醒参数生产验证 — 2026-05-22

## 背景

`scripts/diagnose-pilot-calendar-gaps.py` 诊断出一条生产日历同步失败：

```text
calendar_payload_reminder_method_rejected
```

对应钉钉 API 错误：

```text
Unknown reminder method.
```

代码中原先创建日历事件时发送：

```json
{"method": "app", "minutes": 5}
```

PR #126 已将其改为：

```json
{"method": "dingtalk", "minutes": 5}
```

## 自动化验证

本地定向测试：

```bash
PYTHONPATH=. .venv/bin/pytest -q tests/test_dingtalk_client.py tests/test_calendar_service.py
```

结果：

```text
31 passed
```

## 生产验证

2026-05-22 23:36 CST，部署 PR #126 后，在生产环境使用 Frank 的日历授权记录创建一条临时验证日程：

```text
Title: Codex日历提醒参数验证-可删除
Due: 2026-05-23 09:30 Asia/Shanghai
Reminder method: dingtalk
```

钉钉返回成功：

```text
calendar_create_ok event_id=UlBlZ2RMOStkQS93WENqYjVtdFdJdz09
```

随后调用钉钉日历删除接口清理该验证日程：

```text
status=200 body={"requestId":"93F4347B-B26D-7A41-9EA3-0311AA48C381"}
```

## 结论

- `Unknown reminder method` 已在生产环境复现修复路径并验证通过。
- 验证日程已删除，没有遗留到 Frank 日历。
- 该修复只解决 reminder method 参数错误，不处理早期权限缺失、旧授权码、李珍未授权等其他日历缺口。
