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
from sc_gr_app.services.sc_service import approve_sc, create_sc, create_sc_draft
from sc_gr_app.services.vendor_service import create_vendor
from tests.test_sc_po_gr_flow import ADMIN, OTHER_USER, USER, seed_other_user, seed_users


def seed_query_data(app_config):
    """Create standard test data. Returns (sc_id, po_id, gr_id)."""
    migrate(app_config)
    seed_users(app_config)
    created_sc = create_sc(
        app_config,
        USER,
        {
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
    sc_id = created_sc["sc_id"]
    approve_sc(app_config, ADMIN, sc_id)
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
    created_po = create_po(
        app_config,
        ADMIN,
        {
            "sc_id": sc_id,
            "vendor_id": "V1",
            "po_no": "PO-ALPHA",
            "po_amount": 800,
            "status": "po_approved",
        },
    )
    po_id = created_po["po_id"]
    created_gr = create_gr(
        app_config,
        ADMIN,
        {
            "po_id": po_id,
            "requester_id": "U1",
            "estimated_amount": 100,
            "remark": "alpha remark",
        },
    )
    gr_id = created_gr["gr_id"]
    return sc_id, po_id, gr_id


def test_query_service_searches_seeded_sc_vendor_and_po(app_config):
    seed_query_data(app_config)

    assert search_scs(app_config, text="alpha")[0]["sc_no"] == "SC-ALPHA"
    assert search_scs(app_config, text="Alpha Vendor")[0]["sc_no"] == "SC-ALPHA"
    assert search_vendors(app_config, text="KV-1")[0]["vendor_name"] == "Alpha Vendor"
    assert search_pos(app_config, text="PO-ALPHA")[0]["po_no"] == "PO-ALPHA"


def test_search_pos_returns_derived_open_po_amount(app_config):
    seed_query_data(app_config)

    row = search_pos(app_config, text="PO-ALPHA")[0]

    assert row["open_po_amount"] == 700


def test_search_pos_returns_zero_for_fully_consumed_po(app_config):
    sc_id, po_id, gr_id = seed_query_data(app_config)
    approve_gr(app_config, ADMIN, gr_id, con_value=800)

    row = search_pos(app_config, filters={"po_id": po_id})[0]

    assert row["open_po_amount"] == 0


def test_search_pos_can_sort_by_contract_to(app_config):
    seed_query_data(app_config)

    rows = search_pos(app_config, sort="contract_to", direction="asc")

    assert rows[0]["po_no"] == "PO-ALPHA"


def test_invalid_sort_field_raises_validation_error(app_config):
    seed_query_data(app_config)

    with pytest.raises(ValidationError, match="sort field is invalid"):
        search_scs(app_config, sort="created_at; drop table sc_records")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"direction": None}, "sort direction is invalid"),
        ({"direction": "desc; drop table users"}, "sort direction is invalid"),
        ({"filters": {"unknown": "value"}}, "filter field is invalid"),
        ({"limit": 0}, "limit is invalid"),
        ({"offset": -1}, "offset is invalid"),
    ],
)
def test_invalid_query_controls_raise_validation_error(app_config, kwargs, message):
    seed_query_data(app_config)

    with pytest.raises(ValidationError, match=message):
        search_scs(app_config, **kwargs)


def test_filters_and_pagination_work_for_scs(app_config):
    sc_id, po_id, gr_id = seed_query_data(app_config)
    create_sc(
        app_config,
        USER,
        {
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
    sc_id, po_id, gr_id = seed_query_data(app_config)

    rows = search_grs(app_config, text="remark")

    assert rows[0]["gr_id"] == gr_id
    assert rows[0]["po_no"] == "PO-ALPHA"
    assert rows[0]["sc_no"] == "SC-ALPHA"
    assert rows[0]["vendor_name"] == "Alpha Vendor"


def test_search_audit_logs_returns_audit_rows(app_config):
    sc_id, po_id, gr_id = seed_query_data(app_config)
    approve_gr(app_config, ADMIN, gr_id, con_value=90)

    rows = search_audit_logs(
        app_config,
        filters={"object_type": "gr"},
        sort="action_type",
        direction="asc",
    )

    assert [row["action_type"] for row in rows] == ["approve_gr", "create_gr"]


def test_search_audit_logs_searches_text_fields(app_config):
    sc_id, po_id, gr_id = seed_query_data(app_config)
    approve_gr(app_config, ADMIN, gr_id, con_value=90)

    assert search_audit_logs(app_config, text="approve_gr")[0]["action_type"] == "approve_gr"
    assert search_audit_logs(app_config, text=gr_id.lower())[0]["object_id"] == gr_id
    assert search_audit_logs(app_config, text="90")[0]["action_type"] == "approve_gr"


def test_search_audit_logs_scopes_draft_sc_rows_to_owner(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)
    created = create_sc_draft(app_config, USER, {"requester_id": "U1"})
    draft_sc_id = created["sc_id"]

    admin_rows = search_audit_logs(app_config, current_user=ADMIN, limit=100)
    owner_rows = search_audit_logs(app_config, current_user=USER, limit=100)
    other_rows = search_audit_logs(app_config, current_user=OTHER_USER, limit=100)

    assert [row["object_id"] for row in admin_rows] == []
    assert [row["object_id"] for row in owner_rows] == [draft_sc_id]
    assert [row["object_id"] for row in other_rows] == []


@pytest.mark.parametrize(
    ("search_func", "filters"),
    [
        (search_scs, {"created_at; drop table sc_records": "2026-01-01"}),
        (search_vendors, {"unknown": "Alpha Vendor"}),
        (search_pos, {"bad_filter": "PO1"}),
        (search_grs, {"vendor_name": "Alpha Vendor"}),
        (search_audit_logs, {"before_json": "{}"}),
    ],
)
def test_invalid_filter_name_raises_validation_error(app_config, search_func, filters):
    seed_query_data(app_config)

    with pytest.raises(ValidationError, match="filter field is invalid"):
        search_func(app_config, filters=filters)


@pytest.mark.parametrize("direction", ["sideways", "", None, 1])
def test_invalid_sort_direction_raises_validation_error(app_config, direction):
    seed_query_data(app_config)

    with pytest.raises(ValidationError, match="sort direction is invalid"):
        search_scs(app_config, direction=direction)


def test_text_search_keeps_sql_looking_input_bound(app_config):
    seed_query_data(app_config)

    rows = search_scs(app_config, text="alpha%' OR 1=1 --")

    assert rows == []
    assert search_scs(app_config, text="alpha")[0]["sc_no"] == "SC-ALPHA"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("limit", 0, "limit is invalid"),
        ("limit", -1, "limit is invalid"),
        ("limit", 1.9, "limit is invalid"),
        ("limit", True, "limit is invalid"),
        ("limit", "1.9", "limit is invalid"),
        ("limit", "01", "limit is invalid"),
        ("limit", " 1", "limit is invalid"),
        ("offset", -1, "offset is invalid"),
        ("offset", 1.9, "offset is invalid"),
        ("offset", False, "offset is invalid"),
        ("offset", "1.9", "offset is invalid"),
        ("offset", "01", "offset is invalid"),
        ("offset", " 1", "offset is invalid"),
    ],
)
def test_invalid_pagination_values_raise_validation_error(
    app_config,
    field,
    value,
    message,
):
    seed_query_data(app_config)

    kwargs = {field: value}
    with pytest.raises(ValidationError, match=message):
        search_scs(app_config, **kwargs)


