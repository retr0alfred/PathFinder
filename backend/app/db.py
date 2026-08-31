"""Database engine, schema creation and the FastAPI session dependency.

SQLite is the default store. Two pragmas matter for this workload:

* ``journal_mode=WAL`` -- the app writes an ``Event`` row on nearly every
  request while the dashboard reads concurrently. Without WAL, SQLite's default
  rollback journal takes a global write lock and concurrent path generations
  raise "database is locked".
* ``foreign_keys=ON`` -- SQLite ignores foreign keys unless asked, which would
  let orphaned ``PathItem`` rows accumulate silently.

Both are applied per-connection via a SQLAlchemy ``connect`` event so pooled
connections created later in the process get them too.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


def _normalise(url: str) -> str:
    """Accept the URL shape hosts actually hand out.

    Render (and Heroku before it) publish ``postgres://``, which SQLAlchemy 2
    no longer recognises, and they publish it without a driver. Rewriting it
    here means the environment variable can be pasted in verbatim rather than
    edited into a dialect string nobody enjoys remembering.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _safe_url(url: str) -> str:
    """The URL with any password removed, for logging.

    A hosted database URL carries its own credentials, and container logs are
    not a private place -- they are visible to anyone with dashboard access and
    are frequently pasted into issues. Printing the connection string verbatim
    published the password on every boot.
    """
    if "@" not in url:
        return url
    prefix, _, host = url.rpartition("@")
    scheme, sep, credentials = prefix.partition("://")
    user = credentials.split(":")[0]
    return f"{scheme}{sep}{user}:***@{host}"


DATABASE_URL = _normalise(_settings.database_url)
_is_sqlite = DATABASE_URL.startswith("sqlite")

# A free container sleeps and its database connections are severed with it, so
# a pooled connection is frequently dead by the time the next request arrives.
# pre_ping costs one round trip and turns "connection already closed" into a
# transparent reconnect; recycle keeps a connection from ageing past the
# provider's own idle timeout.
_pool_args = {} if _is_sqlite else {"pool_pre_ping": True, "pool_recycle": 280}

engine: Engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    **_pool_args,
)


@event.listens_for(engine, "connect")
def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Enable WAL and foreign keys on every new SQLite connection."""
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def init_db() -> None:
    """Create every table declared on SQLModel's metadata."""
    import app.models  # noqa: F401  -- registers the tables as a side effect

    SQLModel.metadata.create_all(engine)
    logger.info("database ready at %s", _safe_url(DATABASE_URL))


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    with Session(engine) as session:
        yield session
