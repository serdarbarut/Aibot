"""Eski oturumların temizliği: servis, worker işi ve zamanlama."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from app.services import session_service as svc
from app.workers import session_cleanup
from app.workers.settings import WorkerSettings

FIXED_NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


async def test_delete_stale_sessions_targets_only_old_expired_or_revoked(monkeypatch):
    monkeypatch.setattr(svc, "_now", lambda: FIXED_NOW)
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=4))

    deleted = await svc.delete_stale_sessions(db)

    sql = compiled(db.execute.await_args.args[0])
    cutoff = (FIXED_NOW - timedelta(days=svc.STALE_SESSION_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    assert deleted == 4
    assert sql.startswith("DELETE FROM sessions")
    # Yalnızca süresi dolalı veya iptal edileli saklama süresini aşanlar; aktif oturumlar korunur
    assert f"sessions.expires_at < '{cutoff}" in sql
    assert f"sessions.revoked_at < '{cutoff}" in sql
    assert " OR " in sql and " AND " not in sql


async def test_delete_stale_sessions_respects_custom_retention(monkeypatch):
    monkeypatch.setattr(svc, "_now", lambda: FIXED_NOW)
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=0))

    await svc.delete_stale_sessions(db, retention_days=7)

    assert "2026-09-17 12:00:00" in compiled(db.execute.await_args.args[0])


async def test_delete_stale_sessions_handles_missing_rowcount():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=None))

    assert await svc.delete_stale_sessions(db) == 0


async def test_worker_job_deletes_and_commits(monkeypatch):
    db = MagicMock()
    db.commit = AsyncMock()

    class FakeFactory:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(session_cleanup, "async_session_factory", lambda: FakeFactory())
    delete = AsyncMock(return_value=3)
    monkeypatch.setattr(session_cleanup, "delete_stale_sessions", delete)

    result = await session_cleanup.cleanup_stale_sessions({})

    assert result == {"status": "success", "deleted": 3}
    delete.assert_awaited_once_with(db)
    db.commit.assert_awaited_once()  # silme kalıcı olsun


def test_job_is_registered_and_scheduled_daily():
    assert session_cleanup.cleanup_stale_sessions in WorkerSettings.functions

    jobs = [j for j in WorkerSettings.cron_jobs if j.coroutine is session_cleanup.cleanup_stale_sessions]
    assert len(jobs) == 1
    assert jobs[0].hour == 3 and jobs[0].minute == 0
