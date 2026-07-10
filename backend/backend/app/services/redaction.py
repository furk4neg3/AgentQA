from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

DEFAULT_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "gemini_api_key",
        "password",
        "secret",
        "set-cookie",
        "system_prompt",
        "token",
    }
)


def redact_sensitive(
    value: Any,
    *,
    sensitive_keys: Iterable[str] = DEFAULT_SENSITIVE_KEYS,
    sensitive_values: Iterable[str] = (),
) -> Any:
    """Return a recursively redacted copy suitable for persistence or export."""

    normalized_keys = {_normalize_key(key) for key in sensitive_keys}
    protected_values = tuple(item for item in sensitive_values if item)
    return _redact(value, normalized_keys=normalized_keys, protected_values=protected_values)


def _redact(value: Any, *, normalized_keys: set[str], protected_values: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if _normalize_key(str(key)) in normalized_keys
                else _redact(
                    item, normalized_keys=normalized_keys, protected_values=protected_values
                )
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [
            _redact(item, normalized_keys=normalized_keys, protected_values=protected_values)
            for item in value
        ]
    if isinstance(value, str):
        redacted = value
        for protected in protected_values:
            redacted = redacted.replace(protected, "[REDACTED]")
        return redacted
    return value


def _normalize_key(value: str) -> str:
    return value.casefold().replace("-", "_").replace(" ", "_")
