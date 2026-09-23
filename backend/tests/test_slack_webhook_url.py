"""Slack webhook adresi doğrulaması (SSRF koruması)."""

import pytest
from pydantic import ValidationError

from app.api.v1.notifications import SlackTestRequest, SlackWebhookRequest
from app.services.notification_service import validate_slack_webhook_url

VALID = "https://hooks.slack.com/services/T000/B000/XXXXXXXX"


def test_valid_url_is_accepted_and_stripped():
    assert validate_slack_webhook_url(f"  {VALID}  ") == VALID


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.slack.com/services/T/B/X",              # https değil
        "https://evil.com/services/T/B/X",                    # başka alan adı
        "https://hooks.slack.com.evil.com/services/T/B/X",    # alt alan adı hilesi
        "https://hooks.slack.com@evil.com/services/T/B/X",    # kullanıcı bilgisi hilesi
        "https://user:pw@hooks.slack.com/services/T/B/X",     # kullanıcı bilgisi
        "https://hooks.slack.com:8443/services/T/B/X",        # farklı port
        "https://hooks.slack.com/other/T/B/X",                # /services/ değil
        "http://169.254.169.254/latest/meta-data/",           # bulut meta veri servisi
        "http://localhost:6379/",                             # iç servis
        "file:///etc/passwd",
        "",
        "hooks.slack.com/services/T/B/X",                     # şemasız
    ],
)
def test_invalid_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_slack_webhook_url(url)


@pytest.mark.parametrize("model", [SlackWebhookRequest, SlackTestRequest])
def test_request_schemas_validate_the_url(model):
    assert model(webhook_url=VALID).webhook_url == VALID
    with pytest.raises(ValidationError):
        model(webhook_url="http://169.254.169.254/")
