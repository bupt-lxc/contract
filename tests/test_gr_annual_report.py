import pytest
from sc_gr_app.services.gr_service import get_annual_report_data
from sc_gr_app.errors import PermissionDenied, ValidationError


def test_get_annual_report_filters_by_year_and_status(app_config, sample_data):
    """Only approved/finished GRs in the given year should be returned."""
    rows = get_annual_report_data(app_config, "2026", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    assert len(rows) == 2
    for r in rows:
        assert r["status"] in ("approved", "finished")
        if r["status"] == "finished":
            assert r["finished_at"].startswith("2026")
        elif r["status"] == "approved":
            assert r["approved_date"].startswith("2026")


def test_get_annual_report_excludes_other_years(app_config, sample_data):
    """GRs from other years should not appear."""
    rows = get_annual_report_data(app_config, "2020", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    assert len(rows) == 0


def test_get_annual_report_excludes_draft_pending(app_config, sample_data):
    """Draft/pending/denied GRs should be excluded regardless of year."""
    rows = get_annual_report_data(app_config, "2026", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    statuses = {r["status"] for r in rows}
    assert "draft" not in statuses
    assert "pending" not in statuses
    assert "denied" not in statuses


def test_get_annual_report_enriches_joins(app_config, sample_data):
    """Returned rows should include joined fields from PO, SC, vendor, users."""
    rows = get_annual_report_data(app_config, "2026", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    assert len(rows) > 0
    r = rows[0]
    assert r["po_no"] == "PO-2026-001"
    assert r["sc_no"] == "SC-2026-001"
    assert r["cost_center"] == 60473000
    assert r["vendor_name"] == "Test Vendor"
    assert r["requester_name"] is not None


def test_get_annual_report_rejects_invalid_year(app_config, sample_data):
    """Non-4-digit year should raise ValidationError."""
    with pytest.raises(ValidationError):
        get_annual_report_data(app_config, "abc", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    with pytest.raises(ValidationError):
        get_annual_report_data(app_config, "202", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})


def test_get_annual_report_requires_admin(app_config, sample_data):
    with pytest.raises(PermissionDenied):
        get_annual_report_data(
            app_config,
            "2026",
            {"role": "requester", "user_id": "u1", "machine_id": "M000001"},
        )


def test_gr_annual_report_ignores_po_manual_amounts(app_config, sample_data):
    import sqlite3

    conn = sqlite3.connect(app_config.db_path)
    conn.execute(
        """
        INSERT INTO po_manual_amounts (
          manual_amount_id, po_id, year, type, amount, created_by, created_at
        ) VALUES ('PMA-GR-GUARD', 'po-001', '2026', 'to_be_gr', 999999, 'u1', '2026-07-09')
        """
    )
    conn.commit()
    conn.close()

    rows = get_annual_report_data(
        app_config,
        "2026",
        {"role": "admin", "user_id": "u1", "machine_id": "M000001"},
    )

    assert {row["gr_no"] for row in rows} == {"GR-001", "GR-002"}
    assert all("selected_year_to_be_gr" not in row for row in rows)
    assert all("previous_year_provision" not in row for row in rows)
