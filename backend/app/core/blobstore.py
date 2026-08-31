"""Where the generated overlay physically lives.

The overlay -- syllabi designed for uncurated subjects, the pages verified for
them, their embeddings and placement questions -- was always a directory of
files. That is exactly right on a laptop: it survives restarts, it is trivial
to inspect, and ``rm -r`` is a working undo.

It is exactly wrong on a free container. A free Render instance sleeps after
fifteen idle minutes and comes back with a blank disk, so a subject a learner
waited two minutes to build is gone by the time anyone else asks for it. The
committed demo corpus survives because it is baked into the image; anything
built *after* deploy did not survive at all.

So the overlay now sits behind a storage interface with two implementations,
chosen by what the database is:

``files``      a directory. Used locally, where the disk is real.
``database``   one row per file. Used wherever a real database is configured,
               because that is the only thing in a free deployment that
               outlives the container.

The unit is a whole named blob of bytes, not a record, because that is what the
overlay already was -- ``skills.json``, ``catalog_embeddings.bge-small.npy``.
Keeping the same shape means the database backend is a storage swap rather than
a rewrite, and the local behaviour a developer relies on is bit-for-bit
unchanged.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

from sqlalchemy import Column, LargeBinary, MetaData, String, Table, delete, select
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_metadata = MetaData()

# One row per overlay file. `name` is the filename it would have had on disk,
# which keeps the two backends interchangeable and the contents inspectable
# with an ordinary SELECT.
generated_blob = Table(
    "generated_blob",
    _metadata,
    Column("name", String(200), primary_key=True),
    Column("data", LargeBinary, nullable=False),
)


class BlobStore(Protocol):
    """Named byte blobs. Whole-file reads and writes only."""

    def read(self, name: str) -> bytes | None: ...
    def write(self, name: str, data: bytes) -> None: ...
    def names(self) -> list[str]: ...
    def clear(self) -> None: ...


class FileBlobStore:
    """A directory. What the overlay has always been, locally."""

    kind = "files"

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def read(self, name: str) -> bytes | None:
        path = self.directory / name
        if not path.exists():
            return None
        try:
            return path.read_bytes()
        except OSError as exc:
            logger.error("generated file %s is unreadable (%s) -- ignoring it", name, exc)
            return None

    def write(self, name: str, data: bytes) -> None:
        """Write atomically, so a concurrent reader never sees half a file."""
        target = self.directory / name
        temporary = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
        temporary.write_bytes(data)
        temporary.replace(target)

    def names(self) -> list[str]:
        return sorted(p.name for p in self.directory.iterdir() if p.is_file())

    def clear(self) -> None:
        for path in self.directory.iterdir():
            if path.is_file():
                path.unlink()


class DatabaseBlobStore:
    """One row per overlay file, in whatever database the app already uses.

    This exists because a free container's filesystem is scratch space. It is
    deliberately not clever: the same bytes, under the same names, in a table
    that any Postgres client can read.
    """

    kind = "database"

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        _metadata.create_all(engine, tables=[generated_blob], checkfirst=True)

    def read(self, name: str) -> bytes | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(generated_blob.c.data).where(generated_blob.c.name == name)
            ).first()
        return bytes(row[0]) if row else None

    def write(self, name: str, data: bytes) -> None:
        """Insert or replace. Not a true upsert, but it runs under the
        process lock ``store`` already holds for the whole read-modify-write."""
        with self.engine.begin() as conn:
            conn.execute(delete(generated_blob).where(generated_blob.c.name == name))
            conn.execute(generated_blob.insert().values(name=name, data=data))

    def names(self) -> list[str]:
        with self.engine.connect() as conn:
            return sorted(r[0] for r in conn.execute(select(generated_blob.c.name)))

    def clear(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(generated_blob))


_store: BlobStore | None = None


def get_store() -> BlobStore:
    """The overlay's storage, chosen once per process.

    The rule is "does this deployment have a database worth trusting". A real
    database means a hosted deployment whose disk is scratch; SQLite means a
    laptop, where files are better in every way -- inspectable, greppable, and
    deletable without a client.
    """
    global _store
    if _store is not None:
        return _store

    from app.config import get_settings
    from app.core import store as store_module

    settings = get_settings()
    backend = (settings.generated_store or "auto").lower().strip()
    if backend == "auto":
        backend = "files" if settings.database_url.startswith("sqlite") else "database"

    if backend == "database":
        from app.db import engine

        _store = DatabaseBlobStore(engine)
        logger.info("generated overlay stored in the database")
    else:
        _store = FileBlobStore(store_module.generated_dir())
        logger.info("generated overlay stored in %s", store_module.generated_dir())
    return _store


def bootstrap() -> int:
    """Seed an empty database overlay from the corpus shipped in the image.

    The committed subjects -- quantum computing, business studies, the French
    Revolution and eight more -- travel as files inside the image, exactly as
    ``skills.json`` does. When the overlay moved into the database those files
    stopped being read, and a deployment that had shipped 260 skills came back
    up serving 152: the database was empty and nothing had told it otherwise.

    So the shipped files seed the database once, the same way the curated
    graph seeds everything else. This runs at startup, does nothing when the
    overlay already has content, and does nothing at all on the file backend,
    where the files *are* the overlay.

    Returns the number of blobs imported.
    """
    store = get_store()
    if store.kind != "database" or store.names():
        return 0

    from app.core import store as store_module

    shipped = store_module.generated_dir()
    imported = 0
    for path in sorted(shipped.iterdir()):
        if not path.is_file() or path.name.endswith(".tmp"):
            continue
        store.write(path.name, path.read_bytes())
        imported += 1
    if imported:
        logger.info("seeded the database overlay with %d shipped files", imported)
    return imported


def reset() -> None:
    """Drop the cached store. Used by tests that change configuration."""
    global _store
    _store = None
