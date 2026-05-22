from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["entry"])


ENTRY_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TDL 管理助手</title>
  <style>
    :root {
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #172033;
      background: #f6f8fb;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
    }
    main {
      width: min(640px, calc(100vw - 32px));
      background: #ffffff;
      border: 1px solid #e6ebf2;
      border-radius: 8px;
      padding: 28px;
      box-shadow: 0 10px 30px rgba(21, 34, 50, 0.08);
    }
    h1 {
      margin: 0 0 12px;
      font-size: 24px;
      line-height: 1.25;
    }
    p {
      margin: 0 0 14px;
      font-size: 15px;
      line-height: 1.7;
      color: #3c4658;
    }
    .assistant {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 18px 0;
      padding: 12px 14px;
      background: #f8fafc;
      border: 1px solid #e1e7ef;
      border-radius: 6px;
    }
    .assistant-name {
      font-size: 18px;
      font-weight: 700;
      color: #172033;
      overflow-wrap: anywhere;
    }
    button {
      flex: 0 0 auto;
      border: 1px solid #1d6fdc;
      border-radius: 6px;
      background: #1d6fdc;
      color: #ffffff;
      padding: 9px 12px;
      font-size: 14px;
      line-height: 1;
      cursor: pointer;
    }
    button:focus-visible {
      outline: 3px solid #b7d5ff;
      outline-offset: 2px;
    }
    .status {
      margin-top: 18px;
      padding: 12px 14px;
      background: #eef6ff;
      border: 1px solid #d7eaff;
      border-radius: 6px;
      color: #145da0;
      font-size: 14px;
    }
    a {
      color: #1464d2;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <main>
    <h1>TDL 管理助手</h1>
    <p>这是 TDL 管理助手的钉钉网页入口。当前任务创建、确认、完成、暂缓和拒绝仍通过钉钉里的 <strong>TDL管理助手</strong> 私聊完成。</p>
    <p>如果你是从工作通知进入这里，请回到钉钉搜索下面这个名称，在私聊中继续处理任务卡片。</p>
    <div class="assistant">
      <div class="assistant-name" id="assistant-name">TDL管理助手</div>
      <button type="button" id="copy-name">复制名称</button>
    </div>
    <div class="status">服务状态检查：<a href="./health">/health</a></div>
  </main>
  <script>
    const button = document.getElementById("copy-name");
    const name = document.getElementById("assistant-name").textContent;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(name);
        button.textContent = "已复制";
      } catch {
        button.textContent = name;
      }
    });
  </script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def tdl_entry_home() -> HTMLResponse:
    return HTMLResponse(ENTRY_HTML)


@router.get("/entry", response_class=HTMLResponse)
async def tdl_entry() -> HTMLResponse:
    return HTMLResponse(ENTRY_HTML)
