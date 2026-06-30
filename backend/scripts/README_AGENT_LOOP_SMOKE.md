# Agent Loop Live Smoke

This script sends a request to the backend agent loop smoke endpoint and prints a compact result summary.

## Start the backend

From `backend/`:

```bash
uv run uvicorn app.main:app --reload
```

## Run the smoke

Example OpenRouter or OpenAI-compatible provider:

```bash
uv run python scripts/agent_loop_live_smoke.py \
  --request "Reply with exactly: Stratum agent loop smoke test passed." \
  --provider openai \
  --model gpt-4.1-mini \
  --base-url http://127.0.0.1:8000
```

If your backend is already configured for a different live provider, pass that provider id instead. The script does not call providers directly; it only posts to `POST /agent-loop/smoke`.

## Output

The script prints these fields:

- `status`
- `iterations_used`
- `final_answer`
- `error`

It exits nonzero when the loop status is `failed`.

## Expected provider behavior

The live provider should return JSON-only tool output that the agent loop can parse. For a smoke run, that means a valid provider response with structured JSON content rather than prose wrapped around the payload.

## Approval warning

Mutation tools such as file writes or shell execution require approval in the agent loop. The smoke is intended to be safe, but if the model selects a mutating tool, the approval workflow will gate execution before the tool runs.
