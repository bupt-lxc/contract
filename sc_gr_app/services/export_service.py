# sc_gr_app/services/export_service.py
import sqlite3
from collections import defaultdict

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.services import query_service


def build_cascade_rows(
    config: AppConfig,
    entity_type: str,
    filters: dict,
    sort: str,
    direction: str,
    cascade_options: dict,
    current_user: dict,
    selected_ids: list[str] | None = None,
    text: str | None = None,
) -> list[dict]:
    """Return a flat ordered list of dicts with _type marker for cascade export."""
    rows: list[dict] = []

    if entity_type == "sc":
        rows = _build_sc_cascade(config, filters, sort, direction, cascade_options, current_user, selected_ids, text=text)
    elif entity_type == "po":
        rows = _build_po_cascade(config, filters, sort, direction, cascade_options, current_user, selected_ids, text=text)
    elif entity_type == "gr":
        rows = _build_gr_rows(config, filters, sort, direction, current_user, selected_ids, text=text)

    return rows


def _build_sc_cascade(config, filters, sort, direction, cascade_options, current_user, selected_ids, text=None):
    rows = []
    include_po = cascade_options.get("po", False)
    include_gr = cascade_options.get("gr", False)

    # Get all matching SCs (paginate internally)
    all_scs = _fetch_all_search("sc", config, filters, sort, direction, current_user, selected_ids, text=text)

    with connect(config) as conn:
        for sc in all_scs:
            sc["_type"] = "SC"
            # Resolve requester name
            requester = conn.execute(
                "SELECT user_name FROM users WHERE user_id = ?", (sc["requester_id"],)
            ).fetchone()
            sc["requester_name"] = requester["user_name"] if requester else ""
            rows.append(sc)

            if not include_po:
                continue

            pos = conn.execute(
                "SELECT po.*, v.vendor_name, v.ksrm_vendor_code FROM pos po LEFT JOIN vendors v ON v.vendor_id = po.vendor_id WHERE po.sc_id = ? ORDER BY po.po_no",
                (sc["sc_id"],),
            ).fetchall()
            pos = [dict(po) for po in pos]

            for po in pos:
                po["_type"] = "PO"
                po["sc_no"] = sc.get("sc_no")  # carry parent context
                po["requester_name"] = _resolve_requester_name(conn, po.get("requester_id"))
                rows.append(po)

                if not include_gr:
                    continue

                grs = conn.execute(
                    "SELECT * FROM gr_requests WHERE po_id = ? ORDER BY gr_no",
                    (po["po_id"],),
                ).fetchall()
                for gr in grs:
                    gr = dict(gr)
                    gr["_type"] = "GR"
                    gr["sc_id"] = sc["sc_id"]
                    gr["sc_no"] = sc.get("sc_no")
                    gr["po_no"] = po.get("po_no")
                    gr["requester_name"] = _resolve_requester_name(conn, gr.get("requester_id"))
                    rows.append(gr)

    return rows


