"""Phase 5 E2E Validation Test Suite"""
import requests
import time
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ALB = 'http://digestor-dev-1792703510.us-east-1.elb.amazonaws.com'
PASS_COUNT = 0
FAIL_COUNT = 0
ISSUES = []

def test(name, condition, detail=''):
    global PASS_COUNT, FAIL_COUNT, ISSUES
    if condition:
        PASS_COUNT += 1
        print(f'  PASS: {name}')
    else:
        FAIL_COUNT += 1
        ISSUES.append((name, detail))
        print(f'  FAIL: {name} -- {detail}')

# ============================================================
# 1. LOGIN AS ADMIN
# ============================================================
print('=' * 60)
print('TEST 1: Auth flows')
print('=' * 60)

login = requests.post(f'{ALB}/api/auth/login', json={'email': 'admin@digestor-test.com', 'password': 'DigestorAdmin1'})
test('Admin login', login.status_code == 200, f'status={login.status_code}')
admin_token = login.json().get('access_token', '')
admin_headers = {'Authorization': f'Bearer {admin_token}'}

me = requests.get(f'{ALB}/api/auth/me', headers=admin_headers)
test('Get /me', me.status_code == 200, f'status={me.status_code}')
me_data = me.json()
test('/me returns role=admin', me_data.get('role') == 'admin', f'role={me_data.get("role")}')

# Refresh token
refresh_token = login.json().get('refresh_token', '')
refresh = requests.post(f'{ALB}/api/auth/refresh', json={'refresh_token': refresh_token})
test('Token refresh', refresh.status_code == 200, f'status={refresh.status_code}')

print()

# ============================================================
# 2. UPLOAD + PROCESS + RESULTS
# ============================================================
print('=' * 60)
print('TEST 2: Upload -> Process -> Results')
print('=' * 60)

test_text = (
    'STRUCTURAL ENGINEERING REPORT. Building Code: IBC 2021. ASCE 7-22. '
    'Wind Speed Vult: 115 mph. Risk Category: II. Exposure: C. GCpi: 0.18. '
    'Roof Live: 20 psf. Roof Dead: 20 psf. Ground Snow Pg: 30 psf. Is: 1.0. '
    'Ce: 0.9. Ct: 1.0. Pf: 21.6 psf. SDC: D. Ie: 1.0. Site Class: D. '
    'SDS: 0.85g. SD1: 0.45g. Exterior Wall Deflection: H/240. '
    'Floor Joist: L/360. Roof Rafter: L/240.'
)

ts = int(time.time())
upload = requests.post(
    f'{ALB}/api/upload-document',
    headers=admin_headers,
    files={'file': ('phase5-test.pdf', test_text.encode(), 'application/pdf')},
    data={'project_name': f'Phase5Test_{ts}'}
)
test('Upload document', upload.status_code == 200, f'status={upload.status_code} body={upload.text[:200]}')

doc_id = None
new_project_id = None

if upload.status_code == 200:
    upload_data = upload.json()
    doc_id = upload_data['processingId']

    process = requests.post(f'{ALB}/api/process-document', headers=admin_headers,
        json={'document_id': doc_id, 'extracted_text': test_text})
    test('Process document', process.status_code == 200, f'status={process.status_code}')

    # Poll once
    time.sleep(1)
    results = requests.get(f'{ALB}/api/results/{doc_id}', headers=admin_headers)
    rdata = results.json()
    test('Results status=complete', rdata['status'] == 'complete', f'status={rdata["status"]}')
    test('Results has 25 items', len(rdata.get('results', [])) == 25, f'count={len(rdata.get("results", []))}')
    test('Results format: category exists', 'category' in rdata.get('results', [{}])[0], str(list(rdata.get('results', [{}])[0].keys())))
    test('Results format: pairs exists', 'pairs' in rdata.get('results', [{}])[0], '')

    first_conf = rdata['results'][0]['pairs'][0].get('confidence', -1)
    test('Confidence is 0-1 scale', 0 <= first_conf <= 1.0, f'confidence={first_conf}')
    test('Avg confidence is 0-1 scale', 0 <= rdata.get('confidence_avg', -1) <= 1.0, f'avg={rdata.get("confidence_avg")}')

print()

# ============================================================
# 3. FEEDBACK (thumbs up/down)
# ============================================================
print('=' * 60)
print('TEST 3: Feedback (thumbs up/down)')
print('=' * 60)

