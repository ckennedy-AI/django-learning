class ApplicationError(Exception):
    """Raised by services and selectors for business rule violations.

    Caught in exactly one place, api/exception_handlers.py, and translated
    into an HTTP response there. Nothing else should build a Response for
    an application error directly.
    """

    def __init__(self, message: str, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.extra = extra or {}
