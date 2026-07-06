from sc_gr_app.errors import AppError


def ok(data=None) -> dict:
    return {"ok": True, "data": data}


def fail(exc: Exception) -> dict:
    if isinstance(exc, AppError):
        code = exc.code
        message = exc.message
    else:
        code = "UNEXPECTED_ERROR"
        message = str(exc) or "Unexpected application error"

    result = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if isinstance(exc, AppError) and hasattr(exc, 'conflicts') and exc.conflicts:
        result["conflicts"] = exc.conflicts
    return result
