from __future__ import annotations

from typing import Any


def decode_ws_message(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, bytes):
        payload = message
        if payload and payload[0] in {0, 1, 2, 3, 4}:
            payload = payload[1:]
        return payload.decode("utf-8", errors="replace")
    if isinstance(message, str):
        return message
    return str(message)
