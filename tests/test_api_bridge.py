import types
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.errors import PermissionDenied, ValidationError


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
            "message": "boom",
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
    current_user = {"user_id": "U1", "role": "requester"}

    def fake_search(name):
        def _search(config, **payload):
            calls.append((name, config, payload))
            return {"rows": [name], "total": 1}

        return _search

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )
    monkeypatch.setattr(bridge.query_service, "search_scs", fake_search("sc"))
    monkeypatch.setattr(bridge.query_service, "search_vendors", fake_search("vendor"))
    monkeypatch.setattr(bridge.query_service, "search_pos", fake_search("po"))
    monkeypatch.setattr(bridge.query_service, "search_grs", fake_search("gr"))
    monkeypatch.setattr(bridge.query_service, "search_operation_records", fake_search("logs"))

    api = bridge.ApiBridge(app_config)

    assert api.search_scs({"text": "alpha"}) == {"ok": True, "data": {"rows": ["sc"], "total": 1}}
    assert api.search_vendors(None) == {"ok": True, "data": {"rows": ["vendor"], "total": 1}}
    assert api.search_pos() == {"ok": True, "data": {"rows": ["po"], "total": 1}}
    assert api.search_grs({"filters": {"status": "pending"}}) == {"ok": True, "data": {"rows": ["gr"], "total": 1}}
    assert api.search_operation_records({"text": "approve"}) == {"ok": True, "data": {"rows": ["logs"], "total": 1}}
    assert calls == [
        ("sc", app_config, {"text": "alpha", "current_user": current_user}),
        ("vendor", app_config, {}),
        ("po", app_config, {"current_user": current_user}),
        ("gr", app_config, {"filters": {"status": "pending"}, "current_user": current_user}),
        ("logs", app_config, {"text": "approve", "current_user": current_user}),
    ]


def test_bridge_rejects_non_mapping_payload(app_config):
    from sc_gr_app.api import bridge

    response = bridge.ApiBridge(app_config).search_scs(["not", "a", "dict"])

    assert response == {
        "ok": False,
        "error": {"code": "VALIDATION_ERROR", "message": "payload must be an object"},
    }


def test_bridge_search_requires_authorized_current_user(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")

    def fake_get_user(config, machine_id):
        raise PermissionDenied("This machine is not authorized")

    def fake_search(config, **payload):
        raise AssertionError("search must not run for unauthorized machine")

    monkeypatch.setattr(bridge, "get_user_by_machine_id", fake_get_user)
    monkeypatch.setattr(bridge.query_service, "search_scs", fake_search)

    assert bridge.ApiBridge(app_config).search_scs({}) == {
        "ok": False,
        "error": {
            "code": "PERMISSION_DENIED",
            "message": "This machine is not authorized",
        },
    }


def test_bridge_sc_detail_and_write_methods_forward_payload_and_current_user(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    calls = []
    current_user = {"user_id": "U1", "role": "requester"}

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )

    def fake_service(name):
        def _service(config, user, *args, **kwargs):
            calls.append((name, config, user, args))
            return {"name": name, "args": args}

        return _service

    monkeypatch.setattr(bridge.sc_service, "get_sc_detail", fake_service("get_sc_detail"))
    monkeypatch.setattr(bridge.sc_service, "create_sc_draft", fake_service("create_sc_draft"))
    monkeypatch.setattr(bridge.sc_service, "submit_sc", fake_service("submit_sc"))
    monkeypatch.setattr(bridge.sc_service, "update_sc", fake_service("update_sc"))
    monkeypatch.setattr(bridge.sc_service, "approve_sc", fake_service("approve_sc"))
    monkeypatch.setattr(bridge.sc_service, "deny_sc", fake_service("deny_sc"))
    monkeypatch.setattr(bridge.sc_service, "finish_sc", fake_service("finish_sc"))

    api = bridge.ApiBridge(app_config)

    assert api.get_sc_detail({"sc_id": "SC1"}) == {
        "ok": True,
        "data": {"name": "get_sc_detail", "args": ("SC1",)},
    }
    assert api.create_sc_draft({"data": {"vendor": "V1"}}) == {
        "ok": True,
        "data": {"name": "create_sc_draft", "args": ({"vendor": "V1"},)},
    }
    assert api.submit_sc({"sc_id": "SC1", "data": {"amount": 10}}) == {
        "ok": True,
        "data": {"name": "submit_sc", "args": ("SC1", {"amount": 10})},
    }
    assert api.update_sc({"sc_id": "SC2", "data": {"amount": 20}}) == {
        "ok": True,
        "data": {"name": "update_sc", "args": ("SC2", {"amount": 20})},
    }
    assert api.approve_sc({"sc_id": "SC3"}) == {
        "ok": True,
        "data": {"name": "approve_sc", "args": ("SC3",)},
    }
    assert api.deny_sc({"sc_id": "SC4"}) == {
        "ok": True,
        "data": {"name": "deny_sc", "args": ("SC4",)},
    }
    assert api.finish_sc({"sc_id": "SC5"}) == {
        "ok": True,
        "data": {"name": "finish_sc", "args": ("SC5",)},
    }
    assert calls == [
        ("get_sc_detail", app_config, current_user, ("SC1",)),
        ("create_sc_draft", app_config, current_user, ({"vendor": "V1"},)),
        ("submit_sc", app_config, current_user, ("SC1", {"amount": 10})),
        ("update_sc", app_config, current_user, ("SC2", {"amount": 20})),
        ("approve_sc", app_config, current_user, ("SC3",)),
        ("deny_sc", app_config, current_user, ("SC4",)),
        ("finish_sc", app_config, current_user, ("SC5",)),
    ]


def test_bridge_po_write_methods_forward_payload_and_current_user(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    calls = []
    current_user = {"user_id": "U2", "role": "buyer"}

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "2345678")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )

    monkeypatch.setattr(bridge.ApiBridge, "_auto_open_outlook_draft", lambda *a, **kw: None)

    def fake_service(name):
        def _service(config, user, *args, **kwargs):
            calls.append((name, config, user, args))
            if name == "create_po":
                return {"po_id": "PO-NEW", **args[0]}
            return [name, *args]

        return _service

    monkeypatch.setattr(bridge.po_service, "create_po", fake_service("create_po"))
    monkeypatch.setattr(bridge.po_service, "update_po", fake_service("update_po"))
    monkeypatch.setattr(bridge.po_service, "finish_po", fake_service("finish_po"))

    api = bridge.ApiBridge(app_config)

    assert api.create_po({"data": {"sc_id": "SC1"}}) == {
        "ok": True,
        "data": {"po_id": "PO-NEW", "sc_id": "SC1"},
    }
    assert api.update_po({"po_id": "PO1", "data": {"price": 3}}) == {
        "ok": True,
        "data": ["update_po", "PO1", {"price": 3}],
    }
    assert api.finish_po({"po_id": "PO3"}) == {
        "ok": True,
        "data": ["finish_po", "PO3"],
    }
    assert calls == [
        ("create_po", app_config, current_user, ({"sc_id": "SC1"},)),
        ("update_po", app_config, current_user, ("PO1", {"price": 3})),
        ("finish_po", app_config, current_user, ("PO3",)),
    ]


