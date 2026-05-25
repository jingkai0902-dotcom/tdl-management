from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(prefix="/workbench/home", tags=["workbench"])


WORKBENCH_HOME_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>企业工作台 V0 · 只读原型</title>
  <style>
    :root {
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #151c2c;
      background: #f4f6f9;
      --line: #e2e7f0;
      --muted: #667085;
      --brand: #1767c7;
      --brand-soft: #eaf3ff;
      --positive: #167146;
      --warning: #9a5b00;
      --panel: #ffffff;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #f4f6f9; }
    main { width: min(1360px, calc(100vw - 36px)); margin: 0 auto; padding: 20px 0 36px; }
    .topbar {
      display: flex; justify-content: space-between; align-items: flex-end;
      gap: 18px; margin-bottom: 16px;
    }
    h1 { margin: 0 0 5px; font-size: 26px; line-height: 1.25; }
    .meta { color: var(--muted); font-size: 13px; line-height: 1.55; }
    .nav, .scope-nav, .tabs, .actions, .flows { display: flex; flex-wrap: wrap; gap: 8px; }
    .nav { align-items: center; margin-bottom: 14px; }
    .nav a, .scope-link {
      display: inline-flex; align-items: center; min-height: 34px; padding: 0 12px;
      border: 1px solid var(--line); border-radius: 7px; color: #344054;
      background: var(--panel); font-size: 13px; text-decoration: none;
    }
    .nav a.active, .scope-link.active {
      border-color: #b9d5fb; background: var(--brand-soft); color: #145da0; font-weight: 650;
    }
    .scope-nav { margin-left: auto; }
    .status-row {
      display: grid; grid-template-columns: repeat(5, minmax(122px, 1fr));
      gap: 10px; margin-bottom: 12px;
    }
    .stat, .tools, .content, .section, .detail, .horizon, .placeholder {
      background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
    }
    .stat { padding: 12px 14px; min-height: 72px; }
    .stat-label { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .stat-value { font-size: 27px; font-weight: 700; line-height: 1; }
    .stat[data-key="overdue_or_due_soon"] .stat-value { color: var(--warning); }
    .stat[data-key="pending_confirmation"] .stat-value { color: var(--brand); }
    .tools {
      display: grid; grid-template-columns: 1fr 1.25fr; gap: 18px;
      padding: 14px 16px; margin-bottom: 13px;
    }
    .tool-title { color: var(--muted); font-size: 12px; margin-bottom: 9px; }
    button { font: inherit; letter-spacing: 0; }
    .tool-button {
      min-height: 36px; padding: 0 12px; border: 1px solid #d7dfe9;
      border-radius: 7px; background: #fafbfd; color: #344054; font-size: 13px;
    }
    .tool-button:disabled { cursor: not-allowed; opacity: .72; }
    .soon {
      margin-left: 7px; color: var(--muted); font-size: 11px;
    }
    .tabs {
      border-bottom: 1px solid var(--line); margin: 0 0 14px; padding: 0 2px;
    }
    .tab {
      min-height: 43px; border: 0; border-bottom: 2px solid transparent;
      background: transparent; color: #475467; cursor: pointer; font-size: 14px; padding: 0 15px;
    }
    .tab.active { border-bottom-color: var(--brand); color: #101828; font-weight: 650; }
    .content { padding: 15px; }
    .view { display: none; }
    .view.active { display: block; }
    .action-grid, .signal-grid {
      display: grid; grid-template-columns: minmax(0, 1fr) minmax(315px, 370px);
      gap: 14px; align-items: start;
    }
    .sections { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .section { overflow: hidden; min-height: 150px; }
    .section-head {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
      border-bottom: 1px solid #edf1f6; padding: 11px 12px;
    }
    h2 { margin: 0; font-size: 15px; line-height: 1.35; }
    .source { color: var(--muted); font-size: 11px; }
    ul { list-style: none; margin: 0; padding: 0; }
    .item-list { max-height: 300px; overflow-y: auto; }
    li { border-bottom: 1px solid #edf1f6; padding: 10px 12px; }
    li:last-child { border-bottom: 0; }
    .item {
      appearance: none; width: 100%; padding: 0; border: 0;
      color: #172033; background: transparent; cursor: pointer;
      font-size: 13px; font-weight: 650; line-height: 1.45; text-align: left;
      display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
      overflow: hidden; overflow-wrap: anywhere;
    }
    .item:hover, .item:focus-visible { color: var(--brand); text-decoration: underline; outline: none; }
    .pills { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
    .pill {
      border: 1px solid #dbe3ed; border-radius: 999px; background: #f8fafc;
      color: var(--muted); font-size: 11px; padding: 2px 7px; line-height: 1.45;
    }
    .empty, .loading { color: var(--muted); font-size: 13px; line-height: 1.55; padding: 15px 12px; }
    .detail { position: sticky; top: 14px; overflow: hidden; min-height: 278px; }
    .detail-head { border-bottom: 1px solid #edf1f6; padding: 12px 14px; }
    .detail-body { display: grid; gap: 10px; padding: 13px 14px; max-height: calc(100vh - 140px); overflow-y: auto; }
    .detail-title { font-size: 15px; font-weight: 700; line-height: 1.5; overflow-wrap: anywhere; }
    .detail-title.compact {
      display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 4; overflow: hidden;
    }
    .full-text summary {
      color: var(--brand); cursor: pointer; font-size: 12px; font-weight: 650;
    }
    .full-text .value { border-top: 1px solid #edf1f6; margin-top: 8px; padding-top: 8px; }
    .row { display: grid; gap: 3px; }
    .label { color: var(--muted); font-size: 11px; }
    .value { font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }
    .notice {
      border: 1px solid #bfdbfe; border-radius: 7px; background: #eff6ff;
      color: #145da0; font-size: 12px; line-height: 1.55; padding: 9px 11px;
      margin-bottom: 12px;
    }
    .decision { background: #eff6ff; border-radius: 7px; padding: 9px 10px; }
    .gate { background: #fff7e7; border: 1px solid #f3d28f; border-radius: 7px; padding: 9px 10px; }
    .horizons { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 13px; }
    .horizon { padding: 12px 13px; }
    .horizon strong { display: block; font-size: 14px; margin-bottom: 5px; }
    .horizon .pending { color: var(--muted); font-size: 12px; line-height: 1.55; }
    .placeholder { min-height: 260px; padding: 24px; }
    .placeholder h2 { font-size: 18px; margin-bottom: 8px; }
    .placeholder p { max-width: 650px; color: var(--muted); font-size: 14px; line-height: 1.65; margin: 0 0 14px; }
    .planned-list { display: flex; flex-wrap: wrap; gap: 8px; }
    .planned-list span {
      border: 1px dashed #cdd6e3; border-radius: 7px; color: #475467;
      font-size: 13px; padding: 9px 12px;
    }
    @media (max-width: 940px) {
      .topbar { display: block; }
      .scope-nav { margin: 10px 0 0; }
      .status-row, .tools, .action-grid, .signal-grid, .horizons { grid-template-columns: 1fr; }
      .sections { grid-template-columns: 1fr; }
      .detail { position: static; }
    }
  </style>
</head>
<body>
  <main>
    <div class="topbar">
      <div>
        <h1>企业工作台</h1>
        <div class="meta">V0 只读首页原型 · 不创建任务 · 不修改状态 · 不发送通知 · 不发布报告</div>
        <div class="meta">当前仅使用 TDL 任务数据与 5 月月会人工判断样本；未接入区域不展示推测数据。</div>
      </div>
      <div class="meta" id="as-of">正在读取...</div>
    </div>
    <div class="nav">
      <a class="active" href="/workbench/home/view">首页</a>
      <a href="/workbench/view">任务原始视图</a>
      <a href="/workbench/meeting-review/view">5月月会样本</a>
      <nav class="scope-nav" aria-label="管理者视角">
        <a class="scope-link" data-owner-id="" href="/workbench/home/view">全部视角</a>
        <a class="scope-link" data-owner-id="0617564550-1513038363" href="/workbench/home/view?owner_id=0617564550-1513038363">Frank</a>
        <a class="scope-link" data-owner-id="0611436746849471" href="/workbench/home/view?owner_id=0611436746849471">Helen</a>
      </nav>
    </div>
    <div class="status-row" id="stats"><div class="loading">正在读取任务状态...</div></div>
    <div class="tools" aria-label="快捷入口与标准流程">
      <div>
        <div class="tool-title">快捷创建</div>
        <div class="actions">
          <button class="tool-button" disabled>新建任务 <span class="soon">尚未开放</span></button>
          <button class="tool-button" disabled>记录议题 <span class="soon">尚未开放</span></button>
          <button class="tool-button" disabled>补充想法 <span class="soon">尚未开放</span></button>
          <button class="tool-button" disabled>提交资料 <span class="soon">尚未开放</span></button>
        </div>
      </div>
      <div>
        <div class="tool-title">标准流程</div>
        <div class="flows">
          <button class="tool-button" disabled>每日开场 <span class="soon">规划中</span></button>
          <button class="tool-button" disabled>月会准备 <span class="soon">规划中</span></button>
          <button class="tool-button" disabled>经营复盘 <span class="soon">规划中</span></button>
          <button class="tool-button" disabled>生成报告 <span class="soon">规划中</span></button>
        </div>
      </div>
    </div>
    <div class="content">
      <div class="tabs" role="tablist" aria-label="工作台内容区">
        <button class="tab active" type="button" data-view="actions">行动与目标</button>
        <button class="tab" type="button" data-view="metrics">经营数据</button>
        <button class="tab" type="button" data-view="signals">议题与线索</button>
        <button class="tab" type="button" data-view="materials">资料与报告</button>
      </div>
      <div class="view active" id="actions-view">
        <div class="action-grid">
          <div class="sections" id="task-sections"><div class="loading">正在读取行动数据...</div></div>
          <aside class="detail" aria-label="任务判断详情">
            <div class="detail-head"><h2>任务判断详情</h2><div class="meta">只读 · 用于核对待处理事项</div></div>
            <div class="empty" id="task-detail">选择一条任务查看判断所需信息。</div>
          </aside>
        </div>
        <div class="horizons" aria-label="长期目标层级">
          <div class="horizon"><strong>月度重点 / 部门计划</strong><div class="pending">规划中：等待真实数据模板与对象模型确认。</div></div>
          <div class="horizon"><strong>季度目标 / 关键项目</strong><div class="pending">规划中：不将项目伪装为提醒任务。</div></div>
          <div class="horizon"><strong>年度目标 / 里程碑</strong><div class="pending">规划中：仅表达未来管理层级。</div></div>
        </div>
      </div>
      <div class="view" id="metrics-view">
        <div class="placeholder">
          <h2>经营数据</h2>
          <p>尚未接入正式数据。本区域将在征集管理岗位现有表格、数据口径与敏感级别后，再选择首个看板试点。</p>
          <div class="planned-list"><span>招生与销售指标 · 待征集</span><span>教学质量数据 · 待征集</span><span>教务服务数据 · 待征集</span><span>人力与技术数据 · 待征集</span></div>
        </div>
      </div>
      <div class="view" id="signals-view">
        <div class="notice">真实材料验证区：5 月月会样本中没有满足 What + Who + When 的组织级任务。以下内容用于判断议题、想法和观察线索是否值得进入管理视野，不会直接生成任务。</div>
        <div class="signal-grid">
          <div class="sections" id="meeting-sections"><div class="loading">正在读取月会样本...</div></div>
          <aside class="detail" aria-label="材料判断详情">
            <div class="detail-head"><h2>材料判断详情</h2><div class="meta">只读 · 用于核验分类依据</div></div>
            <div class="empty" id="meeting-detail">选择一条材料查看人工判断。</div>
          </aside>
        </div>
      </div>
      <div class="view" id="materials-view">
        <div class="placeholder">
          <h2>资料与报告</h2>
          <p>尚未接入上传、归档或报告发布能力。后续需先明确资料分类、可见范围、审计要求与报告生成边界。</p>
          <div class="planned-list"><span>资料上传 · 尚未开放</span><span>管理报告 · 尚未开放</span><span>会议产出 · 待流程确认</span><span>稍后阅读 · 候选能力</span></div>
        </div>
      </div>
    </div>
  </main>
  <script>
    const escapeHtml = (value) => String(value)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
    const formatDate = (value) => value ? new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
    }).format(new Date(value)) : "待补充";
    const ownerId = new URLSearchParams(window.location.search).get("owner_id") || "";
    const taskLabels = { set_owner: "补负责人", set_due_at: "补截止时间", set_completion_criteria: "补完成标准", confirm: "满足确认条件" };
    const fieldLabels = { owner_id: "负责人", due_at: "截止时间", completion_criteria: "完成标准" };
    const meetingLabels = {
      fact: "事实", confirmed: "已形成判断", pending: "待处理议题", spark: "火花 / 设想", signal: "观察线索",
      Fact: "事实", Decision: "判断", Issue: "议题", Idea: "设想", Signal: "线索"
    };
    const pills = (values) => values.length
      ? values.map((value) => `<span class="pill">${escapeHtml(value)}</span>`).join("")
      : `<span class="pill">无</span>`;
    const row = (name, value) => `<div class="row"><div class="label">${escapeHtml(name)}</div><div class="value">${escapeHtml(value || "无")}</div></div>`;
    const showView = (key) => {
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === key));
      document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `${key}-view`));
    };
    document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showView(tab.dataset.view)));
    document.querySelectorAll(".scope-link").forEach((link) => {
      if (link.dataset.ownerId === ownerId) link.classList.add("active");
    });
    const renderTaskDetail = (item) => {
      const missing = (item.missing_fields || []).map((field) => fieldLabels[field] || field);
      const hints = [...new Set([...(item.next_actions || []), ...(item.recommended_actions || [])])]
        .map((action) => taskLabels[action] || action);
      const longTitle = item.title.length > 110;
      const element = document.getElementById("task-detail");
      element.className = "detail-body";
      element.innerHTML = `
        <div class="detail-title ${longTitle ? "compact" : ""}">${escapeHtml(item.title)}</div>
        ${longTitle ? `<details class="full-text"><summary>展开完整内容</summary><div class="value">${escapeHtml(item.title)}</div></details>` : ""}
        ${row("负责人", item.owner_label || item.owner_id || "待补充")}
        ${row("截止时间", formatDate(item.due_at))}
        ${row("完成标准", item.completion_criteria || "待补充")}
        <div class="row"><div class="label">还缺什么</div><div class="pills">${pills(missing)}</div></div>
        <div class="row decision"><div class="label">判断提示</div><div class="pills">${pills(hints)}</div></div>
        <div class="meta">这里只帮助判断，不会确认、忽略、删除或修改任务。</div>`;
    };
    const renderTasks = (payload) => {
      document.getElementById("stats").innerHTML = payload.sections.map((section) => `
        <div class="stat" data-key="${escapeHtml(section.key)}"><div class="stat-label">${escapeHtml(section.title)}</div><div class="stat-value">${section.count}</div></div>`).join("");
      const priority = ["pending_confirmation", "overdue_or_due_soon", "today", "this_week", "in_progress"];
      const orderedSections = [...payload.sections].sort((left, right) => priority.indexOf(left.key) - priority.indexOf(right.key));
      document.getElementById("task-sections").innerHTML = orderedSections.map((section) => `
        <section class="section">
          <div class="section-head"><h2>${escapeHtml(section.title)}</h2><span class="source">${escapeHtml(section.data_source)}</span></div>
          ${section.items.length ? `<ul class="item-list">${section.items.map((item) => `
            <li><button class="item task-item" type="button" data-tdl-id="${escapeHtml(item.tdl_id)}">${escapeHtml(item.title)}</button>
            <div class="pills">${pills([item.owner_label || item.owner_id || "待补充", formatDate(item.due_at)])}</div></li>`).join("")}</ul>` : `<div class="empty">暂无数据</div>`}
        </section>`).join("");
      document.querySelectorAll(".task-item").forEach((button) => button.addEventListener("click", () => {
        const item = payload.sections.flatMap((section) => section.items).find((candidate) => candidate.tdl_id === button.dataset.tdlId);
        if (item) renderTaskDetail(item);
      }));
    };
    const renderMeetingDetail = (item) => {
      const element = document.getElementById("meeting-detail");
      element.className = "detail-body";
      element.innerHTML = `
        <div class="detail-title">${escapeHtml(item.summary)}</div>
        <div class="row gate"><div class="label">任务准入</div><div class="value">${item.tdl_eligible ? "符合任务准入条件" : "不可直接转为任务"}</div></div>
        ${row("分类", `${meetingLabels[item.maturity] || item.maturity} · ${meetingLabels[item.object_type] || item.object_type}`)}
        ${row("判断说明", item.notes)}
        ${row("材料定位", `${item.source_id} · ${item.evidence_locator}`)}`;
    };
    const renderMeetings = (payload) => {
      document.getElementById("meeting-sections").innerHTML = payload.sections.map((section) => `
        <section class="section">
          <div class="section-head"><h2>${escapeHtml(section.title)} (${section.count})</h2></div>
          <ul class="item-list">${section.items.map((item) => `
            <li><button class="item meeting-item" type="button" data-item-id="${escapeHtml(item.item_id)}">${escapeHtml(item.summary)}</button>
            <div class="pills">${pills([meetingLabels[item.object_type] || item.object_type])}</div></li>`).join("")}</ul>
        </section>`).join("");
      document.querySelectorAll(".meeting-item").forEach((button) => button.addEventListener("click", () => {
        const item = payload.sections.flatMap((section) => section.items).find((candidate) => candidate.item_id === button.dataset.itemId);
        if (item) renderMeetingDetail(item);
      }));
    };
    const loadHome = async () => {
      const now = new Date();
      document.getElementById("as-of").textContent = `截至：${formatDate(now.toISOString())}`;
      const taskParams = new URLSearchParams({ as_of: now.toISOString() });
      if (ownerId) taskParams.set("owner_id", ownerId);
      const [taskResponse, meetingResponse] = await Promise.all([
        fetch(`/workbench?${taskParams.toString()}`),
        fetch("/workbench/meeting-review")
      ]);
      if (!taskResponse.ok || !meetingResponse.ok) throw new Error("home data failed");
      renderTasks(await taskResponse.json());
      renderMeetings(await meetingResponse.json());
    };
    loadHome().catch(() => {
      document.getElementById("task-sections").innerHTML = "<div class='empty'>任务数据读取失败</div>";
      document.getElementById("meeting-sections").innerHTML = "<div class='empty'>月会样本读取失败</div>";
    });
  </script>
</body>
</html>"""


@router.get("/view", response_class=HTMLResponse)
async def get_workbench_home_view() -> HTMLResponse:
    return HTMLResponse(WORKBENCH_HOME_HTML)
