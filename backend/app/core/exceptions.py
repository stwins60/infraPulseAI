from fastapi import HTTPException, status


class InfraPulseException(HTTPException):
    pass


class NotFoundError(InfraPulseException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


class ForbiddenError(InfraPulseException):
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class UnauthorizedError(InfraPulseException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ConflictError(InfraPulseException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class ValidationError(InfraPulseException):
    def __init__(self, detail: str = "Validation failed"):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


class AccountLockedError(InfraPulseException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked due to too many failed login attempts",
        )


class PlanLimitError(InfraPulseException):
    def __init__(self, detail: str = "Plan limit exceeded"):
        super().__init__(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)
