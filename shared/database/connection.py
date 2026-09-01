"""Helpers de conexión DuckDB compartidos entre apps y scripts de inicialización."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

import duckdb

T = TypeVar("T")

# DuckDB no es thread-safe: una sola conexión real en un hilo dedicado.
_db_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="duckdb")
_worker_state = threading.local()

# Evita intercalar transacciones largas (BEGIN…COMMIT) entre peticiones.
_global_db_lock = threading.Lock()

_DML_HEADS = frozenset({"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "CHECKPOINT", "TRUNCATE"})
_READ_HEADS = frozenset({"SELECT", "WITH", "PRAGMA", "EXPLAIN", "SHOW", "DESCRIBE"})


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def resolve_duckdb_path(raw: str | None = None) -> Path:
    value = (raw or os.environ.get("DUCKDB_PATH", "db/globtrade.duckdb")).strip()
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _is_readonly() -> bool:
    return str(os.environ.get("DUCKDB_READONLY", "") or "").strip().lower() in {"1", "true", "yes"}


def _sql_head(sql: str) -> str:
    stripped = sql.strip()
    return stripped.upper().split()[0] if stripped else ""


def _worker_conn(resolved: str) -> duckdb.DuckDBPyConnection:
    """Conexión real; solo invocar desde tareas del executor DuckDB."""
    conn = getattr(_worker_state, "conn", None)
    path = getattr(_worker_state, "path", None)
    if conn is not None and path == resolved:
        try:
            conn.execute("SELECT 1")
            return conn
        except duckdb.Error:
            try:
                conn.close()
            except Exception:
                pass
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    conn = duckdb.connect(resolved, read_only=_is_readonly())
    try:
        conn.execute("SET threads TO 4")
    except duckdb.Error:
        pass
    _worker_state.conn = conn
    _worker_state.path = resolved
    return conn


def _run_db(resolved: str, fn: Callable[[duckdb.DuckDBPyConnection], T]) -> T:
    def task() -> T:
        return fn(_worker_conn(resolved))

    return _db_executor.submit(task).result()


def _exec_on_conn(conn: duckdb.DuckDBPyConnection, sql: str, params: list | tuple | None) -> None:
    if params is not None:
        conn.execute(sql, params)
    else:
        conn.execute(sql)


class SerializedConnection:
    """Proxy thread-safe: cada execute+fetch es atómico en el hilo DuckDB."""

    __slots__ = ("_path", "_pending_sql", "_lock_held", "_in_transaction")

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._pending_sql: tuple[str, list | tuple | None] | None = None
        self._lock_held = False
        self._in_transaction = False

    def _acquire(self) -> None:
        if not self._lock_held:
            _global_db_lock.acquire()
            self._lock_held = True

    def _release(self) -> None:
        if self._lock_held and not self._in_transaction:
            _global_db_lock.release()
            self._lock_held = False

    def force_release_lock(self) -> None:
        if self._lock_held:
            _global_db_lock.release()
            self._lock_held = False
            self._in_transaction = False
        self._pending_sql = None

    def execute(self, sql: str, params: list | tuple | None = None) -> SerializedConnection:
        head = _sql_head(sql)

        if head == "BEGIN":
            self._acquire()
            self._in_transaction = True
            _run_db(self._path, lambda c: _exec_on_conn(c, sql, params))
            return self

        if head in ("COMMIT", "ROLLBACK"):
            _run_db(self._path, lambda c: _exec_on_conn(c, sql, params))
            self._in_transaction = False
            self._release()
            return self

        if self._in_transaction:
            if head in _READ_HEADS:
                self._pending_sql = (sql, params)
                return self
            _run_db(self._path, lambda c: _exec_on_conn(c, sql, params))
            return self

        if head in _DML_HEADS and "RETURNING" not in sql.upper():
            _run_db(self._path, lambda c: _exec_on_conn(c, sql, params))
            return self

        self._acquire()
        self._pending_sql = (sql, params)
        return self

    def _fetch(self, method: str, *args: int) -> Any:
        pending = self._pending_sql
        self._pending_sql = None
        if pending is None:
            if args:
                return _run_db(self._path, lambda c: getattr(c, method)(args[0]))
            return _run_db(self._path, lambda c: getattr(c, method)())

        sql, params = pending

        def work(conn: duckdb.DuckDBPyConnection) -> Any:
            _exec_on_conn(conn, sql, params)
            if args:
                return getattr(conn, method)(args[0])
            return getattr(conn, method)()

        try:
            return _run_db(self._path, work)
        finally:
            self._release()

    def fetchone(self) -> Any:
        return self._fetch("fetchone")

    def fetchall(self) -> list[Any]:
        return self._fetch("fetchall")

    def fetchmany(self, size: int) -> list[Any]:
        return self._fetch("fetchmany", size)

    def commit(self) -> None:
        _run_db(self._path, lambda c: c.commit())
        self._in_transaction = False
        self._release()

    def rollback(self) -> None:
        def work(conn: duckdb.DuckDBPyConnection) -> None:
            try:
                conn.rollback()
            except Exception:
                pass

        _run_db(self._path, work)
        self._in_transaction = False
        self._release()

    def close(self) -> None:
        def work(_: duckdb.DuckDBPyConnection) -> None:
            conn = getattr(_worker_state, "conn", None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            _worker_state.conn = None
            _worker_state.path = None

        _run_db(self._path, work)
        self.force_release_lock()

    def __getattr__(self, name: str) -> Any:
        """Delega register/cursor/etc. al hilo DuckDB."""

        def caller(*args: Any, **kwargs: Any) -> Any:
            self._acquire()
            try:
                return _run_db(self._path, lambda c: getattr(c, name)(*args, **kwargs))
            finally:
                self._release()

        return caller


def open_shared(path: str | Path | None = None) -> SerializedConnection:
    """Conexión compartida serializada (admin + portal en run.py)."""
    resolved = str(resolve_duckdb_path(str(path) if path is not None else None))
    return SerializedConnection(resolved)


def close_shared() -> None:
    """Cierra la conexión del worker DuckDB."""
    path = getattr(_worker_state, "path", None)
    if path:
        SerializedConnection(path).close()


@contextmanager
def shared_connection(path: str | Path | None = None) -> Generator[SerializedConnection, None, None]:
    """Context manager con proxy serializado (seguro entre hilos HTTP)."""
    proxy = open_shared(path)
    try:
        yield proxy
    except Exception:
        try:
            proxy.rollback()
        except Exception:
            pass
        raise
    finally:
        proxy.force_release_lock()


def connect(raw: str | None = None) -> duckdb.DuckDBPyConnection:
    """Conexión independiente (scripts ETL/regeneración). No usar en run.py unificado."""
    return duckdb.connect(str(resolve_duckdb_path(raw)))


def table_exists(conn: duckdb.DuckDBPyConnection | SerializedConnection, name: str) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = ?
        """,
        [name],
    ).fetchone()
    return bool(row and row[0])


def column_exists(conn: duckdb.DuckDBPyConnection | SerializedConnection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return any(r[1] == column for r in rows)
