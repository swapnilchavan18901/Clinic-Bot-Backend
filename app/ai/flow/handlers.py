"""AI layer — what happens when the LLM calls a function in the flow.

Every handler:
  1. saves what it learned in flow_manager.state
  2. calls the business layer if needed
  3. returns (result_for_llm, next_node)   — next_node=None means "stay on this node"
"""

import asyncio
import re
import time
from datetime import date, datetime

from loguru import logger
from pipecat.flows import FlowArgs, FlowManager
from pipecat.frames.frames import TTSSpeakFrame

from app.ai.flow import nodes
from app.business import appointments as svc
from app.business.clinic_info import TOPICS, get_clinic_info
from app.business.errors import ClinicError
from app.business.scheduling import fmt
from app.core.settings import settings
from app.schemas.clinic import BookIn, RescheduleIn


# Spoken while a slow business call runs, so the caller doesn't hear silence.
FILLERS = {
    "en-IN": "One moment, let me check that for you.",
    "hi-IN": "एक पल, मैं देख रही हूँ।",
    "mr-IN": "एक क्षण, मी तपासून सांगते.",
}


def _filler_text() -> str:
    return FILLERS.get(settings.language, FILLERS["en-IN"])


def _run_sync(fn, *args):
    if settings.debug_tool_delay_ms:  # pretend the DB is slow, to hear the filler
        time.sleep(settings.debug_tool_delay_ms / 1000)
    return fn(*args)


async def _call(fm: FlowManager, fn, *args):
    """Run a sync business function off the event loop. Returns (data, error).

    If it takes longer than settings.filler_delay_ms, the bot says a short filler line
    while it keeps waiting. The filler is not added to the LLM context.
    """
    task = asyncio.create_task(asyncio.to_thread(_run_sync, fn, *args))
    done, _ = await asyncio.wait({task}, timeout=settings.filler_delay_ms / 1000)
    if not done:
        logger.debug(f"{fn.__name__} slower than {settings.filler_delay_ms} ms, speaking filler")
        await fm.worker.queue_frame(TTSSpeakFrame(text=_filler_text(), append_to_context=False))
    try:
        return await task, None
    except ClinicError as e:
        return None, str(e)
    except (ValueError, TypeError) as e:
        return None, f"Invalid input: {e}"
    except Exception:
        logger.exception("Business call failed")
        return None, "The booking system had a problem. Please try again."


def _summary(a) -> dict:
    return {
        "appointment_id": a.id,
        "doctor": a.doctor_name,
        "time": fmt(a.start_time),
        "reason": a.reason,
    }


# ---------- greet_identify ----------

async def save_caller(args: FlowArgs, fm: FlowManager):
    phone = re.sub(r"\D", "", args["phone"])[-10:]
    if len(phone) < 10:
        return {"ok": False, "error": "Phone number should have 10 digits. Ask again."}, None
    fm.state["name"] = args["name"].strip()
    fm.state["phone"] = phone

    upcoming, err = await _call(fm, svc.find_upcoming, phone)
    fm.state["upcoming"] = [_summary(a) for a in upcoming or []]
    return {"ok": True, "upcoming_appointments": fm.state["upcoming"], "lookup_error": err}, nodes.intent()


# ---------- intent ----------

async def choose_book(args: FlowArgs, fm: FlowManager):
    fm.state["mode"] = "book"
    return {"ok": True}, nodes.collect_slot(fm.state)


async def choose_reschedule(args: FlowArgs, fm: FlowManager):
    if not fm.state.get("upcoming"):
        return {"ok": False, "error": "This phone number has no upcoming appointments."}, None
    fm.state["mode"] = "reschedule"
    return {"ok": True}, nodes.pick_appointment(fm.state)


async def choose_cancel(args: FlowArgs, fm: FlowManager):
    if not fm.state.get("upcoming"):
        return {"ok": False, "error": "This phone number has no upcoming appointments."}, None
    fm.state["mode"] = "cancel"
    return {"ok": True}, nodes.pick_appointment(fm.state)


async def ask_question(args: FlowArgs, fm: FlowManager):
    return {"ok": True}, nodes.faq()


# ---------- faq ----------
# The faq node has the facts in its prompt, so the LLM answers on its own.
# Handlers are only needed to leave the node (choose_book/… are reused) or
# to note a question we couldn't answer.

async def unanswered_question(args: FlowArgs, fm: FlowManager):
    question = args.get("question", "")
    logger.info(f"FAQ gap: {question}")  # read these logs to see what facts to add
    fm.state.setdefault("unanswered", []).append(question)
    return {"ok": True, "answer": None, "front_desk_phone": settings.clinic_phone}, None  # stay in faq


# ---------- global: quick fact lookup from any node ----------

async def clinic_info(args: FlowArgs, fm: FlowManager):
    topic = args.get("topic", "")
    answer = get_clinic_info().get(topic)
    if not answer:
        return {"ok": False, "error": f"Unknown topic. Known topics: {', '.join(TOPICS)}"}, None
    return {"ok": True, "answer": answer}, None  # None = stay on the current node and carry on


# ---------- pick_appointment ----------

async def select_appointment(args: FlowArgs, fm: FlowManager):
    appt_id = int(args["appointment_id"])
    match = next((a for a in fm.state.get("upcoming", []) if a["appointment_id"] == appt_id), None)
    if not match:
        return {"ok": False, "error": "That appointment isn't one of this caller's bookings."}, None
    fm.state["appointment"] = match
    if fm.state["mode"] == "cancel":
        return {"ok": True}, nodes.confirm_cancel(fm.state)
    return {"ok": True}, nodes.collect_slot(fm.state)