def test_pagination_accepts_ints_and_canonical_digit_strings(app_config):
    sc_id, po_id, gr_id = seed_query_data(app_config)

    rows = search_scs(app_config, limit="10", offset="0")

    assert [row["sc_id"] for row in rows] == [sc_id]


def test_limit_is_clamped_to_max_limit(app_config):
    sc_id, po_id, gr_id = seed_query_data(app_config)

    rows = search_scs(app_config, limit=501)

    assert [row["sc_id"] for row in rows] == [sc_id]


def test_sc_search_hides_drafts_from_admin_and_other_requesters(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft
    from sc_gr_app.services import query_service

    created = create_sc_draft(app_config, USER, {"requester_id": "U1"})
    draft_sc_id = created["sc_id"]

    admin_rows = query_service.search_scs(app_config, current_user=ADMIN, limit=100)
    owner_rows = query_service.search_scs(app_config, current_user=USER, limit=100)
    other_rows = query_service.search_scs(
        app_config,
        current_user=OTHER_USER,
        limit=100,
    )

    assert [row["sc_id"] for row in admin_rows] == []
    assert [row["sc_id"] for row in owner_rows] == [draft_sc_id]
    assert [row["sc_id"] for row in other_rows] == []


def test_sc_search_without_current_user_hides_drafts(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft

    create_sc_draft(app_config, USER, {"requester_id": "U1"})

    assert search_scs(app_config, limit=100) == []


def test_po_and_gr_search_scope_requesters_to_their_own_parent_scs(app_config):
    sc_id, po_id, gr_id = seed_query_data(app_config)
    seed_other_user(app_config)
    created_sc2 = create_sc(
        app_config,
        OTHER_USER,
        {
            "sc_no": "SC-BETA",
            "requester_id": "U2",
            "request_type": "service",
            "cost_center": 2002,
            "sc_amount": 500,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    sc2_id = created_sc2["sc_id"]
    approve_sc(app_config, ADMIN, sc2_id)
    created_po2 = create_po(
        app_config,
        ADMIN,
        {
            "sc_id": sc2_id,
            "vendor_id": "V1",
            "po_no": "PO-BETA",
            "po_amount": 300,
            "status": "po_approved",
        },
    )
    po2_id = created_po2["po_id"]
    created_gr2 = create_gr(
        app_config,
        ADMIN,
        {
            "po_id": po2_id,
            "requester_id": "U2",
            "estimated_amount": 50,
            "remark": "beta remark",
        },
    )
    gr2_id = created_gr2["gr_id"]

    admin_pos = search_pos(app_config, current_user=ADMIN, sort="po_id", direction="asc")
    owner_pos = search_pos(app_config, current_user=USER, sort="po_id", direction="asc")
    other_pos = search_pos(
        app_config,
        current_user=OTHER_USER,
        sort="po_id",
        direction="asc",
    )
    admin_grs = search_grs(app_config, current_user=ADMIN, sort="gr_id", direction="asc")
    owner_grs = search_grs(app_config, current_user=USER, sort="gr_id", direction="asc")
    other_grs = search_grs(
        app_config,
        current_user=OTHER_USER,
        sort="gr_id",
        direction="asc",
    )

    assert sorted([row["po_id"] for row in admin_pos]) == sorted([po_id, po2_id])
    assert [row["po_id"] for row in owner_pos] == [po_id]
    assert [row["po_id"] for row in other_pos] == [po2_id]
    assert sorted([row["gr_id"] for row in admin_grs]) == sorted([gr_id, gr2_id])
    assert [row["gr_id"] for row in owner_grs] == [gr_id]
    assert [row["gr_id"] for row in other_grs] == [gr2_id]


@pytest.mark.parametrize("search_func", [search_pos, search_grs])
def test_po_and_gr_search_reject_invalid_current_user(app_config, search_func):
    seed_query_data(app_config)

    with pytest.raises(ValidationError, match="current_user is invalid"):
        search_func(app_config, current_user={"role": "auditor"})
