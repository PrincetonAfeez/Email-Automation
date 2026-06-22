""" Recurrence for EmailAuto."""

from __future__ import annotations

from datetime import datetime, timedelta

from emailauto.scheduling.models import CampaignSchedule


def add_interval(start: datetime, *, every: int, period: str) -> datetime:
    if period == CampaignSchedule.IntervalPeriod.MINUTES:
        return start + timedelta(minutes=every)
    if period == CampaignSchedule.IntervalPeriod.HOURS:
        return start + timedelta(hours=every)
    if period == CampaignSchedule.IntervalPeriod.DAYS:
        return start + timedelta(days=every)
    raise ValueError(f"Unsupported interval period: {period}")


# Cron weekday convention: Sunday=0 .. Saturday=6, with 7 also accepted as Sunday.
# Three-letter names (case-insensitive) are supported, matching standard cron.
WEEKDAY_NAMES = {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}
MONTH_NAMES = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _resolve_token(token: str, names: dict[str, int] | None) -> int:
    token = token.strip().upper()
    if names and token in names:
        return names[token]
    return int(token)


def _field_matches(value: int, expression: str, *, names: dict[str, int] | None = None) -> bool:
    expression = expression.strip()
    if expression in ("*", "?"):
        return True
    for part in expression.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("*/"):
            step = int(part[2:])
            if step > 0 and value % step == 0:
                return True
        elif "-" in part:
            start_token, end_token = part.split("-", 1)
            start = _resolve_token(start_token, names)
            end = _resolve_token(end_token, names)
            if start <= value <= end:
                return True
        elif _resolve_token(part, names) == value:
            return True
    return False


def _weekday_matches(cron_weekday: int, expression: str) -> bool:
    # cron_weekday is already in cron convention (Sun=0). Normalise any literal 7 in the
    # expression to 0 so both 0 and 7 match Sunday.
    expression = expression.strip()
    if expression in ("*", "?"):
        return True
    for part in expression.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("*/"):
            step = int(part[2:])
            if step > 0 and cron_weekday % step == 0:
                return True
        elif "-" in part:
            start_token, end_token = part.split("-", 1)
            start = _resolve_token(start_token, WEEKDAY_NAMES) % 7
            end = _resolve_token(end_token, WEEKDAY_NAMES) % 7
            if start <= cron_weekday <= end:
                return True
        elif _resolve_token(part, WEEKDAY_NAMES) % 7 == cron_weekday:
            return True
    return False


def _field_is_wildcard(expression: str) -> bool:
    return expression.strip() in ("*", "?")


def _date_matches(moment: datetime, day: str, month: str, weekday: str) -> bool:
    """Whether the date fields (day-of-month, month, day-of-week) could match this day.

    Standard cron ORs day-of-month and day-of-week when both are restricted (neither is
    ``*``/``?``). Month always constrains the match.
    """
    if not _field_matches(moment.month, month, names=MONTH_NAMES):
        return False
    cron_weekday = (moment.weekday() + 1) % 7  # datetime Mon=0..Sun=6 -> cron Sun=0..Sat=6
    dom_wild = _field_is_wildcard(day)
    dow_wild = _field_is_wildcard(weekday)
    dom_matches = dom_wild or _field_matches(moment.day, day)
    dow_matches = dow_wild or _weekday_matches(cron_weekday, weekday)
    if not dom_wild and not dow_wild:
        return dom_matches or dow_matches
    return dom_matches and dow_matches


def cron_matches(moment: datetime, expression: str) -> bool:
    minute, hour, day, month, weekday = expression.split()
    return (
        _field_matches(moment.minute, minute)
        and _field_matches(moment.hour, hour)
        and _date_matches(moment, day, month, weekday)
    )


def validate_cron_expression(expression: str) -> None:
    """Raise ValueError if the cron expression is structurally malformed (bad field count
    or unparseable tokens).

    Each field is evaluated against a sample moment so that an unparseable token in any
    field raises — note `cron_matches` short-circuits, so it cannot be used for validation.
    """
    minute, hour, day, month, weekday = _split_or_raise(expression)
    sample = datetime(2024, 1, 1, 0, 0)
    _field_matches(sample.minute, minute)
    _field_matches(sample.hour, hour)
    _field_matches(sample.day, day)
    _field_matches(sample.month, month, names=MONTH_NAMES)
    _weekday_matches((sample.weekday() + 1) % 7, weekday)


def next_cron_after(start: datetime, expression: str) -> datetime:
    minute_e, hour_e, day_e, month_e, weekday_e = _split_or_raise(expression)
    candidate = (start + timedelta(minutes=1)).replace(second=0, microsecond=0)
    # 8-year horizon: consecutive Feb-29 occurrences can be 8 years apart around century
    # non-leap years (e.g. 2096 -> 2104). Day-skipping below keeps the scan cheap.
    deadline = candidate + timedelta(days=366 * 8)
    while candidate <= deadline:
        if _date_matches(candidate, day_e, month_e, weekday_e):
            if _field_matches(candidate.minute, minute_e) and _field_matches(candidate.hour, hour_e):
                return candidate
            candidate += timedelta(minutes=1)
        else:
            # No time of day on a non-matching date can match — skip to the next midnight.
            candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
    raise ValueError("Could not find a matching cron occurrence within the search horizon.")


def _split_or_raise(expression: str) -> list[str]:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron expression must have exactly five fields.")
    return fields


def next_occurrence(schedule: CampaignSchedule, scheduled_for: datetime) -> datetime | None:
    if schedule.schedule_type != "recurring":
        return None
    if schedule.interval_every and schedule.interval_period:
        return add_interval(scheduled_for, every=schedule.interval_every, period=schedule.interval_period)
    if schedule.cron_expression:
        return next_cron_after(scheduled_for, schedule.cron_expression)
    return None

