from pathlib import Path
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import alerts, comparables, feedback, opportunities, reports, searches, settings
from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.services.scheduled_search_refresh import (
    run_scheduled_saved_search_monitor,
    wait_for_cancelled_monitor,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_settings = get_settings()
    refresh_task: asyncio.Task | None = None
    if app_settings.saved_search_refresh_enabled:
        init_db()
        refresh_task = asyncio.create_task(
            run_scheduled_saved_search_monitor(
                get_session_factory(),
                settings=app_settings,
            )
        )
        app.state.saved_search_refresh_task = refresh_task
    try:
        yield
    finally:
        if refresh_task is not None:
            refresh_task.cancel()
            await wait_for_cancelled_monitor(refresh_task)


def create_app() -> FastAPI:
    app = FastAPI(title="Car Dealer Opportunity Finder", version="0.1.0", lifespan=lifespan)
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(searches.router, prefix="/api/searches", tags=["searches"])
    app.include_router(comparables.router, prefix="/api/comparables", tags=["comparables"])
    app.include_router(opportunities.router, prefix="/api/opportunities", tags=["opportunities"])
    app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
    app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
    dashboard_dir = Path(__file__).resolve().parents[1] / "static" / "dashboard"
    if dashboard_dir.exists():
        app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")
    return app


app = create_app()
