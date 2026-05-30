from sc_gr_app.errors import PermissionDenied


def require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise PermissionDenied("Admin permission required")


def require_requester_or_admin(user: dict) -> None:
    if user.get("role") not in {"admin", "requester"}:
        raise PermissionDenied("Authorized user required")


