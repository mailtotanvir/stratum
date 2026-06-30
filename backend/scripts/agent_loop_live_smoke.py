import argparse
import json
import sys
from urllib import error, request


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an agent loop smoke test through the backend API.",
    )
    parser.add_argument("--request", required=True)
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )
    return parser


def _post_smoke(base_url: str, payload: dict[str, object]) -> dict[str, object]:
    url = f"{base_url.rstrip('/')}/agent-loop/smoke"
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp is not None else ""
        raise RuntimeError(
            f"POST {url} failed with HTTP {exc.code}: {body or exc.reason}"
        ) from exc

    return json.loads(body)


def _print_result(result: dict[str, object]) -> None:
    print(f"status: {result.get('status')}")
    print(f"iterations_used: {result.get('iterations_used')}")
    print(f"final_answer: {result.get('final_answer')}")
    print(f"error: {result.get('error')}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload: dict[str, object] = {
        "user_request": args.request,
        "max_iterations": args.max_iterations,
    }
    if args.provider is not None:
        payload["provider_id"] = args.provider
    if args.model is not None:
        payload["model"] = args.model

    result = _post_smoke(args.base_url, payload)
    _print_result(result)

    if result.get("status") == "failed":
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"agent loop live smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