if doc_id:
    fb = requests.post(f'{ALB}/api/results/feedback', headers=admin_headers,
        json={'document_id': doc_id, 'question_key': 'Q1', 'feedback_type': 'thumbs_down', 'remarks': 'Test feedback'})
    test('Submit feedback (thumbs_down)', fb.status_code == 200, f'status={fb.status_code} body={fb.text[:200]}')

    fb2 = requests.post(f'{ALB}/api/results/feedback', headers=admin_headers,
        json={'document_id': doc_id, 'question_key': 'Q2', 'feedback_type': 'thumbs_up'})
    test('Submit feedback (thumbs_up)', fb2.status_code == 200, f'status={fb2.status_code} body={fb2.text[:200]}')

    # Verify feedback persists
    results2 = requests.get(f'{ALB}/api/results/{doc_id}', headers=admin_headers)
    rdata2 = results2.json()
    feedbacks = rdata2.get('feedback', {})
    test('Feedback persisted in results', len(feedbacks) > 0, f'feedback={feedbacks}')

    # Update feedback (overwrite)
    fb3 = requests.post(f'{ALB}/api/results/feedback', headers=admin_headers,
        json={'document_id': doc_id, 'question_key': 'Q1', 'feedback_type': 'thumbs_up'})
    test('Update existing feedback', fb3.status_code == 200, f'status={fb3.status_code}')
else:
    print('  SKIP: No doc_id from upload')

print()

# ============================================================
# 4. INLINE EDITING
# ============================================================
print('=' * 60)
print('TEST 4: Inline editing of answers')
print('=' * 60)

if doc_id:
    edit = requests.put(f'{ALB}/api/results/update', headers=admin_headers,
        json={'document_id': doc_id, 'question_key': 'Q1', 'new_value': 'IBC 2024 (edited)', 'remarks': 'Test edit'})
    test('Inline edit answer', edit.status_code == 200, f'status={edit.status_code} body={edit.text[:300]}')

    # Verify edit persists
    results_after_edit = requests.get(f'{ALB}/api/results/{doc_id}', headers=admin_headers)
    rdata_edit = results_after_edit.json()
    first_answer = rdata_edit['results'][0]['pairs'][0]['answer'] if rdata_edit.get('results') else ''
    test('Edit persisted in results', 'IBC 2024' in str(rdata_edit.get('results', [])), f'first_answer={first_answer}')
else:
    print('  SKIP: No doc_id from upload')

print()

# ============================================================
# 5. PROJECT CRUD
# ============================================================
print('=' * 60)
print('TEST 5: Project CRUD')
print('=' * 60)

# List projects
projects = requests.get(f'{ALB}/api/projects?page=1&per_page=200', headers=admin_headers)
test('List projects', projects.status_code == 200, f'status={projects.status_code}')
proj_data = projects.json()
test('Projects response has items', 'items' in proj_data, f'keys={list(proj_data.keys())}')
test('Projects response has total', 'total' in proj_data, f'keys={list(proj_data.keys())}')

# Create project
create = requests.post(f'{ALB}/api/projects', headers=admin_headers,
    json={'name': f'CRUDTest_{ts}', 'description': 'Test project for Phase 5'})
test('Create project', create.status_code in (200, 201), f'status={create.status_code} body={create.text[:300]}')

if create.status_code in (200, 201):
    new_project = create.json()
    new_project_id = new_project.get('id', new_project.get('project_id', ''))
    test('Create returns ID', bool(new_project_id), f'response_keys={list(new_project.keys())}')

    if new_project_id:
        # Get project detail
        detail = requests.get(f'{ALB}/api/projects/{new_project_id}', headers=admin_headers)
        test('Get project detail', detail.status_code == 200, f'status={detail.status_code} body={detail.text[:300]}')

        # Update project
        update = requests.put(f'{ALB}/api/projects/{new_project_id}', headers=admin_headers,
            json={'name': f'CRUDTest_{ts}_updated', 'description': 'Updated description'})
        test('Update project', update.status_code == 200, f'status={update.status_code} body={update.text[:300]}')

        # Submit for review
        submit = requests.post(f'{ALB}/api/submit-project', headers=admin_headers,
            json={'project_id': new_project_id})
        test('Submit project for review', submit.status_code == 200, f'status={submit.status_code} body={submit.text[:300]}')

# List pending (admin should see pending)
pending = requests.get(f'{ALB}/api/projects/pending', headers=admin_headers)
test('List pending projects', pending.status_code == 200, f'status={pending.status_code} body={pending.text[:300]}')

print()

# ============================================================
# 6. SUPERVISOR APPROVAL FLOW
# ============================================================
print('=' * 60)
print('TEST 6: Supervisor approval flow')
print('=' * 60)

