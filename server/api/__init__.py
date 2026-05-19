from __future__ import annotations

from fastapi import APIRouter, Depends

from .dependencies import get_workspace_id
from .routes import (
    admin,
    agent_runs,
    dev,
    health,
    integrations,
    me,
    meta,
    reminders,
    threads,
)
from .routes.calendar import events as calendar_events
from .routes.gmail import drafts as gmail_drafts

# Health stays unauthenticated so container orchestrators (Railway,
# Docker, k8s) can ping it without Basic creds. Every other endpoint
# is gated by get_workspace_id, which also binds the ContextVar that
# tools and store helpers read for per-workspace isolation.
public_router = APIRouter(prefix="/api")
public_router.include_router(health.router)

api_router = APIRouter(prefix="/api", dependencies=[Depends(get_workspace_id)])
api_router.include_router(me.router)
api_router.include_router(admin.router)
api_router.include_router(meta.router)
api_router.include_router(threads.router)
api_router.include_router(agent_runs.router)
api_router.include_router(integrations.router)
api_router.include_router(gmail_drafts.router)
api_router.include_router(calendar_events.router)
api_router.include_router(reminders.router)
api_router.include_router(dev.router)

__all__ = ["api_router", "public_router"]
