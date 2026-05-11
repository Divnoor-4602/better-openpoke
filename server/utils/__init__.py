"""Utility exports with lazy imports."""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "error_response": (".responses", "error_response"),
    "UTC": (".timezones", "UTC"),
    "convert_to_user_timezone": (".timezones", "convert_to_user_timezone"),
    "get_user_timezone_name": (".timezones", "get_user_timezone_name"),
    "now_in_user_timezone": (".timezones", "now_in_user_timezone"),
    "resolve_user_timezone": (".timezones", "resolve_user_timezone"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    module = import_module(module_name, __name__)
    return getattr(module, attr_name)


__all__ = sorted(_EXPORTS)
