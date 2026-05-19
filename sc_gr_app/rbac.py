from sc_gr_app.errors import PermissionDenied


def require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise PermissionDenied("Admin permission required")


def require_requester_or_admin(user: dict) -> None:
    if user.get("role") not in {"admin", "requester"}:
        raise PermissionDenied("Authorized user required")


def can_edit_sc(user: dict, requester_id: str) -> bool:
    return user.get("role") == "admin" or user.get("user_id") == requester_id
