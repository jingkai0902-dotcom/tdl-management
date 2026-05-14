# MVP 开发计划

> 7 个开发批次，按依赖顺序串行。每批有明确文件清单和验收标准。

---

## 技术骨架

| 层 | 选型 | 说明 |
|----|------|------|
| 后端框架 | **FastAPI** (Python 3.11+) | 异步支持，AI API 调用密集场景优势明显 |
| ORM | SQLAlchemy 2.0 (async) + Alembic | 数据库迁移管理 |
| 数据库 | PostgreSQL 15 | 已有服务器上安装/复用 |
| 调度器 | APScheduler | 比 Celery 轻，MVP 不需要消息队列 |
| 飞书 SDK | 复用现有 `feishu_client.py` | 已封装消息、日历、文档 API |
| AI 客户端 | 新建 `ai_client.py` | 封装 Claude + ChatGPT 双模型路由 |
| 配置 | python-dotenv + YAML | `.env` 存密钥，`config/*.yaml` 存业务参数 |
| 部署 | systemd + Nginx + git pull | 与励步项目同模式，路径 `/opt/bots/tdl/backend` |

### 项目目录结构（目标态）

```
/opt/bots/tdl/backend/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 配置加载（.env + YAML）
│   ├── database.py              # SQLAlchemy async engine + session
│   ├── models/
│   │   ├── tdl.py               # TDL 数据模型
│   │   └── audit.py             # 审计日志模型
│   ├── api/
│   │   ├── feishu_webhook.py    # 飞书事件回调
│   │   ├── tdl_crud.py          # TDL CRUD API
│   │   └── health.py            # 健康检查
│   ├── services/
│   │   ├── tdl_service.py       # TDL 业务逻辑
│   │   ├── ai_service.py        # AI 处理管道（4 个函数链）
│   │   ├── reminder_service.py  # 催收调度
│   │   └── review_service.py    # 周报生成
│   ├── integrations/
│   │   ├── feishu_client.py     # 飞书 API 封装（从 starplanet_ai 复用）
│   │   ├── feishu_card.py       # 飞书卡片构建
│   │   └── ai_client.py         # Claude + ChatGPT 客户端
│   └── utils/
│       ├── scheduler.py         # APScheduler 配置
│       └── security.py          # 权限校验
├── config/
│   ├── tdl_rules.yaml           # 置信度阈值、自动创建条件
│   ├── tag_dictionary.yaml      # 标签词典
│   ├── escalation_policy.yaml   # 升级策略参数
│   └── feishu_config.yaml       # 非敏感飞书配置（不含密钥）
├── skills/
│   ├── tdl-intake.SKILL.md      # 录入行为规则
│   ├── tdl-classify.SKILL.md    # 分类行为规则
│   ├── tdl-remind.SKILL.md      # 催收行为规则
│   ├── tdl-escalate.SKILL.md    # 升级行为规则
│   └── tdl-review.SKILL.md      # 复盘行为规则
├── alembic/                     # 数据库迁移
├── tests/
│   ├── test_tdl_service.py
│   ├── test_ai_service.py
│   ├── test_reminder_service.py
│   └── test_feishu_card.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 批次 1：项目骨架 + 数据库 + 配置 + 审计日志

**依赖**：无（第一批）  
**预计**：1-2 天

### 文件清单

| # | 文件 | 职责 |
|---|------|------|
| 1 | `requirements.txt` | FastAPI, SQLAlchemy, asyncpg, alembic, apscheduler, anthropic, openai, httpx, pyyaml, python-dotenv, pydantic |
| 2 | `.env.example` | 模板：`DATABASE_URL`, `CLAUDE_API_KEY`, `OPENAI_API_KEY`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_VERIFICATION_TOKEN` |
| 3 | `.gitignore` | `.env`, `__pycache__`, `.pytest_cache`, `alembic/versions/*.pyc` |
| 4 | `app/config.py` | 加载 `.env` + 读取 `config/*.yaml`，合并为单例配置对象 |
| 5 | `app/database.py` | SQLAlchemy async engine + async_session factory |
| 6 | `app/models/tdl.py` | TDL 数据模型（见下方 schema） |
| 7 | `app/models/audit.py` | AuditLog 模型 |
| 8 | `app/models/__init__.py` | 模型注册 |
| 9 | `alembic.ini` + `alembic/env.py` | Alembic 迁移配置 |
| 10 | `app/main.py` | FastAPI 最小入口（`/health` 端点 + 迁移用了 logger） |
| 11 | `app/api/health.py` | `GET /health` 返回 `{"status":"ok","db":"connected"}` |
| 12 | `config/tdl_rules.yaml` | confidence_threshold: 0.7, auto_create_threshold: 0.85, max_daily_tokens: 50000 |
| 13 | `config/escalation_policy.yaml` | 升级节奏参数 |
| 14 | `config/tag_dictionary.yaml` | 从 `design/05-标签词典.md` 转 YAML |
| 15 | `config/feishu_config.yaml` | 卡片样式、消息模板（不含密钥） |

