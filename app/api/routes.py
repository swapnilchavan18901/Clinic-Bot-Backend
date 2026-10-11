"""API layer — thin HTTP routes over the business layer."""

from datetime import date

from fastapi import APIRouter, Query

from app.business import appointments as svc
from app.business.clinic_info import get_clinic_info
from app.schemas.clinic import AppointmentOut, AvailabilityOut, BookIn, DoctorOut, RescheduleIn

router = APIRouter()


@router.get("/clinic-info")
def clinic_info():
    return get_clinic_info()


@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors():
    return svc.list_doctors()


@router.get("/availability", response_model=AvailabilityOut)
def get_availability(day: date = Query(..., alias="date"), doctor_id: int | None = None):
    return svc.get_availability(day, doctor_id)


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
def book(body: BookIn):
    return svc.book(body)


@router.get("/appointments", response_model=list[AppointmentOut])
def find_appointments(phone: str):
    return svc.find_upcoming(phone)


@router.get("/appointments/{appt_id}", response_model=AppointmentOut)
def read_appointment(appt_id: int):
    return svc.get_appointment(appt_id)


@router.post("/appointments/{appt_id}/reschedule", response_model=AppointmentOut)
def reschedule(appt_id: int, body: RescheduleIn):
    return svc.reschedule(appt_id, body)


@router.post("/appointments/{appt_id}/cancel", response_model=AppointmentOut)
def cancel(appt_id: int):
    return svc.cancel(appt_id)