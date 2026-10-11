"""API layer — map business errors to HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.business.errors import ClinicError, InvalidSlot, InvalidState, NotFound, SlotTaken

STATUS = {NotFound: 404, InvalidSlot: 422, SlotTaken: 409, InvalidState: 409}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ClinicError)
    async def _handle(_: Request, exc: ClinicError):
        return JSONResponse(status_code=STATUS.get(type(exc), 400), content={"detail": str(exc)})