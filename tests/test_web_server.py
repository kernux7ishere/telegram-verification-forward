"""Tests for the Flask API, stats collection and duration formatting."""

import pytest

from app.database import Database
from app.discord_sender import DiscordSender
from app.stats_collector import StatsCollector, format_duration
from app.web_server import _mask, create_app
from tests.test_database import make_code


class FakeTelegram:
    status = "online"
    last_message_time = None


class FakeService:
    def __init__(self, db):
        self.db = db
        self.telegram = FakeTelegram()
        self.discord = DiscordSender("https://discord.com/api/webhooks/1/token")
        self.stats = StatsCollector(self.telegram, db, self.discord)

    def start(self):  # the test app never launches the bot
        return False


@pytest.fixture()
def service(tmp_path):
    db = Database(str(tmp_path / "api.db"))
    yield FakeService(db)
    db.close()


@pytest.fixture()
def client(service):
    app = create_app(service=service, start_bot=False)
    app.config.update(TESTING=True)
    return app.test_client()


# --- endpoints -------------------------------------------------------------


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["timestamp"].endswith("Z")


def test_index_renders_the_dashboard(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Verification Forwarder" in response.data
    assert b"pet-sprite" in response.data


def test_dashboard_does_not_expose_codes_or_bot_status(client, service):
    service.db.add_log(make_code("15825"))

    body = client.get("/").data

    # These were deliberately removed from the dashboard; /api/stats still
    # carries them, but nothing in the page should render them.
    for needle in (b"Bot Status", b"Codes Today", b"Total Codes", b"Last Code"):
        assert needle not in body
    assert b"15825" not in body


def test_stats_endpoint_shape(client, service):
    service.db.add_log(make_code("15825"))

    payload = client.get("/api/stats").get_json()

    assert payload["codes_today"] == 1
    assert payload["codes_total"] == 1
    assert payload["last_code"] == "15825"
    assert payload["bot_status"] == "online"
    assert payload["memory_used_mb"] > 0
    assert payload["uptime_formatted"]
    assert payload["last_update"].endswith("Z")


def test_logs_endpoint_masks_code_values(client, service):
    service.db.add_log(make_code("15825"))

    payload = client.get("/api/logs?limit=5").get_json()

    assert payload["limit"] == 5
    assert len(payload["logs"]) == 1
    entry = payload["logs"][0]
    assert "code_value" not in entry
    assert entry["code_preview"] == "158**"


def test_security_headers_are_present(client):
    headers = client.get("/health").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert headers["Cache-Control"] == "no-store"


def test_static_assets_are_cacheable(client):
    response = client.get("/static/css/style.css")

    assert response.status_code == 200
    assert "max-age=3600" in response.headers["Cache-Control"]


def test_unknown_route_returns_json_404(client):
    response = client.get("/nope")

    assert response.status_code == 404
    assert response.get_json() == {"error": "not found"}


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [("15825", "158**"), ("1582", "1***"), ("", ""), ("sEHa-bQyZcM", "sEH********")],
)
def test_mask(code, expected):
    assert _mask(code) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0s"),
        (42, "42s"),
        (60, "1m"),
        (3600, "1h"),
        (5400, "1h 30m"),
        (95400, "1d 2h 30m"),
        (-5, "0s"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_stats_are_cached_for_five_seconds(service):
    first = service.stats.collect()
    second = service.stats.collect()

    assert first is second
    assert service.stats.collect(force=True) is not first


def test_memory_percent_is_bounded(service):
    used_mb, percent = service.stats.get_memory_usage()

    assert used_mb > 0
    assert 0 <= percent <= 100
