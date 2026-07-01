"""Seed test data for dev database."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from sc_gr_app.config import default_config
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.sc_service import create_sc_draft, submit_sc, approve_sc, close_sc
from sc_gr_app.services.po_service import create_po, finish_po
from sc_gr_app.services.user_service import seed_users
from sc_gr_app.services.vendor_service import create_vendor
from sc_gr_app.services.gr_service import create_gr, approve_gr

config = default_config()
migrate(config)
seed_users(config)

from datetime import datetime, timezone
_dev_ts = datetime.now(timezone.utc).isoformat()
with connect(config) as conn:
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
        ("U-86183", "86183", "86183", "admin", "86183@audi.com.cn", _dev_ts, _dev_ts),
    )
    conn.commit()

def get_user(user_id):
    with connect(config) as conn:
        return dict(conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone())

admin = get_user("U-86183")
req1  = get_user("U-UJWVFIH")
req2  = get_user("U-FO5LZ6P")
req3  = get_user("U-EZHOLW0")

print("=== Users ===")
for u in [admin, req1, req2, req3]:
    print(f"  {u['user_name']} [{u['role']}]")

# -- 1. Vendors --
print("\n=== Vendors ===")
mid = admin["machine_id"]
vendor_data = [
    {"vendor_id": f"V-{mid}-001", "vendor_name": "Siemens Ltd.", "ksrm_vendor_code": "V-SIE-001",
     "contact_person": "Zhang Wei", "phone": "13800001001", "service_scope": "engineering Service",
     "email": "zhangwei@siemens.com", "description": "Automation and control systems"},
    {"vendor_id": f"V-{mid}-002", "vendor_name": "Bosch Automotive", "ksrm_vendor_code": "V-BOS-002",
     "contact_person": "Li Ming", "phone": "13800001002", "service_scope": "Equipment",
     "email": "liming@bosch.com", "description": "Testing equipment and validation services"},
    {"vendor_id": f"V-{mid}-003", "vendor_name": "Dassault Systemes", "ksrm_vendor_code": "V-DAS-003",
     "contact_person": "Wang Fang", "phone": "13800001003", "service_scope": "engineering Service",
     "email": "wangfang@3ds.com", "description": "CAD/CAE software and consulting"},
    {"vendor_id": f"V-{mid}-004", "vendor_name": "TUV Rheinland", "ksrm_vendor_code": "V-TUV-004",
     "contact_person": "Chen Jie", "phone": "13800001004", "service_scope": "engineering Service",
     "email": "chenjie@tuv.com", "description": "Homologation and certification services"},
    {"vendor_id": f"V-{mid}-005", "vendor_name": "AVL List GmbH", "ksrm_vendor_code": "V-AVL-005",
     "contact_person": "Liu Yang", "phone": "13800001005", "service_scope": "Equipment",
     "email": "liuyang@avl.com", "description": "Powertrain testing equipment"},
]
v_ids = []
for vd in vendor_data:
    r = create_vendor(config, admin, vd)
    v_ids.append(r["vendor_id"])
    print(f"  {r['vendor_id']} - {r['vendor_name']} [{r['service_scope']}]")

# -- 2. SC + PO Records --
print("\n=== SC + PO Records ===")

def _link_vendors(sc_id, vendor_ids):
    with connect(config) as conn:
        for vid in vendor_ids:
            conn.execute(
                "INSERT OR IGNORE INTO sc_vendors (sc_id, vendor_id) VALUES (?, ?)",
                (sc_id, vid),
            )
        conn.commit()

_sc_counter = 0
def _next_sc_no():
    global _sc_counter
    _sc_counter += 1
    return f"SC-2026-{_sc_counter:03d}"

def make_sc(user, desc):
    return create_sc_draft(config, user, {"requester_id": user["user_id"], "description": desc})

def submit(sc_id, user, req_type, cost_center, sc_amount, start, end, desc="", internal_sys=None):
    d = {"requester_id": user["user_id"], "sc_no": _next_sc_no(), "request_type": req_type,
         "cost_center": cost_center, "sc_amount": sc_amount,
         "service_period_start": start, "service_period_end": end,
         "description": desc or "", "asset": "N"}
    if internal_sys:
        d["internal_system_number"] = internal_sys
    return submit_sc(config, user, sc_id, d)

# SC-1: Draft (kept draft for draft PO)
sc1 = make_sc(req1, "SC-1: Draft - annual IT maintenance")
_link_vendors(sc1["sc_id"], [v_ids[0]])
print(f"  {sc1['sc_id']} (draft)")

# PO-1: Draft under draft SC-1
po1 = create_po(config, req1, {"sc_id": sc1["sc_id"], "vendor_id": v_ids[0],
    "po_amount": 250000, "contract_no": "C-2026-001", "contract_from": "2026-03-01",
    "contract_to": "2026-08-31", "payment_frequency": "Monthly"})
print(f"  {po1['po_id']} (draft)")

# SC-2: Pending
sc2 = make_sc(req2, "SC-2: test equipment calibration")
sc2 = submit(sc2["sc_id"], req2, "service", 1002, 300000, "2026-03-01", "2026-08-31", "SC-2: test equipment calibration")
_link_vendors(sc2["sc_id"], [v_ids[0], v_ids[1]])
print(f"  {sc2['sc_id']} (pending)")

# SC-3: Pending
sc3 = make_sc(req1, "SC-3: chassis components testing")
sc3 = submit(sc3["sc_id"], req1, "material", 1003, 800000, "2026-02-01", "2026-10-31", "SC-3: chassis components testing")
_link_vendors(sc3["sc_id"], [v_ids[1]])
print(f"  {sc3['sc_id']} (pending)")

# SC-4: Approved
sc4 = make_sc(req2, "SC-4: NVH testing services")
sc4 = submit(sc4["sc_id"], req2, "service", 1004, 600000, "2026-04-01", "2026-09-30", "SC-4: NVH testing services")
sc4 = approve_sc(config, admin, sc4["sc_id"])
_link_vendors(sc4["sc_id"], [v_ids[1], v_ids[2]])
print(f"  {sc4['sc_id']} (approved)")

# PO-2: Active under approved SC-4
po2 = create_po(config, req2, {"sc_id": sc4["sc_id"], "vendor_id": v_ids[1],
    "po_amount": 350000, "contract_no": "C-2026-002", "contract_from": "2026-04-15",
    "contract_to": "2026-09-15", "payment_frequency": "Quarterly"})
print(f"  {po2['po_id']} (active)")

# SC-5: Approved
sc5 = make_sc(req3, "SC-5: powertrain calibration tools")
sc5 = submit(sc5["sc_id"], req3, "fixed_asset", 1005, 450000, "2026-05-01", "2026-12-31", "SC-5: powertrain calibration tools")
sc5 = approve_sc(config, admin, sc5["sc_id"])
_link_vendors(sc5["sc_id"], [v_ids[3]])
print(f"  {sc5['sc_id']} (approved)")

# PO-3: Active under approved SC-5
po3 = create_po(config, req3, {"sc_id": sc5["sc_id"], "vendor_id": v_ids[2],
    "po_amount": 450000, "contract_no": "C-2026-003", "contract_from": "2026-05-01",
    "contract_to": "2026-12-31", "payment_frequency": "Monthly"})
print(f"  {po3['po_id']} (active)")

# SC-6: Approved FC
sc6 = make_sc(req1, "SC-6: KSRM system integration (FC)")
sc6 = submit(sc6["sc_id"], req1, "FC", 1006, 1200000, "2026-01-01", "2027-12-31",
            "SC-6: KSRM system integration (FC)", internal_sys="FC-SYS-2026-001")
sc6 = approve_sc(config, admin, sc6["sc_id"])
_link_vendors(sc6["sc_id"], [v_ids[4]])
print(f"  {sc6['sc_id']} (approved, FC)")

# PO-5: Active under FC SC-6
po5 = create_po(config, req1, {"sc_id": sc6["sc_id"], "vendor_id": v_ids[4],
    "po_amount": 600000, "contract_no": "C-2026-005", "contract_from": "2026-01-01",
    "contract_to": "2027-12-31", "payment_frequency": "Annual"})
print(f"  {po5['po_id']} (active)")

# SC-7: Create + approve + PO + GR, THEN close
sc7 = make_sc(req2, "SC-7: brake system testing (completed)")
sc7 = submit(sc7["sc_id"], req2, "service", 1007, 200000, "2026-01-01", "2026-03-31", "SC-7: brake system testing (completed)")
sc7 = approve_sc(config, admin, sc7["sc_id"])

po4 = create_po(config, req2, {"sc_id": sc7["sc_id"], "vendor_id": v_ids[3],
    "po_amount": 200000, "contract_no": "C-2026-004", "contract_from": "2026-01-01",
    "contract_to": "2026-03-31", "payment_frequency": "Monthly"})

# GR-4: Create while PO-4 is still active, before finishing
gr4 = create_gr(config, req2, {"po_id": po4["po_id"], "requester_id": req2["user_id"],
    "estimated_amount": 200000, "remark": "Final payment - brake testing complete"})
gr4 = approve_gr(config, admin, gr4["gr_id"], con_value=198000)
print(f"  {gr4['gr_id']} (approved)")

po4 = finish_po(config, req2, po4["po_id"])
print(f"  {po4['po_id']} (finished)")

sc7 = close_sc(config, admin, sc7["sc_id"])
_link_vendors(sc7["sc_id"], [v_ids[3]])
print(f"  {sc7['sc_id']} (closed)")

# -- 3. Remaining GRs --
print("\n=== GR Records ===")

gr1 = create_gr(config, req2, {"po_id": po2["po_id"], "requester_id": req2["user_id"],
    "estimated_amount": 100000, "remark": "First milestone - initial setup"})
print(f"  {gr1['gr_id']} (pending)")

gr2 = create_gr(config, req2, {"po_id": po2["po_id"], "requester_id": req2["user_id"],
    "estimated_amount": 150000, "remark": "Second milestone - testing phase 1 complete"})
gr2 = approve_gr(config, admin, gr2["gr_id"], con_value=148500)
print(f"  {gr2['gr_id']} (approved)")

gr3 = create_gr(config, req3, {"po_id": po3["po_id"], "requester_id": req3["user_id"],
    "estimated_amount": 200000, "remark": "Initial installation and setup"})
print(f"  {gr3['gr_id']} (pending)")

gr5 = create_gr(config, req1, {"po_id": po1["po_id"], "requester_id": req1["user_id"],
    "estimated_amount": 50000, "remark": "Draft GR for draft PO"})
print(f"  {gr5['gr_id']} (draft)")

# -- Summary --
print(f"\n{'='*60}")
print("Seed Complete!")
print(f"{'='*60}")
print(f"  Users:    7")
print(f"  Vendors:  {len(v_ids)}")
print(f"  SC:       7 (draft, 2 pending, 3 approved, closed)")
print(f"  PO:       5 (draft, 3 active, finished)")
print(f"  GR:       5 (draft, 2 pending, 2 approved)")
