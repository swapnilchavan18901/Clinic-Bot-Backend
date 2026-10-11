"""Business errors — framework-free. The API layer maps them to HTTP codes."""


class ClinicError(Exception):
    """Base class for all business-rule failures."""


class NotFound(ClinicError):
    pass


class InvalidSlot(ClinicError):
    pass


class SlotTaken(ClinicError):
    pass


class InvalidState(ClinicError):
    pass