### TDL 表核心 Schema

```sql
CREATE TABLE tdl (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tdl_id        VARCHAR(20) UNIQUE NOT NULL,          -- TDL-20260514-001
    title         VARCHAR(500) NOT NULL,
    description   TEXT,
    owner_id      VARCHAR(100) NOT NULL,                 -- 飞书 user_id
    created_by    VARCHAR(100) NOT NULL,
    due_at        TIMESTAMP WITH TIME ZONE,
    start_at      TIMESTAMP WITH TIME ZONE,
    status        VARCHAR(20) DEFAULT 'draft',           -- draft/active/overdue/snoozed/escalated/done/cancelled
    priority      VARCHAR(5) DEFAULT 'P2',               -- P0/P1/P2/P3
    source        VARCHAR(50) DEFAULT 'manual',          -- manual/feishu_msg/feishu_calendar
    source_event_id VARCHAR(200),                        -- 日历事件 ID，防重复
    business_line VARCHAR(50),                           -- 励步英语/斯坦星球/飞书工资/跨业务
    product_line  VARCHAR(50),
    function_domain VARCHAR(50),                         -- 教务教学/销售/市场/人力/行政/运营管理/客服续费/财务/产品研发
    stage         VARCHAR(20),                           -- 立项/执行中/验收/复盘
    key_actions   TEXT[],                                -- 关键动作标签数组
    outcome_kpi   TEXT,                                  -- 效果指标
    roi_estimate  VARCHAR(10),                           -- 高/中/低
    tags          TEXT[],                                -- @waiting_for/@blocked/@review/@delegated/@recurring/@next_action
    waiting_for   VARCHAR(100),                          -- 等待谁（飞书 user_id）
    blocked_by    UUID REFERENCES tdl(id),               -- 被哪条 TDL 阻塞
    parent_id     UUID REFERENCES tdl(id),               -- 父任务
    completion_criteria TEXT,                            -- 完成标准
    confidence    FLOAT DEFAULT 0.0,                     -- AI 分类置信度
    snooze_until  TIMESTAMP WITH TIME ZONE,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### AuditLog 表

```sql
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tdl_id      UUID REFERENCES tdl(id),
    actor       VARCHAR(100),         -- user/system/ai
    action      VARCHAR(50),          -- created/updated/completed/snoozed/escalated/ai_modified/user_confirmed/owner_viewed
    field       VARCHAR(50),          -- 哪个字段被改
    old_value   TEXT,
    new_value   TEXT,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 验收标准
- [ ] `uvicorn app.main:app` 启动成功
- [ ] `GET /health` 返回 200 且 db 状态 connected
- [ ] `alembic upgrade head` 建表成功
- [ ] `config/` 下 4 个 YAML 可被 `app/config.py` 正确加载
- [ ] 手动插入一条测试 TDL → 查询成功
- [ ] 审计日志表写入成功

---

## 批次 2：飞书机器人收发 + 文本 TDL 创建 + 卡片交互

**依赖**：批次 1  
**预计**：2-3 天

### 文件清单

| # | 文件 | 职责 |
|---|------|------|
| 1 | `app/api/feishu_webhook.py` | 飞书事件回调：接收消息事件，验签，路由到处理函数 |
| 2 | `app/integrations/feishu_client.py` | 从 starplanet_ai 复用，补充：发送卡片消息、更新卡片 |
| 3 | `app/integrations/feishu_card.py` | 构建确认卡片、草稿卡片、已创建卡片、追问卡片 |
| 4 | `app/services/tdl_service.py` | TDL CRUD：创建草稿、确认创建、自动创建、查询 |
| 5 | `app/api/tdl_crud.py` | REST API：`POST /tdl`, `GET /tdl/{id}`, `PATCH /tdl/{id}`, `GET /tdl?status=active` |

