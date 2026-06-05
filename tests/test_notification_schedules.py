"""Unit tests for custom schedule matching logic (not DB-dependent)."""

from datetime import date

from sc_gr_app.notification.schedules import _schedule_matches_today


class TestMonthlyDay:
    def test_matches_on_correct_day(self):
        schedule = {"schedule_type": "monthly_day", "day_of_month": 15}
        assert _schedule_matches_today(schedule, date(2026, 6, 15)) is True

    def test_does_not_match_on_wrong_day(self):
        schedule = {"schedule_type": "monthly_day", "day_of_month": 15}
        assert _schedule_matches_today(schedule, date(2026, 6, 14)) is False

    def test_day_31_in_feb_non_leap_falls_back_to_last_day(self):
        schedule = {"schedule_type": "monthly_day", "day_of_month": 31}
        assert _schedule_matches_today(schedule, date(2025, 2, 28)) is True

    def test_day_31_in_feb_leap_year(self):
        schedule = {"schedule_type": "monthly_day", "day_of_month": 31}
        # Feb 2024 has 29 days (leap year), but 31 > 29 → falls back to 29
        assert _schedule_matches_today(schedule, date(2024, 2, 29)) is True

    def test_day_31_in_feb_does_not_match_27(self):
        schedule = {"schedule_type": "monthly_day", "day_of_month": 31}
        assert _schedule_matches_today(schedule, date(2025, 2, 27)) is False


class TestWeeklyDay:
    def test_matches_correct_weekday(self):
        # 0=Monday, date(2026,6,8) is a Monday
        schedule = {"schedule_type": "weekly_day", "weekday": 0}
        assert _schedule_matches_today(schedule, date(2026, 6, 8)) is True

    def test_does_not_match_wrong_weekday(self):
        # 0=Monday, date(2026,6,9) is a Tuesday
        schedule = {"schedule_type": "weekly_day", "weekday": 0}
        assert _schedule_matches_today(schedule, date(2026, 6, 9)) is False

    def test_matches_sunday(self):
        # 6=Sunday, date(2026,6,7) is a Sunday
        schedule = {"schedule_type": "weekly_day", "weekday": 6}
        assert _schedule_matches_today(schedule, date(2026, 6, 7)) is True


class TestMonthlyWeekday:
    def test_first_monday_matches(self):
        schedule = {
            "schedule_type": "monthly_weekday",
            "weekday": 0,  # Monday
            "occurrence": "first",
        }
        # June 2026: 1st is Monday → first Monday = June 1
        assert _schedule_matches_today(schedule, date(2026, 6, 1)) is True

    def test_first_monday_does_not_match_second_monday(self):
        schedule = {
            "schedule_type": "monthly_weekday",
            "weekday": 0,  # Monday
            "occurrence": "first",
        }
        # June 2026: 1st is Monday → second Monday = June 8
        assert _schedule_matches_today(schedule, date(2026, 6, 8)) is False

    def test_second_monday_matches(self):
        schedule = {
            "schedule_type": "monthly_weekday",
            "weekday": 0,  # Monday
            "occurrence": "second",
        }
        assert _schedule_matches_today(schedule, date(2026, 6, 8)) is True

    def test_last_friday_matches(self):
        schedule = {
            "schedule_type": "monthly_weekday",
            "weekday": 4,  # Friday
            "occurrence": "last",
        }
        # June 2026: last Friday = June 26
        assert _schedule_matches_today(schedule, date(2026, 6, 26)) is True

    def test_last_friday_does_not_match_second_to_last(self):
        schedule = {
            "schedule_type": "monthly_weekday",
            "weekday": 4,  # Friday
            "occurrence": "last",
        }
        # June 2026: second-to-last Friday = June 19
        assert _schedule_matches_today(schedule, date(2026, 6, 19)) is False

    def test_wrong_weekday_does_not_match(self):
        schedule = {
            "schedule_type": "monthly_weekday",
            "weekday": 0,  # Monday
            "occurrence": "first",
        }
        # June 2, 2026 is a Tuesday
        assert _schedule_matches_today(schedule, date(2026, 6, 2)) is False
