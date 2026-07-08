from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError


DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _row_to_dict(row) -> dict:
    return dict(row)


def _normalize_direction(direction: str) -> str:
    if not isinstance(direction, str):
        raise ValidationError("sort direction is invalid")
    normalized = direction.lower()
    if normalized not in {"asc", "desc"}:
        raise ValidationError("sort direction is invalid")
    return normalized


def _normalize_integer(value, message: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(message)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal() and str(int(value)) == value:
        return int(value)
    raise ValidationError(message)


def _normalize_limit(limit: int) -> int:
    normalized = _normalize_integer(limit, "limit is invalid")
    if normalized < 1:
        raise ValidationError("limit is invalid")
    return min(normalized, MAX_LIMIT)


def _normalize_offset(offset: int) -> int:
    normalized = _normalize_integer(offset, "offset is invalid")
    if normalized < 0:
        raise ValidationError("offset is invalid")
    return normalized


def _append_text_search(
    clauses: list[str],
    params: list,
    text: str | None,
    columns: tuple[str, ...],
) -> None:
    if not text:
        return
    like_text = f"%{text.lower()}%"
    search_clauses = (
        f"lower(coalesce({column}, '')) like ?"
        for column in columns
    )
    clauses.append("(" + " or ".join(search_clauses) + ")")
    params.extend([like_text] * len(columns))


def _append_filters(
    clauses: list[str],
    params: list,
    filters: dict | None,
    allowed_filters: dict[str, str],
    like_fields: set[str] | None = None,
) -> None:
    if not filters:
        return
    like_fields = like_fields or set()
    for field, value in filters.items():
        if value is None or value == "":
            continue
        if field.endswith("_from"):
            base = field[:-5]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} >= ?")
            params.append(value)
        elif field.endswith("_to"):
            base = field[:-3]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} <= ?")
            params.append(value)
        elif field.endswith("_min"):
            base = field[:-4]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} >= ?")
            params.append(value)
        elif field.endswith("_max"):
            base = field[:-4]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} <= ?")
            params.append(value)
        elif field in like_fields:
            column = allowed_filters.get(field)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} like ?")
            params.append(f"%{value}%")
        else:
            column = allowed_filters.get(field)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} = ?")
            params.append(value)


def _sc_visibility_clauses(
    current_user: dict | None,
    *,
    sc_alias: str = "sc",
    include_own_drafts: bool = False,
) -> tuple[list[str], list]:
    if current_user is None:
        return [f"{sc_alias}.status != 'draft'"], []

    role = current_user.get("role")
    if role == "admin":
        return [], []
    if role == "requester":
        if include_own_drafts:
            return [
                f"({sc_alias}.requester_id = ? OR {sc_alias}.sc_id IN (SELECT sa.sc_id FROM sc_assignees sa WHERE sa.user_id = ?))"
            ], [current_user["user_id"], current_user["user_id"]]
        return [
            f"{sc_alias}.status != 'draft'",
            f"({sc_alias}.requester_id = ? OR {sc_alias}.sc_id IN (SELECT sa.sc_id FROM sc_assignees sa WHERE sa.user_id = ?))",
        ], [current_user["user_id"], current_user["user_id"]]
    raise ValidationError("current_user is invalid")


def _search(
    config: AppConfig,
    *,
    select_sql: str,
    text: str | None,
    text_columns: tuple[str, ...],
    filters: dict | None,
    allowed_filters: dict[str, str],
    sort: str,
    allowed_sorts: dict[str, str],
    direction: str,
    limit: int,
    offset: int,
    base_clauses: list[str] | None = None,
    base_params: list | None = None,
    like_fields: set[str] | None = None,
) -> list[dict]:
    sort_column = allowed_sorts.get(sort)
    if sort_column is None:
        raise ValidationError("sort field is invalid")

    clauses: list[str] = list(base_clauses or [])
    params: list = list(base_params or [])
    _append_text_search(clauses, params, text, text_columns)
    _append_filters(clauses, params, filters, allowed_filters, like_fields)

    where_sql = f" where {' and '.join(clauses)}" if clauses else ""

    count_sql = f"select count(*) from ({select_sql}{where_sql}) subq"

    sql = (
        f"{select_sql}{where_sql} "
        f"order by {sort_column} {_normalize_direction(direction)} "
        "limit ? offset ?"
    )
    params.extend([_normalize_limit(limit), _normalize_offset(offset)])

    with connect(config) as conn:
        total = conn.execute(count_sql, params[:-2]).fetchone()[0]
        rows = conn.execute(sql, params).fetchall()

    return {"rows": [_row_to_dict(row) for row in rows], "total": total}