def _build_po_cascade(config, filters, sort, direction, cascade_options, current_user, selected_ids, text=None):
    rows = []
    include_gr = cascade_options.get("gr", False)

    all_pos = _fetch_all_search("po", config, filters, sort, direction, current_user, selected_ids, text=text)

    with connect(config) as conn:
        for po in all_pos:
            po["_type"] = "PO"
            sc = None
            if po.get("sc_id"):
                sc = conn.execute(
                    "SELECT sc_no, request_type FROM sc_records WHERE sc_id = ?",
                    (po["sc_id"],),
                ).fetchone()
            po["sc_no"] = sc["sc_no"] if sc else ""
            effective_type = po.get("request_type") or (sc["request_type"] if sc else "")
            po["requester_name"] = _resolve_requester_name(conn, po.get("requester_id"))
            vendor = conn.execute("SELECT vendor_name, ksrm_vendor_code FROM vendors WHERE vendor_id = ?", (po["vendor_id"],)).fetchone()
            po["vendor_name"] = vendor["vendor_name"] if vendor else ""
            po["ksrm_vendor_code"] = vendor["ksrm_vendor_code"] if vendor else ""
            rows.append(po)

            if not include_gr:
                continue

            # FC POs have call-off SCs instead of GRs
            if effective_type == "FC":
                calloffs = conn.execute(
                    "SELECT sc.* FROM sc_records sc WHERE sc.calloff_po_id = ? ORDER BY sc.sc_no",
                    (po["po_id"],),
                ).fetchall()
                for co in calloffs:
                    co = dict(co)
                    co["_type"] = "CALL-OFF SC"
                    co["sc_id"] = co.get("sc_id")
                    co["sc_no"] = co.get("sc_no")
                    co["po_no"] = po.get("po_no")
                    co["requester_name"] = _resolve_requester_name(conn, co.get("requester_id"))
                    rows.append(co)
            else:
                grs = conn.execute(
                    "SELECT * FROM gr_requests WHERE po_id = ? ORDER BY gr_no",
                    (po["po_id"],),
                ).fetchall()
                for gr in grs:
                    gr = dict(gr)
                    gr["_type"] = "GR"
                    gr["sc_id"] = po["sc_id"]
                    gr["sc_no"] = po.get("sc_no")
                    gr["po_no"] = po.get("po_no")
                    gr["requester_name"] = _resolve_requester_name(conn, gr.get("requester_id"))
                    rows.append(gr)

    return rows


def _build_gr_rows(config, filters, sort, direction, current_user, selected_ids, text=None):
    rows = []
    all_grs = _fetch_all_search("gr", config, filters, sort, direction, current_user, selected_ids, text=text)
    with connect(config) as conn:
        for gr in all_grs:
            gr["_type"] = "GR"
            po = conn.execute("SELECT po.sc_id, po.po_no FROM pos po WHERE po.po_id = ?", (gr["po_id"],)).fetchone()
            gr["sc_id"] = po["sc_id"] if po else ""
            sc = conn.execute("SELECT sc_no FROM sc_records WHERE sc_id = ?", (gr["sc_id"],)).fetchone() if po else None
            gr["sc_no"] = sc["sc_no"] if sc else ""
            gr["po_no"] = po["po_no"] if po else ""
            gr["requester_name"] = _resolve_requester_name(conn, gr.get("requester_id"))
            rows.append(gr)
    return rows


def _fetch_all_search(entity_type, config, filters, sort, direction, current_user, selected_ids, text=None):
    """Paginate through search API to get all matching rows."""
    if selected_ids:
        if not selected_ids:
            return []
        # Filter by selected IDs using a direct query
        with connect(config) as conn:
            table = {"sc": "sc_records", "po": "pos", "gr": "gr_requests"}[entity_type]
            id_col = {"sc": "sc_id", "po": "po_id", "gr": "gr_id"}[entity_type]
            placeholders = ",".join(["?"] * len(selected_ids))
            query = f"SELECT * FROM {table} WHERE {id_col} IN ({placeholders})"
            rows = conn.execute(query, selected_ids).fetchall()
            result = [dict(r) for r in rows]
            # Apply SC visibility inline (matches CLAUDE.md visibility rules:
            # Admin sees all non-draft SCs. Requester sees only own records.
            # None: sees non-draft only. Drafts invisible except to owning requester.)
            if entity_type == "sc":
                if current_user:
                    role = current_user.get("role")
                    if role == "admin":
                        result = [r for r in result if r.get("status") != "draft"]
                    elif role == "requester":
                        result = [r for r in result if r.get("requester_id") == current_user["user_id"]]
                else:
                    result = [r for r in result if r.get("status") != "draft"]
            return result

    all_rows = []
    limit = 500
    offset = 0
    search_fn = {
        "sc": query_service.search_scs,
        "po": query_service.search_pos,
        "gr": query_service.search_grs,
    }[entity_type]

    while True:
        kwargs = {"config": config, "filters": filters, "sort": sort, "direction": direction, "limit": limit, "offset": offset}
        if text is not None:
            kwargs["text"] = text
        if current_user is not None:
            kwargs["current_user"] = current_user
        result = search_fn(**kwargs)
        batch = result["rows"] if isinstance(result, dict) else result
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    # Apply SC visibility: admin sees non-draft only, matching CLAUDE.md rules.
    # search_scs returns all SCs for admin (no built-in draft filter), so we
    # filter here to ensure drafts are only visible to the owning requester.
    if entity_type == "sc":
        if current_user is None:
            all_rows = [r for r in all_rows if r.get("status") != "draft"]
        elif current_user.get("role") == "admin":
            all_rows = [r for r in all_rows if r.get("status") != "draft"]

    return all_rows


