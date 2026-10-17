"""
Tests for Stage 6: Deterministic Enterprise Query Engine & Entity Resolution
Covers ER01-ER14, EQ01-EQ10, MQ01-MQ05, DQ01-DQ10, PQ01-PQ07, CTX01-CTX08,
AG01-AG03, H01-H06, Write Proposals, and Acceptance Sequences.
"""

import pytest
from backend.services.enterprise_data import EnterpriseDataRepository, enterprise_repo
from backend.services.entity_resolver import EntityResolver, entity_resolver
from backend.services.enterprise_query import EnterpriseQueryEngine, enterprise_engine
from backend.services.enterprise_dispatcher import EnterpriseConversationDispatcher, EnterpriseConversationContext, enterprise_dispatcher


class TestStage6EntityResolution:
    def test_er01_aarav(self):
        res = entity_resolver.resolve_employee("Aarav")
        assert res.status == "resolved"
        assert res.entity_id == "EMP-1001"

    def test_er02_aarav_mehta(self):
        res = entity_resolver.resolve_employee("Aarav Mehta")
        assert res.status == "resolved"
        assert res.entity_id == "EMP-1001"

    def test_er03_emp_1001(self):
        res = entity_resolver.resolve_employee("EMP-1001")
        assert res.status == "resolved"
        assert res.entity_id == "EMP-1001"

    def test_er04_priya(self):
        res = entity_resolver.resolve_employee("Priya")
        assert res.status == "resolved"
        assert res.entity_id == "EMP-2001"

    def test_er05_arvind(self):
        res = entity_resolver.resolve_employee("Arvind")
        assert res.status == "resolved"
        assert res.entity_id == "EMP-4002"

    def test_er06_engineering(self):
        res = entity_resolver.resolve_department("Engineering")
        assert res.status == "resolved"
        assert res.entity_id == "DEPT-ENG"

    def test_er07_rnd(self):
        res = entity_resolver.resolve_department("R&D")
        assert res.status == "resolved"
        assert res.entity_id == "DEPT-RND"

    def test_er08_qa(self):
        res = entity_resolver.resolve_department("QA")
        assert res.status == "resolved"
        assert res.entity_id == "DEPT-QA"

    def test_er09_application_engineering(self):
        res = entity_resolver.resolve_team("Application Engineering")
        assert res.status == "resolved"
        assert res.entity_id == "TEAM-ENG-APP"

    def test_er10_csp(self):
        res = entity_resolver.resolve_project("Customer Support Portal")
        assert res.status == "resolved"
        assert res.entity_id == "PRJ-ENG-CSP"

    def test_er11_iad(self):
        res = entity_resolver.resolve_project("Internal Analytics Dashboard")
        assert res.status == "resolved"
        assert res.entity_id == "PRJ-ENG-IAD"

    def test_er12_speaker_verification(self):
        res = entity_resolver.resolve_project("Speaker Verification Evaluation")
        assert res.status == "resolved"
        assert res.entity_id == "PRJ-RND-SPEAKER"

    def test_er13_unknown_employee(self):
        res = entity_resolver.resolve_employee("EMP-9999")
        assert res.status == "not_found"

    def test_er14_ambiguous_rao(self):
        res = entity_resolver.resolve_employee("Rao")
        assert res.status == "clarification_required"
        assert len(res.candidates) >= 2


