from __future__ import annotations

from typing import Any


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    """Convert common DataFrame return types at the adapter boundary."""
    if frame is None:
        return []
    if isinstance(frame, list):
        return [dict(row) for row in frame]
    if isinstance(frame, dict):
        return [dict(frame)]
    if hasattr(frame, "to_dicts"):
        return [dict(row) for row in frame.to_dicts()]
    if hasattr(frame, "to_dict"):
        try:
            result = frame.to_dict(orient="records")
        except TypeError:
            result = frame.to_dict("records")
        if isinstance(result, list):
            return [dict(row) for row in result]
    raise TypeError(f"Unsupported parser frame type: {type(frame)!r}")
