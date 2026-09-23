"""Kimlik doğrulaması gerektirmeyen uçların listesini kilitler.

Yeni bir uç kimlik istemeden eklenirse bu test düşer; ya `get_current_active_user`
bağımlılığı eklenmeli ya da uç bilinçli olarak ALLOWLIST'e yazılmalıdır.
"""

from pathlib import Path

from fastapi.routing import APIRoute

from app.main import app
from app.middleware.auth import get_current_user

# Bilerek herkese açık uçlar
PUBLIC = {
    "GET /health", "GET /health/ready", "GET /health/live", "GET /status",
    "POST /api/v1/auth/register", "POST /api/v1/auth/login", "POST /api/v1/auth/refresh",
    "POST /api/v1/auth/password-reset/request", "POST /api/v1/auth/password-reset/confirm",
    "POST /api/v1/billing/webhook",  # Stripe imzasıyla doğrulanır
    "GET /api/v1/connections/callback/{platform}",  # OAuth dönüşü, state ile doğrulanır
    # Statik meta veri
    "GET /api/v1/ai/platform-limits", "GET /api/v1/billing/plans",
    "GET /api/v1/webhooks/event-types",
    "GET /api/v1/automation/metadata/conditions", "GET /api/v1/automation/metadata/actions",
}

# Henüz iskelet olan uçlar: ilgili tur yazılınca kimlik şartı eklenmeli
STUBS_PENDING_AUTH = {
    "POST /api/v1/auth/logout", "GET /api/v1/auth/sessions", "DELETE /api/v1/auth/sessions",
    "DELETE /api/v1/auth/sessions/{session_id}",
    "POST /api/v1/auth/mfa/setup", "POST /api/v1/auth/mfa/verify",
    "POST /api/v1/auth/mfa/challenge", "POST /api/v1/auth/mfa/disable",
    "DELETE /api/v1/users/me", "POST /api/v1/users/organizations",
    "PATCH /api/v1/users/organizations/current",
    "GET /api/v1/users/organizations/current/invitations",
    "POST /api/v1/users/organizations/current/invitations",
    "DELETE /api/v1/users/organizations/current/invitations/{invitation_id}",
    "GET /api/v1/users/organizations/current/members",
    "PATCH /api/v1/users/organizations/current/members/{user_id}/role",
    "DELETE /api/v1/users/organizations/current/members/{user_id}",
    "POST /api/v1/users/organizations/current/transfer",
}


def _requires_auth(dependant) -> bool:
    if dependant.call is get_current_user:
        return True
    return any(_requires_auth(d) for d in dependant.dependencies)


def _unauthenticated_routes() -> set[str]:
    found = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(("/api/v1", "/health", "/status")):
            continue
        if not _requires_auth(route.dependant):
            found.update(f"{m} {route.path}" for m in route.methods if m != "HEAD")
    return found


def test_only_allowlisted_routes_are_unauthenticated():
    unexpected = _unauthenticated_routes() - PUBLIC - STUBS_PENDING_AUTH
    assert not unexpected, f"Kimlik istemeyen yeni uç(lar): {sorted(unexpected)}"


def test_allowlist_has_no_stale_entries():
    stale = (PUBLIC | STUBS_PENDING_AUTH) - _unauthenticated_routes()
    assert not stale, f"Artık kimlik isteyen ama listede duran uç(lar): {sorted(stale)}"


def test_no_hardcoded_placeholder_ids_in_app():
    app_dir = Path(__file__).resolve().parent.parent / "app"
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if "00000000-0000-0000-0000-00000000000" in p.read_text()
    ]
    assert not offenders, f"Sabit sahte kimlik bulunan dosyalar: {offenders}"
