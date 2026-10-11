"""Entry point — the clinic REST API.

    uvicorn main:app --reload --port 8000      → http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import router
from app.core.settings import settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=f"{settings.clinic_name} API", lifespan=lifespan)
register_error_handlers(app)
app.include_router(router)