"""Business layer — appointment use cases.

get_availability, book, find_upcoming, reschedule, cancel.
Used by both the API layer and the AI layer; knows nothing about HTTP or LLMs.
"""

from datetime import date

from sqlalchemy.exc import IntegrityError

from app.business.errors import InvalidState, NotFound, SlotTaken
from app.business.scheduling import day_slots, fmt, now_local, validate_slot
from app.db.database import session_scope
from app.db.repositories import AppointmentRepo, DoctorRepo
from app.db.tables import Appointment, AppointmentStatus
from app.schemas.clinic import (
    AppointmentOut,
    AvailabilityOut,
    BookIn,
    DoctorAvailability,
    DoctorOut,
    RescheduleIn,
)


def _out(a: Appointment) -> AppointmentOut:
    return AppointmentOut.model_validate(
        {**{c: getattr(a, c) for c in AppointmentOut.model_fields if hasattr(a, c)},
         "doctor_name": a.doctor.name, "specialty": a.doctor.specialty}
    )


def _doctor_or_404(repo: DoctorRepo, doctor_id: int):
    doc = repo.get(doctor_id)
    if not doc:
        raise NotFound(f"Doctor {doctor_id} not found.")
    return doc


def _appt_or_404(repo: AppointmentRepo, appt_id: int) -> Appointment:
    appt = repo.get(appt_id)
    if not appt:
        raise NotFound(f"Appointment {appt_id} not found.")
    return appt


def list_doctors() -> list[DoctorOut]:
    with session_scope() as s:
        return [DoctorOut.model_validate(d) for d in DoctorRepo(s).list()]


def get_availability(day: date, doctor_id: int | None = None) -> AvailabilityOut:
    with session_scope() as s:
        doctors_repo, appts = DoctorRepo(s), AppointmentRepo(s)
        doctors = [_doctor_or_404(doctors_repo, doctor_id)] if doctor_id else doctors_repo.list()
        now, slots = now_local(), day_slots(day)
        result = []
        for d in doctors:
            booked = appts.booked_times(d.id, day)
            free = [fmt(t) for t in slots if t > now and t not in booked]
            result.append(DoctorAvailability(doctor_id=d.id, doctor_name=d.name, specialty=d.specialty, slots=free))
        return AvailabilityOut(date=day, closed=not slots, doctors=result)


def book(data: BookIn) -> AppointmentOut:
    slot = validate_slot(data.start_time)
    try:
        with session_scope() as s:
            doctors, appts = DoctorRepo(s), AppointmentRepo(s)
            _doctor_or_404(doctors, data.doctor_id)
            if appts.is_taken(data.doctor_id, slot):
                raise SlotTaken("That slot is already booked.")
            ts = now_local()
            appt = appts.add(
                Appointment(
                    doctor_id=data.doctor_id,
                    patient_name=data.patient_name.strip(),
                    patient_phone=data.patient_phone.strip(),
                    start_time=slot,
                    reason=data.reason,
                    status=AppointmentStatus.booked,
                    created_at=ts,
                    updated_at=ts,
                )
            )
            s.refresh(appt, ["doctor"])
            return _out(appt)
    except IntegrityError:  # lost a race on the unique index
        raise SlotTaken("That slot is already booked.")


def find_upcoming(phone: str) -> list[AppointmentOut]:
    with session_scope() as s:
        return [_out(a) for a in AppointmentRepo(s).upcoming_by_phone(phone.strip(), now_local())]


def get_appointment(appt_id: int) -> AppointmentOut:
    with session_scope() as s:
        return _out(_appt_or_404(AppointmentRepo(s), appt_id))


def reschedule(appt_id: int, data: RescheduleIn) -> AppointmentOut:
    slot = validate_slot(data.new_start_time)
    try:
        with session_scope() as s:
            doctors, appts = DoctorRepo(s), AppointmentRepo(s)
            appt = _appt_or_404(appts, appt_id)
            if appt.status != AppointmentStatus.booked:
                raise InvalidState(f"Appointment is {appt.status.value}; can't reschedule.")
            doctor_id = data.doctor_id or appt.doctor_id
            _doctor_or_404(doctors, doctor_id)
            if appts.is_taken(doctor_id, slot, exclude_id=appt_id):
                raise SlotTaken("That slot is already booked.")
            appt.start_time, appt.doctor_id, appt.updated_at = slot, doctor_id, now_local()
            s.flush()
            s.refresh(appt, ["doctor"])
            return _out(appt)
    except IntegrityError:
        raise SlotTaken("That slot is already booked.")


def cancel(appt_id: int) -> AppointmentOut:
    with session_scope() as s:
        appt = _appt_or_404(AppointmentRepo(s), appt_id)
        if appt.status == AppointmentStatus.cancelled:
            raise InvalidState("Appointment is already cancelled.")
        appt.status, appt.updated_at = AppointmentStatus.cancelled, now_local()
        return _out(appt)