"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from precheck.config import Settings, get_settings
from precheck.db.engine import engine_for, session_factory
from precheck.engine import JevEvaluator
from precheck.translator.llm import JsonLLM

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_session_factory(settings: SettingsDep) -> sessionmaker[Session]:
    return session_factory(engine_for(str(settings.db_path)))


# Endpoints open their own unit of work (`with session_scope(db) as s:`) so the commit
# happens before the response is sent.
SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]


def get_jev(request: Request) -> JevEvaluator:
    """The process-wide Jev client created at startup (see app lifespan)."""
    return request.app.state.jev  # type: ignore[no-any-return]


JevDep = Annotated[JevEvaluator, Depends(get_jev)]


def get_llm(request: Request) -> JsonLLM:
    """The process-wide translator LLM client (see app lifespan)."""
    return request.app.state.llm  # type: ignore[no-any-return]


LLMDep = Annotated[JsonLLM, Depends(get_llm)]
