import os
import sys
from pathlib import Path

from sc_gr_app.api.schemas import fail, ok
from sc_gr_app.config import AppConfig
from sc_gr_app.errors import NotFound, PermissionDenied, ValidationError
from sc_gr_app.identity import get_7_digit_id
from sc_gr_app.services import export_service, gr_service, notification_service, po_service, query_service, sc_service, vendor_service
from sc_gr_app.services.record_service import format_timestamp, write_operation_record
from sc_gr_app.services.user_service import enable_user, get_user_by_machine_id, register_user


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


def _format_entity_timestamps(entity: dict) -> dict:
    """Format timestamp fields in an entity dict for display."""
    _TIMESTAMP_FIELDS = (
        "created_at", "updated_at", "pending_date", "approved_date",
        "finished_at", "denied_at", "confirmed_at", "active_date",
        "approved_at", "sent_at", "submitted_date",
    )
    for f in _TIMESTAMP_FIELDS:
        if f in entity and entity[f]:
            entity[f] = format_timestamp(entity[f])
    return entity


def _format_list_timestamps(items: list) -> list:
    """Format timestamps in each entity of a list."""
    if not items:
        return items
    return [_format_entity_timestamps(item) for item in items]


class ApiBridge:
    def __init__(self, config: AppConfig):
        self.config = config

    def is_dev(self, _payload=None) -> dict:
        return ok(os.getenv("SC_GR_DEV") == "1")

    def is_beta(self, _payload=None) -> dict:
        return ok(os.getenv("SC_GR_BETA") == "1")

    def get_version(self, _payload=None) -> dict:
        from sc_gr_app import __version__
        return ok(__version__)

    def install_update(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            version = _require_payload_field(payload, "version")
            installer_name = _require_payload_field(payload, "installer_name")
            expected_hash = _require_payload_field(payload, "sha256")
        except Exception as exc:
            return fail(exc)

        from sc_gr_app.update import _releases_dir, sha256_file

        releases_dir = _releases_dir()
        installer_src = releases_dir / installer_name
        temp_dir = Path(os.getenv("TEMP")) / "pomp-update"

        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return fail(exc)

        installer_dst = temp_dir / installer_name

        try:
            import shutil
            shutil.copy2(str(installer_src), str(installer_dst))
        except OSError as exc:
            return fail(exc)

        actual_hash = sha256_file(installer_dst)
        if actual_hash != expected_hash:
            return fail(Exception(
                "Update file is corrupted. Contact your administrator."
            ))

        install_dir = Path(sys.executable).parent
        try:
            import subprocess
            subprocess.Popen(
                [
                    str(installer_dst),
                    "/SILENT",
                    f"/DIR={install_dir}",
                ],
            )
        except OSError as exc:
            return fail(exc)

        os._exit(0)
        return ok(None)  # unreachable, but satisfies the return type

    def switch_dev_role(self, payload) -> dict:
        """Switch the dev user's role between admin and requester. Dev mode only."""
        if os.getenv("SC_GR_DEV") != "1" and os.getenv("SC_GR_BETA") != "1":
            return fail(PermissionDenied("switch_dev_role is only available in dev or beta mode"))
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
            return ok(_format_entity_timestamps(user))
        except Exception as exc:
            return fail(exc)

    def current_user(self, payload=None) -> dict:
        try:
            machine_id = get_7_digit_id()
            return ok(_format_entity_timestamps(get_user_by_machine_id(self.config, machine_id)))
        except PermissionDenied:
            machine_id = get_7_digit_id()
            if os.getenv("SC_GR_DEV") == "1":
                return ok(_format_entity_timestamps(self._auto_create_dev_user(machine_id)))
            return fail(PermissionDenied(f"Machine {machine_id} is not authorized"))
        except Exception as exc:
            return fail(exc)

    def detect_machine_id(self, _payload=None) -> dict:
        """Return the current machine ID. Works for unregistered machines."""
        return ok(get_7_digit_id())

    def register_user(self, payload) -> dict:
        """Register a new user. No auth required — only for unregistered machines."""
        try:
            payload = self._required_payload(payload)
            machine_id = get_7_digit_id()
            user_name = _require_payload_field(payload, "user_name")
            email = _require_payload_field(payload, "email")

            # Verify this machine is NOT already registered
            try:
                get_user_by_machine_id(self.config, machine_id)
                return fail(ValidationError("This machine is already registered."))
            except PermissionDenied:
                pass  # Expected — machine not registered yet

            user = register_user(self.config, machine_id, user_name, email)
            return ok(_format_entity_timestamps(user))
        except ValidationError as e:
            return fail(e)

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
            result = sc_service.get_sc_detail(self.config, current_user, sc_id)
            if isinstance(result, dict):
                for key in ("sc",):
                    if key in result:
                        result[key] = _format_entity_timestamps(result[key])
                for key in ("pos", "grs", "operation_records"):
                    if key in result:
                        result[key] = _format_list_timestamps(result[key])
            return ok(result)
        except Exception as exc:
            return fail(exc)

    def create_sc_draft(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(_format_entity_timestamps(sc_service.create_sc_draft(self.config, current_user, data)))
        except Exception as exc:
            return fail(exc)

    def submit_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            result = sc_service.submit_sc(self.config, current_user, sc_id, data)
            self._auto_open_outlook_draft("sc", sc_id, "submit")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def update_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            data = _require_payload_field(payload, "data")
            return ok(_format_entity_timestamps(sc_service.update_sc(self.config, current_user, sc_id, data)))
        except Exception as exc:
            return fail(exc)

    def approve_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            result = sc_service.approve_sc(self.config, current_user, sc_id)
            self._auto_open_outlook_draft("sc", sc_id, "approve")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def deny_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            result = sc_service.deny_sc(self.config, current_user, sc_id)
            self._auto_open_outlook_draft("sc", sc_id, "deny")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def finish_sc(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            result = sc_service.finish_sc(self.config, current_user, sc_id)
            self._auto_open_outlook_draft("sc", sc_id, "finish")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def confirm_sc(self, payload) -> dict:
        """Admin confirms an SC in manager_confirm status."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            result = sc_service.confirm_sc(self.config, current_user, sc_id)
            self._auto_open_outlook_draft("sc", sc_id, "confirm")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def recall_sc(self, payload) -> dict:
        """Recall SC back to draft."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            result = sc_service.recall_sc(self.config, current_user, sc_id)
            self._auto_open_outlook_draft("sc", sc_id, "recall")
            return ok(_format_entity_timestamps(result))
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

    def transfer_sc(self, payload) -> dict:
        """Transfer SC ownership to another user."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            new_requester_id = _require_payload_field(payload, "new_requester_id")
            return ok(_format_entity_timestamps(sc_service.transfer_sc(self.config, current_user, sc_id, new_requester_id)))
        except Exception as exc:
            return fail(exc)

    def create_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            result = po_service.create_po(self.config, current_user, data)
            self._auto_open_outlook_draft("po", result["po_id"], "submit")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def update_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            data = _require_payload_field(payload, "data")
            return ok(_format_entity_timestamps(po_service.update_po(self.config, current_user, po_id, data)))
        except Exception as exc:
            return fail(exc)

    def finish_po(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            result = po_service.finish_po(self.config, current_user, po_id)
            self._auto_open_outlook_draft("po", po_id, "finish")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def submit_po(self, payload) -> dict:
        """Submit a draft PO to active (admin or SC owner)."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            result = po_service.submit_po(self.config, current_user, po_id)
            self._auto_open_outlook_draft("po", po_id, "submit")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def recall_po(self, payload) -> dict:
        """Recall PO back to draft."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            result = po_service.recall_po(self.config, current_user, po_id)
            self._auto_open_outlook_draft("po", po_id, "recall")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def delete_po(self, payload) -> dict:
        """Delete a draft PO (admin or SC owner)."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            return ok(po_service.delete_po(self.config, current_user, po_id))
        except Exception as exc:
            return fail(exc)

    def create_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            file_paths = data.pop("_attachments", None) or []
            parent_sc_id = data.pop("_parent_sc_id", None)
            parent_po_id = data.pop("_parent_po_id", None)
            result = gr_service.create_gr(self.config, current_user, data)
            if file_paths:
                self._add_attachments_inline(
                    entity_type="gr", entity_id=result["gr_id"],
                    file_paths=file_paths, current_user=current_user,
                    parent_sc_id=parent_sc_id, parent_po_id=parent_po_id,
                )
            self._auto_open_outlook_draft("gr", result["gr_id"], "submit")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def update_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            data = _require_payload_field(payload, "data")
            return ok(_format_entity_timestamps(gr_service.update_gr(self.config, current_user, gr_id, data)))
        except Exception as exc:
            return fail(exc)

    def approve_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            con_value = payload.get("con_value")  # optional — auto-calculated from tax_rate if omitted
            result = gr_service.approve_gr(self.config, current_user, gr_id, con_value)
            self._auto_open_outlook_draft("gr", gr_id, "approve")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def deny_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            result = gr_service.deny_gr(self.config, current_user, gr_id)
            self._auto_open_outlook_draft("gr", gr_id, "deny")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def finish_gr(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            confirm_cascade = payload.get("confirm_cascade", False)
            result = gr_service.finish_gr(self.config, current_user, gr_id, confirm_cascade)

            if isinstance(result, dict) and "needs_cascade" in result:
                # LD GR needs cascade confirmation — return directly (ok:true, data has needs_cascade)
                return ok(result)
            elif isinstance(result, dict) and "gr" in result:
                # Cascade executed successfully
                primary_gr = _format_entity_timestamps(result["gr"])
                self._auto_open_outlook_draft("gr", gr_id, "finish")
                self._auto_open_outlook_draft("po", result["po_finished"], "finish")
                return ok(primary_gr)
            else:
                # Normal finish: result is the GR dict
                self._auto_open_outlook_draft("gr", gr_id, "finish")
                return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def confirm_gr(self, payload) -> dict:
        """Admin confirms a GR in manager_confirm status."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            result = gr_service.confirm_gr(self.config, current_user, gr_id)
            self._auto_open_outlook_draft("gr", gr_id, "confirm")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def submit_gr(self, payload) -> dict:
        """Submit a draft GR to pending (admin or SC owner)."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            result = gr_service.submit_gr(self.config, current_user, gr_id)
            self._auto_open_outlook_draft("gr", gr_id, "submit")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def recall_gr(self, payload) -> dict:
        """Recall GR back to draft."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            result = gr_service.recall_gr(self.config, current_user, gr_id)
            self._auto_open_outlook_draft("gr", gr_id, "recall")
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def delete_gr(self, payload) -> dict:
        """Delete a draft GR (admin or GR owner)."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            gr_id = _require_payload_field(payload, "gr_id")
            return ok(gr_service.delete_gr(self.config, current_user, gr_id))
        except Exception as exc:
            return fail(exc)

    def workbench_data(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            result = query_service.workbench_data(self.config, current_user)
            # Format timestamps in workbench rows (e.g., gr.created_at)
            for category in ("sc", "po", "gr"):
                if category in result:
                    for status_key in result[category]:
                        result[category][status_key]["rows"] = _format_list_timestamps(
                            result[category][status_key]["rows"]
                        )
            return ok(result)
        except Exception as exc:
            return fail(exc)

    def search_scs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            result = query_service.search_scs(self.config, **payload)
            return ok({"rows": _format_list_timestamps(result["rows"]), "total": result["total"]})
        except Exception as exc:
            return fail(exc)

    def search_vendors(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            self._require_current_user()
            result = query_service.search_vendors(self.config, **payload)
            return ok({"rows": _format_list_timestamps(result["rows"]), "total": result["total"]})
        except Exception as exc:
            return fail(exc)

    def create_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            return ok(_format_entity_timestamps(vendor_service.create_vendor(self.config, current_user, data)))
        except Exception as exc:
            return fail(exc)

    def update_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            vendor_id = _require_payload_field(payload, "vendor_id")
            data = _require_payload_field(payload, "data")
            return ok(_format_entity_timestamps(vendor_service.update_vendor(self.config, current_user, vendor_id, data)))
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

    def delete_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            vendor_id = _require_payload_field(payload, "vendor_id")
            return ok(vendor_service.delete_vendor(self.config, current_user, vendor_id))
        except Exception as exc:
            return fail(exc)

    def check_ksrm_duplicate(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            self._require_current_user()
            ksrm_code = _require_payload_field(payload, "ksrm_code")
            exclude_vendor_id = payload.get("exclude_vendor_id")
            result = vendor_service.check_ksrm_duplicate(self.config, ksrm_code, exclude_vendor_id)
            return ok({"duplicate": result})
        except Exception as exc:
            return fail(exc)

    def add_sc_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            vendor_id = _require_payload_field(payload, "vendor_id")
            from sc_gr_app.services import sc_service
            return ok(sc_service.add_sc_vendor(self.config, current_user, sc_id, vendor_id))
        except Exception as exc:
            return fail(exc)

    def remove_sc_vendor(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            sc_id = _require_payload_field(payload, "sc_id")
            vendor_id = _require_payload_field(payload, "vendor_id")
            from sc_gr_app.services import sc_service
            return ok(sc_service.remove_sc_vendor(self.config, current_user, sc_id, vendor_id))
        except Exception as exc:
            return fail(exc)

    def preview_vendor_import(self, _payload=None) -> dict:
        """Open file dialog for Excel/CSV, parse and return preview with validation."""
        try:
            import tkinter.filedialog as fd
            import tkinter as tk

            self._require_current_user()
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = fd.askopenfilename(
                title="Select vendor file to import",
                filetypes=[
                    ("Excel & CSV files", "*.xlsx *.xls *.csv"),
                    ("Excel files", "*.xlsx *.xls"),
                    ("CSV files", "*.csv"),
                    ("All files", "*.*"),
                ],
            )
            root.destroy()

            if not file_path:
                return ok(None)

            preview = vendor_service.preview_import(self.config, file_path)
            return ok({"file_path": file_path, "rows": preview})
        except Exception as exc:
            return fail(exc)

    def confirm_vendor_import(self, payload) -> dict:
        """Import validated vendor rows into the database."""
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            rows = _require_payload_field(payload, "rows")
            result = vendor_service.execute_import(self.config, current_user, rows)
            return ok(result)
        except Exception as exc:
            return fail(exc)

    def list_users(self, payload=None) -> dict:
        try:
            self._require_current_user()
            from sc_gr_app.services.user_service import list_active_users
            return ok(_format_list_timestamps(list_active_users(self.config)))
        except Exception as exc:
            return fail(exc)

    def create_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            data = _require_payload_field(payload, "data")
            from sc_gr_app.services.user_service import create_user
            return ok(_format_entity_timestamps(create_user(self.config, current_user, data)))
        except Exception as exc:
            return fail(exc)

    def update_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            data = _require_payload_field(payload, "data")
            from sc_gr_app.services.user_service import update_user
            return ok(_format_entity_timestamps(update_user(self.config, current_user, machine_id, data)))
        except Exception as exc:
            return fail(exc)

    def disable_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            from sc_gr_app.services.user_service import disable_user
            return ok(_format_entity_timestamps(disable_user(self.config, current_user, machine_id)))
        except Exception as exc:
            return fail(exc)

    def enable_user(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            machine_id = _require_payload_field(payload, "machine_id")
            return ok(_format_entity_timestamps(enable_user(self.config, current_user, machine_id)))
        except Exception as exc:
            return fail(exc)

    def search_pos(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            result = query_service.search_pos(self.config, **payload)
            return ok({"rows": _format_list_timestamps(result["rows"]), "total": result["total"]})
        except Exception as exc:
            return fail(exc)

    def search_grs(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            result = query_service.search_grs(self.config, **payload)
            return ok({"rows": _format_list_timestamps(result["rows"]), "total": result["total"]})
        except Exception as exc:
            return fail(exc)

    def search_operation_records(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            payload = {**payload, "current_user": current_user}
            result = query_service.search_operation_records(self.config, **payload)
            return ok({"rows": _format_list_timestamps(result["rows"]), "total": result["total"]})
        except Exception as exc:
            return fail(exc)

    def get_po_notification_config(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            return ok(notification_service.get_po_notification_config(self.config, po_id))
        except Exception as exc:
            return fail(exc)

    def save_po_notification_config(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            data = _require_payload_field(payload, "data")
            from sc_gr_app.db.connection import connect
            from sc_gr_app.errors import PermissionDenied, NotFound
            with connect(self.config) as conn:
                po = conn.execute(
                    "SELECT sc.requester_id FROM pos po JOIN sc_records sc ON sc.sc_id = po.sc_id WHERE po.po_id = ?",
                    (po_id,),
                ).fetchone()
            if not po:
                raise NotFound("PO not found")
            if current_user.get("role") != "admin" and current_user.get("user_id") != po["requester_id"]:
                raise PermissionDenied("Only the SC owner or admin can modify notification settings")
            notification_service.save_po_notification_config(self.config, po_id, data)
            return ok()
        except Exception as exc:
            return fail(exc)

    def get_po_custom_schedules(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            return ok(_format_list_timestamps(notification_service.get_po_custom_schedules(self.config, po_id)))
        except Exception as exc:
            return fail(exc)

    def save_po_custom_schedules(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            schedules = _require_payload_field(payload, "schedules")
            from sc_gr_app.db.connection import connect
            from sc_gr_app.errors import PermissionDenied, NotFound
            with connect(self.config) as conn:
                po = conn.execute(
                    """SELECT sc.requester_id FROM pos po
                       JOIN sc_records sc ON sc.sc_id = po.sc_id
                       WHERE po.po_id = ?""", (po_id,),
                ).fetchone()
            if not po:
                raise NotFound("PO not found")
            if current_user.get("role") != "admin" and current_user.get("user_id") != po["requester_id"]:
                raise PermissionDenied("Only the SC owner or admin can modify custom schedules")
            notification_service.save_po_custom_schedules(self.config, po_id, schedules)
            return ok()
        except Exception as exc:
            return fail(exc)

    def get_po_fc_budget(self, payload) -> dict:
        """Return FC budget for a given PO (FC)."""
        try:
            payload = self._required_payload(payload)
            self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            from sc_gr_app.services.budget_service import compute_po_fc_budget
            return ok(compute_po_fc_budget(self.config, po_id))
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
            from sc_gr_app.rbac import require_admin
            require_admin(current_user)
            data = _require_payload_field(payload, "data")
            notification_service.save_notification_defaults(self.config, data)
            return ok()
        except Exception as exc:
            return fail(exc)

    def export_scs_cascade(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            filters = payload.get("filters", {})
            sort = payload.get("sort", "created_at")
            direction = payload.get("direction", "desc")
            cascade = payload.get("cascade", {"po": False, "gr": False})
            selected_ids = payload.get("selected_ids")

            cascade_options = {"po": bool(cascade.get("po")), "gr": bool(cascade.get("gr"))}
            entity_types = {"SC"}
            if cascade_options["po"]:
                entity_types.add("PO")
            if cascade_options["po"] and cascade_options["gr"]:
                entity_types.add("GR")

            cascade_rows = export_service.build_cascade_rows(
                self.config, "sc", filters, sort, direction,
                cascade_options, current_user, selected_ids,
            )
            statistics = export_service.compute_statistics(
                self.config, entity_types, filters, selected_ids,
            )
            return ok({"cascade_rows": cascade_rows, "statistics": statistics})
        except Exception as exc:
            return fail(exc)

    def export_pos_cascade(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            filters = payload.get("filters", {})
            sort = payload.get("sort", "created_at")
            direction = payload.get("direction", "desc")
            cascade = payload.get("cascade", {"gr": False})
            selected_ids = payload.get("selected_ids")

            cascade_options = {"gr": bool(cascade.get("gr"))}
            entity_types = {"PO"}
            if cascade_options["gr"]:
                entity_types.add("GR")

            cascade_rows = export_service.build_cascade_rows(
                self.config, "po", filters, sort, direction,
                cascade_options, current_user=current_user, selected_ids=selected_ids,
            )
            statistics = export_service.compute_statistics(
                self.config, entity_types, filters, selected_ids,
            )
            return ok({"cascade_rows": cascade_rows, "statistics": statistics})
        except Exception as exc:
            return fail(exc)

    def export_grs_with_stats(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            filters = payload.get("filters", {})
            sort = payload.get("sort", "created_at")
            direction = payload.get("direction", "desc")
            selected_ids = payload.get("selected_ids")

            cascade_rows = export_service.build_cascade_rows(
                self.config, "gr", filters, sort, direction,
                cascade_options={}, current_user=current_user, selected_ids=selected_ids,
            )
            statistics = export_service.compute_statistics(
                self.config, {"GR"}, filters, selected_ids,
            )
            return ok({"cascade_rows": cascade_rows, "statistics": statistics})
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
            result = notification_service.list_notification_queue(
                self.config,
                sc_id=payload.get("sc_id"),
                status=payload.get("status"),
                entity_type=payload.get("entity_type"),
                entity_id=payload.get("entity_id"),
                limit=payload.get("limit", 50),
                offset=payload.get("offset", 0),
            )
            result["items"] = _format_list_timestamps(result["items"])
            return ok(result)
        except Exception as exc:
            return fail(exc)

    def generate_email_draft(self, payload) -> dict:
        """Generate email content for preview. Returns draft data."""
        try:
            user = self._require_current_user()
            payload = self._required_payload(payload)
            entry_id = _require_payload_field(payload, "entry_id")

            from sc_gr_app.db.connection import connect
            from sc_gr_app.notification import sender
            with connect(self.config) as conn:
                entry = conn.execute(
                    "SELECT * FROM notification_queue WHERE id = ?", (entry_id,)
                ).fetchone()
                if not entry:
                    return fail(NotFound(f"Queue entry {entry_id} not found"))
                draft = sender.generate_draft(conn, dict(entry))
                return ok(draft)
        except (PermissionDenied, ValidationError, NotFound) as e:
            return fail(e)

    def open_email_draft_in_outlook(self, payload) -> dict:
        """Generate email via Outlook COM and open in Outlook for manual send."""
        try:
            user = self._require_current_user()
            payload = self._required_payload(payload)
            entry_id = _require_payload_field(payload, "entry_id")

            import pythoncom
            import win32com.client
            from sc_gr_app.db.connection import connect
            from sc_gr_app.notification import sender

            with connect(self.config) as conn:
                entry = conn.execute(
                    "SELECT * FROM notification_queue WHERE id = ?", (entry_id,)
                ).fetchone()
                if not entry:
                    return fail(NotFound(f"Queue entry {entry_id} not found"))
                draft = sender.generate_draft(conn, dict(entry))

            pythoncom.CoInitialize()
            try:
                outlook = win32com.client.Dispatch("Outlook.Application")
                mail = outlook.CreateItem(0)
                mail.Subject = draft["subject"]
                mail.HTMLBody = draft["html_body"]
                mail.To = "; ".join(draft["to_addresses"])
                if draft["cc_addresses"]:
                    mail.CC = "; ".join(draft["cc_addresses"])
                for att_path in draft["attachment_paths"]:
                    try:
                        mail.Attachments.Add(att_path)
                    except Exception:
                        pass
                mail.Save()
                mail.Display()
            finally:
                pythoncom.CoUninitialize()

            return ok({"message": "Draft opened in Outlook"})
        except (PermissionDenied, ValidationError, NotFound) as e:
            return fail(e)

    def open_entity_email(self, payload) -> dict:
        """Generate and open an email draft for an SC/PO/GR entity in Outlook.

        Uses notification config to determine recipients (requester as To,
        admin_recipients + per-entity CC + default CC as Cc).
        """
        try:
            user = self._require_current_user()
            payload = self._required_payload(payload)
            entity_type = _require_payload_field(payload, "entity_type")
            entity_id = _require_payload_field(payload, "entity_id")

            if entity_type not in ("sc", "po", "gr"):
                return fail(ValidationError(f"Invalid entity_type: {entity_type}"))

            import json
            import pythoncom
            import win32com.client
            from sc_gr_app.db.connection import connect
            from sc_gr_app.notification import sender

            with connect(self.config) as conn:
                # Fetch entity
                entity_info = {}
                if entity_type == "sc":
                    row = conn.execute(
                        "SELECT * FROM sc_records WHERE sc_id = ?", (entity_id,)
                    ).fetchone()
                elif entity_type == "po":
                    row = conn.execute(
                        """SELECT p.*, v.vendor_name FROM pos p
                           LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
                           WHERE p.po_id = ?""", (entity_id,)
                    ).fetchone()
                elif entity_type == "gr":
                    row = conn.execute(
                        "SELECT * FROM gr_requests WHERE gr_id = ?", (entity_id,)
                    ).fetchone()

                if not row:
                    return fail(NotFound(f"{entity_type.upper()} {entity_id} not found"))
                entity_info = dict(row)

                requester_id = entity_info.get("requester_id") or ""
                to_ids = [requester_id] if requester_id else []

                # Cc: admin_recipients + per-entity CC + default CC
                cc_ids = []
                admin_setting = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.admin_recipients'"
                ).fetchone()
                if admin_setting:
                    cc_ids.extend(json.loads(admin_setting["setting_value"]) or [])

                default_cc = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.default_cc'"
                ).fetchone()
                if default_cc:
                    cc_ids.extend(json.loads(default_cc["setting_value"]) or [])

                # Per-entity CC config
                if entity_type == "sc":
                    config_row = conn.execute(
                        "SELECT cc_user_ids FROM notification_config WHERE entity_type = 'sc' AND entity_id = ? AND enabled = 1",
                        (entity_id,),
                    ).fetchone()
                elif entity_type == "po":
                    config_row = conn.execute(
                        "SELECT cc_user_ids FROM notification_config WHERE entity_type = 'po' AND entity_id = ? AND enabled = 1",
                        (entity_id,),
                    ).fetchone()
                elif entity_type == "gr":
                    gr_po = conn.execute(
                        "SELECT po_id FROM gr_requests WHERE gr_id = ?", (entity_id,)
                    ).fetchone()
                    if gr_po:
                        config_row = conn.execute(
                            "SELECT cc_user_ids FROM notification_config WHERE entity_type = 'po' AND entity_id = ? AND enabled = 1",
                            (gr_po["po_id"],),
                        ).fetchone()
                    else:
                        config_row = None

                if config_row:
                    extra_cc = json.loads(config_row["cc_user_ids"])
                    cc_ids.extend(extra_cc or [])

                # Deduplicate and remove To recipients from CC
                seen = set()
                unique_cc = []
                for uid in cc_ids:
                    if uid and uid not in seen:
                        seen.add(uid)
                        unique_cc.append(uid)
                cc_ids = [uid for uid in unique_cc if uid not in to_ids]

                # If no To recipients, promote CC to To
                if not to_ids:
                    if cc_ids:
                        to_ids = cc_ids
                        cc_ids = []
                    else:
                        to_ids = [user["user_id"]]

                # Build synthetic entry for generate_draft
                entry = {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "event_type": "status_change",
                    "event_key": "notify",
                    "to_recipients": json.dumps(to_ids),
                    "cc_recipients": json.dumps(cc_ids),
                    "actor_id": user["user_id"],
                }
                draft = sender.generate_draft(conn, entry)

            pythoncom.CoInitialize()
            try:
                outlook = win32com.client.Dispatch("Outlook.Application")
                mail = outlook.CreateItem(0)
                mail.Subject = draft["subject"]
                mail.HTMLBody = draft["html_body"]
                mail.To = "; ".join(draft["to_addresses"])
                if draft["cc_addresses"]:
                    mail.CC = "; ".join(draft["cc_addresses"])
                for att_path in draft["attachment_paths"]:
                    try:
                        mail.Attachments.Add(att_path)
                    except Exception:
                        pass
                mail.Save()
                mail.Display()
            finally:
                pythoncom.CoUninitialize()

            return ok({"message": "Draft opened in Outlook"})
        except (PermissionDenied, ValidationError, NotFound) as e:
            return fail(e)

    def _auto_open_outlook_draft(self, entity_type: str, entity_id: str, event_key: str = "") -> None:
        """After a status transition, find the matching pending queue entry
        and open the email draft in Outlook. Best-effort — failures are
        logged but never raise."""
        try:
            import pythoncom
            import win32com.client
            from sc_gr_app.db.connection import connect
            from sc_gr_app.notification import sender

            with connect(self.config) as conn:
                if event_key:
                    entry = conn.execute(
                        """SELECT * FROM notification_queue
                           WHERE entity_type = ? AND entity_id = ? AND status = 'pending'
                             AND event_key = ?
                           ORDER BY id DESC LIMIT 1""",
                        (entity_type, entity_id, event_key),
                    ).fetchone()
                else:
                    entry = conn.execute(
                        """SELECT * FROM notification_queue
                           WHERE entity_type = ? AND entity_id = ? AND status = 'pending'
                           ORDER BY id DESC LIMIT 1""",
                        (entity_type, entity_id),
                    ).fetchone()
                if not entry:
                    return
                draft = sender.generate_draft(conn, dict(entry))

            pythoncom.CoInitialize()
            try:
                outlook = win32com.client.Dispatch("Outlook.Application")
                mail = outlook.CreateItem(0)
                mail.Subject = draft["subject"]
                mail.HTMLBody = draft["html_body"]
                mail.To = "; ".join(draft["to_addresses"])
                if draft["cc_addresses"]:
                    mail.CC = "; ".join(draft["cc_addresses"])
                for att_path in draft["attachment_paths"]:
                    try:
                        mail.Attachments.Add(att_path)
                    except Exception:
                        pass
                mail.Save()
                mail.Display()
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            pass  # best-effort; don't block the operation

    # ── Attachment APIs ──────────────────────────────────────────────

    def _attachments_dir(self) -> Path:
        from pathlib import Path
        from sc_gr_app.db.connection import connect
        # Check for custom attachments directory in app_settings
        try:
            with connect(self.config) as conn:
                row = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key = 'attachments_dir'"
                ).fetchone()
                if row and row["setting_value"]:
                    custom = Path(row["setting_value"])
                    if custom.exists() or custom.parent.exists():
                        return custom
        except Exception:
            pass
        return Path(self.config.db_path).parent / "attachments"

    def get_attachments_dir(self, _payload=None) -> dict:
        """Return the current attachments directory path."""
        try:
            self._require_current_user()
            return ok({"path": str(self._attachments_dir())})
        except Exception as exc:
            return fail(exc)

    def set_attachments_dir(self, payload) -> dict:
        """Set a custom attachments directory. Old files stay in place; new files go to the new path."""
        try:
            from sc_gr_app.db.connection import connect
            from datetime import datetime, timezone
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            from sc_gr_app.rbac import require_admin
            require_admin(current_user)
            new_path = _require_payload_field(payload, "path")
            target = Path(new_path)
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
            if not target.is_dir():
                return fail(ValidationError("Path is not a directory"))
            timestamp = datetime.now(timezone.utc).isoformat()
            with connect(self.config) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                    ("attachments_dir", str(target), timestamp),
                )
                conn.commit()
            return ok({"path": str(target)})
        except Exception as exc:
            return fail(exc)

    def get_sender_email(self, _payload=None) -> dict:
        """Return the configured notification sender email address."""
        try:
            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                row = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.sender_email'"
                ).fetchone()
                return ok({"email": row["setting_value"] if row else ""})
        except Exception as exc:
            return fail(exc)

    def set_sender_email(self, payload) -> dict:
        """Set the notification sender email address."""
        try:
            from sc_gr_app.db.connection import connect
            from datetime import datetime, timezone
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            from sc_gr_app.rbac import require_admin
            require_admin(current_user)
            email = _require_payload_field(payload, "email")
            timestamp = datetime.now(timezone.utc).isoformat()
            with connect(self.config) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                    ("notify.sender_email", email.strip(), timestamp),
                )
                conn.commit()
            return ok({"email": email.strip()})
        except Exception as exc:
            return fail(exc)

    def pick_folder(self, _payload=None) -> dict:
        """Open native folder picker dialog, return chosen path."""
        try:
            import tkinter.filedialog as fd
            import tkinter as tk
            self._require_current_user()
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = fd.askdirectory(title="Select attachments folder")
            root.destroy()
            if not folder:
                return ok({"cancelled": True})
            return ok({"path": str(Path(folder))})
        except Exception as exc:
            return fail(exc)

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

    def _add_attachments_inline(self, entity_type, entity_id, file_paths, current_user,
                                  parent_sc_id=None, parent_po_id=None):
        """Copy files and create DB records inline — best-effort, never raises.

        Used internally so create_gr / submit_sc can attach files before
        _auto_open_outlook_draft runs.
        """
        try:
            import shutil
            from datetime import datetime, timezone
            if not isinstance(file_paths, list) or len(file_paths) == 0:
                return
            timestamp = datetime.now(timezone.utc).isoformat()
            sc_id = _attachment_sc_id(entity_type, entity_id, parent_sc_id, parent_po_id)
            from sc_gr_app.db.connection import connect
            with connect(self.config) as conn:
                conn.execute("BEGIN IMMEDIATE")
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
                    write_operation_record(
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
        except Exception:
            pass  # best-effort; never block the parent operation

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
                conn.execute("BEGIN IMMEDIATE")
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
                    write_operation_record(
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
                conn.execute("BEGIN IMMEDIATE")
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
                    write_operation_record(
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
            return ok(_format_list_timestamps([{
                "id": r["id"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "filename": r["filename"],
                "file_size": r["file_size"],
                "created_by": r["created_by"],
                "created_at": r["created_at"],
            } for r in rows]))
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

                conn.execute("BEGIN IMMEDIATE")
                write_operation_record(
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

    def import_scs(self, payload) -> dict:
        """Import SC records from Excel rows."""
        try:
            from sc_gr_app.services import import_service
            user = self._require_current_user()
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            result = import_service.import_scs(self.config, user, rows)
            return ok(result)
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)

    def preview_sc_import(self, payload) -> dict:
        """Validate SC import rows without inserting. Returns annotated rows.

        Note: intentionally does NOT call _require_current_user() — preview is read-only
        validation that does not write to the database, so no auth check is needed.
        """
        try:
            from sc_gr_app.services import import_service
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            preview = import_service.preview_sc_import(self.config, rows)
            return ok({"rows": preview})
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)

    def preview_po_import(self, payload) -> dict:
        """Validate PO import rows without inserting. Returns annotated rows."""
        try:
            from sc_gr_app.services import import_service
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            preview = import_service.preview_po_import(self.config, rows)
            return ok({"rows": preview})
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)

    def preview_gr_import(self, payload) -> dict:
        """Validate GR import rows without inserting. Returns annotated rows."""
        try:
            from sc_gr_app.services import import_service
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            preview = import_service.preview_gr_import(self.config, rows)
            return ok({"rows": preview})
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)

    def download_sc_template(self, _payload=None) -> dict:
        """Return SC import template as base64-encoded xlsx data."""
        import io
        import base64
        import zipfile

        current_user = self._require_current_user()

        headers = ["sc_no", "vendor_id", "requester_id", "request_type", "cost_center",
                   "sc_amount", "service_period_start", "service_period_end", "status",
                   "description", "currency", "internal_system_number", "calloff_po_id",
                   "asset", "asset_nums"]
        hints = ["Required (business NO, must be unique)",
                 "Optional (comma-separated, e.g. V000001,V000002)",
                 "Optional (defaults to importer)",
                 "material/service/fixed_asset/FC", "Cost center number",
                 "Required (e.g. 50000)", "YYYY-MM-DD or MM/DD/YYYY", "YYYY-MM-DD or MM/DD/YYYY",
                 "approved/finished", "Optional",
                 "CNY/EUR/USD", "Optional (FC only)",
                 "Optional (FC call-off only)",
                 "Y/N (default N)", "Optional"]
        sample = ["[EXAMPLE]", "", current_user["user_id"], "material", "12345",
                  "50000", "2026-01-01", "2026-12-31", "approved",
                  "Sample SC description", "CNY", "", "",
                  "N", ""]

        def _col_letter(i):
            """Convert 0-based column index to Excel column letter(s)."""
            s = ""
            n = i
            while n >= 0:
                s = chr(ord('A') + n % 26) + s
                n = n // 26 - 1
            return s

        # Build inlineStr cells for header, hint, and sample rows
        def _inline_str_cell(col, row_num, text):
            ref = f"{_col_letter(col)}{row_num}"
            return f'<c r="{ref}" t="inlineStr"><is><t>{_xml_escape(text)}</t></is></c>'

        def _xml_escape(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        header_cells = "".join(_inline_str_cell(i, 2, h) for i, h in enumerate(headers))
        hint_cells = "".join(_inline_str_cell(i, 3, h) for i, h in enumerate(hints))
        sample_cells = "".join(_inline_str_cell(i, 4, v) for i, v in enumerate(sample))

        last_col = _col_letter(len(headers) - 1)
        info_text = (
            "Import Rules: Only SC records with status \"approved\" or \"finished\" can be imported. "
            "Required fields: SC NO, SC Amount, Status. "
            "Linking: Records are identified by SC NO (not system ID). "
            "Duplicate SC NOs in database will cause import errors."
        )
        info_cell = f'<c r="A1" t="inlineStr"><is><t>{_xml_escape(info_text)}</t></is></c>'

        sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">{info_cell}</row>
    <row r="2">{header_cells}</row>
    <row r="3">{hint_cells}</row>
    <row r="4">{sample_cells}</row>
  </sheetData>
  <mergeCells count="1"><mergeCell ref="A1:{last_col}1"/></mergeCells>
</worksheet>"""

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>')
            zf.writestr("_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>')
            zf.writestr("xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="SC Import" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>')
            zf.writestr("xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                '</Relationships>')
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")
        return ok({"filename": "SC_Import_Template.xlsx", "data": b64})

    def import_pos(self, payload) -> dict:
        """Import PO records from Excel rows."""
        try:
            from sc_gr_app.services import import_service
            user = self._require_current_user()
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            result = import_service.import_pos(self.config, user, rows)
            return ok(result)
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)

    def download_po_template(self, _payload=None) -> dict:
        """Return PO import template as base64-encoded xlsx data."""
        import io
        import base64
        import zipfile

        current_user = self._require_current_user()

        headers = ["sc_no", "vendor_id", "po_no", "requester_id",
                   "po_amount", "status", "contract_from", "contract_to", "contract_no",
                   "payment_frequency", "contract_pos", "contract_type", "cost_center",
                   "purchaser", "active_date"]
        hints = ["Required (SC NO, must exist in DB)",
                 "Optional (must exist if provided)",
                 "Required (business NO, must be unique)",
                 "Optional (defaults to importer)", "Required",
                 "active/finished", "YYYY-MM-DD or MM/DD/YYYY", "YYYY-MM-DD or MM/DD/YYYY", "Optional",
                 "monthly/quarterly/yearly", "Optional", "Optional", "Optional",
                 "Optional", "YYYY-MM-DD or MM/DD/YYYY"]
        sample = ["", "", "[EXAMPLE]", current_user["user_id"],
                  "50000", "active", "", "", "",
                  "monthly", "", "", "", "",
                  ""]

        def _col_letter(i):
            """Convert 0-based column index to Excel column letter(s)."""
            s = ""
            n = i
            while n >= 0:
                s = chr(ord('A') + n % 26) + s
                n = n // 26 - 1
            return s

        def _inline_str_cell(col, row_num, text):
            ref = f"{_col_letter(col)}{row_num}"
            return f'<c r="{ref}" t="inlineStr"><is><t>{_xml_escape(text)}</t></is></c>'

        def _xml_escape(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        header_cells = "".join(_inline_str_cell(i, 2, h) for i, h in enumerate(headers))
        hint_cells = "".join(_inline_str_cell(i, 3, h) for i, h in enumerate(hints))
        sample_cells = "".join(_inline_str_cell(i, 4, v) for i, v in enumerate(sample))

        last_col = _col_letter(len(headers) - 1)
        info_text = (
            "Import Rules: Only PO records with status \"active\" or \"finished\" can be imported. "
            "Required fields: SC NO, PO NO, PO Amount, Status. "
            "Linking: PO is linked to SC via SC NO (not SC ID). "
            "Duplicate PO NOs in database will cause import errors."
        )
        info_cell = f'<c r="A1" t="inlineStr"><is><t>{_xml_escape(info_text)}</t></is></c>'

        sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">{info_cell}</row>
    <row r="2">{header_cells}</row>
    <row r="3">{hint_cells}</row>
    <row r="4">{sample_cells}</row>
  </sheetData>
  <mergeCells count="1"><mergeCell ref="A1:{last_col}1"/></mergeCells>
</worksheet>"""

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>')
            zf.writestr("_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>')
            zf.writestr("xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="PO Import" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>')
            zf.writestr("xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                '</Relationships>')
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")
        return ok({"filename": "PO_Import_Template.xlsx", "data": b64})

    def import_grs(self, payload) -> dict:
        """Import GR records from Excel rows."""
        try:
            from sc_gr_app.services import import_service
            user = self._require_current_user()
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            result = import_service.import_grs(self.config, user, rows)
            return ok(result)
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)

    def download_gr_template(self, _payload=None) -> dict:
        """Return GR import template as base64-encoded xlsx data."""
        import io
        import base64
        import zipfile

        current_user = self._require_current_user()

        headers = ["po_no", "gr_no", "requester_id",
                   "estimated_amount", "con_value", "status", "remark", "tax_rate",
                   "gross_cost", "goods_service_description", "confirmation_name",
                   "delivery_from", "delivery_to", "last_delivery"]
        hints = ["Required (PO NO, must exist in DB)",
                 "Required (business NO, must be unique)",
                 "Optional (defaults to importer)",
                 "Required", "Required",
                 "approved/finished", "Optional",
                 "Optional (e.g. 13)", "Optional", "Optional", "Optional",
                 "Required (YYYY-MM-DD or MM/DD/YYYY)", "Required (YYYY-MM-DD or MM/DD/YYYY)", "Optional (YYYY-MM-DD or MM/DD/YYYY)"]
        sample = ["", "[EXAMPLE]", current_user["user_id"],
                  "10000", "10000", "approved", "", "13",
                  "", "Sample goods description", "",
                  "2026-01-01", "2026-12-31", ""]

        def _col_letter(i):
            """Convert 0-based column index to Excel column letter(s)."""
            s = ""
            n = i
            while n >= 0:
                s = chr(ord('A') + n % 26) + s
                n = n // 26 - 1
            return s

        def _inline_str_cell(col, row_num, text):
            ref = f"{_col_letter(col)}{row_num}"
            return f'<c r="{ref}" t="inlineStr"><is><t>{_xml_escape(text)}</t></is></c>'

        def _xml_escape(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        header_cells = "".join(_inline_str_cell(i, 2, h) for i, h in enumerate(headers))
        hint_cells = "".join(_inline_str_cell(i, 3, h) for i, h in enumerate(hints))
        sample_cells = "".join(_inline_str_cell(i, 4, v) for i, v in enumerate(sample))

        last_col = _col_letter(len(headers) - 1)
        info_text = (
            "Import Rules: Only GR records with status \"approved\" or \"finished\" can be imported. "
            "Required fields: PO NO, GR NO, Estimated Amount, Con Value, Delivery From, Delivery To, Status. "
            "Linking: GR is linked to PO via PO NO (not PO ID). "
            "Duplicate GR NOs in database will cause import errors."
        )
        info_cell = f'<c r="A1" t="inlineStr"><is><t>{_xml_escape(info_text)}</t></is></c>'

        sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">{info_cell}</row>
    <row r="2">{header_cells}</row>
    <row r="3">{hint_cells}</row>
    <row r="4">{sample_cells}</row>
  </sheetData>
  <mergeCells count="1"><mergeCell ref="A1:{last_col}1"/></mergeCells>
</worksheet>"""

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>')
            zf.writestr("_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>')
            zf.writestr("xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="GR Import" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>')
            zf.writestr("xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                '</Relationships>')
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")
        return ok({"filename": "GR_Import_Template.xlsx", "data": b64})
