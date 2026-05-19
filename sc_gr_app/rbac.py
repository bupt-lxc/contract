from sc_gr_app.errors import PermissionDenied


def require_admin(user) -> None:
    if user["role"] != "admin":
        raise PermissionDenied("Admin permission required")


def require_requester_or_admin(user) -> None:
    if user["role"] not in {"admin", "requester"}:
        raise PermissionDenied("Authorized user required")


def can_edit_sc(user, requester_id: str) -> bool:
    return user["role"] == "admin" or user["user_id"] == requester_id