def search_scs(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    current_user: dict | None = None,
) -> list[dict]:
    base_clauses, base_params = _sc_visibility_clauses(
        current_user,
        include_own_drafts=True,
    )

    if filters and "is_calloff" in filters:
        if filters["is_calloff"] == "1":
            base_clauses.append("sc.calloff_po_id IS NOT NULL")
        elif filters["is_calloff"] == "0":
            base_clauses.append("sc.calloff_po_id IS NULL")
        filters = {k: v for k, v in filters.items() if k != "is_calloff"}

    return _search(
        config,
        select_sql="""
        select distinct
          sc.*,
          requester.user_name as requester_name
        from sc_records sc
        join users requester on requester.user_id = sc.requester_id
        join users creator on creator.user_id = sc.created_by
        left join pos po on po.sc_id = sc.sc_id
        left join vendors vendor on vendor.vendor_id = po.vendor_id
        """,
        text=text,
        text_columns=(
            "sc.sc_no",
            "sc.description",
            "sc.service_scope",
            "sc.request_type",
            "cast(sc.cost_center as text)",
            "requester.user_name",
            "creator.user_name",
            "po.po_no",
            "vendor.vendor_name",
            "vendor.ksrm_vendor_code",
            "cast(sc.sc_amount as text)",
            "sc.service_period_start",
            "sc.service_period_end",
            "sc.created_at",
            "sc.approved_at",
            "sc.approved_by",
            "sc.asset",
            "sc.asset_nums",
            "sc.confirmed_at",
        ),
        filters=filters,
        allowed_filters={
            "sc_id": "sc.sc_id",
            "sc_no": "sc.sc_no",
            "requester_id": "sc.requester_id",
            "request_type": "sc.request_type",
            "service_scope": "sc.service_scope",
            "cost_center": "sc.cost_center",
            "status": "sc.status",
            "created_by": "sc.created_by",
            "requester_name": "requester.user_name",
            "created_by_name": "creator.user_name",
            "sc_amount": "sc.sc_amount",
            "sc_amount_min": "sc.sc_amount",
            "sc_amount_max": "sc.sc_amount",
            "service_period_start": "sc.service_period_start",
            "service_period_start_from": "sc.service_period_start",
            "service_period_start_to": "sc.service_period_start",
            "service_period_end": "sc.service_period_end",
            "service_period_end_from": "sc.service_period_end",
            "service_period_end_to": "sc.service_period_end",
            "description": "sc.description",
            "created_at": "sc.created_at",
            "created_at_from": "sc.created_at",
            "created_at_to": "sc.created_at",
            "updated_at": "sc.updated_at",
            "approved_by": "sc.approved_by",
            "approved_at": "sc.approved_at",
            "closed_at": "sc.finished_at",
            "asset": "sc.asset",
            "pending_date": "sc.pending_date",
            "pending_date_from": "sc.pending_date",
            "pending_date_to": "sc.pending_date",
            "approved_date": "sc.approved_date",
            "approved_date_from": "sc.approved_date",
            "approved_date_to": "sc.approved_date",
            "confirmed_at": "sc.confirmed_at",
            "confirmed_at_from": "sc.confirmed_at",
            "confirmed_at_to": "sc.confirmed_at",
            "deadline": "sc.service_period_end",
            "deadline_from": "sc.service_period_end",
            "deadline_to": "sc.service_period_end",
            "calloff_po_id": "sc.calloff_po_id",
        },
        sort=sort,
        allowed_sorts={
            "sc_id": "sc.sc_id",
            "sc_no": "sc.sc_no",
            "requester_id": "sc.requester_id",
            "requester_name": "requester.user_name",
            "request_type": "sc.request_type",
            "service_scope": "sc.service_scope",
            "cost_center": "sc.cost_center",
            "sc_amount": "sc.sc_amount",
            "status": "sc.status",
            "created_at": "sc.created_at",
            "updated_at": "sc.updated_at",
            "asset": "sc.asset",
            "pending_date": "sc.pending_date",
            "approved_date": "sc.approved_date",
            "confirmed_at": "sc.confirmed_at",
            "calloff_po_id": "sc.calloff_po_id",
        },
        direction=direction,
        limit=limit,
        offset=offset,
        base_clauses=base_clauses,
        base_params=base_params,
        like_fields={"requester_id", "created_by", "requester_name", "created_by_name"},
    )