# ---------- collect_slot ----------

async def check_availability(args: FlowArgs, fm: FlowManager):
    try:
        day = date.fromisoformat(args["date"])
    except ValueError:
        return {"ok": False, "error": "Date must be YYYY-MM-DD."}, None
    data, err = await _call(fm, svc.get_availability, day, args.get("doctor_id"))
    if err:
        return {"ok": False, "error": err}, None
    return {"ok": True, "data": data.model_dump(mode="json")}, None  # stay here, caller picks


async def select_slot(args: FlowArgs, fm: FlowManager):
    doctor_id = int(args["doctor_id"])
    try:
        start = datetime.fromisoformat(args["start_time"])
    except ValueError:
        return {"ok": False, "error": "start_time must be YYYY-MM-DDTHH:MM."}, None

    # make sure it's still free before reading it back to the caller
    avail, err = await _call(fm, svc.get_availability, start.date(), doctor_id)
    if err:
        return {"ok": False, "error": err}, None
    if fmt(start) not in avail.doctors[0].slots:
        return {"ok": False, "error": "That slot is not available.", "free_slots": avail.doctors[0].slots}, None

    fm.state["slot"] = {
        "doctor_id": doctor_id,
        "doctor": avail.doctors[0].doctor_name,
        "start_time": fmt(start),
        "reason": args.get("reason"),
    }
    if fm.state["mode"] == "reschedule":
        return {"ok": True}, nodes.confirm_reschedule(fm.state)
    return {"ok": True}, nodes.confirm_booking(fm.state)


# ---------- confirm_* ----------

async def confirm_booking(args: FlowArgs, fm: FlowManager):
    s = fm.state
    appt, err = await _call(
        fm,
        svc.book,
        BookIn(
            doctor_id=s["slot"]["doctor_id"],
            patient_name=s["name"],
            patient_phone=s["phone"],
            start_time=s["slot"]["start_time"],
            reason=s["slot"]["reason"],
        ),
    )
    if err:  # e.g. someone took the slot a second ago
        return {"ok": False, "error": err}, nodes.collect_slot(s)
    s["outcome"] = f"Booked with {appt.doctor_name} at {fmt(appt.start_time)} (appointment {appt.id})."
    return {"ok": True, "appointment": _summary(appt)}, nodes.close(s)


async def confirm_reschedule(args: FlowArgs, fm: FlowManager):
    s = fm.state
    appt, err = await _call(
        fm,
        svc.reschedule,
        s["appointment"]["appointment_id"],
        RescheduleIn(new_start_time=s["slot"]["start_time"], doctor_id=s["slot"]["doctor_id"]),
    )
    if err:
        return {"ok": False, "error": err}, nodes.collect_slot(s)
    s["outcome"] = f"Moved appointment {appt.id} to {fmt(appt.start_time)} with {appt.doctor_name}."
    return {"ok": True, "appointment": _summary(appt)}, nodes.close(s)


async def confirm_cancel(args: FlowArgs, fm: FlowManager):
    s = fm.state
    appt, err = await _call(fm, svc.cancel, s["appointment"]["appointment_id"])
    if err:
        return {"ok": False, "error": err}, nodes.intent()
    s["outcome"] = f"Cancelled appointment {appt.id} with {appt.doctor_name} at {fmt(appt.start_time)}."
    s["upcoming"] = [a for a in s["upcoming"] if a["appointment_id"] != appt.id]
    return {"ok": True}, nodes.close(s)


async def change_slot(args: FlowArgs, fm: FlowManager):
    return {"ok": True}, nodes.collect_slot(fm.state)


async def keep_appointment(args: FlowArgs, fm: FlowManager):
    fm.state["outcome"] = "Caller decided to keep the appointment."
    return {"ok": True}, nodes.close(fm.state)


# ---------- close ----------

async def another_request(args: FlowArgs, fm: FlowManager):
    for key in ("mode", "slot", "appointment", "outcome"):
        fm.state.pop(key, None)
    upcoming, _ = await _call(fm, svc.find_upcoming, fm.state["phone"])
    fm.state["upcoming"] = [_summary(a) for a in upcoming or []]
    return {"ok": True, "upcoming_appointments": fm.state["upcoming"]}, nodes.intent()


async def end_call(args: FlowArgs, fm: FlowManager):
    return {"ok": True}, nodes.goodbye()


# ---------- global ----------

async def emergency(args: FlowArgs, fm: FlowManager):
    logger.warning(f"Emergency reported: {args.get('description')}")
    return {"ok": True}, nodes.emergency()


async def transfer_to_human(args: FlowArgs, fm: FlowManager):
    """Hand the caller to staff with a summary, then end the bot's part of the call."""
    s = fm.state
    handoff = {
        "reason": args.get("reason", ""),
        "caller": s.get("name"),
        "phone": s.get("phone"),
        "was_doing": s.get("mode"),
        "at_step": fm.current_node,
        "slot_in_progress": s.get("slot"),
        "unanswered_questions": s.get("unanswered", []),
    }
    s["handoff"] = handoff
    # In a phone deployment this is where you'd dial the front desk (e.g. a Twilio/Daily
    # SIP transfer) and pass `handoff` along. For the web demo we log it for staff.
    logger.warning(f"HANDOFF TO STAFF: {handoff}")
    return {"ok": True}, nodes.transfer(s)