class TestStage6EmployeeQueries:
    def test_eq01_who_is_aarav(self):
        res = enterprise_engine.get_employee_profile("EMP-1001")
        assert res["status"] == "success"
        assert res["data"]["name"] == "Aarav Mehta"

    def test_eq02_who_manages_aarav(self):
        res = enterprise_engine.get_employee_manager("EMP-1001")
        assert res["status"] == "success"
        assert res["data"]["manager_id"] == "EMP-2001"
        assert "Priya Sharma" in res["data"]["manager_name"]

    def test_eq03_which_team_is_aarav_in(self):
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        assert emp["employment"]["team_id"] == "TEAM-ENG-APP"

    def test_eq04_which_dept_is_aarav_in(self):
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        assert emp["employment"]["department_id"] == "DEPT-ENG"

    def test_eq05_aarav_projects(self):
        res = enterprise_engine.get_employee_projects("EMP-1001")
        assert res["status"] == "success"
        project_ids = [r[0] for r in res["rows"]]
        assert "PRJ-ENG-CSP" in project_ids
        assert "PRJ-ENG-IAD" in project_ids

    def test_eq06_aarav_allocation(self):
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        allocs = {p["project_id"]: p["allocation_percent"] for p in emp["projects"]["current"]}
        assert allocs["PRJ-ENG-CSP"] == 60
        assert allocs["PRJ-ENG-IAD"] == 40

    def test_eq07_does_aarav_know_fastapi(self):
        res = enterprise_dispatcher.dispatch("Does Aarav know FastAPI?")
        assert res["status"] == "success"
        assert res["data"]["has_skill"] is True

    def test_eq08_does_aarav_know_postgresql(self):
        res = enterprise_dispatcher.dispatch("Does Aarav know PostgreSQL?")
        assert res["status"] == "success"
        assert res["data"]["has_skill"] is True

    def test_eq09_aarav_tickets(self):
        res = enterprise_engine.get_tickets(assignee_id="EMP-1001")
        assert res["status"] == "success"
        assert res["count"] > 0

    def test_eq10_aarav_open_tickets_count(self):
        res = enterprise_engine.get_tickets(assignee_id="EMP-1001", status_filter="Open")
        assert res["status"] == "success"
        assert res["count"] == 7


class TestStage6ManagerQueries:
    def test_mq01_who_reports_to_priya(self):
        res = enterprise_engine.get_direct_reports("EMP-2001")
        assert res["status"] == "success"
        report_ids = [r[0] for r in res["rows"]]
        assert "EMP-1001" in report_ids
        assert "EMP-1501" in report_ids

    def test_mq02_priya_direct_reports_count(self):
        res = enterprise_engine.get_direct_reports("EMP-2001")
        assert res["count"] == 2

    def test_mq03_which_team_priya_manages(self):
        teams = [t for t in enterprise_repo.teams if t.get("manager_id") == "EMP-2001"]
        assert len(teams) == 1
        assert teams[0]["team_id"] == "TEAM-ENG-APP"

    def test_mq04_which_projects_priya_manages(self):
        prjs = [p for p in enterprise_repo.projects if p.get("project_manager_id") == "EMP-2001"]
        prj_ids = [p["project_id"] for p in prjs]
        assert "PRJ-ENG-CSP" in prj_ids
        assert "PRJ-ENG-IAD" in prj_ids

    def test_mq05_who_is_priya_manager(self):
        res = enterprise_engine.get_employee_manager("EMP-2001")
        assert res["status"] == "success"
        assert res["data"]["manager_id"] == "EMP-3001"


class TestStage6DepartmentQueries:
    def test_dq01_who_works_in_engineering(self):
        res = enterprise_engine.get_department_profile("DEPT-ENG")
        assert res["status"] == "success"
        assert res["data"]["headcount"] == 4

    def test_dq02_engineering_headcount(self):
        dept = enterprise_repo.departments_by_id["DEPT-ENG"]
        assert len(dept["member_ids"]) == 4

    def test_dq03_who_heads_engineering(self):
        dept = enterprise_repo.departments_by_id["DEPT-ENG"]
        assert dept["head_id"] == "EMP-3001"

    def test_dq04_engineering_executive_owner(self):
        dept = enterprise_repo.departments_by_id["DEPT-ENG"]
        assert dept["executive_owner_id"] == "EMP-4002"

    def test_dq05_engineering_teams(self):
        dept = enterprise_repo.departments_by_id["DEPT-ENG"]
        assert dept["team_ids"] == ["TEAM-ENG-APP"]

    def test_dq06_engineering_owned_projects(self):
        owned = [p["project_id"] for p in enterprise_repo.projects if p.get("owning_department_id") == "DEPT-ENG"]
        assert "PRJ-ENG-CSP" in owned
        assert "PRJ-ENG-IAD" in owned

    def test_dq07_engineering_open_tickets(self):
        res = enterprise_engine.get_tickets(department_id="DEPT-ENG", status_filter="Open")
        assert res["status"] == "success"
        assert res["count"] == 18

    def test_dq08_rnd_teams(self):
        dept = enterprise_repo.departments_by_id["DEPT-RND"]
        assert len(dept["team_ids"]) == 4

    def test_dq09_rnd_head(self):
        dept = enterprise_repo.departments_by_id["DEPT-RND"]
        assert dept["head_id"] == "RND-5001"

    def test_dq10_rnd_executive_owner(self):
        dept = enterprise_repo.departments_by_id["DEPT-RND"]
        assert dept["executive_owner_id"] == "EMP-4002"


