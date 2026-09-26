"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from precheck.config import Settings, get_settings
from precheck.db.engine import engine_for, session_factory

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_session_factory(settings: SettingsDep) -> sessionmaker[Session]:
    return session_factory(engine_for(str(settings.db_path)))


# Endpoints open their own unit of work (`with session_scope(db) as s:`) so the commit
# happens before the response is sent.
SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]
