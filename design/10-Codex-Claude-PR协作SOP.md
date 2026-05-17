# 10 · Codex 主开发 + Claude 审核 PR 协作 SOP

> 目的：把本项目中“Codex 开发、Claude 审核、用户拍板”的协作方式固化下来。后续开启新对话或新项目时，可直接把本文作为操作规范交给 Codex / Claude。

---

## 一、角色分工

| 角色 | 职责 | 明确不做 |
|------|------|----------|
| Codex | 主开发、测试、部署、开 PR、处理 review、合并 | 不让 Claude 同时改主线 |
| Claude | 只审 PR，挑漏洞，提出风险和测试缺口 | 不直接改主分支，不并行写代码 |
| 用户 | 最终裁决范围、业务判断、关键外部授权 | 不承担 git / 部署细节 |

核心原则：**一个 owner 写主线，一个 reviewer 挑问题。**

这能避免两个 AI 同时改文件导致文档漂移、代码冲突、责任不清。

---

## 二、每个 PR 的标准流程

### 1. Codex 开发前

Codex 先确认：

```bash
git status --short --branch
```

如果工作区里有用户改动：
- 先判断是否相关
- 不相关就不要碰
- 相关但会冲突，先说明风险
- 永远不要回退用户文件

### 2. Codex 开发后

必须完成四件事：

```bash
PYTHONPATH=. .venv/bin/pytest -q
git status --short --branch
git log --oneline -5
gh pr create ...
```

PR 标题必须带状态：

```text
[WIP] xxx
[Ready for review] xxx
```

PR 描述必须包含：

```markdown
## Summary
- 改了什么
- 为什么改
- 是否涉及产品行为变化

## Verification
- `PYTHONPATH=. .venv/bin/pytest -q`
- 多少项测试通过
- 是否已部署 / smoke test / 真实钉钉测试

## Local unpushed commits
- no
```

如果本地还有没推上 GitHub 的提交，不能让 Claude 审。先推，或明确写：

```text
Local unpushed commits: yes, do not review yet
```

---

## 三、发给 Claude 的一次性消息模板

这是硬规则：**发给 Claude 的 review 请求必须是一条完整消息。**

不要先发链接、再补范围、再补测试结果、再补注意事项。这样 Claude 容易拿到残缺上下文，也容易审错范围。Codex 以前在本项目里犯过这个错误，后续必须避免。

允许发送第二条消息的情况只有三种：
- 第一条发错了，需要明确撤回并重发完整版本
- Claude 卡在取数方式上，需要补充“请改用本地分支 pr-xx 审”
- Claude 已经审完，Codex 修完后请求复审

推荐模板：

```text
Please review PR #<number>: <PR URL>.

Status: [Ready for review].
Local unpushed commits: no.

Scope:
1. <本 PR 的第一件事>
2. <本 PR 的第二件事>
3. <本 PR 的第三件事>

Verification:
- <测试命令>
- <测试结果>
- <如有：ECS deploy / smoke test / live DingTalk retest>

Please focus on:
1. <最担心的边界>
2. <是否符合设计文档>
3. <测试是否覆盖关键路径>

Do not modify files. Review only.
```

中文项目也可以用中文，但建议保留这些固定字段：`Status`、`Local unpushed commits`、`Scope`、`Verification`、`Please focus on`。

发送前自检：

```text
这条消息是否包含 PR 链接？
这条消息是否包含 Status？
这条消息是否包含 Local unpushed commits？
这条消息是否包含 Scope？
这条消息是否包含 Verification？
这条消息是否告诉 Claude 只 review、不改文件？
如果任何一项是否定，就不要发送。
```

---

## 四、Claude 审核时最常见的卡点

### 卡点 1：GitHub 私有仓库访问失败

现象：
- Claude 说 PR 页面打不开
- 或 web fetch 拉不到 diff

处理：
- 让 Claude 直接用本地仓库
- 本地准备一个 PR 分支名，例如 `pr-43`

```bash
git fetch origin pull/43/head:pr-43
```

如果 fetch 因网络失败，可以由 Codex 本地创建同名分支指向 PR commit。

### 卡点 2：PR 混入旧 commit

Claude 应只看“本 PR 相对 main 的 diff”。

可提醒 Claude：

```text
This PR may include previous merged commits in history. Please review only the diff against origin/main.
```

### 卡点 3：Claude 还在看未推送版本

审查前必须问：

```text
Local unpushed commits: no?
```

如果答案不是 no，不审。

---

## 五、Codex 取回 review 后怎么处理