def test_bridge_gr_write_methods_forward_payload_and_current_user(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    calls = []
    current_user = {"user_id": "U3", "role": "warehouse"}

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "3456789")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )

    monkeypatch.setattr(bridge.ApiBridge, "_auto_open_outlook_draft", lambda *a, **kw: None)

    def fake_service(name):
        def _service(config, user, *args):
            calls.append((name, config, user, args))
            if name == "create_gr":
                return {"gr_id": "GR-NEW", "method": name, "args": args}
            return {"method": name, "args": args}

        return _service

    monkeypatch.setattr(bridge.gr_service, "create_gr", fake_service("create_gr"))
    monkeypatch.setattr(bridge.gr_service, "update_gr", fake_service("update_gr"))
    monkeypatch.setattr(bridge.gr_service, "approve_gr", fake_service("approve_gr"))
    monkeypatch.setattr(bridge.gr_service, "deny_gr", fake_service("deny_gr"))

    api = bridge.ApiBridge(app_config)

    assert api.create_gr({"data": {"po_id": "PO1"}}) == {
        "ok": True,
        "data": {"gr_id": "GR-NEW", "method": "create_gr", "args": ({"po_id": "PO1"},)},
    }
    assert api.update_gr({"gr_id": "GR1", "data": {"qty": 4}}) == {
        "ok": True,
        "data": {"method": "update_gr", "args": ("GR1", {"qty": 4})},
    }
    assert api.approve_gr({"gr_id": "GR2", "con_value": 99.5}) == {
        "ok": True,
        "data": {"method": "approve_gr", "args": ("GR2", 99.5)},
    }
    assert api.deny_gr({"gr_id": "GR3"}) == {
        "ok": True,
        "data": {"method": "deny_gr", "args": ("GR3",)},
    }
    assert calls == [
        ("create_gr", app_config, current_user, ({"po_id": "PO1"},)),
        ("update_gr", app_config, current_user, ("GR1", {"qty": 4})),
        ("approve_gr", app_config, current_user, ("GR2", 99.5)),
        ("deny_gr", app_config, current_user, ("GR3",)),
    ]


def test_bridge_write_methods_reject_non_mapping_payload(app_config):
    from sc_gr_app.api import bridge

    response = bridge.ApiBridge(app_config).create_sc_draft(["not", "a", "dict"])

    assert response == {
        "ok": False,
        "error": {"code": "VALIDATION_ERROR", "message": "payload must be an object"},
    }


def test_bridge_write_methods_reject_none_payload(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: {"user_id": "U1"},
    )

    response = bridge.ApiBridge(app_config).get_sc_detail(None)

    assert response == {
        "ok": False,
        "error": {"code": "VALIDATION_ERROR", "message": "payload must be an object"},
    }


