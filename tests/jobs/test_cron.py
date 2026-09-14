from datetime import UTC, datetime

from blh.jobs.cron import cron_matches, validate_cron


def _dt(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_cron_matches_every_minute():
    moment = _dt(2026, 9, 14, 10, 30)
    assert cron_matches("* * * * *", moment)
    assert cron_matches("*/5 * * * *", moment)
    assert not cron_matches("*/7 * * * *", moment)


def test_cron_matches_specific_minute_hour():
    assert cron_matches("30 10 * * *", _dt(2026, 9, 14, 10, 30))
    assert not cron_matches("30 10 * * *", _dt(2026, 9, 14, 10, 31))


def test_cron_matches_ranges_and_lists():
    assert cron_matches("0-30 10 * * *", _dt(2026, 9, 14, 10, 15))
    assert cron_matches("0,15,30 10 * * *", _dt(2026, 9, 14, 10, 15))
    assert not cron_matches("0,15,30 10 * * *", _dt(2026, 9, 14, 10, 20))


def test_cron_matches_weekday():
    monday = _dt(2026, 8, 10, 9, 0)  # 周一,cron 周一=1
    assert cron_matches("0 9 * * 1", monday)
    assert not cron_matches("0 9 * * 2", monday)


def test_validate_cron_accepts_valid():
    assert validate_cron("0 9 * * *") is None
    assert validate_cron("*/5 * * * *") is None
    assert validate_cron("0 9 * * 1-5") is None


def test_validate_cron_rejects_wrong_field_count():
    assert "Expected 5 fields" in validate_cron("0 9 * *")
    assert "Expected 5 fields" in validate_cron("0 9 * * * *")


def test_validate_cron_rejects_out_of_range():
    assert validate_cron("60 9 * * *") is not None
    assert "hour" in validate_cron("0 24 * * *")
    assert validate_cron("0 9 0 * *") is not None
    assert validate_cron("0 9 * 13 *") is not None


def test_validate_cron_rejects_bad_field():
    assert validate_cron("x 9 * * *") is not None
    assert validate_cron("*/0 * * * *") is not None
    assert validate_cron("5-1 * * * *") is not None
