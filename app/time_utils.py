"""Local calendar days expressed as the naive UTC timestamps stored in SQLite."""

from datetime import date, datetime, time, timedelta, timezone


LOCAL_TZ = timezone(timedelta(hours=8))


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, start_utc + timedelta(days=1)
