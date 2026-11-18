import asyncio
import sys
from pathlib import Path
import pytest
import httpx
from fastapi import HTTPException
from starlette.requests import Request

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from main import app
from database import SessionLocal
from seeds.seed_standalone_db import initialize_and_seed_standalone_db
from models.user import BudgetUser
from models.budget import BudgetLineItem
from api.budget_routes import (
    get_budget_dashboard_data,
    get_budget_governance_settings,
    upsert_budget_line_item,
    update_item_governance,
    list_budget_users,
    create_budget_user,
    update_budget_user,
    delete_budget_user,
    reset_user_password,
    list_system_lookups,
    create_system_lookup,
    update_system_lookup,
    delete_system_lookup,
    BudgetLineItemPayload,
    GovernancePayload,
    UserCreatePayload,
    UserUpdatePayload,
    UserResetPasswordPayload,
    LookupCreatePayload,
    LookupUpdatePayload,
)


def _make_dummy_request(query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v2/budget/dashboard-data",
        "query_string": query_string.encode("utf-8"),
        "headers": [],
    }
    return Request(scope)


def test_standalone_budget_app_end_to_end():
    seed_summary = initialize_and_seed_standalone_db()
    assert seed_summary["total_users"] >= 50
    assert seed_summary["total_gov_configs"] >= 15
    assert seed_summary["total_lookups"] >= 40

    db = SessionLocal()
    try:
        req = _make_dummy_request()

        # 1. Verify dashboard-data logic & User Identity fields in actor
        payload = get_budget_dashboard_data(
            request=req,
            year=2026,
            quarter=3,
            dept_name=None,
            simulate_role=None,
            simulate_dept=None,
            db=db,
        )
        assert payload["status"] == "success"
        assert payload["kpis"]["total_allocated"] > 0
        assert len(payload["line_items"]) >= 8
        assert len(payload["top_departments"]) == 3
        assert payload["lowest_department"] is not None
        assert "job_title" in payload["actor"]
        assert "general_dept" in payload["actor"]

        # 2. Verify Anonymized Seeding: Every General Department has >=1 GM and >=2 Standard Employees
        users_resp = list_budget_users(request=req, db=db)
        assert users_resp["status"] == "success"
        assert users_resp["total"] >= 50
        all_users = users_resp["users"]
        for dept in users_resp["available_departments"]:
            dept_users = [u for u in all_users if u["general_dept_name"] == dept]
            dept_gms = [u for u in dept_users if u["role"] in ("dept_gm", "hse_officer") or dept in u.get("designated_gm_depts", [])]
            dept_emps = [u for u in dept_users if u["role"] == "employee"]
            assert len(dept_gms) >= 1, f"Department {dept} missing GM"
            assert len(dept_emps) >= 2, f"Department {dept} has fewer than 2 standard employees"

        # 3. Verify Role Simulator (Department Isolation for EMPLOYEE)
        sim_payload = get_budget_dashboard_data(
            request=req,
            year=2026,
            quarter=3,
            dept_name=None,
            simulate_role="EMPLOYEE",
            simulate_dept="الشئون المالية",
            db=db,
        )
        assert sim_payload["actor"]["effective_role"] == "EMPLOYEE"
        assert sim_payload["actor"]["can_view_all_depts"] is False
        assert all(it["general_dept_name"] == "الشئون المالية" for it in sim_payload["line_items"])

        # 4. Verify governance-settings logic
        gov_data = get_budget_governance_settings(request=req, db=db)
        assert gov_data["hse_officer"]["emp_id"] == 10019
        assert "الشئون الإدارية" in gov_data["gm_map"]

        # 5. Verify User Directory & Employee Management (CRUD & Filters)
        filtered_resp = list_budget_users(dept_name="الشئون الإدارية", request=req, db=db)
        assert all(u["general_dept_name"] == "الشئون الإدارية" for u in filtered_resp["users"])

        new_emp_payload = UserCreatePayload(
            emp_id=9876,
            name="م. سامر توفيق التجريبي",
            role="employee",
            general_dept_name="السلامة والصحة المهنية وحماية",
            work_location="حقول الصحراء الغربية",
            phone="01098765432",
            email="env.test9876@petro-demo.local"
        )
        create_res = create_budget_user(payload=new_emp_payload, request=req, db=db)
        assert create_res["status"] == "success"
        assert create_res["user"]["emp_id"] == 9876

        up_emp_payload = UserUpdatePayload(
            work_location="المركز الرئيسي - القاهرة",
            role="dept_gm"
        )
        update_res = update_budget_user(emp_id=9876, payload=up_emp_payload, request=req, db=db)
        assert update_res["status"] == "success"
        assert update_res["user"]["role"] == "dept_gm"
        assert update_res["user"]["work_location"] == "المركز الرئيسي - القاهرة"

        pwd_res = reset_user_password(
            emp_id=9876,
            payload=UserResetPasswordPayload(new_password="NewSecurePass2026!"),
            request=req,
            db=db
        )
        assert pwd_res["status"] == "success"

        with pytest.raises(HTTPException) as exc_admin:
            delete_budget_user(emp_id=7071, request=req, db=db)
        assert exc_admin.value.status_code == 400

        del_res = delete_budget_user(emp_id=9876, request=req, db=db)
        assert del_res["status"] == "success"

        # 6. Verify Dynamic Lookup Options CRUD (Departments, Sub-Departments, Work Locations, Job Titles, Roles)
        lookups_initial = list_system_lookups(request=req, db=db)
        assert "departments" in lookups_initial
        assert "sub_departments" in lookups_initial
        assert "work_locations" in lookups_initial
        assert "job_titles" in lookups_initial
        assert "roles" in lookups_initial
        assert len(lookups_initial["sub_departments"]) >= 10
        assert len(lookups_initial["roles"]) >= 4

        # Test Work Location CRUD
        add_lk = create_system_lookup(
            payload=LookupCreatePayload(category="WORK_LOCATION", value="منصة بحرية تجريبية 1"),
            request=req,
            db=db
        )
        assert add_lk["status"] == "success"
        assert "منصة بحرية تجريبية 1" in add_lk["work_locations"]
        lk_id = add_lk["option"]["id"]

        ren_lk = update_system_lookup(
            lookup_id=lk_id,
            payload=LookupUpdatePayload(value="منصة بحرية مطورة 2"),
            request=req,
            db=db
        )
        assert ren_lk["status"] == "success"
        assert "منصة بحرية مطورة 2" in ren_lk["work_locations"]

        del_lk = delete_system_lookup(lookup_id=lk_id, request=req, db=db)
        assert del_lk["status"] == "success"
        assert "منصة بحرية مطورة 2" not in del_lk["work_locations"]

        # Test Sub-Department & Role CRUD
        add_sub = create_system_lookup(
            payload=LookupCreatePayload(category="SUB_DEPARTMENT", value="قسم الذكاء الاصطناعي والتحليلات"),
            request=req,
            db=db
        )
        assert "قسم الذكاء الاصطناعي والتحليلات" in add_sub["sub_departments"]
        delete_system_lookup(lookup_id=add_sub["option"]["id"], request=req, db=db)

        add_role = create_system_lookup(
            payload=LookupCreatePayload(category="ROLE", value="financial_controller"),
            request=req,
            db=db
        )
        assert "financial_controller" in add_role["roles"]
        delete_system_lookup(lookup_id=add_role["option"]["id"], request=req, db=db)

        # 7. Verify Strict Departmental Isolation for GM approvals
        item_admin_dept = db.query(BudgetLineItem).join(BudgetLineItem.budget).filter(
            BudgetLineItem.budget.has(general_dept_name="الشئون الإدارية")
        ).first()
        assert item_admin_dept is not None

        with pytest.raises(HTTPException) as exc_gm_iso:
            update_item_governance(
                item_id=item_admin_dept.id,
                payload=GovernancePayload(
                    workflow_status="UNDER_EVALUATION",
                    gm_approved=True,
                    hse_approved=False,
                    simulate_role="DEPT_GM",
                    simulate_dept="الشئون المالية"
                ),
                request=req,
                db=db
            )
        assert exc_gm_iso.value.status_code == 403

        # Restore original GM for HSE department after test
        initialize_and_seed_standalone_db()

    finally:
        db.close()

    # 8. Verify Route Guard & Role-Based UI Visibility via ASGI HTTP Client
    async def _verify_http_security():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Unauthenticated visit to /budget-dashboard redirects to /login
            unauth_res = await client.get("/budget-dashboard", follow_redirects=False)
            assert unauth_res.status_code == 303
            assert unauth_res.headers["location"] == "/login"

            # Login as Standard Employee (268)
            login_emp = await client.post("/login", data={"emp_id": 268, "password": "123456"}, follow_redirects=False)
            assert login_emp.status_code == 303
            emp_dash = await client.get("/budget-dashboard")
            assert emp_dash.status_code == 200
            html_emp = emp_dash.text
            assert "Cost Rationalization & Incentives" not in html_emp
            assert "محاكاة الدور:" not in html_emp
            assert "openUsersModal()" not in html_emp
            assert "أ. رامي عادل الشاذلي" in html_emp

            # Logout and Login as System Admin (7071)
            await client.get("/logout")
            login_admin = await client.post("/login", data={"emp_id": 7071, "password": "123456"}, follow_redirects=False)
            assert login_admin.status_code == 303
            admin_dash = await client.get("/budget-dashboard")
            assert admin_dash.status_code == 200
            html_admin = admin_dash.text
            assert "Cost Rationalization & Incentives" not in html_admin
            assert "محاكاة الدور:" in html_admin
            assert "openUsersModal()" in html_admin
            assert "م. طارق محمود العلي" in html_admin
            assert '@click.away="usersModalOpen = false"' not in html_admin
            assert '@click.away="userFormModalOpen = false"' not in html_admin
            assert '@click.away="lookupModalOpen = false"' not in html_admin
            assert "closeLookupManager()" in html_admin
            assert "الأقسام / الإدارات الفرعية" in html_admin
            assert "الدور الوظيفي / الصلاحيات" in html_admin

    asyncio.run(_verify_http_security())
    print("[ALL STANDALONE TESTS PASSED SUCCESSFULLY]")


if __name__ == "__main__":
    test_standalone_budget_app_end_to_end()