sup_login = requests.post(f'{ALB}/api/auth/login', json={'email': 'supervisor@digestor-test.com', 'password': 'DigestorSuper1'})
test('Supervisor login', sup_login.status_code == 200, f'status={sup_login.status_code}')
sup_token = sup_login.json().get('access_token', '')
sup_headers = {'Authorization': f'Bearer {sup_token}'}

sup_me = requests.get(f'{ALB}/api/auth/me', headers=sup_headers)
test('Supervisor /me', sup_me.status_code == 200, f'status={sup_me.status_code}')
test('Supervisor role', sup_me.json().get('role') == 'supervisor', f'role={sup_me.json().get("role")}')

# Supervisor sees pending projects
sup_pending = requests.get(f'{ALB}/api/projects/pending', headers=sup_headers)
test('Supervisor list pending', sup_pending.status_code == 200, f'status={sup_pending.status_code} body={sup_pending.text[:300]}')

# Approve a project
if new_project_id:
    approve = requests.post(f'{ALB}/api/approve-project', headers=sup_headers,
        json={'project_id': new_project_id, 'approved': True, 'remarks': 'Looks good'})
    test('Approve project', approve.status_code == 200, f'status={approve.status_code} body={approve.text[:300]}')

    # Verify status changed
    detail2 = requests.get(f'{ALB}/api/projects/{new_project_id}', headers=admin_headers)
    if detail2.status_code == 200:
        proj_status = detail2.json().get('status', '')
        test('Project status after approval', proj_status == 'approved', f'status={proj_status}')
else:
    print('  SKIP: No project to approve')

print()

# ============================================================
# 7. ENGINEER LOGIN & ACCESS
# ============================================================
print('=' * 60)
print('TEST 7: Engineer login & access')
print('=' * 60)

eng_login = requests.post(f'{ALB}/api/auth/login', json={'email': 'engineer@digestor-test.com', 'password': 'DigestorEngineer1'})
test('Engineer login', eng_login.status_code == 200, f'status={eng_login.status_code}')
eng_token = eng_login.json().get('access_token', '')
eng_headers = {'Authorization': f'Bearer {eng_token}'}

eng_me = requests.get(f'{ALB}/api/auth/me', headers=eng_headers)
test('Engineer /me', eng_me.status_code == 200, f'status={eng_me.status_code}')
test('Engineer role', eng_me.json().get('role') == 'engineer', f'role={eng_me.json().get("role")}')

eng_projects = requests.get(f'{ALB}/api/projects?page=1&per_page=10', headers=eng_headers)
test('Engineer list projects', eng_projects.status_code == 200, f'status={eng_projects.status_code}')

# Engineer should NOT be able to access pending (supervisor only)
eng_pending = requests.get(f'{ALB}/api/projects/pending', headers=eng_headers)
test('Engineer cannot list pending', eng_pending.status_code in (403, 401), f'status={eng_pending.status_code}')

print()

# ============================================================
# 8. TICKETS
# ============================================================
print('=' * 60)
print('TEST 8: Ticket creation & listing')
print('=' * 60)

ticket_create = requests.post(f'{ALB}/api/tickets', headers=admin_headers,
    json={'subject': f'Test Ticket {ts}', 'description': 'This is a test ticket for Phase 5 validation', 'priority': 'medium'})
test('Create ticket', ticket_create.status_code in (200, 201), f'status={ticket_create.status_code} body={ticket_create.text[:300]}')

ticket_list = requests.get(f'{ALB}/api/tickets', headers=admin_headers)
test('List tickets', ticket_list.status_code == 200, f'status={ticket_list.status_code}')

if ticket_list.status_code == 200:
    tickets = ticket_list.json()
    if isinstance(tickets, list):
        test('Tickets is array', len(tickets) > 0, f'count={len(tickets)}')
    elif isinstance(tickets, dict):
        items = tickets.get('items', tickets.get('tickets', []))
        test('Tickets has items', len(items) > 0, f'keys={list(tickets.keys())}')

print()

# ============================================================
# 9. ANALYTICS
# ============================================================
print('=' * 60)
print('TEST 9: Analytics dashboard')
print('=' * 60)

analytics = requests.get(f'{ALB}/api/analytics/overview', headers=admin_headers)
test('Analytics overview', analytics.status_code == 200, f'status={analytics.status_code} body={analytics.text[:300]}')

if analytics.status_code == 200:
    adata = analytics.json()
    test('Analytics has doc_count', 'doc_count' in adata or 'total_documents' in adata, f'keys={list(adata.keys())}')

print()

# ============================================================
# SUMMARY
# ============================================================
print('=' * 60)
print(f'RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed')
print('=' * 60)
if ISSUES:
    print()
    print('FAILURES:')
    for name, detail in ISSUES:
        print(f'  - {name}: {detail}')
print()
