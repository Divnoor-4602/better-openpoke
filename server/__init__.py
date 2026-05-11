"""OpenPoke Python server package."""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "app":
        from .app import app

        return app
    raise AttributeError(name)


__all__ = ["app"]
