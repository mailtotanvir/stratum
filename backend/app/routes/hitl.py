from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.services.hitl_service import NoPendingQuestionError, hitl_service

router = APIRouter()


class HumanResponse(BaseModel):
    text: str


@router.get("/pending")
async def pending() -> dict[str, str] | None:
    return await hitl_service.pending()


@router.post("/respond")
async def respond(response: HumanResponse) -> dict[str, str]:
    try:
        await hitl_service.respond(response.text)
    except NoPendingQuestionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/demo/ask")
async def demo_ask() -> dict[str, str]:
    status = await hitl_service.start_demo()
    return {"status": status}


@router.get("/demo/result")
async def demo_result() -> dict[str, Any]:
    return await hitl_service.snapshot()


@router.get("/ui")
def ui() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stratum HITL Demo</title>
    <style>
      body {
        font-family: system-ui, sans-serif;
        max-width: 720px;
        margin: 40px auto;
        padding: 0 20px;
        line-height: 1.5;
      }
      button, input {
        font: inherit;
        padding: 8px 10px;
      }
      input {
        min-width: 280px;
      }
      .panel {
        border: 1px solid #ccc;
        padding: 16px;
        margin-top: 16px;
      }
      .muted {
        color: #666;
      }
    </style>
  </head>
  <body>
    <h1>Stratum HITL Demo</h1>
    <button id="start">Start Demo Ask</button>

    <div class="panel">
      <p class="muted">Pending question</p>
      <p id="question">None</p>
      <form id="form">
        <input id="answer" name="answer" autocomplete="off" placeholder="Type answer">
        <button type="submit">Submit</button>
      </form>
    </div>

    <div class="panel">
      <p class="muted">Result</p>
      <p id="result">None</p>
    </div>

    <script>
      async function refresh() {
        const pending = await fetch("/pending").then((response) => response.json());
        const result = await fetch("/demo/result").then((response) => response.json());

        document.getElementById("question").textContent = pending ? pending.question : "None";
        document.getElementById("result").textContent = result.result || "None";
      }

      document.getElementById("start").addEventListener("click", async () => {
        await fetch("/demo/ask", { method: "POST" });
        await refresh();
      });

      document.getElementById("form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const input = document.getElementById("answer");
        await fetch("/respond", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ text: input.value })
        });
        input.value = "";
        setTimeout(refresh, 50);
      });

      refresh();
      setInterval(refresh, 1000);
    </script>
  </body>
</html>
        """.strip()
    )

