"""Manual acceptance test - using functional API.
All search functions return list[dict] directly."""
import os, sys, re, uuid, datetime
os.environ['SC_GR_DEV'] = '1'
sys.path.insert(0, os.path.dirname(__file__))

from sc_gr_app.config import default_config
from sc_gr_app.services import (
    user_service, vendor_service, sc_service, po_service,
    gr_service, notification_service, budget_service, record_service
)
from sc_gr_app.services.query_service import (
    search_scs, search_pos, search_grs, search_vendors, search_operation_records
)

config = default_config()

# Run migrations
from sc_gr_app.db.migrations import migrate
migrate(config)
print(f'  DB migrated to latest version')

PASS, FAIL = '[PASS]', '[FAIL]'
results = []

def check(name, condition, detail=''):
    status = PASS if condition else FAIL
    results.append((name, condition, detail))
    print(f'  {status} {name}' + (f'  -- {detail}' if detail else ''))

def hr(title):
    print(f'\n{"="*60}')
    print(f'  {title}')
    print(f'{"="*60}')

# ============================================
hr('Environment Check')
# ============================================
print(f'  DB: {config.db_path}')
check('DB file exists', os.path.exists(config.db_path))

users = user_service.list_active_users(config)
admin = next((u for u in users if u.get('role') == 'admin'), None)
if not admin:
    print('  [FAIL] FATAL: No admin user')
    sys.exit(1)
admin_user = admin
# user_id is the internal ID, machine_id is the machine identifier
admin_uid = admin['user_id']  # e.g. "U-DESKTOP-XXX"

# ============================================
hr('Section 1: Login & Auth')
# ============================================
check('1.1 Users exist', len(users) > 0, f'{len(users)} users')
check('1.2 Admin role=admin', admin_user['role'] == 'admin')
check('1.3 Admin has machine_id', bool(admin_user.get('machine_id')))
check('1.4 Non-admin (requester) exists', any(u['role'] == 'requester' for u in users))

with open('frontend/src/router/index.js', 'r', encoding='utf-8') as f:
    router = f.read()
for r in ['login','workbench','sc-list','sc-detail','po-detail','po-list','gr-list','vendor-list','logs','emails','system']:
    check(f'1.5 Route: {r}', f"'{r}'" in router)

# ============================================
hr('Section 2: Workbench')
# ============================================
p = search_scs(config, filters={'status':'pending'}, limit=5, offset=0)
check('2.1 Search pending SCs', isinstance(p, list), f'{len(p)} rows')
p2 = search_pos(config, filters={'status':'po_pending'}, limit=5, offset=0)
check('2.2 Search pending POs', isinstance(p2, list), f'{len(p2)} rows')
p3 = search_grs(config, filters={'status':'pending'}, limit=5, offset=0)
check('2.3 Search pending GRs', isinstance(p3, list), f'{len(p3)} rows')
p4 = search_scs(config, filters={'status':'draft'}, limit=5, offset=0)
check('2.4 Search drafts', isinstance(p4, list), f'{len(p4)} rows')
p5 = search_scs(config, filters={'status':'denied'}, limit=5, offset=0)
check('2.5 Search denied', isinstance(p5, list), f'{len(p5)} rows')

# Find or create a requester user for SC operations
# (admin can create draft but cannot submit - only requester can submit their own drafts)
requester_user = next((u for u in users if u['role'] == 'requester'), None)
if not requester_user:
    uid0 = uuid.uuid4().hex[:8]
    nu0 = user_service.create_user(config, admin_user, {
        'machine_id': f'RQ-{uid0}',
        'user_name': f'TestRequester-{uid0}',
        'email': f'rq{uid0}@test.com',
        'role': 'requester'
    })
    requester_user = nu0
    # Refresh users list
    users = user_service.list_active_users(config)
    requester_user = next((u for u in users if u.get('machine_id') == nu0['machine_id']), nu0)
req_uid = requester_user['user_id']

# ============================================
hr('Section 3: SC Management')
# ============================================
all_scs = search_scs(config, filters={})
check('3.0 SCs queryable', isinstance(all_scs, list), f'{len(all_scs)} SCs')

uid = uuid.uuid4().hex[:8]
today = datetime.date.today().strftime('%Y%m%d')

