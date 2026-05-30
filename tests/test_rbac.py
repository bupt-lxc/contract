import pytest

from sc_gr_app.errors import PermissionDenied
from sc_gr_app.rbac import require_admin, require_requester_or_admin


def test_require_admin_allows_admin():
    user = {"role": "admin"}

    require_admin(user)


def test_require_admin_raises_permission_denied_for_requester():
    user = {"role": "requester"}

    with pytest.raises(PermissionDenied, match="Admin permission required"):
        require_admin(user)


def test_require_requester_or_admin_allows_admin_and_requester():
    require_requester_or_admin({"role": "admin"})
    require_requester_or_admin({"role": "requester"})


def test_require_admin_raises_permission_denied_for_malformed_user():
    with pytest.raises(PermissionDenied, match="Admin permission required"):
        require_admin({})


def test_require_requester_or_admin_raises_permission_denied_for_malformed_user():
    with pytest.raises(PermissionDenied, match="Authorized user required"):
        require_requester_or_admin({})

