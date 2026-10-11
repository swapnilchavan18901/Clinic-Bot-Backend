"""DB layer — data access. Only queries here, no business rules."""

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.tables import Appointment, AppointmentStatus, Doctor


class DoctorRepo:
    def __init__(self, s: Session):
        self.s = s

    def list(self) -> list[Doctor]:
        return list(self.s.scalars(select(Doctor).order_by(Doctor.id)))

    def get(self, doctor_id: int) -> Doctor | None:
        return self.s.get(Doctor, doctor_id)


class AppointmentRepo:
    def __init__(self, s: Session):
        self.s = s

    def get(self, appt_id: int) -> Appointment | None:
        return self.s.get(Appointment, appt_id, options=[joinedload(Appointment.doctor)])

    def booked_times(self, doctor_id: int, day: date) -> set[datetime]:
        q = select(Appointment.start_time).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.booked,
            Appointment.start_time >= datetime.combine(day, time.min),
            Appointment.start_time <= datetime.combine(day, time.max),
        )
        return set(self.s.scalars(q))

    def is_taken(self, doctor_id: int, slot: datetime, exclude_id: int | None = None) -> bool:
        q = select(Appointment.id).where(
            Appointment.doctor_id == doctor_id,
            Appointment.start_time == slot,
            Appointment.status == AppointmentStatus.booked,
        )
        if exclude_id:
            q = q.where(Appointment.id != exclude_id)
        return self.s.scalar(q) is not None

    def upcoming_by_phone(self, phone: str, after: datetime) -> list[Appointment]:
        q = (
            select(Appointment)
            .options(joinedload(Appointment.doctor))
            .where(
                Appointment.patient_phone == phone,
                Appointment.status == AppointmentStatus.booked,
                Appointment.start_time > after,
            )
            .order_by(Appointment.start_time)
        )
        return list(self.s.scalars(q))

    def add(self, appt: Appointment) -> Appointment:
        self.s.add(appt)
        self.s.flush()  # surfaces unique-index violations now
        return appt