### 核心流程

```
用户飞书消息
  → feishu_webhook.py 验签 + 解析
  → tdl_service.create_draft(text)
  → ai_service.intake_extract(text)  [批次 3 实现，本批次先用规则版占位]
  → 判断自动创建 or 草稿确认 [规则：config/tdl_rules.yaml]
  → feishu_card 构建卡片
  → feishu_client 发送卡片
```

### 卡片交互
- 确认创建卡片：`[✅ 确认] [📅 改时间] [👤 改负责人] [📝 补标准] [⚡ 改优先级] [🗑 忽略]`
- 已创建卡片：`[✏️ 修改] [✅ 标记完成] [⏸ 暂缓]`
- 草稿过期：24 小时未确认 → 自动取消 + 通知

### 验收标准
- [ ] 飞书给机器人发「下周三前审核斯坦星球暑期班方案」→ 收到确认卡片
- [ ] 点「确认创建」→ 数据库出现 active TDL，审计日志有 create 记录
- [ ] 缺截止时间的消息 → 收到追问卡片「请补充截止时间」
- [ ] 高置信度明确任务 → 收到「已创建」卡片（非草稿）
- [ ] 飞书消息验签通过，伪造请求被拒绝

---

## 批次 3：AI 处理管道

**依赖**：批次 2  
**预计**：3-4 天

### 文件清单

| # | 文件 | 职责 |
|---|------|------|
| 1 | `app/integrations/ai_client.py` | Claude + ChatGPT 双模型客户端，带 fallback 路由 |
| 2 | `app/services/ai_service.py` | 4 个函数链：intake_extract, classify_tags, detect_missing, suggest_next_action |
| 3 | `config/tdl_rules.yaml` | 补充：AI prompt 模板、confidence 阈值 |
| 4 | `config/tag_dictionary.yaml` | AI 分类的受控词表（已建，本批次确认格式 AI 可消费） |
| 5 | `skills/tdl-intake.SKILL.md` | 录入行为规则（行为原则，不含硬参数） |
| 6 | `skills/tdl-classify.SKILL.md` | 分类行为规则 |

### AI 函数链

```
intake_extract(text) → {title, due_at, owner, ...}
    ↓
classify_tags(extracted) → {business_line, function_domain, priority, tags, confidence}
    ↓
detect_missing(structured) → [{field, question}]
    ↓
suggest_next_action(structured) → "建议：..."
```

### 护栏实现

| 护栏 | 实现方式 |
|------|---------|
| 输出护栏：不编造业务线/人员 | 标签词典做 enum constraint，LLM 只能从中选 |
| 置信度 < 70% | 不硬塞，标记"待确认" |
| 成本护栏 | ai_client 内维护每日 token 计数器，超阈值拒绝调用 |
| 高风险护栏 | 升级/批量操作 → 检查 `config/escalation_policy.yaml` 的 require_confirmation 字段 |

### 验收标准
- [ ] 输入「下周三前审核斯坦星球暑期班方案」→ 准确提取 title, due_at, business_line=斯坦星球, function_domain=教务教学
- [ ] 输入模糊消息「那个英语课的事情」→ confidence < 70%，标记"待确认"
- [ ] 输入「励步招生方案」缺截止时间 → detect_missing 返回「请补充截止时间」
- [ ] 编造不存在的业务线 → AI 不输出不在标签词典中的值
- [ ] Claude API 挂了 → 自动 fallback 到 ChatGPT
- [ ] 单日 token 超阈值 → 返回「今日 AI 调用已达上限」

---

## 批次 4：催收调度 + 逾期追问 + 暂缓

**依赖**：批次 2（不需要等批次 3 全部完成，催收逻辑不依赖 AI）  
**预计**：2-3 天

### 文件清单

| # | 文件 | 职责 |
|---|------|------|
| 1 | `app/utils/scheduler.py` | APScheduler 配置：每日 08:30 触发 reminder_job，每周一 09:00 触发 review_job |
| 2 | `app/services/reminder_service.py` | 催收核心逻辑：查询到期/逾期 TDL → 按策略路由 → 构建提醒/追问/升级消息 |
| 3 | `app/integrations/feishu_card.py` | 补充：追问卡片（已完成/延期/需协助 按钮）、升级通知卡片 |
| 4 | `app/main.py` | 补充：启动 APScheduler |
| 5 | `skills/tdl-remind.SKILL.md` | 催收行为规则 |
| 6 | `skills/tdl-escalate.SKILL.md` | 升级行为规则 |

