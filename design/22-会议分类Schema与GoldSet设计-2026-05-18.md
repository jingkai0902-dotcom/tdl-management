# 22 · 会议分类 Schema 与 Gold Set 设计 — 2026-05-18

## 一、本文定位

本文把 `16-会议内容判定口径` 中的人工判断标准，翻译成后续可以：

1. 人工标注
2. 模型抽取
3. 自动评测
4. 错例回收

的一套统一 schema 与 gold set 设计。

本文只解决“怎么标、怎么评”的问题，不直接重新标注 5 月月会材料。  
5 月材料的正式重标属于下一步 `PR-C`。

## 二、设计原则

### 1. 先保真，再抽取

会议材料的首要目标不是尽可能多地产生 TDL，而是尽可能少地产生伪结论。

因此：

1. 原文证据必须先于抽象结论。
2. 推断必须显式标记，不能伪装成事实。
3. `confirmed` 只能在满足 `What + Who + When` 后成立。
4. 对“愿望、倡导、方向感、个人设想”，默认宁可降级，不可冒进。

### 2. 成熟度与对象类型分离

任何会议片段都必须同时回答两个问题：

1. 它成熟到哪一步
2. 它本质上是什么

不能再用一个含混的“决议”把二者揉在一起。

### 3. 人工基准优先于模型输出

gold set 是后续模型评测的裁判，不是模型输出的复述。

只有先有人工基准，后续的：

1. 召回率
2. 误提率
3. 伪决议率
4. 编造日期数

才有可靠参照。

## 三、一级 schema

### 1. `maturity`

| 值 | 含义 | 是否可直接转 TDL |
|---|---|---|
| `fact` | 已发生 / 已存在的客观内容 | 否 |
| `confirmed` | 已达到执行阈值 | 可以进入 TDL 草稿池 |
| `pending` | 已进入讨论，但尚未达到执行阈值 | 否 |
| `spark` | 愿望、倡导、方向、初步设想 | 否 |
| `signal` | 现象、风险、机会或值得继续看的苗头 | 否 |

### 2. `object_type`

| 值 | 含义 |
|---|---|
| `Fact` | 客观事实 |
| `Task` | 可执行动作 |
| `Decision` | 判断或处理结论 |
| `Issue` | 待处理问题 |
| `Idea` | 火花、设想、倡导 |
| `Signal` | 观察线索 |

### 3. 基本组合规则

| 组合 | 说明 |
|---|---|
| `fact + Fact` | 已发生事实 |
| `confirmed + Task` | 已明确可执行动作 |
| `confirmed + Decision` | 已明确处理结论，但未必立即形成任务 |
| `pending + Issue` | 已进入讨论、仍待处理 |
| `spark + Idea` | 值得保留但未成熟的想法 |
| `signal + Signal` | 需要后续验证的观察线索 |

不允许默认出现：

1. `spark + Task`
2. `signal + Task`
3. `pending + confirmed`
4. 没有证据片段的 `confirmed`

## 四、字段 schema

### 1. 所有对象都必须有的字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `item_id` | string | 标注项唯一编号 |
| `source_id` | string | 来源材料编号 |
| `source_type` | enum | `meeting_transcript / report / workbook / derived_note` |
| `speaker` | string/null | 发言人；非口语材料可为空 |
| `speaker_role` | string/null | 发言人岗位或职责范围 |
| `evidence_span` | string | 原始证据片段，不允许只写总结 |
| `evidence_locator` | string | 时间戳、页码、sheet 名或段落定位 |
| `summary` | string | 人工保守摘要 |
| `maturity` | enum | `fact / confirmed / pending / spark / signal` |
| `object_type` | enum | `Fact / Task / Decision / Issue / Idea / Signal` |
| `confidence` | enum | `high / medium / low` |
| `review_status` | enum | `draft / reviewed / disputed / locked` |
| `notes` | string/null | 标注说明、争议点、降级原因 |

### 2. `confirmed` 必填字段

只有 `maturity = confirmed` 时，才允许填写：

| 字段 | 类型 | 说明 |
|---|---|---|
| `what` | string | 要做什么 |
| `who` | string | 谁负责 |
| `when_type` | enum | `start / due / both` |
| `when_value` | string | 已明确的开始时间或截止时间 |
| `evidence_for_what` | string | 支撑 `What` 的证据 |
| `evidence_for_who` | string | 支撑 `Who` 的证据 |
| `evidence_for_when` | string | 支撑 `When` 的证据 |
| `tdl_eligible` | boolean | 是否可进入 TDL 草稿池 |

强约束：

1. `what / who / when_value` 任一缺失，`maturity` 不得为 `confirmed`
2. `tdl_eligible = true` 仅允许出现在 `confirmed + Task`
3. `Decision` 可以是 `confirmed`，但若没有动作分配，不应直接转 TDL

### 3. 非 confirmed 对象的扩展字段

| 字段 | 适用对象 | 说明 |
|---|---|---|
| `next_review_trigger` | `pending / spark / signal` | 下次回看触发条件 |
| `upgrade_condition` | `pending / spark / signal` | 升级到下一状态所需证据 |
| `related_entities` | 全部 | 涉及人员、部门、项目、指标 |
| `derived_from` | 全部 | 如来自个人述职、复盘材料、二次分析 |

## 五、分类闸门

### 1. `confirmed` 三要素闸门

只有以下三问都能从原始材料中找到直接证据，才允许进入 `confirmed`：

1. `What`：具体做什么
2. `Who`：明确由谁负责
3. `When`：明确开始时间或完成时间之一

| 情况 | 处理 |
|---|---|
| 有 `What`，无 `Who` | 降级为 `pending + Issue` |
| 有 `What + Who`，无 `When` | 降级为 `pending + Issue` |
| 只有目标或倡导 | 降级为 `spark + Idea` |
| 只有现象或风险 | 降级为 `signal + Signal` |

