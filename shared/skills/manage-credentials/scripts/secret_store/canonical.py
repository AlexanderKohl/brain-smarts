"""RFC 8785 canonical JSON for the subset the store uses: objects, arrays, strings, booleans,
null and integers within the safe range. Floats, duplicate keys and non-string keys are refused."""

from __future__ import annotations

import json
from typing import Any

from .errors import SecretStoreError

MAX_SAFE_INTEGER = 2**53 - 1
_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _string(value: str) -> str:
    out = ['"']
    for char in value:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20:
            out.append("\\u%04x" % ord(char))
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _utf16_order(key: str) -> bytes:
    return key.encode("utf-16-be", "surrogatepass")


def _encode(value: Any, depth: int) -> str:
    if depth > 64:
        raise SecretStoreError("canonical JSON nested too deeply")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise SecretStoreError("canonical JSON refuses integers outside the safe range")
        return str(int(value))
    if isinstance(value, float):
        raise SecretStoreError("canonical JSON refuses floating-point numbers")
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item, depth + 1) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise SecretStoreError("canonical JSON refuses non-string object keys")
        parts = [_string(key) + ":" + _encode(value[key], depth + 1)
                 for key in sorted(value, key=_utf16_order)]
        return "{" + ",".join(parts) + "}"
    raise SecretStoreError(f"canonical JSON refuses values of type {type(value).__name__}")


def dumps(value: Any) -> bytes:
    """Canonical UTF-8 bytes of value."""
    try:
        return _encode(value, 0).encode("utf-8")
    except UnicodeEncodeError:
        raise SecretStoreError("canonical JSON refuses lone surrogates") from None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecretStoreError("JSON has a duplicate key")
        result[key] = value
    return result


def _refuse_float(_text: str) -> Any:
    raise SecretStoreError("JSON floating-point numbers are refused")


def _refuse_constant(_text: str) -> Any:
    raise SecretStoreError("JSON NaN and Infinity are refused")


def _int(text: str) -> int:
    number = int(text)
    if abs(number) > MAX_SAFE_INTEGER:
        raise SecretStoreError("JSON integer outside the safe range")
    return number


def loads(data: bytes | str) -> Any:
    """Strict parse: duplicate keys, floats, NaN/Infinity and unsafe integers are refused."""
    if isinstance(data, (bytes, bytearray)):
        try:
            data = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            raise SecretStoreError("JSON is not valid UTF-8") from None
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_float=_refuse_float,
                          parse_int=_int, parse_constant=_refuse_constant)
    except json.JSONDecodeError:
        raise SecretStoreError("JSON could not be parsed") from None