def _resolve_requester_name(conn, requester_id):
    if not requester_id:
        return ""
    u = conn.execute("SELECT user_name FROM users WHERE user_id = ?", (requester_id,)).fetchone()
    return u["user_name"] if u else ""


def _ids_by_entity_from_export_rows(rows):
    ids = {"SC": [], "PO": [], "GR": []}
    for row in rows or []:
        row_type = row.get("_type")
        if row_type == "SC" and row.get("sc_id"):
            ids["SC"].append(row["sc_id"])
        elif row_type == "PO" and row.get("po_id"):
            ids["PO"].append(row["po_id"])
        elif row_type == "GR" and row.get("gr_id"):
            ids["GR"].append(row["gr_id"])
    return ids


def compute_statistics(
    config: AppConfig,
    entity_types: set[str],
    filters: dict,
    selected_ids: list[str] | None = None,
    export_rows: list[dict] | None = None,
    text: str | None = None,
) -> dict:
    """Return statistics dict with keys: overview, financial, budget_health, processing, by_requester.
    budget_health only present when 'SC' in entity_types.

    When export_rows is provided, entity-specific IDs are derived from the rows
    and statistics are scoped to those entities only.
    """
    if export_rows is not None:
        entity_ids = _ids_by_entity_from_export_rows(export_rows)
    elif selected_ids is not None:
        entity_ids = {"SC": selected_ids, "PO": selected_ids, "GR": selected_ids}
    else:
        entity_ids = None

    stats = {}

    with connect(config) as conn:
        overview = {}
        if "SC" in entity_types:
            sc_ids = entity_ids["SC"] if entity_ids else None
            overview["sc"] = _sc_overview(conn, filters, sc_ids)
        if "PO" in entity_types:
            po_ids = entity_ids["PO"] if entity_ids else None
            overview["po"] = _po_overview(conn, filters, po_ids)
        if "GR" in entity_types:
            gr_ids = entity_ids["GR"] if entity_ids else None
            overview["gr"] = _gr_overview(conn, filters, gr_ids)
        stats["overview"] = overview

        stats["financial"] = _financial_summary(conn, entity_types, filters, entity_ids)
        stats["processing"] = _processing_time(conn, entity_types, filters, entity_ids)
        stats["by_requester"] = _by_requester(conn, entity_types, filters, entity_ids)

        if "SC" in entity_types:
            sc_ids_budget = entity_ids["SC"] if entity_ids else None
            stats["budget_health"] = _budget_health(conn, filters, sc_ids_budget)

    return stats


def _sc_overview(conn, filters, selected_ids):
    clause, params = _build_where("sc_records", filters, selected_ids, "sc_id")
    row = conn.execute(f"SELECT count(*) as cnt, coalesce(sum(sc_amount), 0) as total FROM sc_records WHERE status != 'draft'{clause}", params).fetchone()
    statuses = conn.execute(f"SELECT status, count(*) as cnt, coalesce(sum(sc_amount),0) as total FROM sc_records WHERE status != 'draft'{clause} GROUP BY status", params).fetchall()
    return {
        "total_count": row["cnt"],
        "total_amount": row["total"],
        **{f"{s['status']}_count": s["cnt"] for s in statuses},
        **{f"{s['status']}_amount": s["total"] for s in statuses},
    }


