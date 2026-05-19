"""OpenPoke Python server package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import app as app


def __getattr__(name: str) -> object:
    if name == "app":
        from .app import app

        return app
    raise AttributeError(name)


__all__ = ["app"]
