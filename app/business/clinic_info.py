"""Business layer — clinic facts (hours, address, fees …).

One source of truth for FAQ answers. The AI layer reads it to answer callers,
and the API exposes it at GET /clinic-info. To change an answer, change settings.
"""

from app.business.appointments import list_doctors
from app.core.settings import settings

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _t(t) -> str:
    return t.strftime("%I:%M %p").lstrip("0").replace(":00", "")


def _days() -> str:
    open_days = [DAY_NAMES[i] for i in sorted(settings.working_days)]
    closed = [d for i, d in enumerate(DAY_NAMES) if i not in settings.working_days]
    text = f"{open_days[0]} to {open_days[-1]}" if len(open_days) > 2 else ", ".join(open_days)
    return text + (f" (closed on {', '.join(closed)})" if closed else "")


def get_clinic_info() -> dict[str, str]:
    """Topic → answer. Plain facts only; the LLM turns them into speech."""
    return {
        "hours": (
            f"Open {_days()}, {_t(settings.open_time)} to {_t(settings.close_time)}, "
            f"with a lunch break from {_t(settings.lunch_start)} to {_t(settings.lunch_end)}."
        ),
        "address": f"{settings.clinic_address}, {settings.clinic_landmark}.",
        "phone": f"Front desk number: {settings.clinic_phone}.",
        "fees": (
            f"Consultation fee is {settings.consultation_fee} rupees. "
            f"A follow-up within 7 days is {settings.followup_fee} rupees. "
            f"We accept {settings.payment_modes}."
        ),
        "doctors": "; ".join(f"{d.name}, {d.specialty}" for d in list_doctors()) + ".",
        "parking": settings.parking.capitalize() + ".",
        "booking": (
            f"Appointments are {settings.slot_minutes} minutes. Walk-ins are seen only if a slot is free, "
            "so booking ahead is better."
        ),
    }


TOPICS = ["hours", "address", "phone", "fees", "doctors", "parking", "booking"]


def facts_text() -> str:
    """All facts as one block, for putting in a prompt."""
    return "\n".join(f"- {topic}: {answer}" for topic, answer in get_clinic_info().items())