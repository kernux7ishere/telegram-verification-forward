"""Tests for Discord webhook formatting, retries and rate limiting."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.discord_sender import DiscordSender
from app.message_processor import ALPHANUMERIC, CUSTOM, NUMERIC, VerificationCode

WEBHOOK = "https://discord.com/api/webhooks/1/token"


def make_code(value="15825", code_type=NUMERIC):
    return VerificationCode(
        code=value,
        type=code_type,
        confidence=0.95,
        pattern_matched="numeric",
        raw_message=f"Login code: {value}",
    )


def response(status=204, headers=None, body=None, text=""):
    fake = MagicMock(spec=requests.Response)
    fake.status_code = status
    fake.headers = headers or {}
    fake.text = text
    fake.json.return_value = body if body is not None else {}
    return fake


@pytest.fixture()
def sender():
    return DiscordSender(WEBHOOK, max_retries=3, rate_limit=10)


# --- formatting ------------------------------------------------------------


def test_numeric_code_uses_key_emoji(sender):
    payload = sender.format_message(make_code("15825", NUMERIC))

    assert payload["content"] == "🔑 Login code: 15825"
    assert payload["allowed_mentions"] == {"parse": []}


def test_alphanumeric_code_uses_globe_emoji(sender):
    payload = sender.format_message(make_code("sEHa-bQyZcM", ALPHANUMERIC))

    assert payload["content"] == "🌐 Web login code: sEHa-bQyZcM"


def test_custom_code_falls_back_to_generic_wording(sender):
    payload = sender.format_message(make_code("abc", CUSTOM))

    assert payload["content"] == "📩 Verification code: abc"


# --- sending ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_send(sender):
    with patch("app.discord_sender.requests.post", return_value=response(204)) as post:
        result = await sender.send_code(make_code())

    assert bool(result) is True
    assert result.status_code == 204
    assert result.attempts == 1
    assert sender.sent_count == 1
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["content"] == "🔑 Login code: 15825"


@pytest.mark.asyncio
async def test_retries_on_server_error_then_succeeds(sender):
    responses = [response(500, text="oops"), response(204)]
    with patch("app.discord_sender.requests.post", side_effect=responses) as post:
        with patch("app.discord_sender.asyncio.sleep") as sleep:
            result = await sender.send_code(make_code())

    assert bool(result) is True
    assert result.attempts == 2
    assert post.call_count == 2
    sleep.assert_awaited()


@pytest.mark.asyncio
async def test_gives_up_after_max_retries(sender):
    with patch("app.discord_sender.requests.post", return_value=response(500, text="oops")) as post:
        with patch("app.discord_sender.asyncio.sleep"):
            result = await sender.send_code(make_code())

    assert bool(result) is False
    assert post.call_count == 3
    assert result.attempts == 3
    assert sender.failed_count == 1


@pytest.mark.asyncio
async def test_network_error_is_retried(sender):
    side_effect = [requests.ConnectionError("boom"), response(204)]
    with patch("app.discord_sender.requests.post", side_effect=side_effect) as post:
        with patch("app.discord_sender.asyncio.sleep"):
            result = await sender.send_code(make_code())

    assert bool(result) is True
    assert post.call_count == 2


@pytest.mark.asyncio
async def test_rate_limited_response_honours_retry_after(sender):
    responses = [response(429, headers={"Retry-After": "2.5"}), response(204)]
    with patch("app.discord_sender.requests.post", side_effect=responses):
        with patch("app.discord_sender.asyncio.sleep") as sleep:
            result = await sender.send_code(make_code())

    assert bool(result) is True
    sleep.assert_any_await(2.5)


@pytest.mark.asyncio
async def test_retry_after_falls_back_to_response_body(sender):
    responses = [response(429, body={"retry_after": 1.5}), response(204)]
    with patch("app.discord_sender.requests.post", side_effect=responses):
        with patch("app.discord_sender.asyncio.sleep") as sleep:
            await sender.send_code(make_code())

    sleep.assert_any_await(1.5)


@pytest.mark.asyncio
async def test_unauthorised_webhook_disables_the_sender(sender):
    with patch("app.discord_sender.requests.post", return_value=response(404, text="unknown")) as post:
        result = await sender.send_code(make_code())

    assert bool(result) is False
    assert sender.disabled is True
    assert post.call_count == 1  # no point retrying a dead webhook


@pytest.mark.asyncio
async def test_invalid_webhook_url_disables_sending():
    disabled = DiscordSender("not-a-url")

    result = await disabled.send_code(make_code())

    assert bool(result) is False
    assert disabled.disabled is True


# --- rate limiting ---------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_queues_further_sends():
    sender = DiscordSender(WEBHOOK, max_retries=1, rate_limit=2)

    async def rolling_window(_seconds):
        # Stand in for the rolling window advancing past the earlier sends.
        sender._sent_at.clear()

    with patch("app.discord_sender.requests.post", return_value=response(204)):
        await sender.send_code(make_code())
        await sender.send_code(make_code())
        assert sender.is_rate_limited() is True

        with patch("app.discord_sender.asyncio.sleep", side_effect=rolling_window) as sleep:
            result = await sender.send_code(make_code())

    assert bool(result) is True
    assert sleep.await_count == 1
    assert sender.sent_count == 3


def test_expired_sends_leave_the_window():
    sender = DiscordSender(WEBHOOK, rate_limit=1)
    sender._sent_at.append(-1e9)  # monotonic timestamp far in the past

    assert sender.is_rate_limited() is False
    assert len(sender._sent_at) == 0


@pytest.mark.asyncio
async def test_send_alert_wraps_text(sender):
    with patch("app.discord_sender.requests.post", return_value=response(204)) as post:
        result = await sender.send_alert("Telegram authentication failed")

    assert bool(result) is True
    assert post.call_args.kwargs["json"]["content"].startswith("⚠️ ")
