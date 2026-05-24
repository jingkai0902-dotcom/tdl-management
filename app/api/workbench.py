from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.schemas import WorkbenchRead
from app.services.workbench_service import generate_workbench_summary


router = APIRouter(prefix="/workbench", tags=["workbench"])


def _normalize_as_of(as_of: datetime) -> datetime:
    timezone = ZoneInfo(get_settings().scheduler_timezone)
    if as_of.tzinfo is None:
        return as_of.replace(tzinfo=timezone)
    return as_of.astimezone(timezone)


WORKBENCH_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TDL 管理工作台 V0</title>
  <style>
    :root {
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #18202f;
      background: #f5f7fb;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: #f5f7fb;
    }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      margin-bottom: 20px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 26px;
      line-height: 1.25;
    }
    .meta {
      color: #667085;
      font-size: 14px;
      line-height: 1.6;
    }
    .scope-nav {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0 18px;
    }
    .scope-link {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      border: 1px solid #d9e0ea;
      border-radius: 999px;
      padding: 0 12px;
      color: #344054;
      background: #ffffff;
      font-size: 13px;
      text-decoration: none;
    }
    .scope-link.active {
      border-color: #1d6fdc;
      color: #145da0;
      background: #eef6ff;
      font-weight: 650;
    }
    .status-row {
      display: grid;
      grid-template-columns: repeat(5, minmax(130px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }
    .stat {
      background: #ffffff;
      border: 1px solid #dfe6f0;
      border-radius: 8px;
      padding: 12px 14px;
    }
    .stat-title {
      color: #667085;
      font-size: 13px;
      margin-bottom: 6px;
    }
    .stat-count {
      font-size: 28px;
      font-weight: 700;
      line-height: 1;
    }
    .sections {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
      gap: 16px;
      align-items: start;
    }
    section {
      background: #ffffff;
      border: 1px solid #dfe6f0;
      border-radius: 8px;
      min-height: 180px;
      overflow: hidden;
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid #edf1f7;
    }
    h2 {
      margin: 0;
      font-size: 17px;
      line-height: 1.3;
    }
    .source {
      color: #667085;
      font-size: 12px;
      white-space: nowrap;
    }
    ul {
      list-style: none;
      padding: 0;
      margin: 0;
    }
    li {
      padding: 12px 16px;
      border-bottom: 1px solid #edf1f7;
    }
    li:last-child {
      border-bottom: 0;
    }
    .task-title {
      appearance: none;
      border: 0;
      background: transparent;
      color: #18202f;
      cursor: pointer;
      display: block;
      font-size: 15px;
      font-weight: 650;
      line-height: 1.45;
      overflow-wrap: anywhere;
      margin-bottom: 6px;
      padding: 0;
      text-align: left;
      width: 100%;
    }
    .task-title:hover,
    .task-title:focus-visible {
      color: #145da0;
      outline: none;
      text-decoration: underline;
    }
    .task-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: #667085;
      font-size: 12px;
      line-height: 1.4;
    }
    .pill {
      border: 1px solid #d9e0ea;
      border-radius: 999px;
      padding: 2px 8px;
      background: #f8fafc;
    }
    .empty,
    .loading,
    .error {
      padding: 18px 16px;
      color: #667085;
      font-size: 14px;
    }
    .error {
      color: #b42318;
    }
    .detail-panel {
      background: #ffffff;
      border: 1px solid #dfe6f0;
      border-radius: 8px;
      max-height: calc(100vh - 32px);
      min-height: 320px;
      overflow: hidden;
      position: sticky;
      top: 16px;
    }
    .detail-head {
      border-bottom: 1px solid #edf1f7;
      padding: 14px 16px;
    }
    .detail-title {
      font-size: 16px;
      font-weight: 700;
      line-height: 1.45;
      margin: 0 0 8px;
      overflow-wrap: anywhere;
    }
    .detail-body {
      display: grid;
      gap: 12px;
      max-height: calc(100vh - 124px);
      overflow-y: auto;
      padding: 14px 16px 18px;
    }
    .detail-row {
      display: grid;
      gap: 4px;
    }
    .detail-label {
      color: #667085;
      font-size: 12px;
    }
    .detail-value {
      color: #18202f;
      font-size: 14px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .detail-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .detail-decision {
      background: #eef6ff;
      border: 1px solid #c9e2ff;
      border-radius: 8px;
      padding: 10px 12px;
    }
    .detail-decision .detail-label {
      color: #145da0;
      font-weight: 650;
    }
    .detail-note {
      color: #667085;
      font-size: 12px;
      line-height: 1.5;
    }
    .detail-more {
      border-top: 1px solid #edf1f7;
      padding-top: 10px;
    }
    .detail-more summary {
      color: #344054;
      cursor: pointer;
      font-size: 13px;
      font-weight: 650;
      line-height: 1.4;
    }
    .detail-more[open] summary {
      margin-bottom: 10px;
    }
    .detail-empty {
      color: #667085;
      font-size: 14px;
      line-height: 1.6;
      padding: 18px 16px;
    }
    @media (max-width: 820px) {
      header {
        display: block;
      }
      .status-row,
      .workspace,
      .sections {
        grid-template-columns: 1fr;
      }
      .detail-panel {
        position: static;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>TDL 管理工作台 V0</h1>
        <div class="meta">只读视图 · 不创建任务 · 不修改状态 · 不发送钉钉</div>
        <div class="meta">各区块是多维视角，同一任务可能同时出现在多个区块。</div>
      </div>
      <div class="meta" id="as-of">加载中</div>
    </header>
    <nav class="scope-nav" aria-label="工作台视角">
      <a class="scope-link" data-owner-id="" href="/workbench/view">全部</a>
      <a class="scope-link" data-owner-id="0617564550-1513038363" href="/workbench/view?owner_id=0617564550-1513038363">Frank</a>
      <a class="scope-link" data-owner-id="0611436746849471" href="/workbench/view?owner_id=0611436746849471">Helen</a>
    </nav>
    <div class="status-row" id="stats"></div>
    <div class="workspace">
      <div class="sections" id="sections">
        <div class="loading">正在读取工作台数据...</div>
      </div>
      <aside class="detail-panel" aria-label="任务详情">
        <div class="detail-head">
          <h2>任务详情</h2>
          <div class="meta">只读详情 · 用于判断确认、忽略、清理或补信息</div>
        </div>
        <div class="detail-empty" id="detail">选择一条任务查看详情。</div>
      </aside>
    </div>
  </main>
  <script>
    const escapeHtml = (value) => String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

    const formatDate = (value) => {
      if (!value) return "未设置";
      return new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value));
    };

    const labelActions = (actions) => {
      const labels = {
        set_owner: "补负责人",
        set_due_at: "补截止时间",
        set_completion_criteria: "补完成标准",
        confirm: "满足确认条件",
      };
      return actions.map((action) => labels[action] || action);
    };

    const labelFields = (fields) => {
      const labels = {
        owner_id: "负责人",
        due_at: "截止时间",
        completion_criteria: "完成标准",
      };
      return fields.map((field) => labels[field] || field);
    };

    const itemMeta = (item) => [
      `负责人：${item.owner_label || item.owner_id || "待补充"}`,
      `截止：${formatDate(item.due_at)}`,
      `状态：${item.status}`,
      `优先级：${item.priority}`,
      `来源：${item.source}`,
    ];

    const renderPills = (values) => values.length
      ? values.map((value) => `<span class="pill">${escapeHtml(value)}</span>`).join("")
      : `<span class="pill">无</span>`;

    const renderDetailRow = (label, value) => `
      <div class="detail-row">
        <div class="detail-label">${escapeHtml(label)}</div>
        <div class="detail-value">${escapeHtml(value || "无")}</div>
      </div>
    `;

    const renderDetail = (item) => {
      const missingFields = labelFields(item.missing_fields || []);
      const nextActions = labelActions(item.next_actions || []);
      const recommendedActions = labelActions(item.recommended_actions || []);
      const decisionHints = [...new Set([...nextActions, ...recommendedActions])];
      document.getElementById("detail").className = "detail-body";
      document.getElementById("detail").innerHTML = `
        <div class="detail-title">${escapeHtml(item.title)}</div>
        ${renderDetailRow("负责人", item.owner_label || item.owner_id || "待补充")}
        ${renderDetailRow("截止时间", formatDate(item.due_at))}
        ${renderDetailRow("完成标准", item.completion_criteria || "待补充")}
        <div class="detail-row">
          <div class="detail-label">还缺什么</div>
          <div class="detail-actions">${renderPills(missingFields)}</div>
        </div>
        <div class="detail-row detail-decision">
          <div class="detail-label">判断提示</div>
          <div class="detail-actions">${renderPills(decisionHints)}</div>
        </div>
        <div class="detail-note">这里只帮助判断，不会确认、忽略、删除或修改任务。</div>
        <details class="detail-more">
          <summary>技术信息</summary>
          ${renderDetailRow("状态", item.status)}
          ${renderDetailRow("优先级", item.priority)}
          ${renderDetailRow("来源", item.source)}
          ${renderDetailRow("建议补充字段", labelFields(item.recommended_fields || []).join("、") || "无")}
          ${renderDetailRow("下一步判断", nextActions.join("、") || "无")}
          ${renderDetailRow("建议动作", recommendedActions.join("、") || "无")}
        </details>
      `;
    };

    const renderStats = (sections) => {
      document.getElementById("stats").innerHTML = sections.map((section) => `
        <div class="stat">
          <div class="stat-title">${escapeHtml(section.title)}</div>
          <div class="stat-count">${section.count}</div>
        </div>
      `).join("");
    };

    const renderSections = (sections) => {
      document.getElementById("sections").innerHTML = sections.map((section) => `
        <section>
          <div class="section-head">
            <h2>${escapeHtml(section.title)}</h2>
            <div class="source">数据源：${escapeHtml(section.data_source)}</div>
          </div>
          ${
            section.items.length
              ? `<ul>${section.items.map((item) => `
                  <li>
                    <button class="task-title" type="button" data-tdl-id="${escapeHtml(item.tdl_id)}">${escapeHtml(item.title)}</button>
                    <div class="task-meta">
                      ${itemMeta(item).map((meta) => `<span class="pill">${escapeHtml(meta)}</span>`).join("")}
                    </div>
                  </li>
                `).join("")}</ul>`
              : `<div class="empty">暂无数据</div>`
          }
        </section>
      `).join("");
      document.querySelectorAll(".task-title").forEach((button) => {
        button.addEventListener("click", () => {
          const item = sections
            .flatMap((section) => section.items)
            .find((candidate) => candidate.tdl_id === button.dataset.tdlId);
          if (item) renderDetail(item);
        });
      });
    };

    const ownerId = new URLSearchParams(window.location.search).get("owner_id") || "";
    document.querySelectorAll(".scope-link").forEach((link) => {
      if (link.dataset.ownerId === ownerId) {
        link.classList.add("active");
      }
    });

    const loadWorkbench = async () => {
      const asOf = new Date();
      document.getElementById("as-of").textContent = `截至：${formatDate(asOf.toISOString())}`;
      const params = new URLSearchParams({ as_of: asOf.toISOString() });
      if (ownerId) params.set("owner_id", ownerId);
      const response = await fetch(`/workbench?${params.toString()}`);
      if (!response.ok) throw new Error("workbench api failed");
      const payload = await response.json();
      renderStats(payload.sections);
      renderSections(payload.sections);
    };

    loadWorkbench().catch(() => {
      document.getElementById("sections").innerHTML = "<div class='error'>工作台数据读取失败</div>";
    });
  </script>
</body>
</html>"""


@router.get("", response_model=WorkbenchRead)
async def get_workbench_endpoint(
    as_of: datetime,
    owner_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> WorkbenchRead:
    return await generate_workbench_summary(
        session,
        as_of=_normalize_as_of(as_of),
        owner_id=owner_id,
    )


@router.get("/view", response_class=HTMLResponse)
async def get_workbench_view() -> HTMLResponse:
    return HTMLResponse(WORKBENCH_HTML)
