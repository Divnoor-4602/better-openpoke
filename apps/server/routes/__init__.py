from __future__ import annotations

from fastapi import APIRouter

from .chat import router as chat_router
from .execution import router as execution_router
from .meta import router as meta_router

api_router = APIRouter(prefix="/api")
api_router.include_router(meta_router)
api_router.include_router(chat_router)
api_router.include_router(execution_router)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(meta_router)
v1_router.include_router(chat_router)
v1_router.include_router(execution_router)

__all__ = ["api_router", "v1_router"]
