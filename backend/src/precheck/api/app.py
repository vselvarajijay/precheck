"""FastAPI application factory. Routers stay thin; logic lives in service layers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from precheck import __version__
from precheck.api import playground, policy, problems, rules, testing, tests, translate, validate
from precheck.api.deps import SettingsDep
from precheck.authoring.seed import seed_demo
from precheck.config import get_settings
from precheck.db.engine import engine_for, session_factory, session_scope
from precheck.jev import make_jev_client
from precheck.translator.llm import make_claude_client


class Health(BaseModel):
    status: str
    version: str
    jev_configured: bool


def create_app() -> FastAPI:
    # One schema per model (no -Input/-Output split) keeps the generated TS types simple.

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One pooled Jev client per process; tests may pre-set app.state.jev.
        owned = None
        if getattr(app.state, "jev", None) is None:
            owned = app.state.jev = make_jev_client(get_settings())
        if getattr(app.state, "llm", None) is None:
            app.state.llm = make_claude_client(get_settings())
        settings = get_settings()
        if settings.seed_demo:
            with session_scope(session_factory(engine_for(str(settings.db_path)))) as s:
                seed_demo(s, settings.examples_dir)
        yield
        if owned is not None:
            await owned.aclose()

    app = FastAPI(
        title="precheck",
        version=__version__,
        separate_input_output_schemas=False,
        lifespan=lifespan,
    )
    app.state.jev = None
    app.state.llm = None

    @app.get("/api/health", response_model=Health, tags=["meta"])
    def health(settings: SettingsDep) -> Health:
        # Never echo the key itself, only whether one is configured.
        return Health(status="ok", version=__version__, jev_configured=settings.jev_configured)

    problems.install(app)
    app.include_router(rules.router)
    app.include_router(playground.router)
    app.include_router(translate.router)
    app.include_router(tests.router)
    app.include_router(policy.router)
    if get_settings().enable_test_reset:
        app.include_router(testing.router)
    app.include_router(validate.router)
    return app


app = create_app()
