from fastapi import FastAPI

from app.api.routes import opportunities, reports, searches, settings


def create_app() -> FastAPI:
    app = FastAPI(title="Car Dealer Opportunity Finder", version="0.1.0")
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(searches.router, prefix="/api/searches", tags=["searches"])
    app.include_router(opportunities.router, prefix="/api/opportunities", tags=["opportunities"])
    app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
    return app


app = create_app()

