import json

from scripts import agent_loop_live_smoke


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_agent_loop_live_smoke_posts_and_prints_result(monkeypatch, capsys) -> None:
    captured = {}

    def fake_urlopen(req):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse(
            {
                "status": "completed",
                "iterations_used": 2,
                "final_answer": "Done.",
                "error": None,
            }
        )

    monkeypatch.setattr(agent_loop_live_smoke.request, "urlopen", fake_urlopen)

    exit_code = agent_loop_live_smoke.main(
        [
            "--request",
            "Smoke test",
            "--provider",
            "openai",
            "--model",
            "gpt-4.1-mini",
            "--max-iterations",
            "2",
            "--base-url",
            "http://127.0.0.1:8000",
        ]
    )

    assert exit_code == 0
    assert captured["url"] == "http://127.0.0.1:8000/agent-loop/smoke"
    assert captured["body"] == {
        "user_request": "Smoke test",
        "max_iterations": 2,
        "provider_id": "openai",
        "model": "gpt-4.1-mini",
    }
    assert capsys.readouterr().out.splitlines() == [
        "status: completed",
        "iterations_used: 2",
        "final_answer: Done.",
        "error: None",
    ]


def test_agent_loop_live_smoke_exits_nonzero_on_failed_loop(monkeypatch) -> None:
    def fake_urlopen(req):
        return FakeResponse(
            {
                "status": "failed",
                "iterations_used": 3,
                "final_answer": None,
                "error": "boom",
            }
        )

    monkeypatch.setattr(agent_loop_live_smoke.request, "urlopen", fake_urlopen)

    exit_code = agent_loop_live_smoke.main(["--request", "Smoke test"])

    assert exit_code == 1