def test_bridge_write_methods_require_payload_fields(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: {"user_id": "U1"},
    )

    # con_value is now optional — auto-calculated from tax_rate if omitted
    assert bridge.ApiBridge(app_config).approve_gr({"gr_id": "GR1"}) == {
        "ok": False,
        "error": {"code": "PERMISSION_DENIED", "message": "Admin permission required"},
    }


def test_bridge_write_methods_wrap_service_permission_errors(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: {"user_id": "U1"},
    )

def test_run_app_initializes_database_and_starts_pywebview(monkeypatch, tmp_path):
    import sc_gr_app.app_shell as app_shell

    config = AppConfig(
        db_path=tmp_path / "app.sqlite3",
        lock_dir=tmp_path / "locks",
        busy_timeout_ms=1000,
    )
    calls = []

    monkeypatch.setattr(app_shell, "DEV_MODE", False)
    monkeypatch.setattr(app_shell, "default_config", lambda: config)
    monkeypatch.setattr(app_shell, "migrate", lambda actual: calls.append(("migrate", actual)))
    monkeypatch.setattr(
        app_shell,
        "seed_users",
        lambda actual: calls.append(("seed", actual)),
    )

    fake_webview = types.SimpleNamespace()

    fake_window = types.SimpleNamespace(
        events=types.SimpleNamespace(closing=None),
        show=lambda: None,
        restore=lambda: None,
        hide=lambda: None,
        destroy=lambda: None,
    )

    def create_window(*args, **kwargs):
        calls.append(("create_window", args, kwargs))
        return fake_window

    def start(**kwargs):
        calls.append(("start", kwargs))

    fake_webview.create_window = create_window
    fake_webview.start = start
    monkeypatch.setattr(app_shell, "webview", fake_webview)

    # Also patch _setup_tray to skip PIL/pystray calls
    monkeypatch.setattr(app_shell, "_setup_tray", lambda w: None)
    monkeypatch.setattr(app_shell, "_check_update", lambda: None)

    app_shell.run_app()

    expected_url = Path(app_shell.__file__).parent / "web" / "index.html"
    assert calls[0:2] == [("migrate", config), ("seed", config)]
    assert calls[2][0:2] == ("create_window", ("PO Management Platform",))
    window_kwargs = calls[2][2]
    assert window_kwargs["url"] == f"file://{expected_url}"
    assert window_kwargs["js_api"].config is config
    assert window_kwargs["width"] == 1280
    assert window_kwargs["height"] == 820
    assert window_kwargs["min_size"] == (1100, 700)
    assert calls[3] == ("start", {"debug": False})


def test_bridge_annual_report_methods_forward_current_user_and_year(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    current_user = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "1234567"}
    calls = []

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )

    def fake_po_report(config, year, user):
        calls.append(("po", config, year, user))
        return [{"row_type": "po", "po_no": "PO-1"}]

    def fake_gr_report(config, year, user):
        calls.append(("gr", config, year, user))
        return [{"gr_no": "GR-1"}]

    monkeypatch.setattr(bridge.po_service, "get_annual_report_data", fake_po_report)
    monkeypatch.setattr(bridge.gr_service, "get_annual_report_data", fake_gr_report)

    api = bridge.ApiBridge(app_config)

    assert api.get_po_annual_report({"year": "2025"}) == {
        "ok": True,
        "data": {"rows": [{"row_type": "po", "po_no": "PO-1"}]},
    }
    assert api.get_gr_annual_report({"year": "2026"}) == {
        "ok": True,
        "data": {"rows": [{"gr_no": "GR-1"}]},
    }
    assert calls == [
        ("po", app_config, "2025", current_user),
        ("gr", app_config, "2026", current_user),
    ]


def test_bridge_export_methods_forward_text_and_current_user(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    calls = []

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda _config, _machine_id: {"user_id": "U1", "machine_id": "1234567", "user_name": "Alice", "role": "admin"},
    )
    def fake_rows(*args, **kwargs):
        calls.append(("rows", args, kwargs))
        return [{"_type": "SC", "sc_id": "sc-alpha"}]

    def fake_stats(*args, **kwargs):
        calls.append(("stats", args, kwargs))
        return {"overview": {}}

    monkeypatch.setattr(bridge.export_service, "build_cascade_rows", fake_rows)
    monkeypatch.setattr(bridge.export_service, "compute_statistics", fake_stats)

    api = bridge.ApiBridge(app_config)
    api.export_scs_cascade({"text": "alpha", "filters": {"status": "approved"}, "sort": "created_at", "direction": "desc"})

    row_args = calls[0][1]
    row_kwargs = calls[0][2]
    stats_kwargs = calls[1][2]
    # current_user is a positional arg (index 6) in build_cascade_rows
    assert row_kwargs["text"] == "alpha"
    assert row_args[6]["user_id"] == "U1"
    assert stats_kwargs["text"] == "alpha"
    assert "export_rows" in stats_kwargs
