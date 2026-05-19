from sc_gr_app.api.schemas import fail, ok
from sc_gr_app.config import AppConfig
from sc_gr_app.errors import ValidationError
from sc_gr_app.identity import get_7_digit_id
from sc_gr_app.services import query_service
from sc_gr_app.services.user_service import get_user_by_machine_id


class ApiBridge:
    def __init__(self, config: AppConfig):
        self.config = config

    def current_user(self) -> dict:
        try:
            machine_id = get_7_digit_id()
            return ok(get_user_by_machine_id(self.config, machine_id))
        except Exception as exc:
            return fail(exc)

    def _payload(self, payload) -> dict:
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValidationError("payload must be an object")
        return payload

    def search_scs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            return ok(query_service.search_scs(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_vendors(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            return ok(query_service.search_vendors(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_pos(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            return ok(query_service.search_pos(self.config, **payload))
        except Exception as exc:
            return fail(exc)
