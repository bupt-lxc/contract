import pytest

from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.gr_service import approve_gr, create_gr
from sc_gr_app.services.po_service import create_po
from sc_gr_app.services.query_service import (
    search_audit_logs,
    search_grs,
    search_pos,
    search_scs,
    search_vendors,
)
from sc_gr_app.services.sc_service import approve_sc, create_sc
from sc_gr_app.services.vendor_service import create_vendor
from tests.test_sc_po_gr_flow import ADMIN, USER, seed_users


def seed_query_data(app_config):
    migrate(app_config)
    seed_users(app_config)
    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": "SC-ALPHA",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "description": "alpha service",
        },
    )
    approve_sc(app_config, ADMIN, "SC1")
    create_vendor(
        app_config,
        USER,
        {
            "vendor_id": "V1",
            "vendor_name": "Alpha Vendor",
            "ksrm_vendor_code": "KV-1",
            "service_scope": "General Service",
        },
    )
    create_po(
        app_config,
        USER,
        {
            "po_id": "PO1",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_no": "PO-ALPHA",
            "po_amount": 800,
            "status": "po_approved",
        },
    )
    create_gr(
        app_config,
        USER,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
            "estimated_amount": 100,
            "remark": "alpha remark",
        },
    )


def test_query_service_searches_seeded_sc_vendor_and_po(app_config):
    seed_query_data(app_config)

    assert search_scs(app_config, text="alpha")[0]["sc_no"] == "SC-ALPHA"
    assert search_vendors(app_config, text="KV-1")[0]["vendor_name"] == "Alpha Vendor"
    assert search_pos(app_config, text="PO-ALPHA")[0]["po_no"] == "PO-ALPHA"


def test_invalid_sort_field_raises_validation_error(app_config):
    seed_query_data(app_config)

    with pytest.raises(ValidationError, match="sort field is invalid"):
        search_scs(app_config, sort="created_at; drop table sc_records")


def test_filters_and_pagination_work_for_scs(app_config):
    seed_query_data(app_config)
    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC2",
            "sc_no": "SC-BETA",
            "requester_id": "U1",
            "request_type": "material",
            "cost_center": 2002,
            "sc_amount": 500,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    rows = search_scs(
        app_config,
        filters={"requester_id": "U1"},
        sort="sc_no",
        direction="asc",
        limit=1,
        offset=1,
    )

    assert [row["sc_no"] for row in rows] == ["SC-BETA"]


def test_search_grs_finds_by_remark(app_config):
    seed_query_data(app_config)

    rows = search_grs(app_config, text="remark")

    assert rows[0]["gr_id"] == "GR1"
    assert rows[0]["po_no"] == "PO-ALPHA"
    assert rows[0]["sc_no"] == "SC-ALPHA"
    assert rows[0]["vendor_name"] == "Alpha Vendor"


def test_search_audit_logs_returns_audit_rows(app_config):
    seed_query_data(app_config)
    approve_gr(app_config, ADMIN, "GR1", con_value=90)

    rows = search_audit_logs(
        app_config,
        filters={"object_type": "gr"},
        sort="action_type",
        direction="asc",
    )

    assert [row["action_type"] for row in rows] == ["approve_gr", "create_gr"]
