import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Stratum Backend")


class HumanResponse(BaseModel):
    text: str


class HitlState:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending_question: str | None = None
        self._waiter: asyncio.Future[str] | None = None
        self._demo_task: asyncio.Task[None] | None = None
        self.result: str | None = None

    async def pending(self) -> dict[str, str] | None:
        async with self._lock:
            if self._pending_question is None:
                return None
            return {"question": self._pending_question}

    async def ask_human(self, question: str) -> str:
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()

        async with self._lock:
            if self._waiter is not None:
                raise RuntimeError("A question is already pending.")
            self._pending_question = question
            self._waiter = waiter

        return await waiter

    async def respond(self, text: str) -> None:
        async with self._lock:
            if self._waiter is None:
                raise HTTPException(status_code=409, detail="No pending question.")

            waiter = self._waiter
            self._waiter = None
            self._pending_question = None

        if not waiter.done():
            waiter.set_result(text)

    async def start_demo(self) -> str:
        async with self._lock:
            if self._demo_task is not None and not self._demo_task.done():
                return "already_running"

            self.result = None
            self._demo_task = asyncio.create_task(self._run_demo())

        await asyncio.sleep(0)
        return "started"

    async def _run_demo(self) -> None:
        answer = await self.ask_human("What colour is the sky?")
        self.result = f"You answered: {answer}"

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            pending = None
            if self._pending_question is not None:
                pending = {"question": self._pending_question}

            running = self._demo_task is not None and not self._demo_task.done()
            return {"pending": pending, "result": self.result, "running": running}


hitl_state = HitlState()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stratum-backend"}


@app.get("/pending")
async def pending() -> dict[str, str] | None:
    return await hitl_state.pending()


@app.post("/respond")
async def respond(response: HumanResponse) -> dict[str, str]:
    await hitl_state.respond(response.text)
    return {"status": "ok"}


@app.post("/demo/ask")
async def demo_ask() -> dict[str, str]:
    status = await hitl_state.start_demo()
    return {"status": status}


@app.get("/demo/result")
async def demo_result() -> dict[str, Any]:
    return await hitl_state.snapshot()


@app.get("/ui")
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
