"""Tests for the SQLite persistence layer."""

from datetime import datetime, timedelta, timezone

import pytest

from app.database import Database
from app.message_processor import NUMERIC, VerificationCode


def make_code(value="15825", code_type=NUMERIC, confidence=0.95, timestamp=None):
    return VerificationCode(
        code=value,
        type=code_type,
        confidence=confidence,
        pattern_matched="numeric",
        raw_message=f"Login code: {value}",
        timestamp=timestamp or datetime.now(timezone.utc),
        telegram_message_id=7,
    )


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database
    database.close()


def test_schema_is_created(db):
    assert db.get_total_count() == 0
    assert db.get_today_count() == 0
    assert db.get_last_code() is None


def test_add_log_returns_row_id_and_persists_fields(db):
    log_id = db.add_log(make_code())

    assert log_id > 0
    row = db.get_last_code()
    assert row["code_value"] == "15825"
    assert row["code_type"] == NUMERIC
    assert row["confidence"] == pytest.approx(0.95)
    assert row["telegram_message_id"] == 7
    assert row["discord_sent"] == 0


def test_counts_increase(db):
    for value in ("111222", "333444", "555666"):
        db.add_log(make_code(value))

    assert db.get_total_count() == 3
    assert db.get_today_count() == 3


def test_today_count_excludes_older_rows(db):
    db.add_log(make_code("111222", timestamp=datetime.now(timezone.utc) - timedelta(days=3)))
    db.add_log(make_code("333444"))

    assert db.get_total_count() == 2
    assert db.get_today_count() == 1


def test_mark_sent_records_delivery(db):
    log_id = db.add_log(make_code())

    db.mark_sent(log_id, 204, attempts=1)

    row = db.get_last_code()
    assert row["discord_sent"] == 1
    assert row["discord_response_code"] == 204
    assert row["discord_send_time"] is not None
    assert row["discord_failed_attempts"] == 1


def test_mark_failed_is_listed_in_failed_sends(db):
    log_id = db.add_log(make_code())

    db.mark_failed(log_id, 500, attempts=3, notes="HTTP 500")

    failed = db.get_failed_sends()
    assert len(failed) == 1
    assert failed[0]["id"] == log_id
    assert failed[0]["notes"] == "HTTP 500"


def test_update_log_rejects_unknown_columns(db):
    log_id = db.add_log(make_code())

    with pytest.raises(ValueError, match="Unknown column"):
        db.update_log(log_id, injected="value")


def test_update_log_with_no_known_fields_is_a_noop(db):
    log_id = db.add_log(make_code())

    db.update_log(log_id)

    assert db.get_last_code()["discord_sent"] == 0


def test_recent_logs_are_newest_first_and_paginated(db):
    for value in ("111222", "333444", "555666"):
        db.add_log(make_code(value))

    page = db.get_recent_logs(limit=2)
    assert [row["code_value"] for row in page] == ["555666", "333444"]

    second = db.get_recent_logs(limit=2, offset=2)
    assert [row["code_value"] for row in second] == ["111222"]


def test_recent_logs_limit_is_clamped(db):
    db.add_log(make_code())

    assert db.get_recent_logs(limit=10_000) != []
    assert db.get_recent_logs(limit=0) != []


def test_cleanup_removes_only_old_logs(db):
    db.add_log(make_code("111222", timestamp=datetime.now(timezone.utc) - timedelta(days=45)))
    db.add_log(make_code("333444"))

    removed = db.cleanup_old_logs(days=30)

    assert removed == 1
    assert db.get_total_count() == 1
    assert db.get_last_code()["code_value"] == "333444"


def test_export_stats_shape(db):
    db.add_log(make_code())

    stats = db.export_stats()

    assert stats["codes_today"] == 1
    assert stats["codes_total"] == 1
    assert stats["last_code"] == "15825"
    assert stats["last_code_time"] is not None
    assert stats["database_size_mb"] >= 0


def test_size_mb_reports_a_number(db):
    db.add_log(make_code())

    assert isinstance(db.size_mb(), float)
