import json
from collections import Counter

projects = json.load(open('backend/data/projects.json', encoding='utf-8'))
teams = json.load(open('backend/data/teams.json', encoding='utf-8'))
employees = json.load(open('backend/data/all_employees.json', encoding='utf-8'))
tickets = json.load(open('backend/data/all_tickets.json', encoding='utf-8'))

proj_by_id = {p['project_id']: p for p in projects}
emp_by_id = {e['employee_id']: e for e in employees}
team_by_id = {t['team_id']: t for t in teams}

# P01: What projects is Aarav working on?
aarav_projs = [p['name'] for p in emp_by_id['EMP-1001']['projects']['current']]
p01 = 'Customer Support Portal' in aarav_projs and 'Internal Analytics Dashboard' in aarav_projs
print('P01 (Aarav projects):', aarav_projs, '->', 'PASS' if p01 else 'FAIL')

# P02: How much time is Aarav allocated to Customer Support Portal?
p02_alloc = next(p['allocation_percent'] for p in emp_by_id['EMP-1001']['projects']['current'] if p['project_id'] == 'PRJ-ENG-CSP')
p02 = p02_alloc == 60
print('P02 (CSP allocation):', p02_alloc, '->', 'PASS' if p02 else 'FAIL')

# P03: How much time is Aarav allocated to Internal Analytics Dashboard?
p03_alloc = next(p['allocation_percent'] for p in emp_by_id['EMP-1001']['projects']['current'] if p['project_id'] == 'PRJ-ENG-IAD')
p03 = p03_alloc == 40
print('P03 (IAD allocation):', p03_alloc, '->', 'PASS' if p03 else 'FAIL')

# P04: Which project has Aarav's largest allocation?
p04_max = max(emp_by_id['EMP-1001']['projects']['current'], key=lambda x: x['allocation_percent'])
p04 = p04_max['project_id'] == 'PRJ-ENG-CSP' and p04_max['allocation_percent'] == 60
print('P04 (Largest allocation):', p04_max['name'], p04_max['allocation_percent'], '->', 'PASS' if p04 else 'FAIL')

# P05: Who works on Customer Support Portal?
csp_members = [emp_by_id[m]['identity']['full_name'] for m in proj_by_id['PRJ-ENG-CSP']['member_ids']]
p05 = set(proj_by_id['PRJ-ENG-CSP']['member_ids']) == {'EMP-1001', 'EMP-1501'}
print('P05 (CSP members):', csp_members, '->', 'PASS' if p05 else 'FAIL')

# P06: Which team owns Customer Support Portal?
csp_owner = team_by_id[proj_by_id['PRJ-ENG-CSP']['owning_team_id']]['name']
p06 = proj_by_id['PRJ-ENG-CSP']['owning_team_id'] == 'TEAM-ENG-APP'
print('P06 (CSP owning team):', csp_owner, '->', 'PASS' if p06 else 'FAIL')

# P07: Who manages Customer Support Portal?
csp_mgr = emp_by_id[proj_by_id['PRJ-ENG-CSP']['project_manager_id']]['identity']['full_name']
p07 = proj_by_id['PRJ-ENG-CSP']['project_manager_id'] == 'EMP-2001'
print('P07 (CSP manager):', csp_mgr, '->', 'PASS' if p07 else 'FAIL')

# P08: Who leads Customer Support Portal?
csp_lead = emp_by_id[proj_by_id['PRJ-ENG-CSP']['project_lead_id']]['identity']['full_name']
p08 = proj_by_id['PRJ-ENG-CSP']['project_lead_id'] == 'EMP-1501'
print('P08 (CSP lead):', csp_lead, '->', 'PASS' if p08 else 'FAIL')

# P09: What technologies are used on Customer Support Portal?
csp_tech = proj_by_id['PRJ-ENG-CSP']['technologies']
p09 = 'Python' in csp_tech and 'FastAPI' in csp_tech and 'React' in csp_tech
print('P09 (CSP tech):', csp_tech, '->', 'PASS' if p09 else 'FAIL')

# P10: What is Customer Support Portal about?
csp_desc = proj_by_id['PRJ-ENG-CSP']['description']
p10 = len(csp_desc) > 20
print('P10 (CSP description):', csp_desc[:50], '... ->', 'PASS' if p10 else 'FAIL')

# P11: Which tickets belong to Customer Support Portal?
csp_tickets = [t['ticket_id'] for t in tickets if t.get('project_id') == 'PRJ-ENG-CSP']
p11 = len(csp_tickets) == 19
print('P11 (CSP tickets count):', len(csp_tickets), '->', 'PASS' if p11 else 'FAIL')

# P12: How many open tickets belong to Customer Support Portal?
open_statuses = {'Open', 'In Progress', 'Under Review'}
csp_open = [t['ticket_id'] for t in tickets if t.get('project_id') == 'PRJ-ENG-CSP' and t.get('status') in open_statuses]
p12 = len(csp_open) == 6
print('P12 (CSP open tickets count):', len(csp_open), '->', 'PASS' if p12 else 'FAIL')