### 2. 来源闸门

| 来源 | 默认处理 |
|---|---|
| 会议录音原文 | 可作为一级证据 |
| 个人述职 / 部门提报 | 只说明“个人提出”，默认不能代表组织已决议 |
| 人工摘要 | 只能作为导航，不可替代原文证据 |
| 模型归纳 | 只能作为候选，不可直接进入 gold set |

### 3. 深加工闸门

若摘要内容出现以下情况，必须回查原文：

1. 原文只说方向，摘要却出现完整方案
2. 原文只说现象，摘要却出现明确因果
3. 原文只说期待，摘要却出现责任人和排期
4. 原文只提个人计划，摘要却写成组织决议

## 六、Gold Set 设计

### 1. gold set 的用途

gold set 不是“理想答案”，而是“人工认可的基准答案”。

它至少服务四类任务：

1. 训练标注者口径一致
2. 评测模型是否误提、漏提
3. 识别伪决议、编造日期、深加工
4. 作为后续 PR-C 和 evaluator 的回归样本

### 2. gold set 的最小组成

第一版 gold set 不追求覆盖全部会议内容，先覆盖最关键的六类样本：

| 样本类型 | 最低数量 | 目的 |
|---|---:|---|
| `fact + Fact` | 8 | 验证系统能保留客观事实 |
| `confirmed + Task` | 8 | 验证三要素识别 |
| `confirmed + Decision` | 4 | 验证“已判断但不一定转 TDL” |
| `pending + Issue` | 8 | 验证未成熟内容不误转任务 |
| `spark + Idea` | 8 | 验证倡导和设想不被深加工 |
| `signal + Signal` | 8 | 验证线索不被过度解释 |

第一版建议总量：`44` 条左右。

### 3. gold set 的样本来源

第一批样本应优先来自：

1. 5 月月会录音转录
2. 5 月个人述职材料
3. 已被 Frank 指出有“熟悉又陌生”风险的争议片段

这样第一批 gold set 就能天然覆盖系统最容易犯错的地方。

### 4. gold set 的标注层级

每条样本至少经过四层标注：

1. `证据层`：原文片段和定位
2. `对象层`：`maturity + object_type`
3. `任务准入层`：是否满足三要素、是否可转 TDL
4. `争议层`：为什么容易被误判、人工为何如此定类

### 5. 争议样本必须单独保留

gold set 不能只保留“很容易”的样本。以下内容必须单列为 hard cases：

1. 管理倡导
2. 长期目标
3. 部门计划
4. 个人述职方案
5. 数据信号
6. 讨论中出现的半成品动作

如果系统只在简单样本上表现好，实际价值很低。

## 七、评测指标

### 1. 召回率

含义：

> 人工基准里本来应该被系统识别出来的对象，有多少被系统识别到了。

公式：

```text
召回率 = 被正确识别出的 gold items / gold set 中应识别的全部 items
```

说明：

1. 召回率低，说明系统漏掉了很多值得保留的内容
2. 但召回率不能单独看，因为“什么都提”也可能让召回率很高

### 2. 精准率

含义：

> 系统提出来的对象里，有多少是真的对。

公式：

```text
精准率 = 被人工认可的模型输出 / 模型输出总数
```

### 3. 伪决议率

含义：

> 被系统标成 `confirmed` 的内容中，有多少其实没有达到 `What + Who + When`。

公式：

```text
伪决议率 = 错误 confirmed 数 / 全部 predicted confirmed 数
```

这是会议录入最重要的安全指标。

### 4. 编造日期数

含义：

> 原文没有日期，系统却补造了时间字段的次数。

### 5. 深加工错例数

含义：

> 原文没有说到的方案、因果、成熟度，被系统自行扩写出来的次数。

### 6. 当前阶段的优先级

阶段 1 的优先级不是“召回率越高越好”，而是：

1. 伪决议率接近 `0`
2. 编造日期数为 `0`
3. 深加工错例持续下降
4. 在此前提下，再逐步提高召回率

## 八、标注流程

### 1. 单条样本流程

1. 先定位原始片段
2. 摘录原文，不先写结论
3. 判定 `maturity`
4. 判定 `object_type`
5. 若为 `confirmed`，再过三要素闸门
6. 填写争议说明
7. 人工复核后锁定

### 2. 双人复核规则

对于以下样本，必须至少两轮人工复核：

1. `confirmed`
2. 任何 Frank 已指出“熟悉又陌生”的片段
3. 任何来自个人述职但可能被误写成组织决议的内容

### 3. 争议处理规则

若两次复核结论不同：

1. 先回到原文
2. 再检查是否混淆了“会议说过”与“会议决定了”
3. 若仍无法达成一致，宁可降级，不可升级

## 九、与后续 PR 的关系

| 后续 PR | 如何承接本文 |
|---|---|
| `PR-C` | 按本文 schema 重新标注 5 月月会材料，形成人工基准 |
| `PR-D` | 不直接依赖本文，但日常 TDL 试点中的“误建任务”问题要回看同一套严苛原则 |
| 后续 evaluator PR | 直接使用本文定义的指标和 gold set 字段 |
| 后续会议 Skill PR | `meeting-classification-strict` 应严格服从本文 schema |

## 十、当前结论

会议录入的第一阶段目标，不是“尽量聪明”，而是“先足够克制”。

因此，后续所有会议材料处理都按以下顺序执行：

```text
先保留证据
再做分类
再过闸门
最后才考虑是否进入 TDL
```

只有这样，会议系统才可能逐步获得管理者信任，而不是因为几次伪决议把整个链路打穿。
