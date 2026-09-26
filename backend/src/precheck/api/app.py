"""FastAPI application factory. Routers stay thin; logic lives in service layers."""

from fastapi import FastAPI
from pydantic import BaseModel

from precheck import __version__
from precheck.api import problems, rules, validate
from precheck.api.deps import SettingsDep


class Health(BaseModel):
    status: str
    version: str
    jev_configured: bool


def create_app() -> FastAPI:
    app = FastAPI(title="precheck", version=__version__)

    @app.get("/api/health", response_model=Health, tags=["meta"])
    def health(settings: SettingsDep) -> Health:
        # Never echo the key itself, only whether one is configured.
        return Health(status="ok", version=__version__, jev_configured=settings.jev_configured)

    problems.install(app)
    app.include_router(rules.router)
    app.include_router(validate.router)
    return app


app = create_app()