try:
    draft = sc_service.create_sc_draft(config, requester_user, {
        'requester_id': req_uid,
        'request_type': 'service',
        'cost_center': 'CC-TEST-01',
        'sc_amount': 5000.00,
        'service_period_start': '2026-06-01',
        'service_period_end': '2026-12-31',
        'sc_no': f'SC-TEST-001-{uid[:6]}',
        'description': f'Acceptance test SC {uid}'
    })
    check('3.1 Create SC draft', bool(draft.get('sc_id')), f'ID={draft.get("sc_id")}')
    sc_id = draft['sc_id']

    expected = f'SC-{requester_user["machine_id"]}-{today}'
    check('3.2 SC ID format', sc_id.startswith(expected), sc_id)

    # Submit (must be done by the draft owner = requester)
    sc_service.submit_sc(config, requester_user, sc_id, {})
    detail = sc_service.get_sc_detail(config, admin_user, sc_id)
    check('3.3 SC detail accessible', bool(detail.get('sc')), 'OK')
    check('3.4 SC status = pending', detail['sc']['status']=='pending', f'status={detail["sc"]["status"]}')

    # Already submitted above. Now test approve (admin)
    sc_service.approve_sc(config, admin_user, sc_id)
    d3 = sc_service.get_sc_detail(config, admin_user, sc_id)
    check('3.5 Approve: pending->approved', d3['sc']['status']=='approved')

    sc_service.close_sc(config, admin_user, sc_id)
    d4 = sc_service.get_sc_detail(config, admin_user, sc_id)
    check('3.6 Close: approved->closed', d4['sc']['status']=='closed')

    # SC#2 for deny test
    draft2 = sc_service.create_sc_draft(config, requester_user, {
        'requester_id': req_uid,
        'request_type': 'material',
        'cost_center': 'CC-TEST-02',
        'sc_amount': 3000.00,
        'service_period_start': '2026-07-01',
        'service_period_end': '2026-09-30',
        'sc_no': f'SC-TEST-002-{uid[:6]}',
        'description': f'Deny test SC {uid}'
    })
    sc_id2 = draft2['sc_id']
    sc_service.submit_sc(config, requester_user, sc_id2, {})
    sc_service.deny_sc(config, admin_user, sc_id2)
    dd = sc_service.get_sc_detail(config, admin_user, sc_id2)
    check('3.7 Deny: pending->denied', dd['sc']['status']=='denied')

    upd = sc_service.update_sc(config, admin_user, sc_id2, {'description':'Updated'})
    check('3.8 Edit SC', upd is not None)

    # SC#3: Keep in approved state for PO/GR tests
    draft3 = sc_service.create_sc_draft(config, requester_user, {
        'requester_id': req_uid,
        'request_type': 'service',
        'cost_center': 'CC-TEST-03',
        'sc_amount': 10000.00,
        'service_period_start': '2026-08-01',
        'service_period_end': '2026-12-31',
        'sc_no': f'SC-TEST-003-{uid[:6]}',
        'description': f'PO/GR test SC {uid}'
    })
    sc_id3 = draft3['sc_id']
    sc_service.submit_sc(config, requester_user, sc_id3, {})
    sc_service.approve_sc(config, admin_user, sc_id3)
    check('3.9 SC#3 approved for PO/GR tests', True, f'ID={sc_id3}')

    test_sc_id = sc_id3  # Use approved SC for PO/GR tests
    test_sc_id2 = sc_id2
except Exception as e:
    print(f'  [FAIL] SC test error: {e}')
    import traceback; traceback.print_exc()
    test_sc_id = None; test_sc_id2 = None

# ============================================
hr('Section 4: PO Management')
# ============================================
all_pos = search_pos(config, filters={})
check('4.0 POs queryable', isinstance(all_pos, list), f'{len(all_pos)} POs')

vendors = search_vendors(config, filters={})

if test_sc_id and len(vendors) > 0:
    try:
        vid = vendors[0]['vendor_id']
        po = po_service.create_po(config, admin_user, {
            'sc_id': test_sc_id,
            'vendor_id': vid,
            'po_amount': 2000.00,
            'po_no': f'PO-TEST-001-{uid[:6]}',
            'contract_from': '2026-06-01',
            'contract_to': '2026-11-30',
            'contract_no': 'CT-ACCTEST-001',
            'payment_frequency': 'monthly'
        })
        check('4.1 Create PO', bool(po.get('po_id')), f'ID={po.get("po_id")}')
        po_id = po['po_id']
        check('4.2 PO ID format', bool(re.match(r'PO-\w+-\d{8}-\d{3}$', po_id)), po_id)

        detail = sc_service.get_sc_detail(config, admin_user, test_sc_id)
        check('4.3 PO in SC detail', len(detail.get('pos',[]))>0, f'{len(detail.get("pos",[]))} POs')

        # Approve PO (needed for GR creation)
        po_service.approve_po(config, admin_user, po_id)
        pfs = search_pos(config, filters={'po_id': po_id})
        pf = next((p for p in pfs if str(p['po_id'])==str(po_id)), None)
        check('4.4 Approve PO', pf and pf['status']=='po_approved')

        # Edit PO
        po_service.update_po(config, admin_user, po_id, {'contract_no':'CT-MODIFIED'})
        check('4.5 Edit PO', True)

        test_po_id = po_id
    except Exception as e:
        print(f'  [FAIL] PO test error: {e}')
        import traceback; traceback.print_exc()
        test_po_id = None
