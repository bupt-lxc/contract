from decimal import Decimal

from sc_gr_app.db.connection import connect
from sc_gr_app.config import AppConfig
from sc_gr_app.errors import ConflictError, NotFound, ValidationError


def _decimal_or_zero(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _decimal_budget_to_float(budget: dict[str, Decimal]) -> dict[str, float]:
    return {key: float(value) for key, value in budget.items()}


def compute_sc_budget_decimal(config: AppConfig, sc_id: str) -> dict[str, Decimal]:
    with connect(config) as conn:
        sc = conn.execute(
            "select sc_amount from sc_records where sc_id = ?",
            (sc_id,),
        ).fetchone()
        if sc is None:
            raise NotFound(f"SC not found: {sc_id}")

        null_con_value_gr = conn.execute(
            """
            select gr.gr_id
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            where po.sc_id = ?
              and gr.status = 'approved'
              and gr.con_value is null
            limit 1
            """,
            (sc_id,),
        ).fetchone()
        if null_con_value_gr is not None:
            raise ConflictError(
                f"Approved GR has NULL con_value for SC {sc_id}: "
                f"{null_con_value_gr['gr_id']}"
            )

        gr_totals = conn.execute(
            """
            select
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm') then coalesce(gr.con_value, gr.estimated_amount) else 0 end), 0)
                as pending_total,
              coalesce(sum(case when gr.status = 'approved' then gr.con_value else 0 end), 0)
                as con_value_total,
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                then coalesce(gr.gross_cost, gr.estimated_amount) else 0 end), 0)
                as pending_total_incl_tax
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            where po.sc_id = ?
            """,
            (sc_id,),
        ).fetchone()
        po_totals = conn.execute(
            """
            select coalesce(sum(po_amount), 0) as allocated_po_amount
            from pos
            where sc_id = ?
            """,
            (sc_id,),
        ).fetchone()

    sc_amount = _decimal_or_zero(sc["sc_amount"])
    sc_pending_total = _decimal_or_zero(gr_totals["pending_total"])
    sc_con_value_total = _decimal_or_zero(gr_totals["con_value_total"])
    sc_pending_total_incl_tax = _decimal_or_zero(gr_totals["pending_total_incl_tax"])
    allocated_po_amount = _decimal_or_zero(po_totals["allocated_po_amount"])

    return {
        "sc_amount": sc_amount,
        "sc_pending_total": sc_pending_total,
        "sc_con_value_total": sc_con_value_total,
        "sc_pending_total_incl_tax": sc_pending_total_incl_tax,
        "sc_available_amount": sc_amount - sc_pending_total - sc_con_value_total,
        "allocated_po_amount": allocated_po_amount,
        "unallocated_sc_amount": sc_amount - allocated_po_amount,
    }


def compute_sc_budget(config: AppConfig, sc_id: str) -> dict[str, float]:
    return _decimal_budget_to_float(compute_sc_budget_decimal(config, sc_id))


def compute_po_fc_budget_decimal(config: AppConfig, po_id: str) -> dict[str, Decimal]:
    """Compute budget for an FC PO: call-off SC allocation + downstream GR trace."""
    with connect(config) as conn:
        po = conn.execute(
            "select po_amount, sc_id from pos where po_id = ?",
            (po_id,),
        ).fetchone()
        if po is None:
            raise NotFound(f"PO not found: {po_id}")

        sc = conn.execute(
            "select request_type from sc_records where sc_id = ?",
            (po["sc_id"],),
        ).fetchone()
        if sc is None or sc["request_type"] != "FC":
            raise ValidationError("PO is not an FC PO")

        calloff_totals = conn.execute(
            """
            select
              coalesce(sum(sc_amount), 0) as allocated_calloff,
              coalesce(sum(case when status in ('manager_confirm', 'pending', 'approved')
                           then sc_amount else 0 end), 0) as pending_calloff
            from sc_records
            where calloff_po_id = ?
            """,
            (po_id,),
        ).fetchone()

        gr_totals = conn.execute(
            """
            select
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then gr.estimated_amount else 0 end), 0) as pending_total,
              coalesce(sum(case when gr.status = 'approved'
                           then gr.con_value else 0 end), 0) as con_value_total,
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then coalesce(gr.gross_cost, gr.estimated_amount)
                           else 0 end), 0) as pending_total_incl_tax
            from gr_requests gr
            join pos p on p.po_id = gr.po_id
            join sc_records child_sc on child_sc.sc_id = p.sc_id
            where child_sc.calloff_po_id = ?
            """,
            (po_id,),
        ).fetchone()

    po_amount = _decimal_or_zero(po["po_amount"])
    allocated_calloff = _decimal_or_zero(calloff_totals["allocated_calloff"])
    pending_calloff = _decimal_or_zero(calloff_totals["pending_calloff"])

    return {
        "po_amount": po_amount,
        "allocated_calloff_amount": allocated_calloff,
        "pending_calloff_amount": pending_calloff,
        "open_po_amount": po_amount - allocated_calloff,
        "downstream_consumed": _decimal_or_zero(gr_totals["con_value_total"]),
        "downstream_pending_gr": _decimal_or_zero(gr_totals["pending_total"]),
        "downstream_pending_gr_tax": _decimal_or_zero(gr_totals["pending_total_incl_tax"]),
    }


def compute_po_fc_budget(config: AppConfig, po_id: str) -> dict[str, float]:
    return _decimal_budget_to_float(compute_po_fc_budget_decimal(config, po_id))


def compute_sc_fc_budget_decimal(config: AppConfig, sc_id: str) -> dict[str, Decimal]:
    """Compute budget for an SC(FC): PO(FC) allocation + downstream call-off + GR trace."""
    with connect(config) as conn:
        sc = conn.execute(
            "select sc_amount, request_type from sc_records where sc_id = ?",
            (sc_id,),
        ).fetchone()
        if sc is None:
            raise NotFound(f"SC not found: {sc_id}")
        if sc["request_type"] != "FC":
            raise ValidationError("SC is not an FC-type SC")

        po_totals = conn.execute(
            """
            select coalesce(sum(po_amount), 0) as allocated_po
            from pos where sc_id = ?
            """,
            (sc_id,),
        ).fetchone()

        calloff_totals = conn.execute(
            """
            select
              coalesce(sum(child_sc.sc_amount), 0) as downstream_calloff,
              coalesce(sum(case when child_sc.status in ('manager_confirm', 'pending', 'approved')
                           then child_sc.sc_amount else 0 end), 0) as pending_calloff
            from sc_records child_sc
            join pos fc_po on fc_po.po_id = child_sc.calloff_po_id
            where fc_po.sc_id = ?
            """,
            (sc_id,),
        ).fetchone()

        gr_totals = conn.execute(
            """
            select
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then gr.estimated_amount else 0 end), 0) as pending_total,
              coalesce(sum(case when gr.status = 'approved'
                           then gr.con_value else 0 end), 0) as con_value_total,
              coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
                           then coalesce(gr.gross_cost, gr.estimated_amount)
                           else 0 end), 0) as pending_total_incl_tax
            from gr_requests gr
            join pos p on p.po_id = gr.po_id
            join sc_records child_sc on child_sc.sc_id = p.sc_id
            join pos fc_po on fc_po.po_id = child_sc.calloff_po_id
            where fc_po.sc_id = ?
            """,
            (sc_id,),
        ).fetchone()

    sc_amount = _decimal_or_zero(sc["sc_amount"])

    return {
        "sc_amount": sc_amount,
        "allocated_po_amount": _decimal_or_zero(po_totals["allocated_po"]),
        "unallocated_sc_amount": sc_amount - _decimal_or_zero(po_totals["allocated_po"]),
        "downstream_calloff_amount": _decimal_or_zero(calloff_totals["downstream_calloff"]),
        "pending_calloff_amount": _decimal_or_zero(calloff_totals["pending_calloff"]),
        "downstream_consumed": _decimal_or_zero(gr_totals["con_value_total"]),
        "downstream_pending_gr": _decimal_or_zero(gr_totals["pending_total"]),
        "downstream_pending_gr_tax": _decimal_or_zero(gr_totals["pending_total_incl_tax"]),
    }


def compute_sc_fc_budget(config: AppConfig, sc_id: str) -> dict[str, float]:
    return _decimal_budget_to_float(compute_sc_fc_budget_decimal(config, sc_id))


def compute_po_budget_decimal(config: AppConfig, po_id: str) -> dict[str, Decimal]:
    with connect(config) as conn:
        po = conn.execute(
            "select po_amount from pos where po_id = ?",
            (po_id,),
        ).fetchone()
        if po is None:
            raise NotFound(f"PO not found: {po_id}")

        null_con_value_gr = conn.execute(
            """
            select gr_id
            from gr_requests
            where po_id = ?
              and status = 'approved'
              and con_value is null
            limit 1
            """,
            (po_id,),
        ).fetchone()
        if null_con_value_gr is not None:
            raise ConflictError(
                f"Approved GR has NULL con_value for PO {po_id}: "
                f"{null_con_value_gr['gr_id']}"
            )

        gr_totals = conn.execute(
            """
            select
              coalesce(sum(case when status in ('pending', 'manager_confirm') then estimated_amount else 0 end), 0)
                as pending_total,
              coalesce(sum(case when status = 'approved' then con_value else 0 end), 0)
                as con_value_total,
              coalesce(sum(case when status in ('pending', 'manager_confirm')
                then coalesce(gross_cost, estimated_amount) else 0 end), 0)
                as pending_total_incl_tax
            from gr_requests
            where po_id = ?
            """,
            (po_id,),
        ).fetchone()

    po_amount = _decimal_or_zero(po["po_amount"])
    po_pending_total = _decimal_or_zero(gr_totals["pending_total"])
    po_con_value_total = _decimal_or_zero(gr_totals["con_value_total"])
    po_pending_total_incl_tax = _decimal_or_zero(gr_totals["pending_total_incl_tax"])

    return {
        "po_amount": po_amount,
        "po_pending_total": po_pending_total,
        "po_con_value_total": po_con_value_total,
        "po_pending_total_incl_tax": po_pending_total_incl_tax,
        "open_po_amount": po_amount - po_pending_total - po_con_value_total,
    }


def compute_po_budget(config: AppConfig, po_id: str) -> dict[str, float]:
    return _decimal_budget_to_float(compute_po_budget_decimal(config, po_id))
