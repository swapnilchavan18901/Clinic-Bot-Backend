"""Business layer — clinic calendar rules (pure functions, no DB)."""

from datetime import date, datetime, timedelta

from app.business.errors import InvalidSlot
from app.core.settings import settings


def now_local() -> datetime:
    return datetime.now(settings.tz).replace(tzinfo=None, second=0, microsecond=0)


def to_local(dt: datetime) -> datetime:
    """Normalise to naive clinic-local time, minute precision."""
    if dt.tzinfo:
        dt = dt.astimezone(settings.tz).replace(tzinfo=None)
    return dt.replace(second=0, microsecond=0)


def day_slots(d: date) -> list[datetime]:
    if d.weekday() not in settings.working_days:
        return []
    step = timedelta(minutes=settings.slot_minutes)
    t, end = datetime.combine(d, settings.open_time), datetime.combine(d, settings.close_time)
    slots = []
    while t + step <= end:
        if not (settings.lunch_start <= t.time() < settings.lunch_end):
            slots.append(t)
        t += step
    return slots


def validate_slot(dt: datetime) -> datetime:
    dt = to_local(dt)
    if dt not in day_slots(dt.date()):
        raise InvalidSlot(
            "Not a valid slot. Clinic is open Mon–Sat "
            f"{settings.open_time:%H:%M}–{settings.close_time:%H:%M} "
            f"(lunch {settings.lunch_start:%H:%M}–{settings.lunch_end:%H:%M}), "
            f"{settings.slot_minutes}-min slots."
        )
    if dt <= now_local():
        raise InvalidSlot("That time is in the past.")
    return dt


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")