class TestStage6ProjectQueries:
    def test_pq01_csp_owning_department(self):
        res = enterprise_engine.get_project_profile("PRJ-ENG-CSP")
        assert res["data"]["owning_department_id"] == "DEPT-ENG"

    def test_pq02_csp_owning_team(self):
        res = enterprise_engine.get_project_profile("PRJ-ENG-CSP")
        assert res["data"]["owning_team_id"] == "TEAM-ENG-APP"

    def test_pq03_csp_members(self):
        res = enterprise_engine.get_project_profile("PRJ-ENG-CSP")
        member_ids = [m["employee_id"] for m in res["data"]["members"]]
        assert "EMP-1001" in member_ids
        assert "EMP-1501" in member_ids

    def test_pq04_iad_contributing_departments(self):
        res = enterprise_engine.get_project_profile("PRJ-ENG-IAD")
        assert "DEPT-ENG" in res["data"]["contributing_department_ids"]
        assert "DEPT-DATA" in res["data"]["contributing_department_ids"]

    def test_pq05_sve_department(self):
        res = enterprise_engine.get_project_profile("PRJ-RND-SPEAKER")
        assert res["data"]["owning_department_id"] == "DEPT-RND"

    def test_pq06_sve_team(self):
        res = enterprise_engine.get_project_profile("PRJ-RND-SPEAKER")
        assert res["data"]["owning_team_id"] == "TEAM-RND-SPEECH"

    def test_pq07_a2a_auth_department(self):
        res = enterprise_engine.get_project_profile("PRJ-SEC-A2AAUTH")
        assert res["data"]["owning_department_id"] == "DEPT-RND"


class TestStage6ContextAndFollowUps:
    def test_ctx01_show_aarav_who_manages_him(self):
        ctx = EnterpriseConversationContext()
        enterprise_dispatcher.dispatch("Show Aarav profile.", ctx)
        assert ctx.selected_employee_id == "EMP-1001"
        res = enterprise_dispatcher.dispatch("Who manages him?", ctx)
        assert res["status"] == "success"
        assert res["entity_id"] == "EMP-2001"

    def test_ctx02_show_aarav_manager_her_profile(self):
        ctx = EnterpriseConversationContext()
        enterprise_dispatcher.dispatch("Show Aarav profile.", ctx)
        enterprise_dispatcher.dispatch("Who manages him?", ctx)
        res = enterprise_dispatcher.dispatch("Show her profile.", ctx)
        assert res["status"] == "success"
        assert res["entity_id"] == "EMP-2001"

    def test_ctx03_show_priya_reports_first_projects(self):
        ctx = EnterpriseConversationContext()
        enterprise_dispatcher.dispatch("Show Priya profile.", ctx)
        enterprise_dispatcher.dispatch("Who reports to her?", ctx)
        res = enterprise_dispatcher.dispatch("Show the first person's projects.", ctx)
        assert res["status"] == "success"
        assert res["entity_id"] == "EMP-1001"

    def test_ctx04_show_aarav_tickets_only_open(self):
        ctx = EnterpriseConversationContext()
        enterprise_dispatcher.dispatch("Show Aarav tickets.", ctx)
        res = enterprise_dispatcher.dispatch("Only open ones.", ctx)
        assert res["status"] == "success"
        assert res["count"] == 7

    def test_ctx05_show_aarav_tickets_only_open_high_priority(self):
        ctx = EnterpriseConversationContext()
        enterprise_dispatcher.dispatch("Show Aarav tickets.", ctx)
        enterprise_dispatcher.dispatch("Only open ones.", ctx)
        res = enterprise_dispatcher.dispatch("Only high priority.", ctx)
        assert res["status"] == "success"
        assert res["count"] == 3

    def test_ctx06_show_engineering_projects(self):
        ctx = EnterpriseConversationContext()
        enterprise_dispatcher.dispatch("Show Engineering.", ctx)
        res = enterprise_dispatcher.dispatch("Which projects belong to Engineering?", ctx)
        assert res["status"] == "success"
        assert len(res["rows"]) >= 5

    def test_ctx07_show_csp_who_works_on_it(self):
        ctx = EnterpriseConversationContext()
        enterprise_dispatcher.dispatch("Show Customer Support Portal.", ctx)
        res = enterprise_dispatcher.dispatch("Who works on it?", ctx)
        assert res["status"] == "success"
        assert len(res["rows"]) == 2

    def test_ctx08_ui_selected_entity_continuity(self):
        ctx = EnterpriseConversationContext()
        res = enterprise_dispatcher.dispatch("Show his tickets.", ctx, ui_selected_entity={"entity_type": "employee", "entity_id": "EMP-1001"})
        assert res["status"] == "success"
        assert "Aarav Mehta" in res["title"]