def _po_overview(conn, filters, selected_ids):
    clause, params = _build_where("pos", filters, selected_ids, "po_id")
    row = conn.execute(f"SELECT count(*) as cnt, coalesce(sum(po_amount), 0) as total FROM pos WHERE 1=1{clause}", params).fetchone()
    statuses = conn.execute(f"SELECT status, count(*) as cnt, coalesce(sum(po_amount),0) as total FROM pos WHERE 1=1{clause} GROUP BY status", params).fetchall()
    return {
        "total_count": row["cnt"],
        "total_amount": row["total"],
        **{f"{s['status']}_count": s["cnt"] for s in statuses},
        **{f"{s['status']}_amount": s["total"] for s in statuses},
    }


def _gr_overview(conn, filters, selected_ids):
    clause, params = _build_where("gr_requests", filters, selected_ids, "gr_id")
    row = conn.execute(f"SELECT count(*) as cnt, coalesce(sum(estimated_amount), 0) as est_total, coalesce(sum(con_value), 0) as con_total FROM gr_requests WHERE 1=1{clause}", params).fetchone()
    statuses = conn.execute(f"SELECT status, count(*) as cnt, coalesce(sum(estimated_amount),0) as est_total FROM gr_requests WHERE 1=1{clause} GROUP BY status", params).fetchall()
    return {
        "total_count": row["cnt"],
        "total_estimated_amount": row["est_total"],
        "total_con_value": row["con_total"],
        **{f"{s['status']}_count": s["cnt"] for s in statuses},
    }


def _financial_summary(conn, entity_types, filters, entity_ids=None):
    """Monthly financial summary across entity types."""
    parts = []
    params = []

    if "SC" in entity_types:
        sc_ids = entity_ids.get("SC") if entity_ids else None
        clause, p = _build_where("sc_records", filters, sc_ids, "sc_id")
        parts.append(f"SELECT substr(coalesce(submitted_date, created_at), 1, 4) as year, substr(coalesce(submitted_date, created_at), 6, 2) as month, sc_amount as amount, 0 as po_amount, 0 as gr_est, 0 as gr_con, 0 as gr_gross, 'SC' as src FROM sc_records WHERE sc_amount IS NOT NULL {clause}")
        params.extend(p)

    if "PO" in entity_types:
        po_ids = entity_ids.get("PO") if entity_ids else None
        clause, p = _build_where("pos", filters, po_ids, "po_id")
        parts.append(f"SELECT substr(created_at, 1, 4) as year, substr(created_at, 6, 2) as month, 0 as amount, po_amount, 0 as gr_est, 0 as gr_con, 0 as gr_gross, 'PO' as src FROM pos WHERE po_amount IS NOT NULL {clause}")
        params.extend(p)

    if "GR" in entity_types:
        gr_ids = entity_ids.get("GR") if entity_ids else None
        clause, p = _build_where("gr_requests", filters, gr_ids, "gr_id")
        parts.append(f"SELECT substr(created_at, 1, 4) as year, substr(created_at, 6, 2) as month, 0 as amount, 0 as po_amount, estimated_amount, coalesce(con_value, 0), coalesce(gross_cost, estimated_amount), 'GR' as src FROM gr_requests WHERE 1=1{clause}")
        params.extend(p)

    if not parts:
        return []

    union = " UNION ALL ".join(parts)
    rows = conn.execute(f"SELECT year, month, sum(amount) as sc_amount, sum(po_amount) as po_amount, sum(gr_est) as gr_est_amount, sum(gr_con) as gr_con_amount, sum(gr_gross) as gr_gross_amount FROM ({union}) GROUP BY year, month ORDER BY year, month", params).fetchall()
    return [dict(r) for r in rows]