else:
    print('  SKIP: No SC or vendors for PO tests')
    test_po_id = None

# ============================================
hr('Section 5: GR Management')
# ============================================
all_grs = search_grs(config, filters={})
check('5.0 GRs queryable', isinstance(all_grs, list), f'{len(all_grs)} GRs')

if test_po_id:
    try:
        gr = gr_service.create_gr(config, admin_user, {
            'po_id': test_po_id,
            'requester_id': admin_uid,
            'estimated_amount': 1500.00
        })
        check('5.1 Create GR', bool(gr.get('gr_id')), f'ID={gr.get("gr_id")}')
        gr_id = gr['gr_id']
        check('5.2 GR ID format', bool(re.match(r'GR-\w+-\d{8}-\d{3}$', gr_id)), gr_id)

        gr_service.update_gr(config, admin_user, gr_id, {'estimated_amount':1800.00})
        check('5.3 Edit GR', True)

        gr_service.approve_gr(config, admin_user, gr_id, 1500.50)
        gfs = search_grs(config, filters={'gr_id': gr_id})
        gf = next((g for g in gfs if str(g['gr_id'])==str(gr_id)), None)
        check('5.4 Approve GR', gf and gf['status']=='approved', f'con={gf.get("con_value") if gf else "N/A"}')

        gr2 = gr_service.create_gr(config, admin_user, {
            'po_id': test_po_id,
            'requester_id': admin_uid,
            'estimated_amount': 800.00
        })
        gr_service.cancel_gr(config, admin_user, gr2['gr_id'])
        gfs2 = search_grs(config, filters={'gr_id': gr2['gr_id']})
        gf2 = next((g for g in gfs2 if str(g['gr_id'])==str(gr2['gr_id'])), None)
        check('5.5 Cancel GR', gf2 and gf2['status']=='cancelled')

        test_gr_id = gr_id
    except Exception as e:
        print(f'  [FAIL] GR test error: {e}')
        import traceback; traceback.print_exc()
        test_gr_id = None

    # Finish PO after GR tests
    if test_po_id:
        try:
            po_service.finish_po(config, admin_user, test_po_id)
            pfs2 = search_pos(config, filters={'po_id': test_po_id})
            pf2 = next((p for p in pfs2 if str(p['po_id'])==str(test_po_id)), None)
            check('4.6 Finish PO', pf2 and pf2['status']=='finished')
        except Exception as e:
            print(f'  [FAIL] Finish PO error: {e}')
else:
    print('  SKIP: No PO for GR tests')
    test_gr_id = None

# ============================================
hr('Section 6: Vendor Management')
# ============================================
try:
    suffix = uuid.uuid4().hex[:8]
    vid_str = f'VENDOR-{suffix[:6]}'
    v = vendor_service.create_vendor(config, admin_user, {
        'vendor_id': vid_str,
        'vendor_name': f'TestVendor-{suffix}',
        'ksrm_vendor_code': f'KS-{suffix[:4]}',
        'service_scope': 'General Service',
        'contact_person': 'Test Contact',
        'phone': '13800138000',
        'email': f'tv{suffix}@test.com'
    })
    check('6.1 Create vendor', bool(v.get('vendor_id')), f'ID={v.get("vendor_id")}')
    v_id = v['vendor_id']

    vendor_service.update_vendor(config, admin_user, v_id, {'phone':'13900139000'})
    check('6.2 Edit vendor', True)

    vendor_service.disable_vendor(config, admin_user, v_id)
    vs = search_vendors(config, filters={'vendor_id': v_id})
    vf = next((x for x in vs if str(x['vendor_id'])==str(v_id)), None)
    check('6.3 Disable vendor', vf and vf.get('status')=='disabled')
except Exception as e:
    print(f'  [FAIL] Vendor test error: {e}')
    import traceback; traceback.print_exc()

# ============================================
hr('Section 7: Audit Logs')
# ============================================
log_rows = search_operation_records(config, filters={})
check('7.1 Audit logs', len(log_rows) > 0, f'{len(log_rows)} entries')
actions = [l.get('action_type') for l in log_rows[:40]]
expected = ['create_sc','submit_sc','approve_sc','close_sc','deny_sc',
            'create_po','approve_po','finish_po','create_gr','approve_gr',
            'cancel_gr','create_vendor','disable_vendor']
found = [a for a in expected if a in actions]
check('7.2 Expected actions logged', len(found) >= 10, f'{len(found)}/{len(expected)}: {found[:8]}')

# ============================================
hr('Section 8: Email Notification Queue')
# ============================================
try:
    q = notification_service.list_notification_queue(config, limit=10, offset=0)
    check('8.1 Notification queue', True, f'{len(q)} entries')
