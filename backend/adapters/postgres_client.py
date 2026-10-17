"""
IntentLock — Supabase Postgres Async Client & Connection Pool
Provides bounded async connection pooling via asyncpg with statement timeouts,
TLS enforcement, transaction-local actor context for RLS, credential redaction,
and a dedicated worker loop thread to guarantee safe cross-thread and cross-loop execution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional
import asyncpg

from backend.core.config import settings

logger = logging.getLogger("intentlock.postgres_client")


def sanitize_db_error(msg: str) -> str:
    """Redacts passwords, tokens, and credentials from database error messages."""
    redacted = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(msg))
    redacted = re.sub(r"password=([^\s]+)", "password=***", redacted, flags=re.I)
    redacted = re.sub(r"Bearer\s+([a-zA-Z0-9_\-\.]+)", "Bearer ***", redacted)
    redacted = re.sub(r"(apikey|api_key|token|secret)=([^\s&]+)", r"\1=***", redacted, flags=re.I)
    return redacted


class PostgresClient:
    _instance: Optional["PostgresClient"] = None

    def __init__(self, dsn: Optional[str] = None):
        self.dsn: Optional[str] = dsn or settings.SUPABASE_DATABASE_URL
        self._pool: Optional[asyncpg.Pool] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._worker_ready = threading.Event()

    @classmethod
    def get_instance(cls, dsn: Optional[str] = None) -> "PostgresClient":
        if cls._instance is None:
            cls._instance = cls(dsn=dsn)
        return cls._instance

    @property
    def is_configured(self) -> bool:
        return bool(self.dsn)

    def _ensure_worker_loop(self) -> asyncio.AbstractEventLoop:
        """Ensure the dedicated background worker event loop is running."""
        with self._lock:
            if self._loop is None or not self._loop.is_running() or self._thread is None or not self._thread.is_alive():
                self._worker_ready.clear()
                self._thread = threading.Thread(
                    target=self._run_worker,
                    daemon=True,
                    name="IntentLock-Postgres-Worker",
                )
                self._thread.start()
                if not self._worker_ready.wait(timeout=10.0):
                    raise RuntimeError("Failed to start Postgres worker event loop thread.")
            return self._loop

    def _run_worker(self) -> None:
        """Worker thread entrypoint running the dedicated asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._worker_ready.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.close()
            except Exception:
                pass

    def run(self, coro, timeout: Optional[float] = None) -> Any:
        """
        Execute a coroutine synchronously on the dedicated Postgres worker loop.
        Safe to call from any thread or event loop.
        """
        loop = self._ensure_worker_loop()
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is loop:
            raise RuntimeError("Cannot invoke PostgresClient.run() synchronously from inside the worker loop.")

        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        effective_timeout = timeout or (settings.DB_TIMEOUT_SECONDS + 5.0)
        return fut.result(timeout=effective_timeout)

    async def run_async(self, coro, timeout: Optional[float] = None) -> Any:
        """
        Execute a coroutine on the dedicated Postgres worker loop and await its result
        from the caller's active event loop.
        """
        loop = self._ensure_worker_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        effective_timeout = timeout or (settings.DB_TIMEOUT_SECONDS + 5.0)
        return await asyncio.wait_for(asyncio.wrap_future(fut), timeout=effective_timeout)

    async def init_pool(self) -> None:
        """Initialize asyncpg connection pool if not already initialized."""
        if self._pool is not None:
            return

        if not self.dsn:
            raise ValueError(
                "Postgres database URL is not configured. Set SUPABASE_DATABASE_URL environment variable."
            )

        try:
            self._pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                command_timeout=settings.DB_TIMEOUT_SECONDS,
                ssl="require",
            )
            logger.info("Supabase Postgres connection pool initialized successfully.")
        except Exception as exc:
            redacted_err = sanitize_db_error(str(exc))
            logger.error("Failed to initialize Supabase Postgres pool: %s", redacted_err)
            raise RuntimeError(f"Database pool initialization failed: {redacted_err}") from None

    async def close_pool_async(self) -> None:
        """Close connection pool gracefully within the worker loop."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Supabase Postgres connection pool closed.")

    def close(self) -> None:
        """Close pool and stop worker thread."""
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                if self._pool is not None:
                    fut = asyncio.run_coroutine_threadsafe(self.close_pool_async(), self._loop)
                    try:
                        fut.result(timeout=5.0)
                    except Exception:
                        pass
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
                self._thread = None
            self._loop = None

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Acquire a connection from the pool on the worker loop."""
        if self._pool is None:
            await self.init_pool()
        assert self._pool is not None

        conn = await self._pool.acquire()
        try:
            yield conn
        finally:
            await self._pool.release(conn)

    @asynccontextmanager
    async def transaction(self, actor_id: Optional[str] = None) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Acquire a connection and begin a transaction on the worker loop.
        Optionally sets transaction-local actor context for Row Level Security (RLS).
        SET LOCAL ensures actor identity is discarded when the transaction commits or rolls back.
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                if actor_id:
                    clean_actor = re.sub(r"[^a-zA-Z0-9_\-]", "", actor_id.strip().upper())
                    await conn.execute("SELECT set_config('intentlock.actor_id', $1, true)", clean_actor)
                yield conn

    async def ping_async(self) -> Dict[str, Any]:
        """Diagnostic check verifying database connectivity without leaking credentials."""
        if not self.is_configured:
            return {"configured": False, "connected": False, "error": "SUPABASE_DATABASE_URL not set"}
        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT current_database() as db, current_user as usr, version() as ver"
                )
                return {
                    "configured": True,
                    "connected": True,
                    "database": row["db"] if row else None,
                    "user": row["usr"] if row else None,
                    "server": "PostgreSQL (Supabase)",
                }
        except Exception as exc:
            return {"configured": True, "connected": False, "error": sanitize_db_error(str(exc))}

    def ping(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {"configured": False, "connected": False, "error": "SUPABASE_DATABASE_URL not set"}
        return self.run(self.ping_async())
