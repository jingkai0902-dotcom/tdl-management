# Pilot 草稿结果诊断与处理 — 2026-05-23

## 背景

2026-05-22 指标显示：

- AI 草稿确认率：20.0%（1/5），低于 70% 目标。
- 用户主动忽略率：40.0%（2/5），高于 20% 目标。

本轮目标不是直接按总指标修功能，而是先抽样查看草稿明细，判断低确认率和高忽略率是否来自真实试用问题、测试残留或误建草稿。

## 本轮变更

新增只读诊断脚本：

```bash
python scripts/diagnose-pilot-draft-outcomes.py --date 2026-05-22
```

脚本按周累计列出草稿的：

- 当前状态
- 结果分类
- 取消原因
- 缺失字段
- 标题
- 最近草稿动作

同时修复一个真实错例：

```text
补充说明：任务负责人为李珍，非石影
```

此前当系统找不到 15 分钟内可修正对象时，会把这句话误建成新草稿。现在会返回 `未找到可修正的 TDL`，不再新建草稿。

## 生产验证

部署后生产 smoke test 通过：

```text
{"status":"ok","db":"connected"}
TDL smoke test passed
```

本地全量测试：

```text
270 passed
```

## 诊断结果

清理前，2026-05-18 至 2026-05-22 周累计草稿为 5 条：

| TDL ID | 结果 | 状态 | 原因 | 标题 |
|---|---|---|---|---|
| 224f2f35-1061-414d-996b-05b13514331d | still_draft | draft | D1 测试残留 | 完成 Codex 草稿按钮 D1 测试 |
| 8285fa28-1228-4a23-9995-7112ef8e8e71 | confirmed_then_canceled | canceled | 已按测试残留清理 | 完成 Codex 草稿模板卡 D1 复测 |
| 99182e0f-1b13-45c1-a3ba-02b5cb1c70a1 | canceled | canceled | D7 忽略测试 | 完成 Codex 草稿模板卡 D7 忽略测试 |
| 47d1e643-8dd6-4c47-9f48-932ee3a50670 | still_draft | draft | follow-up 找不到目标后的误建草稿 | 补充说明：任务负责人为李珍，非石影 |
| 15c7fc55-8172-420d-abdb-9599653cf0ed | canceled | canceled | 真实用户忽略 | 确保摸查后每人提交完成的表格 |

判断：

1. 5 条草稿中至少 3 条是测试或验证残留。
2. 1 条是已修复的 follow-up 误建草稿。
3. 只有 1 条更像真实用户主动忽略。
4. 因此 20% 确认率和 40% 忽略率不能直接解释为“真实用户不信任草稿”，当前指标被早期验证数据明显污染。

## 清理动作

扩展 `scripts/cleanup-pilot-attention-backlog.py`，新增 `draft-residual` 显式 allowlist，仅包含两个明确 draft 残留：

- `224f2f35-1061-414d-996b-05b13514331d`
- `47d1e643-8dd6-4c47-9f48-932ee3a50670`

先 dry-run：

```text
dry_run=True
category=draft-residual
expected=2 matched=2 errors=0
```

再执行：

```text
dry_run=False
category=draft-residual
expected=2 matched=2 errors=0
applied=2
```

清理后复查：

```text
Drafts sampled: 5
Outcomes: canceled 4 / confirmed_then_canceled 1
```

当前没有遗留 `still_draft`。

## 后续判断

本轮已完成：

1. 草稿结果可诊断。
2. 明确测试残留 draft 已清理。
3. `补充说明 / 负责人为 X，非 Y` 这类无目标上下文修正不再误建草稿。

后续 pilot metrics 仍会显示历史草稿确认率和忽略率不达标，因为统计窗口内仍包含已发生的测试残留和忽略动作。下一步应看新增真实草稿的表现，而不是继续用 2026-05-22 的历史比例判断当前质量。
