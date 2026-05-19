import types
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.errors import ValidationError


def test_response_schemas_wrap_success_and_app_errors():
    from sc_gr_app.api import schemas

    assert schemas.ok() == {"ok": True, "data": None}
    assert schemas.ok({"value": 1}) == {"ok": True, "data": {"value": 1}}
    assert schemas.fail(ValidationError("bad input")) == {
        "ok": False,
        "error": {"code": "VALIDATION_ERROR", "message": "bad input"},
    }


def test_response_schemas_wrap_unexpected_errors():
    from sc_gr_app.api import schemas

    assert schemas.fail(RuntimeError("boom")) == {
        "ok": False,
        "error": {
            "code": "UNEXPECTED_ERROR",
            "message": "Unexpected application error",
        },
    }


def test_bridge_current_user_uses_machine_id_and_wraps_result(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")

    def fake_get_user(config, machine_id):
        assert config is app_config
        assert machine_id == "1234567"
        return {"user_id": "U1"}

    monkeypatch.setattr(bridge, "get_user_by_machine_id", fake_get_user)

    assert bridge.ApiBridge(app_config).current_user() == {
        "ok": True,
        "data": {"user_id": "U1"},
    }


def test_bridge_current_user_wraps_errors(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")

    def fake_get_user(config, machine_id):
        raise ValidationError("not allowed")

    monkeypatch.setattr(bridge, "get_user_by_machine_id", fake_get_user)

    assert bridge.ApiBridge(app_config).current_user() == {
        "ok": False,
        "error": {"code": "VALIDATION_ERROR", "message": "not allowed"},
    }


def test_bridge_search_methods_forward_payload_or_empty_dict(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    calls = []

    def fake_search(name):
        def _search(config, **payload):
            calls.append((name, config, payload))
            return [name]

        return _search

    monkeypatch.setattr(bridge.query_service, "search_scs", fake_search("sc"))
    monkeypatch.setattr(bridge.query_service, "search_vendors", fake_search("vendor"))
    monkeypatch.setattr(bridge.query_service, "search_pos", fake_search("po"))
    monkeypatch.setattr(bridge.query_service, "search_grs", fake_search("gr"))
    monkeypatch.setattr(bridge.query_service, "search_audit_logs", fake_search("logs"))

    api = bridge.ApiBridge(app_config)

    assert api.search_scs({"text": "alpha"}) == {"ok": True, "data": ["sc"]}
    assert api.search_vendors(None) == {"ok": True, "data": ["vendor"]}
    assert api.search_pos() == {"ok": True, "data": ["po"]}
    assert api.search_grs({"filters": {"status": "pending"}}) == {"ok": True, "data": ["gr"]}
    assert api.search_audit_logs({"text": "approve"}) == {"ok": True, "data": ["logs"]}
    assert calls == [
        ("sc", app_config, {"text": "alpha"}),
        ("vendor", app_config, {}),
        ("po", app_config, {}),
        ("gr", app_config, {"filters": {"status": "pending"}}),
        ("logs", app_config, {"text": "approve"}),
    ]


def test_bridge_rejects_non_mapping_payload(app_config):
    from sc_gr_app.api import bridge

    response = bridge.ApiBridge(app_config).search_scs(["not", "a", "dict"])

    assert response == {
        "ok": False,
        "error": {"code": "VALIDATION_ERROR", "message": "payload must be an object"},
    }


def test_run_app_initializes_database_and_starts_pywebview(monkeypatch, tmp_path):
    import sc_gr_app.app_shell as app_shell

    config = AppConfig(
        db_path=tmp_path / "app.sqlite3",
        lock_dir=tmp_path / "locks",
        busy_timeout_ms=1000,
    )
    calls = []

    monkeypatch.setattr(app_shell, "default_config", lambda: config)
    monkeypatch.setattr(app_shell, "migrate", lambda actual: calls.append(("migrate", actual)))
    monkeypatch.setattr(
        app_shell,
        "seed_default_admin",
        lambda actual: calls.append(("seed", actual)),
    )

    fake_webview = types.SimpleNamespace()

    def create_window(*args, **kwargs):
        calls.append(("create_window", args, kwargs))

    def start(**kwargs):
        calls.append(("start", kwargs))

    fake_webview.create_window = create_window
    fake_webview.start = start
    monkeypatch.setattr(app_shell, "webview", fake_webview)

    app_shell.run_app()

    expected_url = Path(app_shell.__file__).parent / "web" / "index.html"
    assert calls[0:2] == [("migrate", config), ("seed", config)]
    assert calls[2][0:2] == ("create_window", ("SC GR Management",))
    window_kwargs = calls[2][2]
    assert window_kwargs["url"] == str(expected_url)
    assert window_kwargs["js_api"].config is config
    assert window_kwargs["width"] == 1280
    assert window_kwargs["height"] == 820
    assert window_kwargs["min_size"] == (1100, 700)
    assert calls[3] == ("start", {"debug": True})