Claude 的 review 分三类。

### 1. 阻塞问题

特征：
- 数据会错
- 权限会错
- 主流程会断
- 与设计文档冲突
- 测试覆盖不了真实风险

处理：
- Codex 修代码
- 跑测试
- 推到同一个 PR
- 再发 Claude 复审

### 2. 非阻塞建议

特征：
- 命名更清晰
- 测试可更完整
- 日后可优化
- 当前 MVP 不影响运行

处理：
- 如果成本低，当场补
- 如果会扩大范围，记入后续待办
- 不为“完美”拖住主链路

### 3. 明确 LGTM / 可以合

处理：

```bash
gh pr merge <number> --merge --delete-branch
git fetch origin main
```

合并后再部署。

不要在没合 PR 的情况下长期只靠手工 scp 热修。热修可以应急，但必须补 PR 追平仓库。

---

## 六、部署与验证顺序

推荐顺序：

```text
本地测试通过
→ 推 PR
→ Claude 审核
→ 合并 PR
→ ECS 部署
→ smoke test
→ 真实钉钉小样本测试
→ 用户确认体验
```

紧急线上 bug 可用临时热修：

```text
本地修最小代码
→ 单测
→ scp 到 ECS
→ restart service
→ smoke test
→ 立即补 PR
```

热修必须满足：
- 改动极小
- 不涉及迁移或大范围重构
- 当天补 PR
- 最终仓库与线上一致

---

## 七、什么时候不要让 Claude 审

以下情况先不要发：

| 场景 | 原因 |
|------|------|
| PR 还没推完整 | Claude 会审旧代码 |
| 本地有未提交变更 | 审查范围不可信 |
| 用户还在改同一批文件 | 容易重复文档漂移 |
| 问题还没复现清楚 | Claude 会被迫猜 |
| PR 同时包含多个无关主题 | review 质量下降 |

---

## 八、推荐给新对话的启动提示

后续新开 Codex 对话，可以直接贴：

```text
请按 /Users/frankj/companyai/TDL管理交互系统/design/10-Codex-Claude-PR协作SOP.md 的方式工作：

你负责主开发、测试、部署、开 PR。
Claude 只做 PR review，不直接改主线。
每个 PR 发给 Claude 前，先确认：
1. PR 标题是 [Ready for review]
2. Local unpushed commits: no
3. 测试结果写在 PR 描述里
4. 发给 Claude 的消息必须一次性完整发送
5. 禁止把 PR 链接、审查范围、测试结果、注意事项拆成多条消息陆续发给 Claude

Claude 审完后，按阻塞 / 非阻塞 / LGTM 三类处理。
```

---

## 九、是否需要做成 skill 或 agent 自动化

### 当前建议：先做成 Skill，而不是 Agent

理由：
- 这个流程主要是“规则 + 模板 + 判断标准”，适合 Skill
- 不需要长期运行的后台自动化
- 不应该让 agent 自动无脑合并 PR
- 仍需要 Codex 在每个项目里判断测试、部署、线上风险

建议创建一个本地 Codex skill：

```text
skill name: pr-review-coordination
触发词：Claude 审 PR、PR review、让 Claude 审、合并 PR、Codex 主开发 Claude 审核
内容：读取本 SOP，生成一次性 Claude review 消息，检查 PR 状态，汇总 review，决定是否合并
```

### 暂不建议完全 Agent 自动化

Agent 自动化适合：
- 定时扫 PR
- CI 全绿后提醒 reviewer
- 自动生成 review brief

但不适合现在直接自动合并：
- 业务判断还没稳定
- 钉钉权限、ECS 部署、真实用户体验都有外部状态
- 自动合并容易把“测试通过但产品错了”的改动放上线

### 更稳的演进路线

1. **现在**：用本文档作为人工可控 SOP
2. **下一步**：沉淀为 Codex Skill，自动生成 Claude review brief
3. **成熟后**：增加 GitHub Action，检查 PR 描述必须包含 `Local unpushed commits`、`Verification`
4. **最后**：只对低风险纯测试 / 文档 PR 开启自动合并

---

## 十、最低质量门槛

每次合并前至少满足：

- PR 是 `[Ready for review]`
- Claude 已审
- 阻塞问题已处理
- 本地测试通过
- 没有未推送提交
- 合并后 main 可部署
- 如果已热修线上，仓库必须追平线上

这套流程的目标不是形式化，而是避免三类事故：

1. Claude 审到旧代码
2. Codex 合了未审完整的代码
3. 线上热修和 GitHub 主线分叉
