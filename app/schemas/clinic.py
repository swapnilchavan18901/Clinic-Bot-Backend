"""Schemas — request/response models shared by the API and AI layers."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.tables import AppointmentStatus


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    specialty: str


class DoctorAvailability(BaseModel):
    doctor_id: int
    doctor_name: str
    specialty: str
    slots: list[str]  # "YYYY-MM-DDTHH:MM"


class AvailabilityOut(BaseModel):
    date: date
    closed: bool
    doctors: list[DoctorAvailability]


class BookIn(BaseModel):
    doctor_id: int
    patient_name: str = Field(min_length=1)
    patient_phone: str = Field(min_length=6)
    start_time: datetime = Field(description="Clinic local time, YYYY-MM-DDTHH:MM")
    reason: str | None = None


class RescheduleIn(BaseModel):
    new_start_time: datetime
    doctor_id: int | None = Field(None, description="Optionally switch doctor")


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doctor_id: int
    doctor_name: str
    specialty: str
    patient_name: str
    patient_phone: str
    start_time: datetime
    reason: str | None
    status: AppointmentStatus
    created_at: datetime
    updated_at: datetime