### 催收流程

```
APScheduler 每日 08:30 触发
  → 查询 status IN (active, overdue) AND due_at <= today + 3d
  → 分类：
     到期提醒：due_at = today → 推送「今天截止」
     逾期提醒：due_at < today AND status != escalated → 推送「已逾期 X 天」
     逾期 2 天 → 追问卡片（按钮：已完成/延期/需协助）
     逾期 3 天 + 未回复 → 自动升级（MVP 期通知少巍自己）
     逾期 7 天 → 标注 escalated
  
用户点「延期」→ 追问新截止时间 → 更新 + 审计日志
用户点「需协助」→ 记录 + 通知创建人
用户点「已完成」→ status = done + 审计日志
用户说「明天再提醒」→ snooze_until = 明天 09:00
```

### MVP 升级路由
少巍自用期没有真正上级 → 升级通知发给自己，标注 `[升级]`。推广后启用 `reports_to` 字段查直属上级。

### 验收标准
- [ ] 创建一条明天到期的 TDL → 明天 08:30 收到飞书提醒
- [ ] 创建一条昨天到期的 TDL（手动改数据）→ 今天 08:30 收到逾期提醒
- [ ] 逾期 2 天的 TDL → 收到追问卡片，点「已完成」→ status 变 done
- [ ] 逾期 3 天未回复 → 收到升级通知
- [ ] 对一条 TDL 说「明天再提醒」→ snooze_until = 明天 09:00，今天不再提醒，明天恢复
- [ ] 催收调度器在系统重启后自动恢复（APScheduler 持久化）

---

## 批次 5：轻量日历抓取

**依赖**：批次 2  
**预计**：1-2 天

### 文件清单

| # | 文件 | 职责 |
|---|------|------|
| 1 | `app/services/calendar_service.py` | 日历抓取核心：调飞书日历 API → 过滤 → 生成草稿 TDL |
| 2 | `app/utils/scheduler.py` | 补充：每 30 分钟触发 calendar_sync_job |
| 3 | `app/integrations/feishu_client.py` | 补充：日历事件列表 API |

### 抓取规则

```
每 30 分钟执行：
  → 调飞书日历 API 获取少巍本人未来 7 天事件
  → 过滤：标题/描述含 TDL/待办/需完成/截止/交付
  → 去重：source_event_id 已存在 → 跳过
  → 生成草稿 TDL：
      title = 事件标题
      due_at = 事件结束时间（全天事件 → 当日 18:00）
      source = feishu_calendar
      source_event_id = 飞书事件 ID
  → 自动创建条件判断 → 日历来源全部走草稿确认
  → 发草稿卡片给用户
```

### 边界处理
- 全天事件：`due_at` = 当天 18:00
- 已取消事件：查飞书事件 status=cancelled → 对应 TDL status → cancelled
- 已过事件：不生成（只抓未来 7 天）
- 关键词误判：走草稿确认，用户点忽略即可

### 验收标准
- [ ] 飞书日历创建一个「TDL 审核方案」事件 → 30 分钟内收到草稿卡片
- [ ] 同一个日历事件重复抓取 → 第二次不会生成重复草稿
- [ ] 日历事件不含关键词 → 不被抓取
- [ ] 用户点「确认创建」→ 草稿变 active TDL，source_event_id 已记录
- [ ] 用户点「忽略」→ 草稿取消，source_event_id 仍然记录（防止下次再抓）

---

## 批次 6：周报事实账本

**依赖**：批次 1（有数据就能跑）  
**预计**：1-2 天

### 文件清单

| # | 文件 | 职责 |
|---|------|------|
| 1 | `app/services/review_service.py` | 统计查询 + 周报生成 |
| 2 | `app/integrations/feishu_card.py` | 补充：周报卡片模板 |
| 3 | `skills/tdl-review.SKILL.md` | 周报行为规则 |

### 统计维度（纯事实，不分析）

```
本周数据：
  - 新增 TDL 数
  - 完成数 / 完成率
  - 逾期未清数
  - 延期处理数
  - waiting_for 中：按等待对象分组
  - blocked 中：按阻塞 TDL 列出
  - 超过 3 天未推进的 TDL 清单
  - 按业务线分布：完成率
下周到期清单
```