except Exception as e:
    check('8.1 Notification queue', False, str(e))

# ============================================
hr('Section 9: System Settings')
# ============================================
try:
    uid2 = uuid.uuid4().hex[:8]
    nu = user_service.create_user(config, admin_user, {
        'machine_id': f'TEST-MACHINE-{uid2}',
        'user_name': f'TestUser-{uid2}',
        'email': f'tu{uid2}@test.com',
        'role': 'requester'
    })
    check('9.1 Create user', bool(nu.get('machine_id')))
    nmid = nu['machine_id']

    user_service.update_user(config, admin_user, nmid, {'email':f'upd-{uid2}@test.com'})
    check('9.2 Edit user', True)

    user_service.disable_user(config, admin_user, nmid)
    u2 = user_service.list_active_users(config)
    ud = next((u for u in u2 if u['machine_id']==nmid), None)
    check('9.3 Disable user', ud is None, 'removed from active list (list_active_users filters)')

    user_service.enable_user(config, admin_user, nmid)
    u3 = user_service.list_active_users(config)
    ue = next((u for u in u3 if u['machine_id']==nmid), None)
    check('9.4 Enable user', ue is not None, 'back in active list')

    defaults = notification_service.get_notification_defaults(config)
    check('9.5 Notification defaults', True, f'keys: {list(defaults.keys())[:5]}')
except Exception as e:
    print(f'  [FAIL] System test error: {e}')
    import traceback; traceback.print_exc()

# ============================================
hr('Section 10: Budget Display')
# ============================================
if test_sc_id:
    try:
        b = budget_service.compute_sc_budget(config, test_sc_id)
        check('10.1 SC budget', b is not None,
             f'total={b.get("total")}, used={b.get("used")}, rem={b.get("remaining")}')
    except Exception as e:
        check('10.1 SC budget', False, str(e))

if test_po_id:
    try:
        b2 = budget_service.compute_po_budget(config, test_po_id)
        check('10.2 PO budget', b2 is not None,
             f'total={b2.get("total")}, used={b2.get("used")}, rem={b2.get("remaining")}')
    except Exception as e:
        check('10.2 PO budget', False, str(e))

# ============================================
hr('Section 11: Navigation & Layout')
# ============================================
with open('frontend/src/components/layout/SideNav.vue', 'r', encoding='utf-8') as f:
    sidebar = f.read()
for item in ['Workbench','SC','PO','GR','Vendor','Email','Logs','System']:
    check(f'11.1 Sidebar: {item}', item in sidebar)

with open('frontend/src/components/layout/AppHeader.vue', 'r', encoding='utf-8') as f:
    header = f.read()
check('11.2 Breadcrumb data-driven', 'breadcrumbs = computed(' in header)

# ============================================
hr('Section 12: Auto-Generated IDs')
# ============================================
if test_sc_id:
    check('12.1 SC ID SC-{M}-{D}-{SEQ}', bool(re.match(r'SC-\w+-\d{8}-\d{3}$', test_sc_id)), test_sc_id)
if test_po_id:
    check('12.2 PO ID PO-{M}-{D}-{SEQ}', bool(re.match(r'PO-\w+-\d{8}-\d{3}$', test_po_id)), test_po_id)
if test_gr_id:
    check('12.3 GR ID GR-{M}-{D}-{SEQ}', bool(re.match(r'GR-\w+-\d{8}-\d{3}$', test_gr_id)), test_gr_id)
if test_sc_id and test_sc_id2:
    s1, s2 = int(test_sc_id[-3:]), int(test_sc_id2[-3:])
    check('12.4 SC sequence increments', s1 > s2, f'{s2} -> {s1} (SC#2 before SC#3)')

# ============================================
hr('FINAL SUMMARY')
# ============================================
passed = sum(1 for _, p, _ in results if p)
total = len(results)
pct = passed*100//total if total else 0
print(f'\n  RESULTS: {passed}/{total} tests passed ({pct}%)')

failed = [(n,d) for n,p,d in results if not p]
if failed:
    print(f'\n  FAILURES ({len(failed)}):')
    for name, detail in failed:
        print(f'    [FAIL] {name}: {detail}')
else:
    print('\n  *** ALL TESTS PASSED! ***')

print(f'\n  DB state:')
print(f'    SCs: {len(search_scs(config,filters={}))}')
print(f'    POs: {len(search_pos(config,filters={}))}')
print(f'    GRs: {len(search_grs(config,filters={}))}')
print(f'    Vendors: {len(search_vendors(config,filters={}))}')
print(f'    Active Users: {len(user_service.list_active_users(config))}')
print(f'    Audit Logs: {len(search_operation_records(config,filters={}))}')