def _budget_health(conn, filters, selected_ids):
    """Per-SC budget health."""
    clause, params = _build_where("sc_records", filters, selected_ids, "sc_id")
    rows = conn.execute(f"""
        SELECT sc.sc_id, sc.sc_no, sc.sc_amount,
          coalesce((SELECT sum(po.po_amount) FROM pos po WHERE po.sc_id = sc.sc_id), 0) as allocated_po,
          sc.sc_amount - coalesce((SELECT sum(po.po_amount) FROM pos po WHERE po.sc_id = sc.sc_id), 0) as po_balance
        FROM sc_records sc
        WHERE sc.sc_amount IS NOT NULL AND sc.status != 'draft' {clause}
        ORDER BY sc.sc_no
    """, params).fetchall()

    result = []
    for r in rows:
        r = dict(r)
        gr_totals = conn.execute("""
            SELECT
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm') then coalesce(gr.gross_cost, gr.estimated_amount) else 0 end), 0) as pending_tax,
              coalesce(sum(case when gr.status IN ('approved', 'finished') then coalesce(gr.con_value, 0) else 0 end), 0) as consumed
            FROM gr_requests gr
            JOIN pos po ON po.po_id = gr.po_id
            WHERE po.sc_id = ?
        """, (r["sc_id"],)).fetchone()
        r["gr_pending_tax"] = gr_totals["pending_tax"] if gr_totals else 0
        r["gr_consumed"] = gr_totals["consumed"] if gr_totals else 0
        remaining = r["sc_amount"] - (r["gr_pending_tax"] or 0) - (r["gr_consumed"] or 0)
        ratio = remaining / r["sc_amount"] if r["sc_amount"] > 0 else 1
        r["health"] = "充足" if ratio > 0.5 else ("注意" if ratio > 0.2 else "紧张")
        result.append(r)
    return result


def _processing_time(conn, entity_types, filters, entity_ids=None):
    """Average days per transition stage for each entity type."""
    result = []
    stages = [
        ("draft→submit", "submitted_date", "created_at"),
        ("submit→confirm", "confirmed_at", "submitted_date"),
        ("confirm→pending", "pending_date", "confirmed_at"),
        ("pending→approved", "approved_date", "pending_date"),
        ("approved→finished", "finished_at", "approved_date"),
    ]

    for entity, table, id_col, has_manager_confirm in [
        ("SC", "sc_records", "sc_id", True),
        ("PO", "pos", "po_id", False),
        ("GR", "gr_requests", "gr_id", True),
    ]:
        if entity not in entity_types:
            continue
        ids = entity_ids.get(entity) if entity_ids else None
        clause, params = _build_where(table, filters, ids, id_col)
        for stage_name, end_col, start_col in stages:
            if not has_manager_confirm and stage_name in ("submit→confirm", "confirm→pending"):
                continue
            try:
                rows = conn.execute(f"""
                    SELECT avg(julianday({end_col}) - julianday({start_col})) as avg_days,
                           min(julianday({end_col}) - julianday({start_col})) as min_days,
                           max(julianday({end_col}) - julianday({start_col})) as max_days
                    FROM {table}
                    WHERE {end_col} IS NOT NULL AND {start_col} IS NOT NULL {clause}
                """, params).fetchone()
            except sqlite3.OperationalError:
                continue  # column does not exist for this entity type
            if rows and rows["avg_days"] is not None:
                result.append({
                    "entity": entity,
                    "stage": stage_name,
                    "avg_days": round(rows["avg_days"], 1),
                    "min_days": round(rows["min_days"], 1) if rows["min_days"] else None,
                    "max_days": round(rows["max_days"], 1) if rows["max_days"] else None,
                })

    return result


