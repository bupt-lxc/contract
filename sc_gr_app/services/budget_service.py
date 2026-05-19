from sc_gr_app.db.connection import connect
from sc_gr_app.config import AppConfig
from sc_gr_app.errors import ConflictError, NotFound


def _float_or_zero(value) -> float:
    return float(value or 0)


def compute_sc_budget(config: AppConfig, sc_id: str) -> dict[str, float]:
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
              coalesce(sum(case when gr.status = 'pending' then gr.estimated_amount else 0 end), 0)
                as pending_total,
              coalesce(sum(case when gr.status = 'approved' then gr.con_value else 0 end), 0)
                as con_value_total
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

    sc_amount = float(sc["sc_amount"])
    sc_pending_total = _float_or_zero(gr_totals["pending_total"])
    sc_con_value_total = _float_or_zero(gr_totals["con_value_total"])
    allocated_po_amount = _float_or_zero(po_totals["allocated_po_amount"])

    return {
        "sc_amount": sc_amount,
        "sc_pending_total": sc_pending_total,
        "sc_con_value_total": sc_con_value_total,
        "sc_available_amount": sc_amount - sc_pending_total - sc_con_value_total,
        "allocated_po_amount": allocated_po_amount,
        "unallocated_sc_amount": sc_amount - allocated_po_amount,
    }


def compute_po_budget(config: AppConfig, po_id: str) -> dict[str, float]:
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
              coalesce(sum(case when status = 'pending' then estimated_amount else 0 end), 0)
                as pending_total,
              coalesce(sum(case when status = 'approved' then con_value else 0 end), 0)
                as con_value_total
            from gr_requests
            where po_id = ?
            """,
            (po_id,),
        ).fetchone()

    po_amount = float(po["po_amount"])
    po_pending_total = _float_or_zero(gr_totals["pending_total"])
    po_con_value_total = _float_or_zero(gr_totals["con_value_total"])

    return {
        "po_amount": po_amount,
        "po_pending_total": po_pending_total,
        "po_con_value_total": po_con_value_total,
        "open_po_amount": po_amount - po_pending_total - po_con_value_total,
    }