# P13: Which project has the most open tickets?
open_by_proj = Counter(t.get('project_id') for t in tickets if t.get('status') in open_statuses and t.get('project_id'))
top_proj = open_by_proj.most_common(1)[0]
p13 = top_proj[0] == 'PRJ-INTENTLOCK' and top_proj[1] == 8
print('P13 (Most open tickets project):', top_proj[0], 'with', top_proj[1], 'tickets ->', 'PASS' if p13 else 'FAIL')

# P14: Which projects does Application Engineering work on?
app_projs = team_by_id['TEAM-ENG-APP']['project_ids']
p14 = 'PRJ-ENG-CSP' in app_projs and 'PRJ-ENG-IAD' in app_projs
print('P14 (Application Engineering projects):', app_projs, '->', 'PASS' if p14 else 'FAIL')

# P15: Which projects does Priya manage?
priya_managed = [p['project_id'] for p in projects if p.get('project_manager_id') == 'EMP-2001']
p15 = 'PRJ-ENG-CSP' in priya_managed and 'PRJ-ENG-IAD' in priya_managed and 'PRJ-ENG-AUTH' in priya_managed
print('P15 (Priya managed projects):', priya_managed, '->', 'PASS' if p15 else 'FAIL')

# P16: Which projects contain employees who report directly to Priya?
priya_reports = set(emp_by_id['EMP-2001']['reporting']['direct_report_ids'])
projs_with_reports = set()
for p in projects:
    if set(p.get('member_ids', [])) & priya_reports:
        projs_with_reports.add(p['project_id'])
p16 = 'PRJ-ENG-CSP' in projs_with_reports and 'PRJ-ENG-IAD' in projs_with_reports
print('P16 (Projects involving Priya direct reports):', projs_with_reports, '->', 'PASS' if p16 else 'FAIL')

# P17: Which R&D projects involve voice security?
voice_sec_projs = [p['project_id'] for p in projects if 'TEAM-RND-SPEECH' in (p.get('owning_team_id'), *p.get('contributing_team_ids', []))]
p17 = 'PRJ-RND-VOICEAUTH' in voice_sec_projs and 'PRJ-RND-SPEAKER' in voice_sec_projs
print('P17 (Voice security R&D projects):', voice_sec_projs, '->', 'PASS' if p17 else 'FAIL')

# P18: Which project evaluates speaker verification?
speaker_eval = next((p['project_id'] for p in projects if p['name'] == 'Speaker Verification Evaluation'), None)
p18 = speaker_eval == 'PRJ-RND-SPEAKER'
print('P18 (Speaker verification evaluation project):', speaker_eval, '->', 'PASS' if p18 else 'FAIL')

# P19: Which projects involve agent security?
agent_sec = [p['project_id'] for p in projects if p['project_type'] == 'Security Research' or 'Agent' in p['name']]
p19 = 'PRJ-RND-TOOLAGENT' in agent_sec and 'PRJ-SEC-A2AAUTH' in agent_sec
print('P19 (Agent security projects count):', len(agent_sec), '->', 'PASS' if p19 else 'FAIL')

# P20: What projects does Arvind directly work on?
arvind_direct = [p['project_id'] for p in projects if 'EMP-4002' in p.get('member_ids', [])]
p20 = arvind_direct == []
print('P20 (Arvind direct project memberships):', arvind_direct, '->', 'PASS' if p20 else 'FAIL')

# P21: Which projects fall under Arvind's technology/R&D oversight?
arvind_oversight = [p['project_id'] for p in projects if p.get('project_manager_id') == 'EMP-4002']
p21 = len(arvind_oversight) >= 8 and 'PRJ-RND-VOICEAUTH' in arvind_oversight
print('P21 (Arvind executive oversight projects count):', len(arvind_oversight), '->', 'PASS' if p21 else 'FAIL')

# P22: Show all active projects.
active_projs = [p['project_id'] for p in projects if p['status'] == 'Active']
p22 = len(active_projs) == len(projects) == 41
print('P22 (All active projects count):', len(active_projs), '->', 'PASS' if p22 else 'FAIL')

# P23: Compare Customer Support Portal and Internal Analytics Dashboard.
p23 = proj_by_id['PRJ-ENG-CSP'] is not None and proj_by_id['PRJ-ENG-IAD'] is not None
print('P23 (CSP and IAD retrievable for comparison):', 'PASS' if p23 else 'FAIL')

# P24: Who works on both Project A and Project B? (CSP and IAD)
intersection_ab = set(proj_by_id['PRJ-ENG-CSP']['member_ids']) & set(proj_by_id['PRJ-ENG-IAD']['member_ids'])
p24 = intersection_ab == {'EMP-1001'}
print('P24 (Intersection of CSP and IAD members):', intersection_ab, '->', 'PASS' if p24 else 'FAIL')

# P25: Show projects with no currently assigned employees.
empty_member_projs = [p['project_id'] for p in projects if len(p.get('member_ids', [])) == 0]
p25 = len(empty_member_projs) > 0
print('P25 (Projects with 0 direct employee members):', len(empty_member_projs), empty_member_projs[:3], '->', 'PASS' if p25 else 'FAIL')
