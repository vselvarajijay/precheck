"""Alembic environment: DB path from precheck settings unless the caller passes a
connection (tests) or sets `sqlalchemy.url`."""

from logging.config import fileConfig

from alembic import context

from precheck.server.db.engine import make_engine
from precheck.server.db.models import Base
from precheck.server.settings import get_settings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    url = config.get_main_option("sqlalchemy.url")
    engine = make_engine(url.removeprefix("sqlite:///") if url else get_settings().db_path)
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


def _run(connection: object) -> None:
    context.configure(
        connection=connection,  # type: ignore[arg-type]
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite ALTER support
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations()
