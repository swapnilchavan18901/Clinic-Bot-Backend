"""App settings — everything configurable lives here, loaded from env / .env."""

from datetime import time
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- database ---
    database_url: str = "sqlite:///./clinic.db"
    db_echo: bool = False

    # --- clinic rules ---
    clinic_name: str = "Sunrise Clinic"
    clinic_address: str = "2nd floor, Shivaji Chowk, Main Road, Roha, Raigad 402109"
    clinic_landmark: str = "opposite the State Bank, next to the bus stand"
    clinic_phone: str = "02194 123456"
    consultation_fee: int = 500  # rupees, first visit
    followup_fee: int = 300  # rupees, within 7 days
    payment_modes: str = "cash, UPI and cards"
    parking: str = "free two-wheeler parking; cars on the main road"
    timezone: str = "Asia/Kolkata"
    open_time: time = time(9, 0)
    close_time: time = time(17, 0)
    lunch_start: time = time(13, 0)
    lunch_end: time = time(14, 0)
    slot_minutes: int = 30
    working_days: list[int] = [0, 1, 2, 3, 4, 5]  # Mon=0 … Sat=5

    # --- AI services (Sarvam only) ---
    sarvam_api_key: str = ""
    sarvam_llm_model: str = "sarvam-105b-conversations"
    sarvam_reasoning_effort: str = ""  # conversations model doesn't take this
    sarvam_stt_model: str = "saaras:v4"  # auto-detects the caller's language
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_voice: str = "priya"
    language: str = "en-IN"  # bot's spoken language: en-IN, hi-IN, mr-IN, …

    # --- voice UX ---
    filler_delay_ms: int = 700  # speak "one moment…" if a tool call takes longer than this
    debug_tool_delay_ms: int = 0  # set e.g. 1500 to fake a slow DB and hear the filler

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()