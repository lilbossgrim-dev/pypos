"""SQLAlchemy 2.x backend (PostgreSQL in production, SQLite for development).

Entities are stored as JSON documents plus indexed key columns. Writes use optimistic
versioning (``UPDATE ... WHERE version = :v``) and ``SELECT ... FOR UPDATE`` on
PostgreSQL. External payment calls are never inside these transactions.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pypos.core.codec import encode_value, from_dict, to_dict
from pypos.core.events import EventBus
from pypos.core.store import (
    Collection,
    CollectionSpec,
    E,
    Store,
    Transaction,
    key_of,
)
from pypos.exceptions import ConfigurationError, ConflictError, DuplicateError, NotFoundError
from pypos.persistence.schema import build_table, describe
from pypos.types import utcnow


class SQLTransaction(Transaction):
    def __init__(self, store: SQLStore, conn: Any) -> None:
        super().__init__()
        self.store = store
        self.conn = conn

    def of(self, spec: CollectionSpec[E]) -> Collection[E]:
        if spec.name not in self.store.specs:
            self.store.register(spec)
        return SQLCollection(self, spec)


class SQLCollection(Collection[E]):
    def __init__(self, tx: SQLTransaction, spec: CollectionSpec[E]) -> None:
        self.tx = tx
        self.spec = spec
        self.table = tx.store.tables[spec.name]
        self.key_cols = describe(spec).key_columns

    def _values(self, obj: E) -> dict[str, Any]:
        data = to_dict(obj)
        values: dict[str, Any] = {
            "id": obj.id, "merchant_id": obj.merchant_id, "version": obj.version,
            "created_at": obj.created_at, "updated_at": obj.updated_at, "data": data,
        }  # fmt: skip
        for c in self.key_cols:
            values[c] = key_of(data.get(c))
        return values

    def add(self, obj: E) -> E:
        from sqlalchemy.exc import IntegrityError

        now = utcnow()
        obj.version, obj.created_at, obj.updated_at = 1, now, now
        try:
            with self.tx.conn.begin_nested():
                self.tx.conn.execute(self.table.insert().values(**self._values(obj)))
        except IntegrityError as exc:
            raise DuplicateError(
                f"{self.spec.name}: duplicate record", collection=self.spec.name
            ) from exc
        return obj

    def get(self, id: str, *, for_update: bool = False) -> E | None:
        stmt = self.table.select().where(self.table.c.id == id)
        if for_update:
            stmt = stmt.with_for_update()
        row = self.tx.conn.execute(stmt).mappings().first()
        return None if row is None else from_dict(self.spec.model, dict(row["data"]))

    def save(self, obj: E) -> E:
        from sqlalchemy.exc import IntegrityError

        expected = obj.version
        obj.version, obj.updated_at = expected + 1, utcnow()
        values = self._values(obj)
        values.pop("id")
        values.pop("created_at")
        stmt = (self.table.update()
                .where(self.table.c.id == obj.id, self.table.c.version == expected)
                .values(**values))  # fmt: skip
        try:
            with self.tx.conn.begin_nested():
                result = self.tx.conn.execute(stmt)
        except IntegrityError as exc:
            obj.version = expected
            raise DuplicateError(f"{self.spec.name}: duplicate record") from exc
        if result.rowcount == 0:
            obj.version = expected
            exists = self.tx.conn.execute(
                self.table.select().where(self.table.c.id == obj.id)).first()  # fmt: skip
            if exists is None:
                raise NotFoundError(f"{self.spec.name} {obj.id!r} not found", id=obj.id)
            raise ConflictError(f"{self.spec.name} {obj.id!r} was modified concurrently", id=obj.id)
        return obj

    def delete(self, id: str) -> None:
        result = self.tx.conn.execute(self.table.delete().where(self.table.c.id == id))
        if result.rowcount == 0:
            raise NotFoundError(f"{self.spec.name} {id!r} not found", id=id)

    def find(self, **filters: Any) -> list[E]:
        want = {f: key_of(encode_value(v)) for f, v in filters.items()}
        columns = {"id", "merchant_id", *self.key_cols}
        stmt = self.table.select()
        for f, w in want.items():
            if f in columns:
                col = self.table.c[f]
                stmt = stmt.where(col.is_(None) if w is None else col == w)
        rows = self.tx.conn.execute(stmt).mappings().all()
        out: list[E] = []
        for row in rows:
            data = dict(row["data"])
            if all(key_of(data.get(f)) == w for f, w in want.items() if f not in columns):
                out.append(from_dict(self.spec.model, data))
        return out


class SQLStore(Store):
    def __init__(self, url: str, *, echo: bool = False, bus: EventBus | None = None) -> None:
        super().__init__(bus)
        try:
            import sqlalchemy as sa
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ConfigurationError(
                "SQLAlchemy is required for database_url other than memory://"
            ) from exc
        self.url = url
        self.engine = sa.create_engine(url, echo=echo, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            self._configure_sqlite(sa)
        self.metadata = sa.MetaData()
        self.tables: dict[str, Any] = {}
        self._local = threading.local()

    def _configure_sqlite(self, sa: Any) -> None:
        @sa.event.listens_for(self.engine, "connect")
        def _connect(dbapi_conn: Any, _rec: Any) -> None:  # pragma: no cover
            dbapi_conn.isolation_level = None  # we emit BEGIN ourselves (SAVEPOINT-safe)

        @sa.event.listens_for(self.engine, "begin")
        def _begin(conn: Any) -> None:  # pragma: no cover
            conn.exec_driver_sql("BEGIN")

    def _on_register(self, spec: CollectionSpec[Any]) -> None:
        self.tables[spec.name] = build_table(self.metadata, spec)

    def initialize(self) -> None:
        self.metadata.create_all(self.engine)

    def ping(self) -> bool:
        import sqlalchemy as sa

        with self.engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return True

    def close(self) -> None:
        self.engine.dispose()

    @contextmanager
    def transaction(self) -> Iterator[SQLTransaction]:
        current: SQLTransaction | None = getattr(self._local, "tx", None)
        if current is not None:  # nested -> SAVEPOINT
            event_mark = len(current.events)
            sp = current.conn.begin_nested()
            try:
                yield current
            except BaseException:
                sp.rollback()
                del current.events[event_mark:]
                raise
            else:
                sp.commit()
            return
        conn = self.engine.connect()
        trans = conn.begin()
        tx = SQLTransaction(self, conn)
        self._local.tx = tx
        committed = False
        try:
            yield tx
            trans.commit()
            committed = True
        except BaseException:
            trans.rollback()
            raise
        finally:
            self._local.tx = None
            conn.close()
        if committed:
            self.bus.publish_many(tx.events)
