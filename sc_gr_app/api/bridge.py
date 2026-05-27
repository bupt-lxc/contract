from sc_gr_app.api.schemas import fail, ok
from sc_gr_app.config import AppConfig
from sc_gr_app.errors import NotFound, PermissionDenied, ValidationError
from sc_gr_app.identity import get_7_digit_id
from sc_gr_app.services import gr_service, po_service, query_service, sc_service, vendor_service
from sc_gr_app.services.user_service import enable_user, get_user_by_machine_id


def _require_payload_field(payload: dict, field: str):
    value = payload.get(field)
    if value is None or value == "":
        raise ValidationError(f"{field} is required")
    return value


class ApiBridge:
    def __init__(self, config: AppConfig):
        self.config = config

    def current_user(self, payload=None) -> dict:
        try:
            machine_id = get_7_digit_id()
            return ok(get_user_by_machine_id(self.config, machine_id))
        except PermissionDenied as exc:
            machine_id = get_7_digit_id()
            return fail(PermissionDenied(f"Machine {machine_id} is not authorized"))
        except Exception as exc:
            return fail(exc)

    def _payload(self, payload) -> dict:
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValidationError("payload must be an object")
        return payload

    def _required_payload(self, payload) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("payload must be an object")
        return payload

    def _require_current_user(self) -> dict:
        machine_id = get_7_digit_id()
        return get_user_by_machine_id(self.config, machine_id)

    def get_sc_detail(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.get_sc_detail(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def create_sc_draft(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(sc_service.create_sc_draft(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def submit_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            return ok(sc_service.submit_sc(self.config, current_user, sc_id, data))
        except Exception as exc:
            return fail(exc)

    def update_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            return ok(sc_service.update_sc(self.config, current_user, sc_id, data))
        except Exception as exc:
            return fail(exc)

    def approve_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.approve_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def deny_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.deny_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def close_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.close_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def create_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(po_service.create_po(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            data = _require_payload_field(payload, "data")
            return ok(po_service.update_po(self.config, current_user, po_id, data))
        except Exception as exc:
            return fail(exc)

    def approve_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            return ok(po_service.approve_po(self.config, current_user, po_id))
        except Exception as exc:
            return fail(exc)

    def finish_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            return ok(po_service.finish_po(self.config, current_user, po_id))
        except Exception as exc:
            return fail(exc)

    def create_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(gr_service.create_gr(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            data = _require_payload_field(payload, "data")
            return ok(gr_service.update_gr(self.config, current_user, gr_id, data))
        except Exception as exc:
            return fail(exc)

    def approve_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            con_value = _require_payload_field(payload, "con_value")
            return ok(gr_service.approve_gr(self.config, current_user, gr_id, con_value))
        except Exception as exc:
            return fail(exc)

    def cancel_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            return ok(gr_service.cancel_gr(self.config, current_user, gr_id))
        except Exception as exc:
            return fail(exc)

    def search_scs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_scs(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_vendors(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            self._require_current_user()
            return ok(query_service.search_vendors(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def create_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(vendor_service.create_vendor(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            vendor_id = _require_payload_field(payload, "vendor_id")
            data = _require_payload_field(payload, "data")
            return ok(vendor_service.update_vendor(self.config, current_user, vendor_id, data))
        except Exception as exc:
            return fail(exc)

    def disable_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            vendor_id = _require_payload_field(payload, "vendor_id")
            return ok(vendor_service.disable_vendor(self.config, current_user, vendor_id))
        except Exception as exc:
            return fail(exc)

    def list_users(self, payload=None) -> dict:
        try:
            self._require_current_user()
            from sc_gr_app.services.user_service import list_active_users
            return ok(list_active_users(self.config))
        except Exception as exc:
            return fail(exc)

    def create_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            from sc_gr_app.services.user_service import create_user
            return ok(create_user(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            data = _require_payload_field(payload, "data")
            from sc_gr_app.services.user_service import update_user
            return ok(update_user(self.config, current_user, machine_id, data))
        except Exception as exc:
            return fail(exc)

    def disable_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            from sc_gr_app.services.user_service import disable_user
            return ok(disable_user(self.config, current_user, machine_id))
        except Exception as exc:
            return fail(exc)

    def enable_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            return ok(enable_user(self.config, current_user, machine_id))
        except Exception as exc:
            return fail(exc)

    def search_pos(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_pos(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_grs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_grs(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_audit_logs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_audit_logs(self.config, **payload))
        except Exception as exc:
            return fail(exc)
