from sc_gr_app.errors import AppError


def ok(data=None) -> dict:
    return {"ok": True, "data": data}


def fail(exc: Exception) -> dict:
    if isinstance(exc, AppError):
        code = exc.code
        message = exc.message
    else:
        code = "UNEXPECTED_ERROR"
        message = "Unexpected application error"

    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
