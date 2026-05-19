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
) -> None:
    if not filters:
        return
    for field, value in filters.items():
        column = allowed_filters.get(field)
        if column is None:
            raise ValidationError("filter field is invalid")
        clauses.append(f"{column} = ?")
        params.append(value)


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
) -> list[dict]:
    sort_column = allowed_sorts.get(sort)
    if sort_column is None:
        raise ValidationError("sort field is invalid")

    clauses: list[str] = []
    params: list = []
    _append_text_search(clauses, params, text, text_columns)
    _append_filters(clauses, params, filters, allowed_filters)

    where_sql = f" where {' and '.join(clauses)}" if clauses else ""
    sql = (
        f"{select_sql}{where_sql} "
        f"order by {sort_column} {_normalize_direction(direction)} "
        "limit ? offset ?"
    )
    params.extend([_normalize_limit(limit), _normalize_offset(offset)])

    with connect(config) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [_row_to_dict(row) for row in rows]


def search_scs(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict]:
    return _search(
        config,
        select_sql="""
        select
          sc.*,
          requester.user_name as requester_name
        from sc_records sc
        join users requester on requester.user_id = sc.requester_id
        """,
        text=text,
        text_columns=(
            "sc.sc_no",
            "sc.description",
            "sc.request_type",
            "cast(sc.cost_center as text)",
            "requester.user_name",
        ),
        filters=filters,
        allowed_filters={
            "sc_id": "sc.sc_id",
            "sc_no": "sc.sc_no",
            "requester_id": "sc.requester_id",
            "request_type": "sc.request_type",
            "cost_center": "sc.cost_center",
            "status": "sc.status",
            "created_by": "sc.created_by",
        },
        sort=sort,
        allowed_sorts={
            "sc_id": "sc.sc_id",
            "sc_no": "sc.sc_no",
            "requester_id": "sc.requester_id",
            "requester_name": "requester.user_name",
            "request_type": "sc.request_type",
            "cost_center": "sc.cost_center",
            "sc_amount": "sc.sc_amount",
            "status": "sc.status",
            "created_at": "sc.created_at",
            "updated_at": "sc.updated_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
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
            "contact_person",
            "service_scope",
            "email",
            "description",
        ),
        filters=filters,
        allowed_filters={
            "vendor_id": "vendor_id",
            "vendor_name": "vendor_name",
            "ksrm_vendor_code": "ksrm_vendor_code",
            "service_scope": "service_scope",
            "created_by": "created_by",
        },
        sort=sort,
        allowed_sorts={
            "vendor_id": "vendor_id",
            "vendor_name": "vendor_name",
            "ksrm_vendor_code": "ksrm_vendor_code",
            "service_scope": "service_scope",
            "created_at": "created_at",
            "updated_at": "updated_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
    )


def search_pos(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict]:
    return _search(
        config,
        select_sql="""
        select
          po.*,
          sc.sc_no,
          vendor.vendor_name,
          vendor.ksrm_vendor_code,
          po.po_amount - coalesce(gr_totals.pending_total, 0)
            - coalesce(gr_totals.con_value_total, 0) as open_po_amount
        from pos po
        join sc_records sc on sc.sc_id = po.sc_id
        join vendors vendor on vendor.vendor_id = po.vendor_id
        left join (
          select
            po_id,
            sum(case when status = 'pending' then estimated_amount else 0 end) as pending_total,
            sum(case when status = 'approved' then con_value else 0 end) as con_value_total
          from gr_requests
          group by po_id
        ) gr_totals on gr_totals.po_id = po.po_id
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
        ),
        filters=filters,
        allowed_filters={
            "po_id": "po.po_id",
            "po_no": "po.po_no",
            "sc_id": "po.sc_id",
            "vendor_id": "po.vendor_id",
            "status": "po.status",
            "vendor_name": "vendor.vendor_name",
        },
        sort=sort,
        allowed_sorts={
            "po_id": "po.po_id",
            "po_no": "po.po_no",
            "sc_no": "sc.sc_no",
            "vendor_name": "vendor.vendor_name",
            "po_amount": "po.po_amount",
            "status": "po.status",
            "created_at": "po.created_at",
            "updated_at": "po.updated_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
    )


def search_grs(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict]:
    return _search(
        config,
        select_sql="""
        select
          gr.*,
          po.po_no,
          po.sc_id,
          sc.sc_no,
          vendor.vendor_id,
          vendor.vendor_name
        from gr_requests gr
        join pos po on po.po_id = gr.po_id
        join sc_records sc on sc.sc_id = po.sc_id
        join vendors vendor on vendor.vendor_id = po.vendor_id
        """,
        text=text,
        text_columns=(
            "gr.remark",
            "gr.status",
            "po.po_no",
            "sc.sc_no",
            "vendor.vendor_name",
        ),
        filters=filters,
        allowed_filters={
            "gr_id": "gr.gr_id",
            "po_id": "gr.po_id",
            "requester_id": "gr.requester_id",
            "status": "gr.status",
            "sc_id": "po.sc_id",
            "vendor_id": "vendor.vendor_id",
        },
        sort=sort,
        allowed_sorts={
            "gr_id": "gr.gr_id",
            "po_no": "po.po_no",
            "sc_no": "sc.sc_no",
            "vendor_name": "vendor.vendor_name",
            "estimated_amount": "gr.estimated_amount",
            "con_value": "gr.con_value",
            "status": "gr.status",
            "created_at": "gr.created_at",
            "approved_at": "gr.approved_at",
            "cancelled_at": "gr.cancelled_at",
        },
        direction=direction,
        limit=limit,
        offset=offset,
    )


def search_audit_logs(
    config: AppConfig,
    text: str | None = None,
    filters: dict | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict]:
    return _search(
        config,
        select_sql="select * from audit_logs",
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
    )
