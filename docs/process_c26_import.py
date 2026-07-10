"""
Process C26.4 historical data into SC/PO/GR import CSVs (v2).
Changes:
  - Col A = Service Scope (new), shifts all indices +1
  - Only process rows WITH Service Scope
  - Include FC and PO under FC types
  - PO under FC: extract 7600 FC PO from Description as calloff_po_id
  - FC with 7600 PO: PO(FC) record
  - Also generates vendor import CSV from unique vendors in scope
"""
import csv
import os
import re
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "sheet_c26.4_v2.csv")
DB_PATH = os.path.join(BASE, "..", "data", "sc_gr.sqlite3")

# Load vendor and user data from DB
vendors_db = {}   # vendor_name (lower) -> vendor_id
vendors_cn = {}   # company_name_cn (lower) -> vendor_id
users_db = {}
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    for v in conn.execute("SELECT vendor_id, vendor_name, company_name_cn FROM vendors"):
        vendors_db[v["vendor_name"].strip().lower()] = v["vendor_id"]
        cn = (v["company_name_cn"] or "").strip().lower()
        if cn:
            vendors_cn[cn] = v["vendor_id"]
    for u in conn.execute("SELECT user_id, user_name FROM users"):
        users_db[u["user_name"].strip().lower()] = u["user_id"]
    conn.close()

print(f"Loaded {len(vendors_db)} vendors (+{len(vendors_cn)} CN names), {len(users_db)} users from DB")

# ── helpers ──────────────────────────────────────────────────────────

def clean_val(val):
    if val is None:
        return ""
    return str(val).strip()

def clean_ref(val):
    s = clean_val(val)
    if s in ("#REF!", "#N/A", "#VALUE!", "#NAME?", "#NULL!", "#NUM!", "#DIV/0!"):
        return ""
    return s

