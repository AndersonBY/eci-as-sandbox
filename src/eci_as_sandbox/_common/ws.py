from __future__ import annotations

from typing import Any


# ECI WebSocket message type prefixes
WS_MSG_STDIN = 0
WS_MSG_STDOUT = 1
WS_MSG_STDERR = 2
WS_MSG_RESIZE = 3
WS_MSG_EXIT = 4


def decode_ws_message(message: Any) -> str:
    """Decode a WebSocket message from ECI, stripping the type prefix."""
    if message is None:
        return ""
    if isinstance(message, bytes):
        payload = message
        if payload and payload[0] in {WS_MSG_STDIN, WS_MSG_STDOUT, WS_MSG_STDERR, WS_MSG_RESIZE, WS_MSG_EXIT}:
            payload = payload[1:]
        return payload.decode("utf-8", errors="replace")
    if isinstance(message, str):
        return message
    return str(message)


def encode_ws_stdin(data: str | bytes) -> bytes:
    """Encode data as a WebSocket stdin message for ECI."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return bytes([WS_MSG_STDIN]) + data
