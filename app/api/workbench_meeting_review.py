from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.schemas import MeetingReviewRead
from app.services.meeting_review_service import load_meeting_review


router = APIRouter(prefix="/workbench/meeting-review", tags=["workbench"])


MEETING_REVIEW_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>5月月会判断样本 · TDL 管理工作台</title>
  <style>
    :root {
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #18202f;
      background: #f5f7fb;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #f5f7fb; }
    main { width: min(1220px, calc(100vw - 32px)); margin: 0 auto; padding: 24px 0 40px; }
    .topbar { display: flex; justify-content: space-between; align-items: end; gap: 16px; margin-bottom: 16px; }
    h1 { margin: 0 0 6px; font-size: 25px; line-height: 1.3; }
    .meta { color: #667085; font-size: 13px; line-height: 1.55; }
    .nav { display: flex; gap: 8px; margin-bottom: 18px; }
    .nav a {
      min-height: 34px; display: inline-flex; align-items: center; padding: 0 12px;
      border: 1px solid #d9e0ea; border-radius: 8px; background: #fff;
      color: #344054; font-size: 13px; text-decoration: none;
    }
    .nav a.active { border-color: #1d6fdc; background: #eef6ff; color: #145da0; font-weight: 650; }
    .notice {
      margin-bottom: 16px; padding: 12px 14px; border: 1px solid #c9e2ff;
      border-radius: 8px; background: #eef6ff; color: #145da0; font-size: 13px; line-height: 1.6;
    }
    .stats { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin-bottom: 16px; }
    .stat { border: 1px solid #dfe6f0; border-radius: 8px; background: #fff; padding: 11px 13px; }
    .stat-label { color: #667085; font-size: 12px; margin-bottom: 5px; }
    .stat-value { font-size: 27px; font-weight: 700; line-height: 1; }
    .workspace { display: grid; grid-template-columns: minmax(0, 1fr) minmax(310px, 400px); gap: 16px; align-items: start; }
    .sections { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    section, aside { background: #fff; border: 1px solid #dfe6f0; border-radius: 8px; overflow: hidden; }
    .section-head, .detail-head { padding: 13px 15px; border-bottom: 1px solid #edf1f7; }
    h2 { margin: 0; font-size: 16px; line-height: 1.35; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { padding: 11px 15px; border-bottom: 1px solid #edf1f7; }
    li:last-child { border-bottom: 0; }
    .item-title {
      display: block; width: 100%; padding: 0; border: 0; background: transparent; text-align: left;
      color: #18202f; cursor: pointer; font-size: 14px; font-weight: 650; line-height: 1.5;
    }
    .item-title:hover, .item-title:focus-visible { color: #145da0; text-decoration: underline; outline: none; }
    .pills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }
    .pill { padding: 2px 7px; border: 1px solid #d9e0ea; border-radius: 999px; background: #f8fafc; color: #667085; font-size: 12px; }
    aside { max-height: calc(100vh - 32px); min-height: 340px; position: sticky; top: 16px; }
    .detail { display: grid; gap: 12px; max-height: calc(100vh - 112px); overflow-y: auto; padding: 14px 15px 18px; }
    .detail-empty { padding: 18px 15px; color: #667085; font-size: 14px; line-height: 1.6; }
    .detail-title { font-size: 17px; font-weight: 700; line-height: 1.5; }
    .row { display: grid; gap: 4px; }
    .label { color: #667085; font-size: 12px; }
    .value { color: #18202f; font-size: 14px; line-height: 1.55; overflow-wrap: anywhere; }
    .gate { border: 1px solid #f5d18c; background: #fff8eb; border-radius: 8px; padding: 10px 12px; }
    .gate .label { color: #8a5300; font-weight: 650; }
    @media (max-width: 860px) {
      .topbar { display: block; }
      .stats, .workspace, .sections { grid-template-columns: 1fr; }
      aside { position: static; max-height: none; }
      .detail { max-height: none; }
    }
  </style>
</head>
<body>
  <main>
    <div class="topbar">
      <div>
        <h1>励步 5 月月会判断样本</h1>
        <div class="meta">只读材料视图 · 来自人工 Gold Set · 不创建任务、不修改状态、不发送通知</div>
      </div>
      <div class="meta" id="count">加载中</div>
    </div>
    <nav class="nav" aria-label="工作台入口">
      <a href="/workbench/home/view">工作台首页</a>
      <a href="/workbench/view">任务工作台</a>
      <a class="active" href="/workbench/meeting-review/view">5月月会判断样本</a>
    </nav>
    <div class="notice">
      这批真实材料中没有达到 What + Who + When 的组织级任务。这里用于判断信息结构是否有用，
      不能把“待议题、火花、观察线索”误当作待办任务。
    </div>
    <div class="stats" id="stats"></div>
    <div class="workspace">
      <div class="sections" id="sections"><div class="meta">正在读取判断样本...</div></div>
      <aside aria-label="样本详情">
        <div class="detail-head">
          <h2>样本详情</h2>
          <div class="meta">用于业务判断和分类校验，不用于执行</div>
        </div>
        <div class="detail-empty" id="detail">选择一条样本查看分类依据。</div>
      </aside>
    </div>
  </main>
  <script>
    const escapeHtml = (value) => String(value)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
    const labels = {
      fact: "事实", confirmed: "已形成判断", pending: "待处理议题",
      spark: "火花 / 设想", signal: "观察线索",
      Fact: "事实", Decision: "判断", Issue: "议题", Idea: "设想", Signal: "线索"
    };
    const label = (value) => labels[value] || value;
    const gateText = (item) => item.tdl_eligible
      ? "符合任务准入条件"
      : "不可直接转为任务";
    const row = (name, value) => `
      <div class="row"><div class="label">${escapeHtml(name)}</div><div class="value">${escapeHtml(value || "无")}</div></div>`;
    const renderDetail = (item) => {
      document.getElementById("detail").className = "detail";
      document.getElementById("detail").innerHTML = `
        <div class="detail-title">${escapeHtml(item.summary)}</div>
        <div class="row gate"><div class="label">任务准入</div><div class="value">${escapeHtml(gateText(item))}</div></div>
        ${row("分类", `${label(item.maturity)} · ${label(item.object_type)}`)}
        ${row("判断说明", item.notes)}
        ${row("材料定位", `${item.source_id} · ${item.evidence_locator}`)}
        ${row("来源类型", item.source_type)}
        ${row("人工信心", item.confidence)}
      `;
    };
    const render = (payload) => {
      document.getElementById("count").textContent = `共 ${payload.total_count} 条 · ${payload.data_source}`;
      document.getElementById("stats").innerHTML = payload.sections.map((section) => `
        <div class="stat"><div class="stat-label">${escapeHtml(section.title)}</div><div class="stat-value">${section.count}</div></div>
      `).join("");
      document.getElementById("sections").innerHTML = payload.sections.map((section) => `
        <section>
          <div class="section-head"><h2>${escapeHtml(section.title)} (${section.count})</h2></div>
          <ul>${section.items.map((item) => `
            <li>
              <button class="item-title" type="button" data-item-id="${escapeHtml(item.item_id)}">${escapeHtml(item.summary)}</button>
              <div class="pills"><span class="pill">${escapeHtml(item.item_id)}</span><span class="pill">${escapeHtml(label(item.object_type))}</span></div>
            </li>`).join("")}</ul>
        </section>`).join("");
      document.querySelectorAll(".item-title").forEach((button) => {
        button.addEventListener("click", () => {
          const item = payload.sections.flatMap((section) => section.items)
            .find((candidate) => candidate.item_id === button.dataset.itemId);
          if (item) renderDetail(item);
        });
      });
    };
    fetch("/workbench/meeting-review").then((response) => {
      if (!response.ok) throw new Error("meeting review data failed");
      return response.json();
    }).then(render).catch(() => {
      document.getElementById("sections").innerHTML = "<div class='meta'>月会判断样本读取失败</div>";
    });
  </script>
</body>
</html>"""


@router.get("", response_model=MeetingReviewRead)
async def get_meeting_review_endpoint() -> MeetingReviewRead:
    return load_meeting_review()


@router.get("/view", response_class=HTMLResponse)
async def get_meeting_review_view() -> HTMLResponse:
    return HTMLResponse(MEETING_REVIEW_HTML)
