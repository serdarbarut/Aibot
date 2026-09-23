"""Kampanya metrikleri yalnızca kampanyanın sahibi organizasyona açık olmalı."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import analytics
from app.middleware.auth import CurrentUser


def make_user(org_id="orgA"):
    return CurrentUser(id="user-1", email="a@example.com", org_id=org_id, role="admin")


async def test_foreign_campaign_is_404_and_metrics_are_not_queried(monkeypatch):
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)  # bu organizasyonda böyle kampanya yok
    metrics = AsyncMock()
    monkeypatch.setattr(analytics, "get_single_campaign_metrics", metrics)

    with pytest.raises(HTTPException) as exc:
        await analytics.get_campaign_metrics(
            campaign_id="baska-orgun-kampanyasi",
            start_date=None,
            end_date=None,
            compare_previous=False,
            db=db,
            current_user=make_user(),
        )

    assert exc.value.status_code == 404
    metrics.assert_not_awaited()


async def test_ownership_check_is_scoped_to_users_org():
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)

    with pytest.raises(HTTPException):
        await analytics.get_campaign_metrics(
            campaign_id="c1", start_date=None, end_date=None,
            compare_previous=False, db=db, current_user=make_user(org_id="orgA"),
        )

    query = str(db.scalar.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "campaigns.org_id = 'orgA'" in query
    assert "campaigns.id = 'c1'" in query