def search_vendors(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "vendor_name",
    direction: str = "asc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict]:
    return _search(
        config,
        select_sql="select * from vendors",
        text=text,
        text_columns=(
            "vendor_name",
            "ksrm_vendor_code",
            "company_name_cn",
            "contact_person",
            "service_scope",
            "email",
            "description",
            "phone",
            "created_at",
        ),
        filters=filters,
        allowed_filters={
            "vendor_id": "vendor_id",
            "vendor_name": "vendor_name",
            "ksrm_vendor_code": "ksrm_vendor_code",
            "company_name_cn": "company_name_cn",
            "service_scope": "service_scope",
            "status": "status",
            "created_by": "created_by",
            "contact_person": "contact_person",
            "email": "email",
            "phone": "phone",
            "description": "description",
            "created_at": "created_at",
            "updated_at": "updated_at",
        },
        sort=sort,
        allowed_sorts={
            "vendor_id": "vendor_id",
            "vendor_name": "vendor_name",
            "ksrm_vendor_code": "ksrm_vendor_code",
            "company_name_cn": "company_name_cn",
            "service_scope": "service_scope",
            "created_at": "created_at",
            "updated_at": "updated_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
        base_clauses=["(status IS NULL OR status != 'disabled')"],
        base_params=[],
        like_fields={"vendor_id", "vendor_name", "ksrm_vendor_code", "company_name_cn", "service_scope", "contact_person", "email"},
    )


def search_pos(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    current_user: dict | None = None,
) -> list[dict]:
    base_clauses, base_params = _sc_visibility_clauses(current_user)

    if current_user and current_user.get("role") == "requester":
        base_clauses = [
            f"({c} OR (po.sc_id IS NULL AND po.requester_id = ?))"
            for c in base_clauses
        ]
        total_placeholders = sum(c.count("?") for c in base_clauses)
        base_params = [current_user["user_id"]] * total_placeholders

    if filters and "is_fc_po" in filters:
        if filters["is_fc_po"] == "1":
            base_clauses.append("(po.request_type = 'FC' OR sc.request_type = 'FC')")
        elif filters["is_fc_po"] == "0":
            base_clauses.append("(po.request_type IS NULL AND sc.request_type != 'FC')")
        filters = {k: v for k, v in filters.items() if k != "is_fc_po"}

    if filters and "is_independent" in filters:
        if filters["is_independent"] == "1":
            base_clauses.append("po.sc_id IS NULL")
        elif filters["is_independent"] == "0":
            base_clauses.append("po.sc_id IS NOT NULL")
        filters = {k: v for k, v in filters.items() if k != "is_independent"}

    return _search(
        config,
        select_sql="""
        select
          po.*,
          sc.sc_no,
          coalesce(po.request_type, sc.request_type) as sc_request_type,
          u.user_name as requester_name,
          vendor.vendor_name,
          vendor.ksrm_vendor_code,
          case when po.request_type = 'FC' or sc.request_type = 'FC'
            then po.po_amount - coalesce(calloff_totals.allocated, 0)
            else po.po_amount - coalesce(gr_totals.pending_total, 0)
                 - coalesce(gr_totals.con_value_total, 0)
          end as open_po_amount,
          coalesce(gr_totals.con_value_total, 0) as consumed_amount,
          coalesce(gr_totals.pending_total, 0) as po_pending_total,
          coalesce(gr_totals.pending_total_incl_tax, 0) as po_pending_total_incl_tax
        from pos po
        left join sc_records sc on sc.sc_id = po.sc_id
        join users u on u.user_id = po.requester_id
        join vendors vendor on vendor.vendor_id = po.vendor_id
        left join (
          select
            po_id,
            sum(case when status in ('pending', 'manager_confirm')
                      then estimated_amount else 0 end) as pending_total,
            sum(case when status = 'approved'
                      then con_value else 0 end) as con_value_total,
            sum(case when status in ('pending', 'manager_confirm')
                      then coalesce(gross_cost, estimated_amount)
                      else 0 end) as pending_total_incl_tax
          from gr_requests
          group by po_id
        ) gr_totals on gr_totals.po_id = po.po_id
        left join (
          select calloff_po_id, coalesce(sum(sc_amount), 0) as allocated
          from sc_records
          where calloff_po_id is not null
          group by calloff_po_id
        ) calloff_totals on calloff_totals.calloff_po_id = po.po_id
        """,
        text=text,
        text_columns=(
            "po.po_no",
            "po.contract_no",
            "po.payment_frequency",
            "po.status",
            "sc.sc_no",
            "vendor.vendor_name",
            "vendor.ksrm_vendor_code",
            "u.user_name",
            "cast(po.po_amount as text)",
            "po.contract_from",
            "po.contract_to",
            "po.created_at",
            "po.contract_pos",
            "po.contract_type",
            "po.cost_center",
            "po.purchaser",
        ),
        filters=filters,
        allowed_filters={
            "po_id": "po.po_id",
            "po_no": "po.po_no",
            "sc_id": "po.sc_id",
            "vendor_id": "po.vendor_id",
            "status": "po.status",
            "vendor_name": "vendor.vendor_name",
            "requester_name": "u.user_name",
            "po_amount": "po.po_amount",
            "po_amount_min": "po.po_amount",
            "po_amount_max": "po.po_amount",
            "contract_from": "po.contract_from",
            "contract_from_from": "po.contract_from",
            "contract_from_to": "po.contract_from",
            "contract_to": "po.contract_to",
            "contract_to_from": "po.contract_to",
            "contract_to_to": "po.contract_to",
            "contract_no": "po.contract_no",
            "payment_frequency": "po.payment_frequency",
            "contract_pos": "po.contract_pos",
            "contract_type": "po.contract_type",
            "cost_center": "po.cost_center",
            "purchaser": "po.purchaser",
            "active_date": "po.active_date",
            "active_date_from": "po.active_date",
            "active_date_to": "po.active_date",
            "deadline": "po.contract_to",
            "deadline_from": "po.contract_to",
            "deadline_to": "po.contract_to",
            "created_at": "po.created_at",
            "updated_at": "po.updated_at",
        },
        sort=sort,
        allowed_sorts={
            "po_id": "po.po_id",
            "po_no": "po.po_no",
            "sc_no": "sc.sc_no",
            "vendor_name": "vendor.vendor_name",
            "requester_name": "u.user_name",
            "po_amount": "po.po_amount",
            "status": "po.status",
            "contract_to": "po.contract_to",
            "contract_type": "po.contract_type",
            "cost_center": "po.cost_center",
            "active_date": "po.active_date",
            "created_at": "po.created_at",
            "updated_at": "po.updated_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
        base_clauses=base_clauses,
        base_params=base_params,
    )


def search_grs(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    current_user: dict | None = None,
) -> list[dict]:
    base_clauses, base_params = _sc_visibility_clauses(current_user)

    return _search(
        config,
        select_sql="""
        select
          gr.*,
          po.po_no,
          po.sc_id,
          sc.sc_no,
          vendor.vendor_id,
          vendor.vendor_name,
          requester.user_name as requester_name
        from gr_requests gr
        join pos po on po.po_id = gr.po_id
        join sc_records sc on sc.sc_id = po.sc_id
        join vendors vendor on vendor.vendor_id = po.vendor_id
        left join users requester on requester.user_id = gr.requester_id
        """,
        text=text,
        text_columns=(
            "gr.gr_no",
            "gr.remark",
            "gr.status",
            "po.po_no",
            "sc.sc_no",
            "vendor.vendor_name",
            "cast(gr.estimated_amount as text)",
            "cast(gr.con_value as text)",
            "cast(gr.gross_cost as text)",
            "cast(gr.tax_rate as text)",
            "gr.goods_service_description",
            "gr.confirmation_name",
            "gr.delivery_from",
            "gr.delivery_to",
            "gr.last_delivery",
            "gr.created_at",
            "gr.created_by",
            "gr.approved_by",
            "gr.pending_date",
            "gr.approved_date",
            "gr.confirmed_at",
        ),
        filters=filters,
        allowed_filters={
            "gr_id": "gr.gr_id",
            "gr_no": "gr.gr_no",
            "po_id": "gr.po_id",
            "requester_id": "gr.requester_id",
            "status": "gr.status",
            "sc_id": "po.sc_id",
            "vendor_id": "vendor.vendor_id",
            "estimated_amount": "gr.estimated_amount",
            "estimated_amount_min": "gr.estimated_amount",
            "estimated_amount_max": "gr.estimated_amount",
            "con_value": "gr.con_value",
            "con_value_min": "gr.con_value",
            "con_value_max": "gr.con_value",
            "gross_cost": "gr.gross_cost",
            "gross_cost_min": "gr.gross_cost",
            "gross_cost_max": "gr.gross_cost",
            "tax_rate": "gr.tax_rate",
            "goods_service_description": "gr.goods_service_description",
            "confirmation_name": "gr.confirmation_name",
            "delivery_from": "gr.delivery_from",
            "delivery_from_from": "gr.delivery_from",
            "delivery_from_to": "gr.delivery_from",
            "delivery_to": "gr.delivery_to",
            "delivery_to_from": "gr.delivery_to",
            "delivery_to_to": "gr.delivery_to",
            "last_delivery": "gr.last_delivery",
            "remark": "gr.remark",
            "created_by": "gr.created_by",
            "created_at": "gr.created_at",
            "created_at_from": "gr.created_at",
            "created_at_to": "gr.created_at",
            "approved_by": "gr.approved_by",
            "approved_at": "gr.approved_at",
            "cancelled_by": "gr.denied_by",
            "cancelled_at": "gr.denied_at",
            "pending_date": "gr.pending_date",
            "pending_date_from": "gr.pending_date",
            "pending_date_to": "gr.pending_date",
            "approved_date": "gr.approved_date",
            "approved_date_from": "gr.approved_date",
            "approved_date_to": "gr.approved_date",
            "confirmed_at": "gr.confirmed_at",
            "confirmed_at_from": "gr.confirmed_at",
            "confirmed_at_to": "gr.confirmed_at",
            "deadline": "po.contract_to",
            "deadline_from": "po.contract_to",
            "deadline_to": "po.contract_to",
        },
        sort=sort,
        allowed_sorts={
            "gr_id": "gr.gr_id",
            "gr_no": "gr.gr_no",
            "po_no": "po.po_no",
            "sc_no": "sc.sc_no",
            "vendor_name": "vendor.vendor_name",
            "estimated_amount": "gr.estimated_amount",
            "con_value": "gr.con_value",
            "gross_cost": "gr.gross_cost",
            "tax_rate": "gr.tax_rate",
            "goods_service_description": "gr.goods_service_description",
            "confirmation_name": "gr.confirmation_name",
            "delivery_from": "gr.delivery_from",
            "delivery_to": "gr.delivery_to",
            "last_delivery": "gr.last_delivery",
            "status": "gr.status",
            "created_at": "gr.created_at",
            "approved_at": "gr.approved_at",
            "cancelled_at": "gr.denied_at",
            "pending_date": "gr.pending_date",
            "approved_date": "gr.approved_date",
            "confirmed_at": "gr.confirmed_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
        base_clauses=base_clauses,
        base_params=base_params,
    )


def workbench_data(
    config: AppConfig,
    current_user: dict | None = None,
) -> dict:
    """Return per-status counts and top rows for the workbench grid.

    Visibility rules:
    - Requester: own records only (all statuses)
    - Admin:
      - Draft / Approved: own records only
      - Pending: all records
    """
    sc_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]
    po_statuses = ["draft", "active"]
    gr_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]

    def _is_own_only(status: str) -> bool:
        if current_user is None:
            return False
        role = current_user.get("role")
        if role == "requester":
            return True
        if role == "admin":
            return status not in ("pending", "active", "manager_confirm", "approved", "denied")
        return False

    user_id = current_user["user_id"] if current_user else None

    with connect(config) as conn:
        sc_data = {}
        for st in sc_statuses:
            clauses = ["sc.status = ?"]
            params = [st]
            if user_id:
                visibility_clause, visibility_params = _sc_visibility_clauses(current_user, sc_alias="sc")
                clauses.extend(visibility_clause)
                params.extend(visibility_params)

            # Own-only statuses: admin sees only their own drafts;
            # requesters already scoped by _sc_visibility_clauses
            if _is_own_only(st) and user_id and current_user.get("role") == "admin":
                clauses.append("sc.requester_id = ?")
                params.append(current_user["user_id"])

            where = "WHERE " + " AND ".join(clauses)

            cnt = conn.execute(
                f"SELECT COUNT(*) FROM sc_records sc {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT sc.sc_id, sc.sc_no, sc.requester_id, "
                f"sc.created_at, sc.pending_date, sc.submitted_date, "
                f"sc.service_period_end AS deadline, "
                f"sc.sc_amount, sc.request_type, sc.currency, "
                f"u.user_name AS requester_name "
                f"FROM sc_records sc "
                f"JOIN users u ON u.user_id = sc.requester_id "
                f"{where} ORDER BY sc.service_period_end ASC LIMIT 6",
                params,
            ).fetchall()
            sc_data[st] = {"count": cnt, "rows": [_row_to_dict(r) for r in rows]}

        po_data = {}
        for st in po_statuses:
            clauses = ["po.status = ?"]
            params = [st]
            if user_id:
                visibility_clause, visibility_params = _sc_visibility_clauses(current_user, sc_alias="sc")
                clauses.extend(visibility_clause)
                params.extend(visibility_params)

            # Own-only statuses: admin sees only their own drafts;
            # requesters already scoped by _sc_visibility_clauses
            if _is_own_only(st) and user_id and current_user.get("role") == "admin":
                clauses.append("po.requester_id = ?")
                params.append(current_user["user_id"])

            where = "WHERE " + " AND ".join(clauses)

            cnt = conn.execute(
                f"SELECT COUNT(*) FROM pos po LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT po.po_id, po.po_no, po.sc_id, po.requester_id, "
                f"po.created_at, po.contract_from, po.contract_to, "
                f"sc.sc_no, sc.currency, "
                f"u.user_name AS requester_name, "
                f"CASE WHEN po.request_type = 'FC' OR sc.request_type = 'FC' "
                f"THEN po.po_amount - COALESCE(calloff_sums.allocated, 0) "
                f"ELSE po.po_amount - COALESCE(gr_sums.pending_total, 0) "
                f"- COALESCE(gr_sums.con_value_total, 0) END AS open_po_amount "
                f"FROM pos po "
                f"JOIN users u ON u.user_id = po.requester_id "
                f"LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id "
                f"LEFT JOIN ("
                f"  SELECT po_id,"
                f"    SUM(CASE WHEN status IN ('pending', 'manager_confirm') "
                f"THEN estimated_amount ELSE 0 END) AS pending_total,"
                f"    SUM(CASE WHEN status = 'approved' "
                f"THEN con_value ELSE 0 END) AS con_value_total"
                f"  FROM gr_requests GROUP BY po_id"
                f") gr_sums ON gr_sums.po_id = po.po_id "
                f"LEFT JOIN ("
                f"  SELECT calloff_po_id, SUM(sc_amount) AS allocated "
                f"  FROM sc_records WHERE calloff_po_id IS NOT NULL "
                f"  GROUP BY calloff_po_id"
                f") calloff_sums ON calloff_sums.calloff_po_id = po.po_id "
                f"{where} ORDER BY po.contract_to ASC LIMIT 6",
                params,
            ).fetchall()
            po_data[st] = {"count": cnt, "rows": [_row_to_dict(r) for r in rows]}

        gr_data = {}
        for st in gr_statuses:
            clauses = ["gr.status = ?"]
            params = [st]
            if user_id:
                visibility_clause, visibility_params = _sc_visibility_clauses(current_user, sc_alias="sc")
                clauses.extend(visibility_clause)
                params.extend(visibility_params)

            # Own-only statuses: admin sees only their own drafts;
            # requesters already scoped by _sc_visibility_clauses
            if _is_own_only(st) and user_id and current_user.get("role") == "admin":
                clauses.append("gr.requester_id = ?")
                params.append(current_user["user_id"])

            where = "WHERE " + " AND ".join(clauses)

            cnt = conn.execute(
                f"SELECT COUNT(*) FROM gr_requests gr "
                f"JOIN pos po ON po.po_id = gr.po_id "
                f"LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id "
                f"{where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT gr.gr_id, gr.po_id, po.sc_id, gr.requester_id, "
                f"gr.created_at, gr.pending_date, gr.submitted_date, "
                f"gr.denied_by, gr.denied_at, "
                f"u.user_name AS requester_name "
                f"FROM gr_requests gr "
                f"JOIN pos po ON po.po_id = gr.po_id "
                f"LEFT JOIN sc_records sc ON sc.sc_id = po.sc_id "
                f"JOIN users u ON u.user_id = gr.requester_id "
                f"{where} ORDER BY gr.created_at ASC LIMIT 6",
                params,
            ).fetchall()
            gr_data[st] = {"count": cnt, "rows": [_row_to_dict(r) for r in rows]}

    return {"sc": sc_data, "po": po_data, "gr": gr_data}


def search_operation_records(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    current_user: dict | None = None,
) -> list[dict]:
    base_clauses: list[str]
    base_params: list
    if current_user is None:
        base_clauses = [
            """
            (
              operation_records.sc_id is null
              or exists (
                select 1
                from sc_records sc
                where sc.sc_id = operation_records.sc_id
                  and sc.status != 'draft'
              )
            )
            """
        ]
        base_params = []
    elif current_user.get("role") == "admin":
        base_clauses = []
        base_params = []
    elif current_user.get("role") == "requester":
        base_clauses = [
            """
            (
              (operation_records.sc_id is null and operation_records.operator_id = ?)
              or exists (
                select 1
                from sc_records sc
                where sc.sc_id = operation_records.sc_id
                  and sc.requester_id = ?
              )
            )
            """
        ]
        base_params = [current_user["user_id"], current_user["user_id"]]
    else:
        raise ValidationError("current_user is invalid")

    return _search(
        config,
        select_sql="select * from operation_records",
        text=text,
        text_columns=(
            "action_type",
            "object_type",
            "object_id",
            "sc_id",
            "operator_id",
            "machine_id",
            "before_json",
            "after_json",
        ),
        filters=filters,
        allowed_filters={
            "action_type": "action_type",
            "object_type": "object_type",
            "object_id": "object_id",
            "sc_id": "sc_id",
            "operator_id": "operator_id",
            "machine_id": "machine_id",
            "operation_mode": "operation_mode",
        },
        sort=sort,
        allowed_sorts={
            "log_id": "log_id",
            "action_type": "action_type",
            "object_type": "object_type",
            "object_id": "object_id",
            "sc_id": "sc_id",
            "operator_id": "operator_id",
            "machine_id": "machine_id",
            "operation_mode": "operation_mode",
            "created_at": "created_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
        base_clauses=base_clauses,
        base_params=base_params,
    )
