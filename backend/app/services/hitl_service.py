import asyncio
from typing import Any

from app.services.event_service import emit_event


class PendingQuestionError(RuntimeError):
    pass


class NoPendingQuestionError(RuntimeError):
    pass


class HitlService:
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
                raise PendingQuestionError("A question is already pending.")
            self._pending_question = question
            self._waiter = waiter

        await emit_event(
            event_type="ask_human_requested",
            severity="info",
            message=question,
            metadata={"question": question},
        )
        return await waiter

    async def respond(self, text: str) -> None:
        async with self._lock:
            if self._waiter is None:
                raise NoPendingQuestionError("No pending question.")

            waiter = self._waiter
            self._waiter = None
            self._pending_question = None

        if not waiter.done():
            waiter.set_result(text)

        await emit_event(
            event_type="ask_human_responded",
            severity="info",
            message="Human response submitted.",
            metadata={"response": text},
        )

    async def start_demo(self) -> str:
        async with self._lock:
            if self._demo_task is not None and not self._demo_task.done():
                return "already_running"

            self.result = None
            self._demo_task = asyncio.create_task(self._run_demo())

        await asyncio.sleep(0)
        return "started"

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            pending = None
            if self._pending_question is not None:
                pending = {"question": self._pending_question}

            running = self._demo_task is not None and not self._demo_task.done()
            return {"pending": pending, "result": self.result, "running": running}

    async def _run_demo(self) -> None:
        answer = await self.ask_human("What colour is the sky?")
        self.result = f"You answered: {answer}"
        await emit_event(
            event_type="demo_task_completed",
            severity="info",
            message="Demo task completed.",
            metadata={"answer": answer, "result": self.result},
        )


hitl_service = HitlService()