def parse_date_str(val):
    s = clean_val(val)
    if not s:
        return ""
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y",
               "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if " " in s:
        try:
            return datetime.strptime(s.split(" ")[0], "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s

def smart_float(val):
    s = clean_val(val)
    if not s:
        return ""
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return s

def extract_contract_no(remark):
    s = clean_ref(remark)
    if not s:
        return ""
    m = re.search(r'CON[-\s]*[A-Za-z0-9]+(?:\([^)]*\))?(?:Sup\d+[-\d]*)?(?:-[A-Za-z0-9]+)?', s)
    if m:
        return m.group(0)
    m2 = re.search(r'AC\d+[-\d]*', s)
    if m2:
        return m2.group(0)
    return s

def extract_7600_po(desc):
    """Extract a 7600-prefix PO number from Description text."""
    s = clean_val(desc)
    if not s:
        return ""
    # Match 7600XXXXX patterns, optionally preceded by "FC" or "FC-"
    m = re.search(r'(?:FC[-\s]*)?(7600\d{5,})', s)
    if m:
        return m.group(1)
    return ""

def normalize_requestor(val):
    """Multi-person: keep first person only. / and _ separate people."""
    s = clean_val(val)
    if not s:
        return ""
    first = re.split(r'[/_]', s)[0]
    return first.strip()

def match_vendor(name):
    name = clean_val(name)
    if not name:
        return "", False
    key = name.strip().lower()

    # 1. Exact match on vendor_name
    if key in vendors_db:
        return vendors_db[key], True

    # 2. Exact match on company_name_cn
    if key in vendors_cn:
        return vendors_cn[key], True

    # 3. Normalize punctuation/spacing, then retry
    def _norm(s):
        s = s.lower()
        s = re.sub(r'[,.()&]+', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    key_norm = _norm(key)
    if key_norm != key:
        for vname, vid in vendors_db.items():
            if _norm(vname) == key_norm:
                return vid, True
        for cn, vid in vendors_cn.items():
            if _norm(cn) == key_norm:
                return vid, True
        # Also compare with all spaces removed (handles "ShanghaiZhongchengAutomotive" vs "Shanghai Zhongcheng Automotive...")
        key_compact = key_norm.replace(" ", "")
        for vname, vid in vendors_db.items():
            if _norm(vname).replace(" ", "") == key_compact:
                return vid, True

    # 4. Trim trailing digits (e.g. "华盈（北京）... 3300275357")
    key_no_tail = re.sub(r'\s+\d+$', '', key).strip()
    if key_no_tail != key:
        if key_no_tail in vendors_cn:
            return vendors_cn[key_no_tail], True
        key_nt_norm = _norm(key_no_tail)
        for cn, vid in vendors_cn.items():
            if _norm(cn) == key_nt_norm:
                return vid, True

    # 5. Substring match (bidirectional) — avoid false positives on short names
    if len(key) >= 4:
        for vname, vid in vendors_db.items():
            if key in vname or vname in key:
                return vid, True
        for cn, vid in vendors_cn.items():
            if key in cn or cn in key:
                return vid, True
        # Also try substring with all spaces removed (handles compact DB names)
        key_compact = key.replace(" ", "")
        for vname, vid in vendors_db.items():
            vname_compact = vname.replace(" ", "")
            if key_compact in vname_compact or vname_compact in key_compact:
                return vid, True

    # 6. Word-based subset matching for English names
    # Filter out generic corporate/location stopwords to avoid false positives
    _STOPWORDS = {
        "co", "ltd", "limited", "inc", "corp", "corporation", "company",
        "group", "international", "china", "beijing", "shanghai", "suzhou",
        "technology", "technologies", "engineering", "service", "services",
        "logistics", "automotive", "automobile", "trading", "industrial",
        "agency", "sales", "system", "systems", "management", "consulting",
        "development", "science", "energy", "new", "global", "branch",
        "logistics",
    }
    key_words = {w for w in key_norm.split() if len(w) > 2 and w not in _STOPWORDS}
    if key_words and len(key_words) >= 1:
        best_score = 0
        best_match = None
        for vname, vid in vendors_db.items():
            db_words = {w for w in _norm(vname).split() if len(w) > 2 and w not in _STOPWORDS}
            if not db_words:
                continue
            common = key_words & db_words
            if not common:
                continue
            # Require at least 1 distinctive word match AND significant overlap
            score = len(common) / min(len(key_words), len(db_words))
            if score > best_score and score >= 0.5:
                best_score = score
                best_match = vid
        if best_match:
            return best_match, True

    return "", False

def match_user(name):
    name = clean_val(name)
    if not name:
        return "", False
    key = name.strip().lower()
    # 1. Exact match
    if key in users_db:
        return users_db[key], True
    # 2. Reversed comma name ("Last, First" → "First Last")
    if "," in key:
        parts = [p.strip() for p in key.split(",")]
        reversed_name = " ".join(reversed(parts)).lower()
        if reversed_name in users_db:
            return users_db[reversed_name], True
    # 3. Fuzzy: remove commas and spaces from both sides, compare normalized
    key_normalized = key.replace(",", "").replace("  ", " ").strip()
    for uname, uid in users_db.items():
        # Strip department suffix "(...)" from DB name
        db_normalized = re.sub(r'\([^)]*\)', '', uname).replace(",", "").replace("  ", " ").strip()
        if key_normalized == db_normalized:
            return uid, True
        # Substring match
        if uname in key or key in uname or key_normalized in uname or uname in key_normalized:
            return uid, True
        # DB "Last, First (Dept)" vs source "First Last"
        # Check if source words are a subset of DB name words
        src_words = set(key_normalized.split())
        db_words = set(db_normalized.split())
        if src_words and db_words and src_words.issubset(db_words):
            return uid, True
    return name, False

def normalize_scope(scope):
    """Normalize service_scope values to match SUPPORTED_SERVICE_SCOPES."""
    scope = clean_val(scope)
    if not scope:
        return scope
    fixes = {
        "engineering service": "Engineering Service",
    }
    return fixes.get(scope.strip().lower(), scope)


def map_request_type(contract_type):
    """Map Excel contract_type to valid system request_type (new/call_off/FC)."""
    mapping = {
        "FC": "FC",
        "PO under FC": "call_off",
        "PO": "new",
        "Contract": "new",
    }
    return mapping.get(contract_type, "new")


# ── read CSV ──────────────────────────────────────────────────────────

with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    raw_rows = list(reader)

# Data starts at row 3 (0-based index 2); row 0=title, row 1=headers
DATA_START = 2

# Column indices (v2: Service Scope at col 0, shifts all +1 vs v1)
COL_SCOPE, COL_YEAR, COL_POS, COL_SC_NO, COL_PO_NO = 0, 1, 2, 3, 4
COL_TYPE, COL_EXPRIED, COL_STATUS, COL_VENDOR, COL_DESC = 5, 6, 7, 8, 9
COL_NET_GR, COL_GR_VAT, COL_CON_VAL, COL_OPEN_PO = 10, 11, 12, 13
COL_PO_AMT, COL_SC_AMT, COL_CAT, COL_REQ, COL_COST = 14, 15, 16, 17, 18
COL_REQ_DATE, COL_CONF_NO, COL_CON_DATE = 19, 20, 21
COL_CON_FROM, COL_CON_TO, COL_PAY_FREQ, COL_PURCHASER = 22, 23, 24, 25
COL_SUPPLIER = 26
COL_ASSET, COL_REMARK, COL_ASSET_NUM = 32, 33, 34

# ── filter & classify ─────────────────────────────────────────────────

sc_rows = []
po_rows = []
gr_rows = []
audit_rows = []  # all source rows with Problem column
unique_vendors = {}  # vendor_name -> service_scope

skipped = {"no_scope": 0, "Cancellation": 0, "SC_Pending": 0,
           "empty": 0, "no_status": 0, "no_sc_no": 0}

def _make_audit(i, row):
    """Build base audit record from source row."""
    return {
        "_row": i + 1,
        "service_scope": clean_val(row[COL_SCOPE]),
        "year": clean_val(row[COL_YEAR]),
        "pos": clean_val(row[COL_POS]),
        "sc_no": clean_val(row[COL_SC_NO]),
        "po_no": clean_val(row[COL_PO_NO]),
        "contract_type": clean_val(row[COL_TYPE]),
        "status": clean_val(row[COL_STATUS]),
        "vendor": clean_val(row[COL_VENDOR]),
        "description": clean_val(row[COL_DESC]),
        "net_gr": clean_val(row[COL_NET_GR]),
        "gr_vat": clean_val(row[COL_GR_VAT]),
        "con_val": clean_val(row[COL_CON_VAL]),
        "open_po": clean_val(row[COL_OPEN_PO]),
        "po_amt": clean_val(row[COL_PO_AMT]),
        "sc_amt": clean_val(row[COL_SC_AMT]),
        "category": clean_val(row[COL_CAT]),
        "req_raw": normalize_requestor(row[COL_REQ]),
        "cost_center": clean_val(row[COL_COST]),
        "req_date": parse_date_str(row[COL_REQ_DATE]),
        "conf_no": clean_val(row[COL_CONF_NO]),
        "con_date": parse_date_str(row[COL_CON_DATE]),
        "conf_from": parse_date_str(row[COL_CON_FROM]),
        "conf_to": parse_date_str(row[COL_CON_TO]),
        "pay_freq": clean_val(row[COL_PAY_FREQ]),
        "purchaser": clean_val(row[COL_PURCHASER]),
        "supplier": clean_val(row[COL_SUPPLIER]),
        "asset": clean_val(row[COL_ASSET]),
        "remark": clean_ref(row[COL_REMARK]),
        "asset_num": clean_ref(row[COL_ASSET_NUM]),
        "record_type": "",   # SC/PO/GR/Skipped
        "action": "",        # Imported/Skipped/Merged/Deduplicated
        "problem": "",       # issues found
        "auto_fix": "",      # automatic corrections applied
    }

def _add_audit(audit, **kw):
    """Append an audit record with optional overrides."""
    audit.update(kw)
    audit_rows.append(audit)

for i, row in enumerate(raw_rows):
    if i < DATA_START:
        continue
    if len(row) < 35:
        continue

    service_scope = normalize_scope(row[COL_SCOPE])
    contract_type = clean_val(row[COL_TYPE])
    status = clean_val(row[COL_STATUS])
    sc_no = clean_val(row[COL_SC_NO])
    po_no = clean_val(row[COL_PO_NO])
    vendor_raw = clean_val(row[COL_VENDOR])
    desc = clean_val(row[COL_DESC])

    audit = _make_audit(i, row)

    # MUST have Service Scope
    if not service_scope or service_scope == "可以删除":
        skipped["no_scope"] += 1
        _add_audit(audit, record_type="Skipped", action="Skipped",
                   problem="No Service Scope" if not service_scope else "Service Scope = '可以删除'")
        continue

    # Skip specific invalid rows
    if po_no == "7300063480" and not sc_no:
        skipped["empty"] += 1
        _add_audit(audit, record_type="Skipped", action="Skipped",
                   problem=f"PO 7300063480 missing SC number, user requested skip")
        continue
    if po_no == "de" or (po_no and len(po_no) < 4):
        skipped["empty"] += 1
        p = f"Invalid PO number: '{po_no}'" if po_no else "Empty PO number"
        _add_audit(audit, record_type="Skipped", action="Skipped", problem=p)
        continue

    # Skip Cancellation, SC Pending
    if status == "Cancellation":
        skipped["Cancellation"] += 1
        _add_audit(audit, record_type="Skipped", action="Skipped", problem="Status is 'Cancellation'")
        continue
    if status == "SC Pending":
        skipped["SC_Pending"] += 1
        _add_audit(audit, record_type="Skipped", action="Skipped", problem="Status is 'SC Pending'")
        continue
    if not status:
        skipped["no_status"] += 1
        _add_audit(audit, record_type="Skipped", action="Skipped", problem="No status value")
        continue

    # Requester is required — skip if empty
    req_raw_check = normalize_requestor(row[COL_REQ])
    if not req_raw_check:
        skipped["empty"] += 1
        _add_audit(audit, record_type="Skipped", action="Skipped", problem="Requester is empty")
        continue

    # 7600 FC PO without SC → independent PO(FC), system handles it
    if contract_type == "FC" and status == "PO Approved" and not sc_no and po_no.startswith("7600"):
        v_id, v_m = match_vendor(vendor_raw)
        if not v_m:
            skipped["empty"] += 1
            _add_audit(audit, record_type="Skipped", action="Skipped",
                       problem=f"Vendor '{vendor_raw}' not in DB, PO import requires vendor_id")
            continue
        r_raw = normalize_requestor(row[COL_REQ])
        r_id, r_m = match_user(r_raw)
        purchaser_raw = clean_val(row[COL_PURCHASER])
        purchaser_id, purchaser_matched = match_user(purchaser_raw)

        fixes = []
        if not r_m:
            fixes.append(f"Requester '{r_raw}' not in DB, using name as ID")
        if not purchaser_matched and purchaser_raw:
            fixes.append(f"Purchaser '{purchaser_raw}' not in DB, using name as ID")

        po_rows.append({
            "_row": i + 1,
            "po_id": "",
            "sc_no": "",  # independent PO(FC), no SC
            "po_no": po_no,
            "po_amount": smart_float(clean_val(row[COL_PO_AMT])),
            "status": "active",
            "request_type": "FC",
            "contract_type": "FC",
            "contract_pos": clean_val(row[COL_POS]),
            "cost_center": clean_val(row[COL_COST]),
            "vendor_id": v_id,
            "_vendor_name_raw": vendor_raw,
            "_vendor_matched": v_m,
            "requester_id": r_id,
            "_requester_raw": r_raw,
            "_requester_matched": r_m,
            "purchaser": purchaser_id if purchaser_matched else purchaser_raw,
            "_purchaser_raw": purchaser_raw,
            "contract_from": parse_date_str(row[COL_CON_FROM]),
            "contract_to": parse_date_str(row[COL_CON_TO]),
            "contract_no": extract_contract_no(row[COL_REMARK]),
            "payment_frequency": clean_val(row[COL_PAY_FREQ]),
        })
        _add_audit(audit, record_type="PO", action="Imported",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem="Independent FC PO (7600, no SC) — system handles directly" if not fixes else "")
        continue

    if not sc_no:
        skipped["no_sc_no"] += 1
        _add_audit(audit, record_type="Skipped", action="Skipped",
                   problem="No SC number")
        continue

    # Fix: if sc_no has multiple space-separated numbers, take last
    if " " in sc_no:
        sc_no = sc_no.split()[-1]

    # Collect vendor for vendor import
    if vendor_raw and vendor_raw not in unique_vendors:
        unique_vendors[vendor_raw] = service_scope

    # ── common fields ──
    vendor_id, vendor_matched = match_vendor(vendor_raw)
    req_raw = normalize_requestor(row[COL_REQ])
    req_id, req_matched = match_user(req_raw)

    # ── classify ──
    if status == "SC Approved":
        sc_amt = smart_float(clean_val(row[COL_SC_AMT]))
        sc_amt_fallback = False
        if not sc_amt or sc_amt == "":
            sc_amt = smart_float(clean_val(row[COL_PO_AMT]))
            sc_amt_fallback = True

        # calloff_po_id: for PO under FC, extract 7600 from description
        calloff_po_id = ""
        if contract_type == "PO under FC":
            calloff_po_id = extract_7600_po(desc)

        _mapped_rt = map_request_type(contract_type)
        fixes = []
        prob = ""
        if sc_amt_fallback:
            fixes.append(f"SC amount empty, using PO amount ({sc_amt}) as fallback")
        if not vendor_raw:
            prob = "Vendor name is empty in source data — SC import will fail without vendor"
        elif not vendor_matched:
            fixes.append(f"Vendor '{vendor_raw}' not in DB, vendor_id left empty")
        if not req_matched:
            fixes.append(f"Requester '{req_raw}' not in DB, using name as ID")
        if calloff_po_id:
            fixes.append(f"Extracted calloff_po_id={calloff_po_id} from Description")
        if contract_type in ("PO", "Contract"):
            fixes.append(f"request_type mapped: '{contract_type}' -> '{_mapped_rt}'")

        sc_rows.append({
            "_row": i + 1,
            "sc_no": sc_no,
            "sc_amount": sc_amt,
            "status": "approved",
            "request_type": _mapped_rt,
            "cost_center": clean_val(row[COL_COST]),
            "description": clean_val(row[COL_DESC]),
            "service_period_start": parse_date_str(row[COL_CON_FROM]),
            "service_period_end": parse_date_str(row[COL_CON_TO]),
            "vendor_id": vendor_id,
            "_vendor_name_raw": vendor_raw,
            "_vendor_matched": vendor_matched,
            "requester_id": req_id,
            "_requester_raw": req_raw,
            "_requester_matched": req_matched,
            "asset": clean_val(row[COL_ASSET]) if clean_val(row[COL_ASSET]) else "N",
            "asset_nums": clean_ref(row[COL_ASSET_NUM]),
            "remark": clean_ref(row[COL_REMARK]),
            "internal_system_number": clean_val(row[COL_SUPPLIER]),
            "calloff_po_id": calloff_po_id,
            "currency": "CNY",
            "service_scope": service_scope,
        })
        _add_audit(audit, record_type="SC", action="Imported",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem=prob)

    elif status == "PO Approved":
        if not vendor_matched:
            skipped["empty"] += 1
            _add_audit(audit, record_type="Skipped", action="Skipped",
                       problem=f"Vendor '{vendor_raw}' not in DB, PO import requires vendor_id")
            continue
        purchaser_raw = clean_val(row[COL_PURCHASER])
        purchaser_id, purchaser_matched = match_user(purchaser_raw)

        # FC-type PO with sc_no: must use call_off, not FC (validation rejects FC+sc_no)
        _rt = map_request_type(contract_type)
        if _rt == "FC" and sc_no:
            _rt = "call_off"

        _po_amt = smart_float(clean_val(row[COL_PO_AMT]))
        _po_amt_fallback = False
        if not _po_amt or _po_amt == "":
            _po_amt = smart_float(clean_val(row[COL_SC_AMT]))
            _po_amt_fallback = True

        fixes = []
        if _po_amt_fallback:
            fixes.append(f"PO amount empty, using SC amount ({_po_amt}) as fallback")
        if not _po_amt or _po_amt == "":
            fixes.append("PO amount still empty after SC fallback")
        if not vendor_matched:
            fixes.append(f"Vendor '{vendor_raw}' not in DB, vendor_id left empty")
        if not req_matched:
            fixes.append(f"Requester '{req_raw}' not in DB, using name as ID")
        if not purchaser_matched and purchaser_raw:
            fixes.append(f"Purchaser '{purchaser_raw}' not in DB, using name as ID")
        if contract_type == "FC" and sc_no and _rt == "call_off":
            fixes.append(f"FC-type PO with sc_no: request_type adjusted FC->call_off (validation requires it)")
        if contract_type in ("PO", "Contract"):
            fixes.append(f"request_type mapped: '{contract_type}' -> '{_rt}'")

        po_rows.append({
            "_row": i + 1,
            "po_id": "",
            "sc_no": sc_no,
            "po_no": po_no,
            "po_amount": _po_amt,
            "status": "active",
            "request_type": _rt,
            "contract_type": contract_type if contract_type else "PO",
            "contract_pos": clean_val(row[COL_POS]),
            "cost_center": clean_val(row[COL_COST]),
            "vendor_id": vendor_id,
            "_vendor_name_raw": vendor_raw,
            "_vendor_matched": vendor_matched,
            "requester_id": req_id,
            "_requester_raw": req_raw,
            "_requester_matched": req_matched,
            "purchaser": purchaser_id if purchaser_matched else purchaser_raw,
            "_purchaser_raw": purchaser_raw,
            "contract_from": parse_date_str(row[COL_CON_FROM]),
            "contract_to": parse_date_str(row[COL_CON_TO]),
            "contract_no": extract_contract_no(row[COL_REMARK]),
            "payment_frequency": clean_val(row[COL_PAY_FREQ]),
        })
        _add_audit(audit, record_type="PO", action="Imported",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem="PO amount empty — manual fix needed" if (not _po_amt or _po_amt == "") else "")

    elif status == "Finish":
        # Finish rows are GR records (the last GR), not PO records.
        conf_no = clean_val(row[COL_CONF_NO])
        if not conf_no:
            skipped["empty"] += 1
            _add_audit(audit, record_type="Skipped", action="Skipped",
                       problem="Finish row has no Confirmation No. (required for GR)")
            continue

        con_date = parse_date_str(row[COL_CON_DATE])
        _gr_est = smart_float(clean_val(row[COL_NET_GR]))

        gr_rows.append({
            "_row": i + 1,
            "po_no": po_no,
            "gr_no": conf_no,
            "estimated_amount": _gr_est,
            "con_value": smart_float(clean_val(row[COL_CON_VAL])),
            "gross_cost": smart_float(clean_val(row[COL_GR_VAT])),
            "status": "finished",
            "goods_service_description": clean_val(row[COL_DESC]),
            "confirmation_name": conf_no,
            "delivery_from": con_date,
            "delivery_to": con_date,
            "requester_id": req_id,
            "_requester_raw": req_raw,
            "_requester_matched": req_matched,
            "remark": clean_ref(row[COL_REMARK]),
            "tax_rate": "",
            "last_delivery": "",
            "_source": "Finish",  # marks this GR as the PO-completing one
        })
        fixes = []
        prob = ""
        if not _gr_est or _gr_est == "":
            fixes.append("estimated_amount empty, will use con_value as fallback")
        if not con_date:
            prob = "CON_DATE empty — delivery_from/to will be empty (import validation requires them)"
        if not req_matched:
            fixes.append(f"Requester '{req_raw}' not in DB, using name as ID")
        _add_audit(audit, record_type="GR", action="Imported",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem=prob)

    elif status == "GR Partially triggered":
        conf_no = clean_val(row[COL_CONF_NO])
        if not conf_no:
            skipped["empty"] += 1
            _add_audit(audit, record_type="Skipped", action="Skipped",
                       problem="GR Partially triggered row has no Confirmation No.")
            continue

        con_date = parse_date_str(row[COL_CON_DATE])
        _gr_est = smart_float(clean_val(row[COL_NET_GR]))

        gr_rows.append({
            "_row": i + 1,
            "po_no": po_no,
            "gr_no": conf_no,
            "estimated_amount": _gr_est,
            "con_value": smart_float(clean_val(row[COL_CON_VAL])),
            "gross_cost": smart_float(clean_val(row[COL_GR_VAT])),
            "status": "finished",
            "goods_service_description": clean_val(row[COL_DESC]),
            "confirmation_name": conf_no,
            "delivery_from": con_date,
            "delivery_to": con_date,
            "requester_id": req_id,
            "_requester_raw": req_raw,
            "_requester_matched": req_matched,
            "remark": clean_ref(row[COL_REMARK]),
            "tax_rate": "",
            "last_delivery": "",
        })
        fixes = []
        prob = ""
        if not _gr_est or _gr_est == "":
            fixes.append("estimated_amount empty, will use con_value as fallback")
        if not con_date:
            prob = "CON_DATE empty — delivery_from/to will be empty (import validation requires them)"
        if not req_matched:
            fixes.append(f"Requester '{req_raw}' not in DB, using name as ID")
        _add_audit(audit, record_type="GR", action="Imported",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem=prob)


# ── Fill missing SC records from PO rows ──────────────────────────────
# Some SC numbers appear only on PO Approved rows (no SC Approved row).
# The PO import requires the SC to exist in DB first, so extract SC records
# from the first PO row for each missing SC.

existing_sc_nos = {r["sc_no"] for r in sc_rows}
po_ref_scs = {r["sc_no"] for r in po_rows if r["sc_no"]}
missing_scs = po_ref_scs - existing_sc_nos

if missing_scs:
    # Map SC no → first source row index where it appears with PO Approved
    first_po_row = {}
    for i, row in enumerate(raw_rows):
        if i < DATA_START or len(row) < 35:
            continue
        sc_no = clean_val(row[COL_SC_NO])
        status = clean_val(row[COL_STATUS])
        if sc_no in missing_scs and status == "PO Approved" and sc_no not in first_po_row:
            first_po_row[sc_no] = (i, row)

    for sc_no in sorted(missing_scs):
        if sc_no not in first_po_row:
            print(f"  [MISSING SC] sc_no={sc_no}: no PO Approved row found, skipping")
            continue
        i, row = first_po_row[sc_no]
        vendor_raw = clean_val(row[COL_VENDOR])
        service_scope = normalize_scope(row[COL_SCOPE])
        vendor_id, vendor_matched = match_vendor(vendor_raw)
        req_raw = normalize_requestor(row[COL_REQ])
        req_id, req_matched = match_user(req_raw)
        contract_type = clean_val(row[COL_TYPE])

        sc_amt = smart_float(clean_val(row[COL_SC_AMT]))
        sc_amt_fallback = False
        if not sc_amt or sc_amt == "":
            sc_amt = smart_float(clean_val(row[COL_PO_AMT]))
            sc_amt_fallback = True

        calloff_po_id = ""
        if contract_type == "PO under FC":
            calloff_po_id = extract_7600_po(clean_val(row[COL_DESC]))

        _mapped_rt = map_request_type(contract_type)
        fixes = []
        prob = ""
        if sc_amt_fallback:
            fixes.append(f"SC amount empty, using PO amount ({sc_amt}) as fallback")
        if not vendor_raw:
            prob = "Vendor name is empty in source data — SC import will fail without vendor"
        elif not vendor_matched:
            fixes.append(f"Vendor '{vendor_raw}' not in DB, vendor_id left empty")
        if not req_matched:
            fixes.append(f"Requester '{req_raw}' not in DB, using name as ID")
        if calloff_po_id:
            fixes.append(f"Extracted calloff_po_id={calloff_po_id} from Description")
        if contract_type in ("PO", "Contract"):
            fixes.append(f"request_type mapped: '{contract_type}' -> '{_mapped_rt}'")

        sc_rows.append({
            "_row": i + 1,
            "sc_no": sc_no,
            "sc_amount": sc_amt,
            "status": "approved",
            "request_type": _mapped_rt,
            "cost_center": clean_val(row[COL_COST]),
            "description": clean_val(row[COL_DESC]),
            "service_period_start": parse_date_str(row[COL_CON_FROM]),
            "service_period_end": parse_date_str(row[COL_CON_TO]),
            "vendor_id": vendor_id,
            "_vendor_name_raw": vendor_raw,
            "_vendor_matched": vendor_matched,
            "requester_id": req_id,
            "_requester_raw": req_raw,
            "_requester_matched": req_matched,
            "asset": clean_val(row[COL_ASSET]) if clean_val(row[COL_ASSET]) else "N",
            "asset_nums": clean_ref(row[COL_ASSET_NUM]),
            "remark": clean_ref(row[COL_REMARK]),
            "internal_system_number": clean_val(row[COL_SUPPLIER]),
            "calloff_po_id": calloff_po_id,
            "currency": "CNY",
            "service_scope": service_scope,
        })
        # Also update the audit for this row (add an SC audit entry)
        _sc_audit = _make_audit(i, row)
        _add_audit(_sc_audit, record_type="SC", action="Imported (extracted from PO row)",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem=prob)
        print(f"  [MISSING SC] sc_no={sc_no}: extracted from PO row {i+1}")


# ── Fill missing PO records from SC/GR rows ───────────────────────────
# Some PO numbers appear only on SC Approved or GR rows (no PO Approved row).
# The GR import requires the PO to exist in DB first, so extract PO records
# from the first source row for each missing PO.

existing_po_nos = {r["po_no"] for r in po_rows}
gr_ref_pos = {r["po_no"] for r in gr_rows}
missing_pos = gr_ref_pos - existing_po_nos

# Exclude POs that user requested to skip
_SKIP_PO_NOS = {"7300063480"}
missing_pos -= _SKIP_PO_NOS

if missing_pos:
    first_src_row = {}
    for i, row in enumerate(raw_rows):
        if i < DATA_START or len(row) < 35:
            continue
        po_no = clean_val(row[COL_PO_NO])
        status = clean_val(row[COL_STATUS])
        contract_type = clean_val(row[COL_TYPE])
        if po_no in missing_pos and po_no not in first_src_row:
            # Prefer PO Approved or SC Approved rows (have more data)
            if status in ("PO Approved", "SC Approved"):
                first_src_row[po_no] = (i, row)

    # Fallback: any row with this PO
    for po_no in sorted(missing_pos):
        if po_no in first_src_row:
            continue
        for i, row in enumerate(raw_rows):
            if i < DATA_START or len(row) < 35:
                continue
            if clean_val(row[COL_PO_NO]) == po_no:
                first_src_row[po_no] = (i, row)
                break

    for po_no in sorted(missing_pos):
        if po_no not in first_src_row:
            print(f"  [MISSING PO] po_no={po_no}: no source row found, skipping")
            continue
        i, row = first_src_row[po_no]
        vendor_raw = clean_val(row[COL_VENDOR])
        vendor_id, vendor_matched = match_vendor(vendor_raw)
        if not vendor_matched:
            _po_audit = _make_audit(i, row)
            _add_audit(_po_audit, record_type="Skipped", action="Skipped (MISSING PO extraction)",
                       problem=f"Vendor '{vendor_raw}' not in DB, PO import requires vendor_id")
            print(f"  [MISSING PO] po_no={po_no}: vendor '{vendor_raw}' not in DB, skipped")
            continue
        req_raw = normalize_requestor(row[COL_REQ])
        req_id, req_matched = match_user(req_raw)
        purchaser_raw = clean_val(row[COL_PURCHASER])
        purchaser_id, purchaser_matched = match_user(purchaser_raw)
        contract_type = clean_val(row[COL_TYPE])
        sc_no = clean_val(row[COL_SC_NO])
        status = clean_val(row[COL_STATUS])

        # If extracted from SC Approved row, the SC NO is this row's SC
        # request_type matches the SC's type
        _rt = map_request_type(contract_type) if contract_type else "new"
        if _rt == "FC" and sc_no:
            _rt = "call_off"

        _po_amt = smart_float(clean_val(row[COL_PO_AMT]))
        _po_amt_fallback = False
        if not _po_amt or _po_amt == "":
            _po_amt = smart_float(clean_val(row[COL_SC_AMT]))
            _po_amt_fallback = True

        fixes = []
        prob = ""
        if _po_amt_fallback:
            fixes.append(f"PO amount empty, using SC amount ({_po_amt}) as fallback")
        if not _po_amt or _po_amt == "":
            prob = "PO amount empty — manual fix needed"
        if not vendor_raw:
            prob = (prob + "; " if prob else "") + "Vendor name is empty"
        if not req_matched:
            fixes.append(f"Requester '{req_raw}' not in DB, using name as ID")
        if not purchaser_matched and purchaser_raw:
            fixes.append(f"Purchaser '{purchaser_raw}' not in DB, using name as ID")
        if contract_type == "FC" and sc_no and _rt == "call_off":
            fixes.append(f"FC-type PO with sc_no: request_type adjusted FC->call_off")
        if contract_type in ("PO", "Contract"):
            fixes.append(f"request_type mapped: '{contract_type}' -> '{_rt}'")

        # Determine PO status: finished if any Finish GR references it
        finished_po_nos_set = {r["po_no"] for r in gr_rows if r.get("_source") == "Finish"}
        po_status = "finished" if po_no in finished_po_nos_set else "active"

        po_rows.append({
            "_row": i + 1,
            "po_id": "",
            "sc_no": sc_no,
            "po_no": po_no,
            "po_amount": _po_amt,
            "status": po_status,
            "request_type": _rt,
            "contract_type": contract_type if contract_type else "PO",
            "contract_pos": clean_val(row[COL_POS]),
            "cost_center": clean_val(row[COL_COST]),
            "vendor_id": vendor_id,
            "_vendor_name_raw": vendor_raw,
            "_vendor_matched": vendor_matched,
            "requester_id": req_id,
            "_requester_raw": req_raw,
            "_requester_matched": req_matched,
            "purchaser": purchaser_id if purchaser_matched else purchaser_raw,
            "_purchaser_raw": purchaser_raw,
            "contract_from": parse_date_str(row[COL_CON_FROM]),
            "contract_to": parse_date_str(row[COL_CON_TO]),
            "contract_no": extract_contract_no(row[COL_REMARK]),
            "payment_frequency": clean_val(row[COL_PAY_FREQ]),
        })
        _po_audit = _make_audit(i, row)
        _add_audit(_po_audit, record_type="PO", action=f"Imported (extracted from {status} row)",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem=prob)
        print(f"  [MISSING PO] po_no={po_no}: extracted from {status} row {i+1}")

# Second pass: after PO extraction, check for newly revealed missing SC refs
existing_sc_nos2 = {r["sc_no"] for r in sc_rows}
po_ref_scs2 = {r["sc_no"] for r in po_rows if r["sc_no"]}
missing_scs2 = po_ref_scs2 - existing_sc_nos2

if missing_scs2:
    first_po_row2 = {}
    for i, row in enumerate(raw_rows):
        if i < DATA_START or len(row) < 35:
            continue
        sc_no = clean_val(row[COL_SC_NO])
        status = clean_val(row[COL_STATUS])
        if sc_no in missing_scs2 and status in ("PO Approved", "SC Approved", "Finish") and sc_no not in first_po_row2:
            first_po_row2[sc_no] = (i, row)

    for sc_no in sorted(missing_scs2):
        if sc_no not in first_po_row2:
            # Try any row
            for i, row in enumerate(raw_rows):
                if i < DATA_START or len(row) < 35:
                    continue
                if clean_val(row[COL_SC_NO]) == sc_no:
                    first_po_row2[sc_no] = (i, row)
                    break
        if sc_no not in first_po_row2:
            print(f"  [MISSING SC-2] sc_no={sc_no}: no source row found, skipping")
            continue
        i, row = first_po_row2[sc_no]
        vendor_raw = clean_val(row[COL_VENDOR])
        service_scope = normalize_scope(row[COL_SCOPE])
        vendor_id, vendor_matched = match_vendor(vendor_raw)
        req_raw = normalize_requestor(row[COL_REQ])
        req_id, req_matched = match_user(req_raw)
        contract_type = clean_val(row[COL_TYPE])

        sc_amt = smart_float(clean_val(row[COL_SC_AMT]))
        sc_amt_fallback = False
        if not sc_amt or sc_amt == "":
            sc_amt = smart_float(clean_val(row[COL_PO_AMT]))
            sc_amt_fallback = True

        calloff_po_id = ""
        if contract_type == "PO under FC":
            calloff_po_id = extract_7600_po(clean_val(row[COL_DESC]))

        _mapped_rt = map_request_type(contract_type)
        fixes = []
        prob = ""
        if sc_amt_fallback:
            fixes.append(f"SC amount empty, using PO amount ({sc_amt}) as fallback")
        if not vendor_raw:
            prob = "Vendor name is empty in source data — SC import will fail without vendor"
        elif not vendor_matched:
            fixes.append(f"Vendor '{vendor_raw}' not in DB, vendor_id left empty")
        if not req_matched:
            fixes.append(f"Requester '{req_raw}' not in DB, using name as ID")
        if calloff_po_id:
            fixes.append(f"Extracted calloff_po_id={calloff_po_id} from Description")
        if contract_type in ("PO", "Contract"):
            fixes.append(f"request_type mapped: '{contract_type}' -> '{_mapped_rt}'")

        sc_rows.append({
            "_row": i + 1,
            "sc_no": sc_no,
            "sc_amount": sc_amt,
            "status": "approved",
            "request_type": _mapped_rt,
            "cost_center": clean_val(row[COL_COST]),
            "description": clean_val(row[COL_DESC]),
            "service_period_start": parse_date_str(row[COL_CON_FROM]),
            "service_period_end": parse_date_str(row[COL_CON_TO]),
            "vendor_id": vendor_id,
            "_vendor_name_raw": vendor_raw,
            "_vendor_matched": vendor_matched,
            "requester_id": req_id,
            "_requester_raw": req_raw,
            "_requester_matched": req_matched,
            "asset": clean_val(row[COL_ASSET]) if clean_val(row[COL_ASSET]) else "N",
            "asset_nums": clean_ref(row[COL_ASSET_NUM]),
            "remark": clean_ref(row[COL_REMARK]),
            "internal_system_number": clean_val(row[COL_SUPPLIER]),
            "calloff_po_id": calloff_po_id,
            "currency": "CNY",
            "service_scope": service_scope,
        })
        _sc_audit2 = _make_audit(i, row)
        _add_audit(_sc_audit2, record_type="SC", action="Imported (extracted from non-SC row, pass 2)",
                   auto_fix="; ".join(fixes) if fixes else "",
                   problem=prob)
        print(f"  [MISSING SC-2] sc_no={sc_no}: extracted from row {i+1}")

# ── deduplicate & merge ────────────────────────────────────────────────

# SC: deduplicate by sc_no
seen_sc = set()
unique_sc = []
for r in sc_rows:
    if r["sc_no"] not in seen_sc:
        seen_sc.add(r["sc_no"])
        unique_sc.append(r)
    else:
        print(f"  [DUP SC] row {r['_row']}: sc_no={r['sc_no']}")
        # Update audit: mark as deduplicated
        for a in audit_rows:
            if a["_row"] == r["_row"] and a["record_type"] == "SC":
                a["action"] = "Deduplicated (duplicate SC NO, first row kept)"
                break

# ── Inherit SC dates from related POs ───────────────────────────────────
# Build PO date lookup: po_no → {contract_from, contract_to}
po_date_lookup: dict[str, dict] = {}
for r in po_rows:
    po_no = r.get("po_no", "")
    cf = r.get("contract_from", "")
    ct = r.get("contract_to", "")
    if cf or ct:
        existing = po_date_lookup.get(po_no, {})
        if cf:
            existing.setdefault("contract_from", cf)
        if ct:
            existing.setdefault("contract_to", ct)
        po_date_lookup[po_no] = existing

# Also build sc_no → PO dates lookup (linked POs)
sc_po_dates: dict[str, dict] = {}
for r in po_rows:
    sc_no = r.get("sc_no", "")
    if not sc_no:
        continue
    cf = r.get("contract_from", "")
    ct = r.get("contract_to", "")
    if cf or ct:
        existing = sc_po_dates.get(sc_no, {})
        if cf:
            existing.setdefault("contract_from", cf)
        if ct:
            existing.setdefault("contract_to", ct)
        sc_po_dates[sc_no] = existing

sc_date_fixes = []
for sc in unique_sc:
    sps = sc.get("service_period_start", "")
    spe = sc.get("service_period_end", "")
    if sps and spe:
        continue
    po_dates = {}
    # Priority 1: calloff_po_id (FC PO)
    calloff = sc.get("calloff_po_id", "")
    if calloff and calloff in po_date_lookup:
        po_dates = po_date_lookup[calloff]
    # Priority 2: linked PO by sc_no
    if (not sps or not spe) and sc["sc_no"] in sc_po_dates:
        linked = sc_po_dates[sc["sc_no"]]
        if "contract_from" in linked and not sps:
            po_dates.setdefault("contract_from", linked["contract_from"])
        if "contract_to" in linked and not spe:
            po_dates.setdefault("contract_to", linked["contract_to"])

    if not po_dates:
        continue

    fixes = []
    if not sps and po_dates.get("contract_from"):
        sps = po_dates["contract_from"]
        fixes.append(f"service_period_start filled from PO ({sps})")
        sc["service_period_start"] = sps
    if not spe and po_dates.get("contract_to"):
        spe = po_dates["contract_to"]
        fixes.append(f"service_period_end filled from PO ({spe})")
        sc["service_period_end"] = spe

    if fixes:
        sc_date_fixes.append((sc["sc_no"], "; ".join(fixes)))
        # Update audit rows for this SC
        for a in audit_rows:
            if a.get("sc_no") == sc["sc_no"] and a["record_type"] == "SC":
                a["auto_fix"] = (a.get("auto_fix", "") + "; " + "; ".join(fixes)).strip("; ")
                a["action"] = "Imported"
                break

if sc_date_fixes:
    print(f"\n  [SC dates inherited from POs]:")
    for sc_no, msg in sorted(sc_date_fixes):
        print(f"    SC {sc_no}: {msg}")

# ── Fill remaining empty SC dates with 'N/A' ─────────────────────────
na_count = 0
for sc in unique_sc:
    for field in ("service_period_start", "service_period_end"):
        if not sc.get(field, ""):
            sc[field] = "N/A"
            na_count += 1
if na_count:
    print(f"  [SC dates filled with N/A]: {na_count} fields in {sum(1 for sc in unique_sc if sc.get('service_period_start') == 'N/A' or sc.get('service_period_end') == 'N/A')} SCs")

# PO: deduplicate by po_no; mark finished if any GR with same po_no exists
finished_po_nos = {r["po_no"] for r in gr_rows if r.get("_source") == "Finish"}
po_groups = {}
for r in po_rows:
    po_groups.setdefault(r["po_no"], []).append(r)

unique_po = []
for po_no, group in po_groups.items():
    # Take first PO Approved row per po_no
    po = dict(group[0])
    if po_no in finished_po_nos:
        po["status"] = "finished"
        # Update audit: mark PO as finished due to Finish GR
        for a in audit_rows:
            if a["_row"] == po["_row"] and a["record_type"] == "PO":
                a["auto_fix"] = (a.get("auto_fix", "") + "; Status set to 'finished' (matching Finish GR exists)").strip("; ")
                break
    unique_po.append(po)
    if len(group) > 1:
        print(f"  [DUP PO] po_no={po_no}, keeping first of {len(group)} rows")
        for dup in group[1:]:
            for a in audit_rows:
                if a["_row"] == dup["_row"] and a["record_type"] == "PO":
                    a["action"] = "Deduplicated (duplicate PO NO, first row kept)"
                    break

# ── Fill empty PO dates with 'N/A' ──────────────────────────────────
po_na_count = 0
for po in unique_po:
    for field in ("contract_from", "contract_to"):
        if not po.get(field, ""):
            po[field] = "N/A"
            po_na_count += 1
if po_na_count:
    print(f"  [PO dates filled with N/A]: {po_na_count} fields")

# GR: deduplicate by gr_no, prefer Finish-sourced rows.
# Fill estimated_amount from con_value when missing (DB has NOT NULL CHECK > 0).
seen_gr = {}  # gr_no -> row
for r in gr_rows:
    gr_no = r["gr_no"]
    if gr_no not in seen_gr:
        if not r["estimated_amount"] or r["estimated_amount"] == "":
            if r["con_value"] and r["con_value"] != "":
                r["estimated_amount"] = r["con_value"]
        seen_gr[gr_no] = r
    elif r.get("_source") == "Finish":
        # Finish overrides earlier GR; carry forward estimated_amount if needed
        if not r["estimated_amount"] or r["estimated_amount"] == "":
            if r["con_value"] and r["con_value"] != "":
                r["estimated_amount"] = r["con_value"]
        print(f"  [DUP GR] row {r['_row']}: gr_no={gr_no} (Finish overrides earlier)")
        # Mark old entry as deduplicated
        old = seen_gr[gr_no]
        for a in audit_rows:
            if a["_row"] == old["_row"] and a["record_type"] == "GR":
                a["action"] = f"Deduplicated (Finish GR row {r['_row']} overrides)"
                break
        seen_gr[gr_no] = r
    else:
        print(f"  [DUP GR] row {r['_row']}: gr_no={gr_no}")
        for a in audit_rows:
            if a["_row"] == r["_row"] and a["record_type"] == "GR":
                a["action"] = "Deduplicated (duplicate GR NO, first row kept)"
                break
unique_gr = list(seen_gr.values())

# Mark estimated_amount fallback in audit
for _gr in unique_gr:
    _est = _gr.get("estimated_amount")
    _cv = _gr.get("con_value")
    if (not _est or _est == "") and _cv and _cv != "":
        for a in audit_rows:
            if a["_row"] == _gr["_row"] and a["record_type"] == "GR":
                a["auto_fix"] = (a.get("auto_fix", "") + f"; estimated_amount filled from con_value ({_cv})").strip("; ")
                break

# ── Resolve internal_system_number -> calloff_po_id for SCs ────────────
# For call-off SCs where calloff_po_id is empty but internal_system_number
# (Supplier column, contains PO external number) is set, look up the
# corresponding PO by po_no and fill in calloff_po_id.
resolved_calloff = 0
unresolved_calloff = 0
if os.path.exists(DB_PATH):
    po_lookup_conn = sqlite3.connect(DB_PATH)
    po_lookup_conn.row_factory = sqlite3.Row
    po_by_no = {}
    for po_row in po_lookup_conn.execute(
        "SELECT po_id, po_no, created_at FROM pos WHERE po_no IS NOT NULL AND po_no != '' ORDER BY created_at DESC"
    ):
        po_by_no.setdefault(po_row["po_no"], []).append(dict(po_row))
    po_lookup_conn.close()

    for sc in unique_sc:
        # Only resolve if calloff_po_id is empty but internal_system_number is set
        if sc.get("calloff_po_id", ""):
            continue
        if sc.get("request_type") != "call_off":
            continue
        isn = sc.get("internal_system_number", "")
        if not isn:
            continue

        matches = po_by_no.get(isn, [])
        if len(matches) == 1:
            sc["calloff_po_id"] = matches[0]["po_id"]
            resolved_calloff += 1
        elif len(matches) > 1:
            # Multiple POs with same po_no — data integrity issue
            sc["calloff_po_id"] = matches[0]["po_id"]  # most recent by created_at DESC
            resolved_calloff += 1
            # Record warning in audit
            for a in audit_rows:
                if a["_row"] == sc["_row"] and a["record_type"] == "SC":
                    a["auto_fix"] = (a.get("auto_fix", "") +
                        f"; Multiple POs with po_no={isn}, used most recent {matches[0]['po_id']}").strip("; ")
                    break
        else:
            unresolved_calloff += 1
            # Record in audit
            for a in audit_rows:
                if a["_row"] == sc["_row"] and a["record_type"] == "SC":
                    a["problem"] = (a.get("problem", "") +
                        f"; No PO found with po_no={isn}, calloff_po_id left empty").strip("; ")
                    break

    print(f"  [calloff_po_id resolution]: {resolved_calloff} resolved, {unresolved_calloff} unresolved")

# ── write import CSVs (columns match download template exactly) ─────────

SC_FIELDS = ["sc_no", "vendor_id", "requester_id", "request_type", "cost_center",
             "sc_amount", "service_period_start", "service_period_end", "status",
             "description", "currency", "service_scope", "internal_system_number",
             "calloff_po_id", "asset", "asset_nums"]

PO_FIELDS = ["po_id", "sc_no", "vendor_id", "po_no", "requester_id",
             "request_type", "po_amount", "status", "contract_from", "contract_to",
             "contract_no", "payment_frequency", "contract_pos", "contract_type",
             "cost_center", "purchaser"]

GR_FIELDS = ["po_no", "gr_no", "requester_id",
             "estimated_amount", "con_value", "status", "remark", "tax_rate",
             "gross_cost", "goods_service_description", "confirmation_name",
             "delivery_from", "delivery_to", "last_delivery"]

VENDOR_FIELDS = ["vendor_id", "vendor_name", "ksrm_vendor_code",
                 "company_name_cn", "contact_person", "phone",
                 "service_scope", "email", "description", "inquiry_history"]

def write_csv(filename, fields, rows):
    path = os.path.join(BASE, filename)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {filename}: {len(rows)} rows")

write_csv("import_sc.csv", SC_FIELDS, unique_sc)
write_csv("import_po.csv", PO_FIELDS, unique_po)
write_csv("import_gr.csv", GR_FIELDS, unique_gr)

# Vendor import: auto-generate vendor_id, use name as-is
vendor_import = []
for vname, scope in sorted(unique_vendors.items()):
    vendor_import.append({
        "vendor_id": vname,  # name as ID (user will fix later)
        "vendor_name": vname,
        "ksrm_vendor_code": "",
        "company_name_cn": "",
        "contact_person": "",
        "phone": "",
        "service_scope": scope,
        "email": "",
        "description": "",
        "inquiry_history": "",
    })
write_csv("import_vendor.csv", VENDOR_FIELDS, vendor_import)

# ── write full_data audit CSV ──────────────────────────────────────────

FULL_DATA_FIELDS = ["_row", "service_scope", "year", "pos", "sc_no", "po_no",
                     "contract_type", "status", "vendor", "description",
                     "net_gr", "gr_vat", "con_val", "open_po", "po_amt", "sc_amt",
                     "category", "req_raw", "cost_center", "req_date",
                     "conf_no", "con_date", "conf_from", "conf_to",
                     "pay_freq", "purchaser", "supplier", "asset", "remark", "asset_num",
                     "record_type", "action", "problem", "auto_fix"]

audit_rows.sort(key=lambda a: a["_row"])
try:
    write_csv("full_data.csv", FULL_DATA_FIELDS, audit_rows)
except PermissionError:
    write_csv("full_data_v2.csv", FULL_DATA_FIELDS, audit_rows)
    print("  [NOTE] full_data.csv was locked, wrote full_data_v2.csv instead")

# ── summary ───────────────────────────────────────────────────────────
print(f"\n=== SUMMARY ===")
print(f"SC:  {len(unique_sc)}")
print(f"PO:  {len(unique_po)}")
print(f"GR:  {len(unique_gr)}")
print(f"Vendors for import: {len(vendor_import)}")
print(f"Total: {len(unique_sc) + len(unique_po) + len(unique_gr)}")
print(f"\nSkipped:")
for k, v in skipped.items():
    print(f"  {k}: {v}")

# Report issues
unmatched_v = set()
unmatched_u = set()
for r in unique_sc + unique_po:
    if not r.get("_vendor_matched") and r.get("_vendor_name_raw"):
        unmatched_v.add(r["_vendor_name_raw"])
    if not r.get("_requester_matched") and r.get("_requester_raw"):
        unmatched_u.add(r["_requester_raw"])
for r in unique_gr:
    if not r.get("_requester_matched") and r.get("_requester_raw"):
        unmatched_u.add(r["_requester_raw"])

if unmatched_v:
    print(f"\n[!] Unmatched vendors ({len(unmatched_v)}):")
    for v in sorted(unmatched_v):
        print(f"  - {v}")
if unmatched_u:
    print(f"\n[!] Unmatched users ({len(unmatched_u)}):")
    for u in sorted(unmatched_u):
        print(f"  - {u}")

# PO with empty amount
empty_po = [r for r in unique_po if not r["po_amount"] or r["po_amount"] == ""]
if empty_po:
    print(f"\n[!] PO empty amount ({len(empty_po)}):")
    for r in empty_po:
        print(f"  po_no={r['po_no']} sc_no={r['sc_no']} row={r['_row']}")

# PO missing contract_from/to
no_dates = [r for r in unique_po if not r['contract_from'] and not r['contract_to']]
if no_dates:
    print(f"\n[!] PO missing contract_from/to ({len(no_dates)}):")
    for r in no_dates:
        print(f"  po_no={r['po_no']} status={r['status']} row={r['_row']}")

# GR missing estimated_amount
no_est = [r for r in unique_gr if not r['estimated_amount'] or r['estimated_amount'] == ""]
if no_est:
    print(f"\n[!] GR missing estimated_amount ({len(no_est)}):")
    for r in no_est[:5]:
        print(f"  gr_no={r['gr_no']} row={r['_row']}")
    if len(no_est) > 5:
        print(f"  ... and {len(no_est)-5} more")

# SC with calloff_po_id
sc_with_calloff = [r for r in unique_sc if r.get("calloff_po_id")]
if sc_with_calloff:
    print(f"\n[!] SC with calloff_po_id ({len(sc_with_calloff)}):")
    for r in sc_with_calloff:
        print(f"  sc_no={r['sc_no']} calloff_po_id={r['calloff_po_id']} desc={r['description'][:60]}")

print("\nDone.")
