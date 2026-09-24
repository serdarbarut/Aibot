"""
Session Cleanup Worker

Süresi dolmuş veya iptal edilmiş oturumları düzenli olarak siler;
`sessions` tablosu aksi halde her girişte büyür.
"""

import structlog

from app.core.database import async_session_factory
from app.services.session_service import delete_stale_sessions

logger = structlog.get_logger()


async def cleanup_stale_sessions(ctx: dict) -> dict:
    """
    Eski oturumları sil.

    Günde bir kez çalışır (bkz. WorkerSettings.cron_jobs).

    Args:
        ctx: Worker context

    Returns:
        dict with status and the number of deleted sessions
    """
    async with async_session_factory() as db:
        deleted = await delete_stale_sessions(db)
        await db.commit()

    logger.info("stale_sessions_cleaned", deleted=deleted)
    return {"status": "success", "deleted": deleted}