### 发送
每周一 09:00 飞书卡片推送（与催收调度共享 APScheduler）

### 验收标准
- [ ] 数据库有本周 15 条 TDL（12 完成 3 逾期 2 等待）→ 周报数字准确
- [ ] 超过 3 天未推进的 TDL 正确列出
- [ ] 按业务线分布统计正确
- [ ] 周一 09:00 自动收到周报卡片

---

## 批次 7：部署到 ECS + systemd + Nginx + 验收

**依赖**：批次 1-6 核心闭环跑通  
**预计**：1 天

### 文件清单

| # | 文件 | 职责 |
|---|------|------|
| 1 | `deploy/tdl-backend.service` | systemd 服务文件 |
| 2 | `deploy/nginx-tdl.conf` | Nginx 反向代理配置 |
| 3 | `deploy/deploy.sh` | 一键部署脚本（git pull + pip install + alembic upgrade + restart） |
| 4 | `README.md` | 项目说明 + 部署步骤 + 飞书配置指引 |
| 5 | `.env.example` | 更新：生产环境变量说明 |

### 部署步骤

```bash
# 1. 服务器上创建目录
ssh root@182.92.9.69 "mkdir -p /opt/bots/tdl/backend"

# 2. 推送代码 + 安装依赖
git push
ssh root@182.92.9.69 "cd /opt/bots/tdl/backend && git pull && pip install -r requirements.txt"

# 3. 创建 .env（手动，仅一次）
# DATABASE_URL=postgresql+asyncpg://...
# CLAUDE_API_KEY=sk-...
# OPENAI_API_KEY=sk-...
# FEISHU_APP_ID=...
# FEISHU_APP_SECRET=...
# FEISHU_VERIFICATION_TOKEN=...

# 4. 数据库迁移
ssh root@182.92.9.69 "cd /opt/bots/tdl/backend && alembic upgrade head"

# 5. 配置 systemd + Nginx + 启动
scp deploy/tdl-backend.service root@182.92.9.69:/etc/systemd/system/
scp deploy/nginx-tdl.conf root@182.92.9.69:/etc/nginx/sites-enabled/tdl
ssh root@182.92.9.69 "systemctl daemon-reload && systemctl enable tdl-backend && systemctl start tdl-backend && systemctl reload nginx"

# 6. 验证
ssh root@182.92.9.69 "systemctl status tdl-backend --no-pager"
ssh root@182.92.9.69 "curl -s http://127.0.0.1:8000/health"
```

### systemd 服务文件

```ini
[Unit]
Description=TDL Management Backend
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/bots/tdl/backend
ExecStart=/opt/bots/tdl/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Nginx 配置

```nginx
server {
    listen 80;
    server_name tdl.bdteach.cn;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /feishu/webhook {
        proxy_pass http://127.0.0.1:8000/api/feishu/webhook;
    }
}
```

### 验收标准（Smoke Test）
- [ ] `systemctl status tdl-backend` → active (running)
- [ ] `curl http://127.0.0.1:8000/health` → `{"status":"ok","db":"connected"}`
- [ ] 飞书给机器人发「测试」→ 收到回复
- [ ] 创建 TDL → 数据库有记录
- [ ] 日志：`journalctl -u tdl-backend -n 50` 无 ERROR
- [ ] 励步后端 `libu-backend.service` 不受影响
- [ ] 重启服务器 → `tdl-backend` 自动启动

---

## 不与并行：依赖链

```
批次 1（骨架）
  ├→ 批次 2（收发+卡片）
  │     ├→ 批次 3（AI 处理）
  │     └→ 批次 5（日历抓取）
  ├→ 批次 4（催收调度）
  ├→ 批次 6（周报）
  └→ 批次 7（部署）[等 2+3+4+5+6 完成]
```

---

## 总工作量估算

| 批次 | 内容 | 预估 |
|------|------|------|
| 1 | 骨架 + 数据库 + 配置 | 1-2 天 |
| 2 | 飞书机器人 + 卡片 | 2-3 天 |
| 3 | AI 处理管道 | 3-4 天 |
| 4 | 催收调度 | 2-3 天 |
| 5 | 日历抓取 | 1-2 天 |
| 6 | 周报 | 1-2 天 |
| 7 | 部署 + 验收 | 1 天 |
| **合计** | | **11-17 天** |

实际用 AI Agent 辅助开发，预计可压缩到 2-3 周。
