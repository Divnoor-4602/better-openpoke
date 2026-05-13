from __future__ import annotations

from fastapi import APIRouter

from .routes import agent_runs, health, integrations, threads

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(threads.router)
api_router.include_router(agent_runs.router)
api_router.include_router(integrations.router)

__all__ = ["api_router"]

