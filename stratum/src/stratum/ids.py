"""Identifier generation for the Stratum runtime.

IDs are lexicographically sortable and roughly time-ordered:
    <prefix><milliseconds-since-epoch-base36>-<random-suffix>
"""

from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def _encode(value: int) -> str:
    if value == 0:
        return "0"
    chars: list[str] = []
    while value:
        value, rem = divmod(value, 36)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def _suffix(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_id(prefix: str) -> str:
    """Generate a new prefixed, time-sortable identifier."""
    millis = time.time_ns() // 1_000_000
    return f"{prefix}_{_encode(millis)}-{_suffix()}"


def task_id() -> str:
    return new_id("tsk")


def execution_id() -> str:
    return new_id("exe")


def plan_id() -> str:
    return new_id("pln")


def event_id() -> str:
    return new_id("evt")
