class AppError(Exception):
    code = "APP_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    code = "VALIDATION_ERROR"


class PermissionDenied(AppError):
    code = "PERMISSION_DENIED"


class NotFound(AppError):
    code = "NOT_FOUND"


class LockError(AppError):
    code = "LOCK_ERROR"


class ConflictError(AppError):
    code = "CONFLICT_ERROR"

    def __init__(self, message: str, conflicts: list = None):
        super().__init__(message)
        self.conflicts = conflicts


class DatabaseError(AppError):
    code = "DATABASE_ERROR"