class TestStage6Aggregations:
    def test_ag01_most_employees_dept(self):
        res = enterprise_engine.get_aggregations("department_headcount_max")
        assert res["entity_id"] == "DEPT-EXEC"
        assert res["data"]["headcount"] == 6

    def test_ag02_most_active_projects_dept(self):
        res = enterprise_engine.get_aggregations("department_active_projects_max")
        assert res["entity_id"] == "DEPT-RND"
        assert res["data"]["active_projects"] == 20

    def test_ag03_most_open_tickets_dept(self):
        res = enterprise_engine.get_aggregations("department_open_tickets_max")
        assert res["entity_id"] == "DEPT-ENG"
        assert res["data"]["open_tickets"] == 18


class TestStage6HallucinationSafety:
    def test_h01_unknown_emp(self):
        res = enterprise_dispatcher.dispatch("Show EMP-9999.")
        assert res["status"] == "not_found"

    def test_h02_unknown_project(self):
        res = enterprise_dispatcher.dispatch("Show Project Phoenix.")
        assert res["status"] == "not_found"

    def test_h03_second_manager(self):
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        assert "second_manager" not in emp["reporting"]

    def test_h04_salary_unavailable(self):
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        assert "salary" not in emp["employment"]

    def test_h05_home_address_unavailable(self):
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        assert "home_address" not in emp.get("personal_info", {})

    def test_h06_arvind_not_in_team(self):
        res = enterprise_dispatcher.dispatch("Does Arvind belong to Application Engineering?")
        assert res["status"] == "success"
        assert res["data"]["belongs_to_team"] is False


class TestStage6WriteProposals:
    def test_contact_update_proposal(self):
        res = enterprise_dispatcher.dispatch("Change Aarav work phone to 9999999999.")
        assert res["status"] == "proposal_created"
        assert res["action_proposal"]["new_value"] == "9999999999"
        # Confirm no actual mutation occurred
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        assert emp["identity"].get("work_phone") != "9999999999"

    def test_ticket_status_proposal(self):
        res = enterprise_dispatcher.dispatch("Close ticket TKT-2026-001.")
        assert res["status"] == "proposal_created"
        assert res["action_proposal"]["new_status"] == "Closed"
        # Confirm no actual mutation occurred
        tkt = enterprise_repo.tickets_by_id["TKT-2026-001"]
        assert tkt["status"] != "Closed"

    def test_unsupported_promotion_proposal(self):
        res = enterprise_dispatcher.dispatch("Promote Aarav to CTO.")
        assert res["status"] == "proposal_created"
        assert res["action_proposal"]["authorized"] is False
        # Confirm authority unchanged
        emp = enterprise_repo.employees_by_id["EMP-1001"]
        assert emp["employment"]["designation"] == "Software Engineer"
