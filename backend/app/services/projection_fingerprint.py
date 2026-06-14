import hashlib
import json
from typing import Any

from app.services.projection_snapshot_manifest_service import (
    normalize_projection_content,
)


def projection_state_fingerprint(state: Any) -> str:
    normalized = normalize_projection_content(state)
    serialized = json.dumps(
        normalized,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
