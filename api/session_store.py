"""Session store for live layout-editing sessions."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from config import SESSION_EXPIRY_SECONDS, SESSION_SWEEP_SECONDS
from layout_session import StatefulLayoutSession


class LayoutSessionStore:
    """In-memory store for ``StatefulLayoutSession`` objects."""

    def __init__(
        self,
        expiry_seconds: float = SESSION_EXPIRY_SECONDS,
        sweep_seconds: float = SESSION_SWEEP_SECONDS,
    ) -> None:
        self.expiry_seconds = expiry_seconds
        self.sweep_seconds = sweep_seconds
        self._sessions: dict[str, StatefulLayoutSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background expiration sweep."""

        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop the background expiration sweep."""

        if self._cleanup_task is None:
            return
        self._cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._cleanup_task
        self._cleanup_task = None

    async def save(self, session: StatefulLayoutSession) -> StatefulLayoutSession:
        """Store or replace a session."""

        async with self._lock:
            session.touch()
            self._sessions[session.session_id] = session
            return session

    async def get(self, session_id: str) -> StatefulLayoutSession | None:
        """Return a non-expired session, touching it on access."""

        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired(self.expiry_seconds):
                self._sessions.pop(session_id, None)
                return None
            session.touch()
            return session

    async def delete(self, session_id: str) -> None:
        """Delete a session if it exists."""

        async with self._lock:
            self._sessions.pop(session_id, None)

    async def _cleanup_loop(self) -> None:
        """Remove expired sessions periodically."""

        while True:
            await asyncio.sleep(self.sweep_seconds)
            await self._delete_expired()

    async def _delete_expired(self) -> None:
        """Drop all expired sessions."""

        async with self._lock:
            expired_ids = [
                session_id
                for session_id, session in self._sessions.items()
                if session.is_expired(self.expiry_seconds)
            ]
            for session_id in expired_ids:
                self._sessions.pop(session_id, None)


_SESSION_STORE = LayoutSessionStore()


def get_layout_session_store() -> LayoutSessionStore:
    """Return the process-wide layout session store."""

    return _SESSION_STORE
