import os
from pathlib import Path

from sc_gr_app.api.schemas import fail, ok
from sc_gr_app.config import AppConfig
from sc_gr_app.errors import NotFound, PermissionDenied, ValidationError
from sc_gr_app.identity import get_7_digit_id
from sc_gr_app.services import gr_service, notification_service, po_service, query_service, sc_service, vendor_service
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services.user_service import enable_user, get_user_by_machine_id


def _require_payload_field(payload: dict, field: str):
    value = payload.get(field)
    if value is None or value == "":
        raise ValidationError(f"{field} is required")
    return value


def _attachment_sc_id(entity_type: str, entity_id: str,
                      parent_sc_id: str = None, parent_po_id: str = None) -> str | None:
    """Resolve the sc_id that an attachment belongs to."""
    if entity_type == "sc":
        return entity_id
    if entity_type == "po":
        return parent_sc_id or None
    if entity_type == "gr":
        return parent_sc_id or None
    return None


class ApiBridge:
    def __init__(self, config: AppConfig):
        self.config = config

    def is_dev(self, _payload=None) -> dict:
        return ok(os.getenv("SC_GR_DEV") == "1")

    def switch_dev_role(self, payload) -> dict:
        """Switch the dev user's role between admin and requester. Dev mode only."""
        if os.getenv("SC_GR_DEV") != "1":
            return fail(PermissionDenied("switch_dev_role is only available in dev mode"))
        try:
            payload = self._required_payload(payload)
            role = _require_payload_field(payload, "role")
            if role not in ("admin", "requester"):
                return fail(ValidationError("role must be 'admin' or 'requester'"))
            machine_id = get_7_digit_id()
            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                conn.execute(
                    "UPDATE users SET role = ? WHERE machine_id = ?",
                    (role, machine_id),
                )
                conn.commit()
            user = get_user_by_machine_id(self.config, machine_id)
            return ok(user)
        except Exception as exc:
            return fail(exc)

    def current_user(self, payload=None) -> dict:
        try:
            machine_id = get_7_digit_id()
            return ok(get_user_by_machine_id(self.config, machine_id))
        except PermissionDenied:
            machine_id = get_7_digit_id()
            if os.getenv("SC_GR_DEV") == "1":
                return ok(self._auto_create_dev_user(machine_id))
            return fail(PermissionDenied(f"Machine {machine_id} is not authorized"))
        except Exception as exc:
            return fail(exc)

    def _auto_create_dev_user(self, machine_id: str) -> dict:
        from sc_gr_app.db.connection import connect
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()
        user_id = f"U-{machine_id}"
        with connect(self.config) as conn:
            existing = conn.execute(
                "SELECT user_id FROM users WHERE machine_id = ?",
                (machine_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE users SET status = 'active', role = 'admin' WHERE machine_id = ?",
                    (machine_id,),
                )
            else:
                conn.execute(
                    "INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'admin', ?, 'active', ?, ?)",
                    (user_id, machine_id, machine_id, f"{machine_id}@audi.com.cn", timestamp, timestamp),
                )
            conn.commit()
        return get_user_by_machine_id(self.config, machine_id)

    def _payload(self, payload) -> dict:
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValidationError("payload must be an object")
        return payload

    def _required_payload(self, payload) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("payload must be an object")
        return payload

    def _require_current_user(self) -> dict:
        machine_id = get_7_digit_id()
        return get_user_by_machine_id(self.config, machine_id)

    def get_sc_detail(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.get_sc_detail(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def create_sc_draft(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(sc_service.create_sc_draft(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def submit_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            return ok(sc_service.submit_sc(self.config, current_user, sc_id, data))
        except Exception as exc:
            return fail(exc)

    def update_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            return ok(sc_service.update_sc(self.config, current_user, sc_id, data))
        except Exception as exc:
            return fail(exc)

    def approve_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.approve_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def deny_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.deny_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def close_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.close_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def revoke_sc(self, payload) -> dict:
        """Move a pending SC back to draft."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.revoke_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def delete_sc(self, payload) -> dict:
        """Delete a draft SC and its attachments."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(sc_service.delete_sc(self.config, current_user, sc_id))
        except Exception as exc:
            return fail(exc)

    def create_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(po_service.create_po(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            data = _require_payload_field(payload, "data")
            return ok(po_service.update_po(self.config, current_user, po_id, data))
        except Exception as exc:
            return fail(exc)

    def approve_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            return ok(po_service.approve_po(self.config, current_user, po_id))
        except Exception as exc:
            return fail(exc)

    def finish_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            return ok(po_service.finish_po(self.config, current_user, po_id))
        except Exception as exc:
            return fail(exc)

    def create_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(gr_service.create_gr(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            data = _require_payload_field(payload, "data")
            return ok(gr_service.update_gr(self.config, current_user, gr_id, data))
        except Exception as exc:
            return fail(exc)

    def approve_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            con_value = _require_payload_field(payload, "con_value")
            return ok(gr_service.approve_gr(self.config, current_user, gr_id, con_value))
        except Exception as exc:
            return fail(exc)

    def cancel_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            return ok(gr_service.cancel_gr(self.config, current_user, gr_id))
        except Exception as exc:
            return fail(exc)

    def search_scs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_scs(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_vendors(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            self._require_current_user()
            return ok(query_service.search_vendors(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def create_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(vendor_service.create_vendor(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            vendor_id = _require_payload_field(payload, "vendor_id")
            data = _require_payload_field(payload, "data")
            return ok(vendor_service.update_vendor(self.config, current_user, vendor_id, data))
        except Exception as exc:
            return fail(exc)

    def disable_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            vendor_id = _require_payload_field(payload, "vendor_id")
            return ok(vendor_service.disable_vendor(self.config, current_user, vendor_id))
        except Exception as exc:
            return fail(exc)

    def list_users(self, payload=None) -> dict:
        try:
            self._require_current_user()
            from sc_gr_app.services.user_service import list_active_users
            return ok(list_active_users(self.config))
        except Exception as exc:
            return fail(exc)

    def create_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            from sc_gr_app.services.user_service import create_user
            return ok(create_user(self.config, current_user, data))
        except Exception as exc:
            return fail(exc)

    def update_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            data = _require_payload_field(payload, "data")
            from sc_gr_app.services.user_service import update_user
            return ok(update_user(self.config, current_user, machine_id, data))
        except Exception as exc:
            return fail(exc)

    def disable_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            from sc_gr_app.services.user_service import disable_user
            return ok(disable_user(self.config, current_user, machine_id))
        except Exception as exc:
            return fail(exc)

    def enable_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            return ok(enable_user(self.config, current_user, machine_id))
        except Exception as exc:
            return fail(exc)

    def search_pos(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_pos(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_grs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_grs(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_audit_logs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            return ok(query_service.search_audit_logs(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def get_sc_notification_config(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            return ok(notification_service.get_sc_notification_config(self.config, sc_id))
        except Exception as exc:
            return fail(exc)

    def save_sc_notification_config(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            notification_service.save_sc_notification_config(self.config, sc_id, data)
            return ok()
        except Exception as exc:
            return fail(exc)

    def get_notification_defaults(self, payload=None) -> dict:
        try:
            current_user = self._require_current_user()
            return ok(notification_service.get_notification_defaults(self.config))
        except Exception as exc:
            return fail(exc)

    def save_notification_defaults(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            notification_service.save_notification_defaults(self.config, data)
            return ok()
        except Exception as exc:
            return fail(exc)

    def save_file(self, payload) -> dict:
        """Receive base64 data, show native save dialog, write to chosen path."""
        try:
            import base64
            import tkinter.filedialog as fd
            import tkinter as tk

            payload = self._required_payload(payload)
            filename = _require_payload_field(payload, "filename")
            data_b64 = _require_payload_field(payload, "data")

            file_bytes = base64.b64decode(data_b64)

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            file_path = fd.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                initialfile=filename,
                title="Save Excel File",
            )
            root.destroy()

            if not file_path:
                return ok({"cancelled": True})

            with open(file_path, "wb") as f:
                f.write(file_bytes)

            return ok({"path": file_path})
        except Exception as exc:
            return fail(exc)

    def list_notification_queue(self, payload=None) -> dict:
        try:
            payload = self._payload(payload) or {}
            current_user = self._require_current_user()
            return ok(notification_service.list_notification_queue(
                self.config,
                sc_id=payload.get("sc_id"),
                status=payload.get("status"),
                entity_type=payload.get("entity_type"),
                entity_id=payload.get("entity_id"),
                limit=payload.get("limit", 50),
                offset=payload.get("offset", 0),
            ))
        except Exception as exc:
            return fail(exc)

    # ── Attachment APIs ──────────────────────────────────────────────

    def _attachments_dir(self) -> Path:
        from pathlib import Path
        return Path(self.config.db_path).parent / "attachments"

    def pick_files(self, _payload=None) -> dict:
        """Open native multi-file dialog, return selected file paths only (no copy, no DB)."""
        try:
            import tkinter.filedialog as fd
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_paths = fd.askopenfilenames(title="Select files to attach")
            root.destroy()

            results = []
            for p in file_paths:
                pp = Path(p)
                results.append({
                    "path": str(pp),
                    "name": pp.name,
                    "size": pp.stat().st_size,
                })
            return ok(results)
        except Exception as exc:
            return fail(exc)

    def add_attachments(self, payload) -> dict:
        """Copy selected files into the attachments directory and create DB records."""
        try:
            import shutil
            from datetime import datetime, timezone

            payload = self._required_payload(payload)
            entity_type = _require_payload_field(payload, "entity_type")
            entity_id = _require_payload_field(payload, "entity_id")
            file_paths = _require_payload_field(payload, "file_paths")
            parent_sc_id = payload.get("parent_sc_id")
            parent_po_id = payload.get("parent_po_id")
            current_user = self._require_current_user()

            if entity_type not in ("sc", "po", "gr"):
                return fail(ValidationError("entity_type must be 'sc', 'po', or 'gr'"))
            if not isinstance(file_paths, list) or len(file_paths) == 0:
                return ok([])

            timestamp = datetime.now(timezone.utc).isoformat()
            results = []
            sc_id = _attachment_sc_id(entity_type, entity_id, parent_sc_id, parent_po_id)
            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                for fp in file_paths:
                    src = Path(fp)
                    if not src.exists():
                        continue
                    dest = self._resolve_target_path(
                        entity_type, entity_id, src.name,
                        parent_sc_id=parent_sc_id, parent_po_id=parent_po_id,
                    )
                    shutil.copy2(src, dest)
                    conn.execute(
                        "INSERT INTO attachments (entity_type, entity_id, filename, stored_path, file_size, created_by, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            entity_type, entity_id, dest.name,
                            str(dest), dest.stat().st_size,
                            current_user["user_id"], timestamp,
                        ),
                    )
                    attach_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    attach_record = {
                        "id": attach_id,
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "filename": dest.name,
                        "stored_path": str(dest),
                        "file_size": dest.stat().st_size,
                        "created_by": current_user["user_id"],
                        "created_at": timestamp,
                    }
                    results.append(attach_record)
                    write_audit_log(
                        conn,
                        action_type="add_attachment",
                        object_type="attachment",
                        object_id=str(attach_id),
                        sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None,
                        after=attach_record,
                    )
                conn.commit()
            return ok(results)
        except Exception as exc:
            return fail(exc)

    def _resolve_target_path(self, entity_type: str, entity_id: str, filename: str,
                              parent_sc_id: str = None, parent_po_id: str = None) -> Path:
        import os as _os

        # Build hierarchical path:
        #   attachments/sc/<sc_id>/                  for SC
        #   attachments/sc/<sc_id>/po/<po_id>/        for PO (under its SC)
        #   attachments/sc/<sc_id>/po/<po_id>/gr/<gr_id>/  for GR (under its PO)
        base = self._attachments_dir()
        if entity_type == "sc":
            target_dir = base / "sc" / entity_id
        elif entity_type == "po":
            pid = parent_sc_id or "unknown-sc"
            target_dir = base / "sc" / pid / "po" / entity_id
        elif entity_type == "gr":
            sid = parent_sc_id or "unknown-sc"
            pid = parent_po_id or "unknown-po"
            target_dir = base / "sc" / sid / "po" / pid / "gr" / entity_id
        else:
            target_dir = base / entity_type / entity_id

        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        # Handle filename conflicts with _1, _2, etc.
        if not target.exists():
            return target
        stem, ext = _os.path.splitext(filename)
        counter = 1
        while True:
            candidate = target_dir / f"{stem}_{counter}{ext}"
            if not candidate.exists():
                return candidate
            counter += 1

    def select_files(self, payload) -> dict:
        """Open native file picker, copy selected files to attachments dir."""
        try:
            import shutil
            import tkinter.filedialog as fd
            import tkinter as tk
            from datetime import datetime, timezone

            payload = self._required_payload(payload)
            entity_type = _require_payload_field(payload, "entity_type")
            entity_id = _require_payload_field(payload, "entity_id")
            parent_sc_id = payload.get("parent_sc_id")
            parent_po_id = payload.get("parent_po_id")
            current_user = self._require_current_user()

            if entity_type not in ("sc", "po", "gr"):
                return fail(ValidationError("entity_type must be 'sc', 'po', or 'gr'"))

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_paths = fd.askopenfilenames(title="Select files to attach")
            root.destroy()

            if not file_paths:
                return ok([])

            timestamp = datetime.now(timezone.utc).isoformat()
            results = []
            sc_id = _attachment_sc_id(entity_type, entity_id, parent_sc_id, parent_po_id)
            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                for src in file_paths:
                    src_path = Path(src)
                    filename = src_path.name
                    dest = self._resolve_target_path(
                        entity_type, entity_id, filename,
                        parent_sc_id=parent_sc_id, parent_po_id=parent_po_id,
                    )
                    shutil.copy2(src_path, dest)
                    conn.execute(
                        "INSERT INTO attachments (entity_type, entity_id, filename, stored_path, file_size, created_by, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            entity_type, entity_id, dest.name,
                            str(dest), dest.stat().st_size,
                            current_user["user_id"], timestamp,
                        ),
                    )
                    attach_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    attach_record = {
                        "id": attach_id,
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "filename": dest.name,
                        "stored_path": str(dest),
                        "file_size": dest.stat().st_size,
                        "created_by": current_user["user_id"],
                        "created_at": timestamp,
                    }
                    results.append(attach_record)
                    write_audit_log(
                        conn,
                        action_type="add_attachment",
                        object_type="attachment",
                        object_id=str(attach_id),
                        sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None,
                        after=attach_record,
                    )
                conn.commit()
            return ok(results)
        except Exception as exc:
            return fail(exc)

    def list_attachments(self, payload) -> dict:
        """List all attachments for a given entity."""
        try:
            payload = self._required_payload(payload)
            entity_type = _require_payload_field(payload, "entity_type")
            entity_id = _require_payload_field(payload, "entity_id")
            self._require_current_user()

            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                rows = conn.execute(
                    "SELECT id, entity_type, entity_id, filename, file_size, created_by, created_at "
                    "FROM attachments WHERE entity_type = ? AND entity_id = ? "
                    "ORDER BY created_at DESC",
                    (entity_type, entity_id),
                ).fetchall()
            return ok([{
                "id": r["id"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "filename": r["filename"],
                "file_size": r["file_size"],
                "created_by": r["created_by"],
                "created_at": r["created_at"],
            } for r in rows])
        except Exception as exc:
            return fail(exc)

    def delete_attachment(self, payload) -> dict:
        """Delete an attachment record and its file from disk."""
        try:
            payload = self._required_payload(payload)
            attachment_id = _require_payload_field(payload, "id")
            current_user = self._require_current_user()

            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                row = conn.execute(
                    "SELECT id, entity_type, entity_id, filename, stored_path, file_size, created_by, created_at "
                    "FROM attachments WHERE id = ?",
                    (attachment_id,),
                ).fetchone()
                if not row:
                    return fail(NotFound(f"Attachment {attachment_id} not found"))

                # Resolve sc_id for audit
                sc_id = None
                if row["entity_type"] == "sc":
                    sc_id = row["entity_id"]
                elif row["entity_type"] == "po":
                    sc_lookup = conn.execute(
                        "SELECT sc_id FROM pos WHERE po_id = ?", (row["entity_id"],)
                    ).fetchone()
                    if sc_lookup:
                        sc_id = sc_lookup["sc_id"]
                elif row["entity_type"] == "gr":
                    sc_lookup = conn.execute(
                        "SELECT po.sc_id FROM gr_requests gr "
                        "JOIN pos po ON po.po_id = gr.po_id "
                        "WHERE gr.gr_id = ?", (row["entity_id"],)
                    ).fetchone()
                    if sc_lookup:
                        sc_id = sc_lookup["sc_id"]

                before = {
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "filename": row["filename"],
                    "stored_path": row["stored_path"],
                    "file_size": row["file_size"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                }
                write_audit_log(
                    conn,
                    action_type="delete_attachment",
                    object_type="attachment",
                    object_id=str(attachment_id),
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=None,
                )

                stored_path = row["stored_path"]
                conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
                conn.commit()
            try:
                Path(stored_path).unlink(missing_ok=True)
            except OSError:
                pass
            return ok({"deleted": True})
        except Exception as exc:
            return fail(exc)

    def open_attachment(self, payload) -> dict:
        """Open an attachment file with the OS default handler."""
        try:
            import os as _os
            payload = self._required_payload(payload)
            attachment_id = _require_payload_field(payload, "id")
            self._require_current_user()

            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                row = conn.execute(
                    "SELECT id, stored_path FROM attachments WHERE id = ?",
                    (attachment_id,),
                ).fetchone()
            if not row:
                return fail(NotFound(f"Attachment {attachment_id} not found"))
            _os.startfile(row["stored_path"])
            return ok({"opened": True})
        except Exception as exc:
            return fail(exc)

    def open_attachment_dir(self, payload) -> dict:
        """Open the attachments directory for an entity in File Explorer."""
        try:
            import os as _os
            payload = self._required_payload(payload)
            entity_type = _require_payload_field(payload, "entity_type")
            entity_id = _require_payload_field(payload, "entity_id")
            parent_sc_id = payload.get("parent_sc_id")
            parent_po_id = payload.get("parent_po_id")
            self._require_current_user()

            # Compute the same directory path used for storing attachments
            dummy = self._resolve_target_path(
                entity_type, entity_id, ".dummy",
                parent_sc_id=parent_sc_id, parent_po_id=parent_po_id,
            )
            target_dir = dummy.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            _os.startfile(str(target_dir))
            return ok({"opened": True})
        except Exception as exc:
            return fail(exc)