def _by_requester(conn, entity_types, filters, entity_ids=None):
    """Per-requester summary."""
    result = defaultdict(lambda: {"requester_name": "", "sc_count": 0, "sc_amount": 0, "po_count": 0, "po_amount": 0, "gr_count": 0, "gr_est": 0, "gr_con": 0})

    if "SC" in entity_types:
        sc_ids = entity_ids.get("SC") if entity_ids else None
        clause, params = _build_where("sc_records", filters, sc_ids, "sc_id")
        rows = conn.execute(f"SELECT requester_id, count(*) as cnt, coalesce(sum(sc_amount),0) as total FROM sc_records WHERE status != 'draft'{clause} GROUP BY requester_id", params).fetchall()
        for r in rows:
            key = r["requester_id"]
            result[key]["sc_count"] = r["cnt"]
            result[key]["sc_amount"] = r["total"]

    if "PO" in entity_types:
        po_ids = entity_ids.get("PO") if entity_ids else None
        clause, params = _build_where("pos", filters, po_ids, "po_id")
        rows = conn.execute(f"SELECT requester_id, count(*) as cnt, coalesce(sum(po_amount),0) as total FROM pos WHERE 1=1{clause} GROUP BY requester_id", params).fetchall()
        for r in rows:
            key = r["requester_id"]
            result[key]["po_count"] = r["cnt"]
            result[key]["po_amount"] = r["total"]

    if "GR" in entity_types:
        gr_ids = entity_ids.get("GR") if entity_ids else None
        clause, params = _build_where("gr_requests", filters, gr_ids, "gr_id")
        rows = conn.execute(f"SELECT requester_id, count(*) as cnt, coalesce(sum(estimated_amount),0) as est, coalesce(sum(con_value),0) as con FROM gr_requests WHERE 1=1{clause} GROUP BY requester_id", params).fetchall()
        for r in rows:
            key = r["requester_id"]
            result[key]["gr_count"] = r["cnt"]
            result[key]["gr_est"] = r["est"]
            result[key]["gr_con"] = r["con"]

    # Resolve names
    for uid in list(result.keys()):
        u = conn.execute("SELECT user_name FROM users WHERE user_id = ?", (uid,)).fetchone()
        result[uid]["requester_name"] = u["user_name"] if u else uid
        result[uid]["user_id"] = uid

    return list(result.values())


def _build_where(table, filters, selected_ids, id_col):
    """Build AND-prefixed filter clauses. Returns (clause_sql, params_list).
    Clause starts with ' AND ' when non-empty. Intended for: WHERE 1=1 {clause}
    """
    clauses = []
    params = []
    if selected_ids:
        placeholders = ",".join(["?"] * len(selected_ids))
        clauses.append(f"{id_col} IN ({placeholders})")
        params.extend(selected_ids)

    elif filters:
        allowed = {
            "sc_records": {"status": "status", "requester_id": "requester_id", "sc_no": "sc_no", "request_type": "request_type", "cost_center": "cost_center", "service_scope": "service_scope"},
            "pos": {"status": "status", "sc_id": "sc_id", "vendor_id": "vendor_id", "po_no": "po_no", "requester_id": "requester_id"},
            "gr_requests": {"status": "status", "po_id": "po_id", "gr_no": "gr_no", "requester_id": "requester_id", "sc_id": "sc_id"},
        }.get(table, {})

        for field, value in filters.items():
            if value is None or value == "":
                continue
            if field.endswith("_from"):
                base = field[:-5]
                col = allowed.get(base)
                if col:
                    clauses.append(f"{col} >= ?")
                    params.append(value)
            elif field.endswith("_to"):
                base = field[:-3]
                col = allowed.get(base)
                if col:
                    clauses.append(f"{col} <= ?")
                    params.append(value)
            elif field.endswith("_min"):
                base = field[:-4]
                col = allowed.get(base)
                if col:
                    clauses.append(f"{col} >= ?")
                    params.append(value)
            elif field.endswith("_max"):
                base = field[:-4]
                col = allowed.get(base)
                if col:
                    clauses.append(f"{col} <= ?")
                    params.append(value)
            else:
                col = allowed.get(field)
                if col:
                    clauses.append(f"{col} = ?")
                    params.append(value)

    if not clauses:
        return ("", [])
    return (" AND " + " AND ".join(clauses), params)
