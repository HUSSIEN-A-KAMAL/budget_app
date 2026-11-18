from typing import Optional, List, Dict, Any
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import String
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash
from jose import jwt, JWTError

from config import settings
from database import get_db, get_all_general_departments, get_employee_names_map, get_dynamic_lookups
from models.user import BudgetUser, GeneralDepartmentLookup, SystemLookupOption
from models.budget import DepartmentBudget, BudgetLineItem, BudgetGovernanceConfig
from models.audit import log_system_action

budget_router = APIRouter(prefix="/api/v2/budget", tags=["v2-budget"])

# Workflow lifecycle (order matters). Statuses after UNDER_EVALUATION are blocked by the HSE gate.
WORKFLOW_STATUSES = ["NEW", "UNDER_EVALUATION", "APPROVED", "IN_PROGRESS", "UNDER_VERIFICATION", "CLOSED"]
HSE_GATED_STATUSES = {"APPROVED", "IN_PROGRESS", "UNDER_VERIFICATION", "CLOSED"}
VERIFIED_STATUS = "CLOSED"


class GovernancePayload(BaseModel):
    workflow_status: str = Field(..., json_schema_extra={"example": "UNDER_EVALUATION"})
    gm_approved: Optional[bool] = None
    hse_approved: bool = False
    cost_avoidance_amount: float = Field(0.0, ge=0.0)
    simulate_role: Optional[str] = None
    simulate_dept: Optional[str] = None


class VariancePayload(BaseModel):
    variance_root_cause: str = Field(..., min_length=3)
    corrective_action: str = Field(..., min_length=3)
    corrective_owner: Optional[str] = None
    corrective_due_date: Optional[date] = None
    simulate_role: Optional[str] = None
    simulate_dept: Optional[str] = None


class BudgetLineItemPayload(BaseModel):
    item_id: Optional[int] = None
    budget_id: Optional[int] = None
    general_dept_name: str = Field(..., json_schema_extra={"example": "الشئون الإدارية"})
    fiscal_year: int = Field(2026, json_schema_extra={"example": 2026})
    quarter: int = Field(3, ge=1, le=4, json_schema_extra={"example": 3})
    item_name: str = Field(..., min_length=2, json_schema_extra={"example": "بند مهمات وأدوات مكتبية"})
    allocated_amount: float = Field(..., ge=0.0, json_schema_extra={"example": 50000.0})
    spent_amount: float = Field(0.0, ge=0.0, json_schema_extra={"example": 32000.0})
    savings_narrative: Optional[str] = Field(
        None,
        json_schema_extra={"example": "الاعتماد على التوقيع الرقمي وتقليص المطبوعات الورقية بنسبة 40%"}
    )
    simulate_role: Optional[str] = None
    simulate_dept: Optional[str] = None


class DepartmentAllocationPayload(BaseModel):
    general_dept_name: str = Field(..., json_schema_extra={"example": "الشئون الإدارية"})
    fiscal_year: int = Field(2026, json_schema_extra={"example": 2026})
    quarter: int = Field(3, ge=1, le=4, json_schema_extra={"example": 3})
    allocated_amount: float = Field(..., ge=0.0, json_schema_extra={"example": 170000.0})


class GovernanceConfigUpdatePayload(BaseModel):
    hse_officer_emp_id: Optional[int] = None
    leaderboard_enabled: bool = True
    dept_gms: Dict[str, Optional[int]] = Field(default_factory=dict)


class UserCreatePayload(BaseModel):
    emp_id: int = Field(..., ge=1, description="رقم الموظف")
    name: str = Field(..., min_length=2, description="الاسم الكامل")
    password: Optional[str] = Field("123456", description="كلمة المرور الافتراضية")
    role: str = Field("employee", description="الدور الوظيفي: admin, dept_gm, hse_officer, employee")
    general_dept_name: Optional[str] = None
    dept_name: Optional[str] = None
    job_title: Optional[str] = None
    work_location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True


class UserUpdatePayload(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    general_dept_name: Optional[str] = None
    dept_name: Optional[str] = None
    job_title: Optional[str] = None
    work_location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserResetPasswordPayload(BaseModel):
    new_password: str = Field(..., min_length=4)


class LookupCreatePayload(BaseModel):
    category: str = Field(..., description="DEPARTMENT, WORK_LOCATION, or JOB_TITLE")
    value: str = Field(..., min_length=2, description="قيمة الخيار في القائمة المنسدلة")


class LookupUpdatePayload(BaseModel):
    value: str = Field(..., min_length=2, description="القيمة الجديدة للخيار")
    is_active: Optional[bool] = True


def resolve_budget_actor(
    request: Request,
    db: Session,
    simulate_role: Optional[str] = None,
    simulate_dept: Optional[str] = None
) -> Dict[str, Any]:
    """
    Resolves the currently logged-in user from the JWT session cookie, enriches it with
    department hierarchy and governance roles (HSE Officer / Dept GM) from the standalone SQLite DB.
    Also supports the Admin Role Simulator when the real user is Admin (e.g. 7071).
    """
    emp_id = 7071
    role = "admin"
    name = "مدير النظام"
    job_title = "مدير النظام وتقنية المعلومات"
    general_dept = ""

    token = request.cookies.get("access_token") if request else None
    if not token and request:
        auth_hdr = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_hdr:
            token = auth_hdr

    if token:
        try:
            if token.startswith("Bearer "):
                token = token.split(" ")[1]
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            sub = payload.get("sub")
            if sub and str(sub).isdigit():
                emp_id = int(sub)
                role = payload.get("role", "employee")
                name = payload.get("name") or f"موظف {emp_id}"
                job_title = (payload.get("job_title") or "").strip()
                general_dept = (payload.get("department") or "").strip()
        except JWTError:
            pass

    # Enrich from standalone SQLite users table for freshest role, name, job_title, and general_dept_name
    try:
        user_row = db.get(BudgetUser, int(emp_id))
        if user_row:
            if user_row.role:
                role = user_row.role
            if user_row.name:
                name = user_row.name
            if user_row.job_title and str(user_row.job_title).strip():
                job_title = str(user_row.job_title).strip()
            if user_row.general_dept_name and str(user_row.general_dept_name).strip():
                general_dept = str(user_row.general_dept_name).strip()
            elif user_row.dept_name and str(user_row.dept_name).strip() and not general_dept:
                general_dept = str(user_row.dept_name).strip()
    except Exception:
        pass

    is_real_admin = (role == "admin" or emp_id == 7071)

    # Read governance configurations from standalone SQLite DB
    configs = db.query(BudgetGovernanceConfig).all()
    hse_officer_emp_id = None
    hse_officer_name = None
    leaderboard_enabled = True
    gm_map: Dict[str, Dict[str, Any]] = {}

    for cfg in configs:
        if cfg.config_type == "HSE_OFFICER" and cfg.scope_key == "GLOBAL":
            hse_officer_emp_id = cfg.assigned_emp_id
            hse_officer_name = cfg.assigned_emp_name
        elif cfg.config_type == "LEADERBOARD_VISIBILITY" and cfg.scope_key == "GLOBAL":
            leaderboard_enabled = bool(cfg.is_enabled)
        elif cfg.config_type == "DEPT_GM" and cfg.scope_key:
            gm_map[cfg.scope_key] = {
                "emp_id": cfg.assigned_emp_id,
                "name": cfg.assigned_emp_name
            }

    # Determine real governance capabilities
    is_hse_officer = (
        (hse_officer_emp_id is not None and int(hse_officer_emp_id) == int(emp_id))
        or role.lower() == "hse_officer"
    )
    managed_gm_depts = [
        dept for dept, info in gm_map.items()
        if info.get("emp_id") is not None and int(info["emp_id"]) == int(emp_id)
    ]
    if not managed_gm_depts and role.lower() in ("dept_gm", "manager") and general_dept:
        managed_gm_depts = [general_dept]

    is_dept_gm = len(managed_gm_depts) > 0

    effective_role = "ADMIN" if is_real_admin else (
        "HSE_OFFICER" if is_hse_officer else (
            "DEPT_GM" if is_dept_gm else "EMPLOYEE"
        )
    )
    effective_dept = (managed_gm_depts[0] if (is_dept_gm and not general_dept) else general_dept)

    # Apply Admin Role Simulator if requested by a real Admin
    sim_role_clean = (simulate_role or (request.query_params.get("simulate_role") if request else "") or "").strip().upper()
    sim_dept_clean = (simulate_dept or (request.query_params.get("simulate_dept") if request else "") or "").strip()

    if is_real_admin and sim_role_clean in ("EMPLOYEE", "DEPT_GM", "HSE_OFFICER"):
        effective_role = sim_role_clean
        if sim_role_clean in ("EMPLOYEE", "DEPT_GM"):
            effective_dept = sim_dept_clean or general_dept or "الشئون الإدارية"
            if sim_role_clean == "DEPT_GM":
                managed_gm_depts = [effective_dept]
                is_dept_gm = True
                is_hse_officer = False
            else:
                managed_gm_depts = []
                is_dept_gm = False
                is_hse_officer = False
        elif sim_role_clean == "HSE_OFFICER":
            effective_dept = ""
            managed_gm_depts = []
            is_dept_gm = False
            is_hse_officer = True

    can_view_all_depts = (effective_role in ("ADMIN", "HSE_OFFICER"))
    can_approve_hse = (effective_role in ("ADMIN", "HSE_OFFICER"))
    can_approve_gm = (effective_role in ("ADMIN", "DEPT_GM"))

    return {
        "emp_id": emp_id,
        "name": name,
        "job_title": job_title,
        "general_dept": general_dept,
        "is_real_admin": is_real_admin,
        "effective_role": effective_role,
        "effective_dept": effective_dept,
        "managed_gm_depts": managed_gm_depts,
        "can_view_all_depts": can_view_all_depts,
        "can_approve_hse": can_approve_hse,
        "can_approve_gm": can_approve_gm,
        "leaderboard_enabled": leaderboard_enabled,
        "hse_officer": {
            "emp_id": hse_officer_emp_id,
            "name": hse_officer_name
        },
        "gm_map": gm_map
    }


@budget_router.get("/governance-settings")
def get_budget_governance_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Returns current RBAC & Governance configuration for the System Admin panel:
    - Designated HSE Officer
    - Leaderboard (Top 3 & Lowest) visibility toggle
    - Designated Department General Managers (GMs) per general department
    """
    actor = resolve_budget_actor(request, db)
    all_depts = get_all_general_departments(db)

    return {
        "status": "success",
        "hse_officer": actor["hse_officer"],
        "leaderboard_enabled": actor["leaderboard_enabled"],
        "gm_map": actor["gm_map"],
        "available_departments": all_depts
    }


@budget_router.post("/governance-settings")
def save_budget_governance_settings(
    payload: GovernanceConfigUpdatePayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Allows System Admin to dynamically assign the HSE Officer, Department GMs,
    and enable/disable the Top 3 & Lowest ranking cards.
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: هذه الإعدادات مخصصة لمدير النظام فقط")

    names_map = get_employee_names_map(db)

    def _resolve_name(e_id: Optional[int]) -> Optional[str]:
        if not e_id:
            return None
        return names_map.get(int(e_id), f"موظف {e_id}")

    # 1. Upsert HSE Officer
    hse_cfg = db.query(BudgetGovernanceConfig).filter(
        BudgetGovernanceConfig.config_type == "HSE_OFFICER",
        BudgetGovernanceConfig.scope_key == "GLOBAL"
    ).first()
    if not hse_cfg:
        hse_cfg = BudgetGovernanceConfig(
            config_type="HSE_OFFICER",
            scope_key="GLOBAL"
        )
        db.add(hse_cfg)
    hse_cfg.assigned_emp_id = payload.hse_officer_emp_id
    hse_cfg.assigned_emp_name = _resolve_name(payload.hse_officer_emp_id)
    hse_cfg.updated_by = str(actor["emp_id"])

    # 2. Upsert Leaderboard Visibility Toggle
    lb_cfg = db.query(BudgetGovernanceConfig).filter(
        BudgetGovernanceConfig.config_type == "LEADERBOARD_VISIBILITY",
        BudgetGovernanceConfig.scope_key == "GLOBAL"
    ).first()
    if not lb_cfg:
        lb_cfg = BudgetGovernanceConfig(
            config_type="LEADERBOARD_VISIBILITY",
            scope_key="GLOBAL"
        )
        db.add(lb_cfg)
    lb_cfg.is_enabled = bool(payload.leaderboard_enabled)
    lb_cfg.updated_by = str(actor["emp_id"])

    # 3. Upsert Department General Managers (GMs)
    for dept_name, gm_emp_id in (payload.dept_gms or {}).items():
        d_clean = dept_name.strip()
        if not d_clean:
            continue
        gm_cfg = db.query(BudgetGovernanceConfig).filter(
            BudgetGovernanceConfig.config_type == "DEPT_GM",
            BudgetGovernanceConfig.scope_key == d_clean
        ).first()
        if gm_emp_id:
            if not gm_cfg:
                gm_cfg = BudgetGovernanceConfig(
                    config_type="DEPT_GM",
                    scope_key=d_clean
                )
                db.add(gm_cfg)
            gm_cfg.assigned_emp_id = int(gm_emp_id)
            gm_cfg.assigned_emp_name = _resolve_name(int(gm_emp_id))
            gm_cfg.updated_by = str(actor["emp_id"])
        elif gm_cfg:
            db.delete(gm_cfg)

    try:
        log_system_action(
            db=db,
            user_id=str(actor["emp_id"]),
            action="UPDATE_BUDGET_RBAC_SETTINGS",
            entity="BudgetModule",
            details=f"HSE Officer={payload.hse_officer_emp_id}, Leaderboard={payload.leaderboard_enabled}, GMs={len(payload.dept_gms)}"
        )
    except Exception:
        pass

    db.commit()
    return {
        "status": "success",
        "message": "تم حفظ إعدادات حوكمة الموازنة وصلاحيات الاعتماد بنجاح"
    }


@budget_router.get("/dashboard-data")
def get_budget_dashboard_data(
    request: Request,
    year: int = Query(2026, description="Fiscal Year (e.g. 2026)"),
    quarter: Optional[int] = Query(None, description="Quarter (1-4), or omit/0 for Full Year"),
    dept_name: Optional[str] = Query(None, description="General Department Name filter"),
    simulate_role: Optional[str] = Query(None, description="Admin Role Simulator override"),
    simulate_dept: Optional[str] = Query(None, description="Admin Role Simulator department"),
    db: Session = Depends(get_db)
):
    """
    Returns calculated KPIs (Total Allocated, Total Spent, Net Savings, Savings %),
    category/department chart data, and the detailed line-item table.
    Enforces Department Isolation when the user is a standard employee or Department GM.
    """
    total_budgets_in_db = db.query(DepartmentBudget).count()
    if total_budgets_in_db == 0:
        try:
            from seeds.seed_standalone_db import initialize_and_seed_standalone_db
            initialize_and_seed_standalone_db()
        except Exception:
            pass

    actor = resolve_budget_actor(request, db, simulate_role=simulate_role, simulate_dept=simulate_dept)

    # Department Isolation Rule: If not Admin or HSE Officer, lock filter to user's department
    effective_dept_filter = dept_name
    if not actor["can_view_all_depts"]:
        effective_dept_filter = actor["effective_dept"] or "الشئون الإدارية"

    q_budgets = db.query(DepartmentBudget).filter(DepartmentBudget.fiscal_year == year)
    if quarter and quarter in (1, 2, 3, 4):
        q_budgets = q_budgets.filter(DepartmentBudget.quarter == quarter)

    if effective_dept_filter and effective_dept_filter.strip() and effective_dept_filter.strip() not in ("ALL", "الكل"):
        q_budgets = q_budgets.filter(DepartmentBudget.general_dept_name == effective_dept_filter.strip())

    budgets = q_budgets.order_by(DepartmentBudget.quarter.asc(), DepartmentBudget.general_dept_name.asc()).all()

    line_items_list: List[Dict[str, Any]] = []
    dept_aggregates: Dict[str, Dict[str, float]] = {}
    category_savings: List[Dict[str, Any]] = []

    total_allocated = 0.0
    total_spent = 0.0

    for b in budgets:
        d_name = b.general_dept_name
        if d_name not in dept_aggregates:
            dept_aggregates[d_name] = {"allocated": 0.0, "spent": 0.0, "savings": 0.0}

        if b.line_items:
            for item in b.line_items:
                alloc = float(item.allocated_amount or 0.0)
                spent = float(item.spent_amount or 0.0)
                savings = round(alloc - spent, 2)
                savings_pct = round((savings / alloc) * 100.0, 1) if alloc > 0 else 0.0

                total_allocated += alloc
                total_spent += spent

                dept_aggregates[d_name]["allocated"] += alloc
                dept_aggregates[d_name]["spent"] += spent
                dept_aggregates[d_name]["savings"] += savings

                item_dict = {
                    "id": item.id,
                    "budget_id": b.id,
                    "general_dept_name": d_name,
                    "fiscal_year": b.fiscal_year,
                    "quarter": b.quarter,
                    "quarter_label": f"الربع {b.quarter} (Q{b.quarter})",
                    "item_name": item.item_name,
                    "allocated_amount": alloc,
                    "spent_amount": spent,
                    "savings_amount": savings,
                    "savings_pct": savings_pct,
                    "savings_narrative": item.savings_narrative or "—",
                    "gm_approved": bool(getattr(item, "gm_approved", False)),
                    "gm_approved_by": getattr(item, "gm_approved_by", None),
                    "hse_approved": bool(item.hse_approved),
                    "hse_approved_by": item.hse_approved_by,
                    "workflow_status": item.workflow_status or "NEW",
                    "cost_avoidance_amount": float(item.cost_avoidance_amount or 0.0),
                    "has_variance": spent > alloc,
                    "variance_amount": round(spent - alloc, 2) if spent > alloc else 0.0,
                    "variance_root_cause": item.variance_root_cause,
                    "corrective_action": item.corrective_action,
                    "corrective_owner": item.corrective_owner,
                    "corrective_due_date": item.corrective_due_date.isoformat() if item.corrective_due_date else None,
                }
                line_items_list.append(item_dict)
                if savings > 0:
                    category_savings.append({
                        "label": f"{item.item_name} ({d_name})",
                        "short_label": item.item_name,
                        "dept_name": d_name,
                        "savings": savings,
                        "allocated": alloc,
                        "spent": spent
                    })
        else:
            alloc = float(b.allocated_amount or 0.0)
            total_allocated += alloc
            dept_aggregates[d_name]["allocated"] += alloc
            dept_aggregates[d_name]["savings"] += alloc

    net_savings = round(total_allocated - total_spent, 2)
    savings_pct = round((net_savings / total_allocated) * 100.0, 1) if total_allocated > 0 else 0.0

    single_dept_selected = bool(effective_dept_filter and effective_dept_filter.strip() and effective_dept_filter.strip() not in ("ALL", "الكل"))
    if single_dept_selected and line_items_list:
        bar_labels = [f"{it['item_name']} (Q{it['quarter']})" if not quarter else it["item_name"] for it in line_items_list]
        bar_allocated = [it["allocated_amount"] for it in line_items_list]
        bar_spent = [it["spent_amount"] for it in line_items_list]
        bar_savings = [it["savings_amount"] for it in line_items_list]
    else:
        bar_labels = list(dept_aggregates.keys())
        bar_allocated = [round(dept_aggregates[k]["allocated"], 2) for k in bar_labels]
        bar_spent = [round(dept_aggregates[k]["spent"], 2) for k in bar_labels]
        bar_savings = [round(dept_aggregates[k]["savings"], 2) for k in bar_labels]

    if single_dept_selected:
        doughnut_labels = [c["short_label"] for c in category_savings]
        doughnut_values = [c["savings"] for c in category_savings]
    else:
        doughnut_labels = [k for k in dept_aggregates.keys() if dept_aggregates[k]["savings"] > 0]
        doughnut_values = [round(dept_aggregates[k]["savings"], 2) for k in doughnut_labels]

    # Compute company-wide departmental rankings for the selected year/quarter
    q_ranking_budgets = db.query(DepartmentBudget).filter(DepartmentBudget.fiscal_year == year)
    if quarter and quarter in (1, 2, 3, 4):
        q_ranking_budgets = q_ranking_budgets.filter(DepartmentBudget.quarter == quarter)

    ranking_aggregates: Dict[str, Dict[str, float]] = {}
    for rb in q_ranking_budgets.all():
        r_dept = rb.general_dept_name
        if r_dept not in ranking_aggregates:
            ranking_aggregates[r_dept] = {"allocated": 0.0, "spent": 0.0, "savings": 0.0}
        if rb.line_items:
            for r_item in rb.line_items:
                r_alloc = float(r_item.allocated_amount or 0.0)
                r_spent = float(r_item.spent_amount or 0.0)
                ranking_aggregates[r_dept]["allocated"] += r_alloc
                ranking_aggregates[r_dept]["spent"] += r_spent
                ranking_aggregates[r_dept]["savings"] += (r_alloc - r_spent)
        else:
            r_alloc = float(rb.allocated_amount or 0.0)
            ranking_aggregates[r_dept]["allocated"] += r_alloc
            ranking_aggregates[r_dept]["savings"] += r_alloc

    ranked_departments: List[Dict[str, Any]] = []
    for r_dept, vals in ranking_aggregates.items():
        r_alloc = round(vals["allocated"], 2)
        r_spent = round(vals["spent"], 2)
        r_saved = round(vals["savings"], 2)
        r_pct = round((r_saved / r_alloc) * 100.0, 1) if r_alloc > 0 else 0.0
        ranked_departments.append({
            "dept_name": r_dept,
            "allocated_amount": r_alloc,
            "spent_amount": r_spent,
            "saved_amount": r_saved,
            "savings_pct": r_pct
        })

    ranked_departments.sort(key=lambda d: (d["saved_amount"], d["savings_pct"]), reverse=True)

    top_departments = ranked_departments[:3]
    lowest_department = ranked_departments[-1] if ranked_departments else None

    governance_kpis = {
        "cost_avoidance_total": round(sum(i["cost_avoidance_amount"] for i in line_items_list), 2),
        "cost_avoidance_items": sum(1 for i in line_items_list if i["cost_avoidance_amount"] > 0),
        "verified_savings": round(sum(
            i["savings_amount"] for i in line_items_list
            if i["hse_approved"] and i["workflow_status"] == VERIFIED_STATUS and i["savings_amount"] > 0
        ), 2),
        "pending_hse_count": sum(1 for i in line_items_list if not i["hse_approved"]),
        "pending_gm_count": sum(1 for i in line_items_list if not i.get("gm_approved")),
        "variance_count": sum(1 for i in line_items_list if i["has_variance"]),
        "variance_unresolved_count": sum(
            1 for i in line_items_list if i["has_variance"] and not i["corrective_action"]
        ),
    }

    all_depts = get_all_general_departments(db)

    return {
        "status": "success",
        "actor": actor,
        "leaderboard_enabled": actor["leaderboard_enabled"],
        "filters": {
            "year": year,
            "quarter": quarter or 0,
            "dept_name": effective_dept_filter or ""
        },
        "kpis": {
            "total_allocated": round(total_allocated, 2),
            "total_spent": round(total_spent, 2),
            "net_savings": net_savings,
            "savings_pct": savings_pct,
            "items_count": len(line_items_list),
            "departments_count": len(dept_aggregates)
        },
        "governance_kpis": governance_kpis,
        "top_departments": top_departments,
        "lowest_department": lowest_department,
        "charts": {
            "bar": {
                "labels": bar_labels,
                "allocated": bar_allocated,
                "spent": bar_spent,
                "savings": bar_savings
            },
            "doughnut": {
                "labels": doughnut_labels,
                "values": doughnut_values
            }
        },
        "line_items": line_items_list,
        "available_departments": all_depts
    }


@budget_router.post("/line-item")
def upsert_budget_line_item(
    payload: BudgetLineItemPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Add or edit a budget line item and its detailed savings mechanism narrative.
    Enforces Department Isolation: non-admin users automatically lock to their assigned department.
    """
    actor = resolve_budget_actor(
        request, db,
        simulate_role=payload.simulate_role,
        simulate_dept=payload.simulate_dept
    )

    if not actor["can_view_all_depts"] and actor["effective_dept"]:
        dept_clean = actor["effective_dept"].strip()
    else:
        dept_clean = payload.general_dept_name.strip()

    if not dept_clean:
        raise HTTPException(status_code=400, detail="يرجى تحديد الإدارة العامة")

    parent_budget = db.query(DepartmentBudget).filter(
        DepartmentBudget.general_dept_name == dept_clean,
        DepartmentBudget.fiscal_year == payload.fiscal_year,
        DepartmentBudget.quarter == payload.quarter
    ).first()

    if not parent_budget:
        parent_budget = DepartmentBudget(
            general_dept_name=dept_clean,
            fiscal_year=payload.fiscal_year,
            quarter=payload.quarter,
            allocated_amount=payload.allocated_amount
        )
        db.add(parent_budget)
        db.flush()

    if payload.item_id:
        item = db.get(BudgetLineItem, payload.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="بند الموازنة غير موجود")
        if not actor["can_view_all_depts"] and item.budget and item.budget.general_dept_name != dept_clean:
            raise HTTPException(status_code=403, detail="غير مصرح بتعديل بنود إدارة أخرى")
        item.budget_id = parent_budget.id
        item.item_name = payload.item_name.strip()
        item.allocated_amount = float(payload.allocated_amount)
        item.spent_amount = float(payload.spent_amount)
        item.savings_narrative = (payload.savings_narrative or "").strip()
        action_type = "UPDATE_BUDGET_ITEM"
    else:
        item = BudgetLineItem(
            budget_id=parent_budget.id,
            item_name=payload.item_name.strip(),
            allocated_amount=float(payload.allocated_amount),
            spent_amount=float(payload.spent_amount),
            savings_narrative=(payload.savings_narrative or "").strip(),
            created_by_emp_id=actor["emp_id"]
        )
        db.add(item)
        db.flush()
        action_type = "CREATE_BUDGET_ITEM"

    db.flush()
    items_sum = sum(float(li.allocated_amount or 0.0) for li in parent_budget.line_items)
    parent_budget.allocated_amount = round(items_sum, 2)

    try:
        log_system_action(
            db=db,
            user_id=str(actor["emp_id"]),
            action=action_type,
            entity="BudgetModule",
            details=f"{dept_clean} - Q{payload.quarter}/{payload.fiscal_year}: {item.item_name} (محجوز: {item.allocated_amount}, منصرف: {item.spent_amount})"
        )
    except Exception:
        pass

    db.commit()
    db.refresh(item)

    return {
        "status": "success",
        "message": "تم حفظ بند الموازنة وتفاصيل التوفير بنجاح",
        "item": {
            "id": item.id,
            "budget_id": item.budget_id,
            "general_dept_name": parent_budget.general_dept_name,
            "fiscal_year": parent_budget.fiscal_year,
            "quarter": parent_budget.quarter,
            "item_name": item.item_name,
            "allocated_amount": item.allocated_amount,
            "spent_amount": item.spent_amount,
            "savings_amount": item.savings_amount,
            "savings_pct": item.savings_pct,
            "savings_narrative": item.savings_narrative
        }
    }


@budget_router.delete("/line-item/{item_id}")
def delete_budget_line_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    actor = resolve_budget_actor(request, db)
    item = db.get(BudgetLineItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="بند الموازنة غير موجود")

    parent_budget = item.budget
    if not actor["can_view_all_depts"] and parent_budget and parent_budget.general_dept_name != actor["effective_dept"]:
        raise HTTPException(status_code=403, detail="غير مصرح بحذف بنود إدارة أخرى")

    item_title = item.item_name
    db.delete(item)
    db.flush()

    if parent_budget:
        items_sum = sum(float(li.allocated_amount or 0.0) for li in parent_budget.line_items)
        parent_budget.allocated_amount = round(items_sum, 2)

    db.commit()
    return {
        "status": "success",
        "message": f"تم حذف البند ({item_title}) بنجاح"
    }


@budget_router.post("/line-item/{item_id}/governance")
def update_item_governance(
    item_id: int,
    payload: GovernancePayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update lifecycle status, GM approval, HSE approval and cost avoidance.
    Enforces RBAC:
    - HSE approval can only be toggled by the designated HSE Officer or Admin.
    - GM approval can only be toggled by the designated Department GM or Admin.
    - HSE gate: no status beyond UNDER_EVALUATION is allowed without HSE approval.
    """
    actor = resolve_budget_actor(
        request, db,
        simulate_role=payload.simulate_role,
        simulate_dept=payload.simulate_dept
    )
    item = db.get(BudgetLineItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="بند الموازنة غير موجود")

    item_dept = item.budget.general_dept_name if item.budget else ""
    if not actor["can_view_all_depts"] and actor["effective_dept"] and item_dept != actor["effective_dept"]:
        raise HTTPException(status_code=403, detail="غير مصرح بتعديل حوكمة بند تابع لإدارة أخرى")

    new_status = (payload.workflow_status or "").strip().upper()
    if new_status not in WORKFLOW_STATUSES:
        raise HTTPException(status_code=400, detail="حالة سير العمل غير صالحة")

    if payload.hse_approved != bool(item.hse_approved) and not actor["can_approve_hse"]:
        raise HTTPException(
            status_code=403,
            detail="غير مصرح: اعتماد السلامة والصحة المهنية (HSE) مخصص لمسؤول السلامة المعتمد فقط"
        )

    if payload.gm_approved is not None and payload.gm_approved != bool(item.gm_approved):
        if not actor["can_approve_gm"]:
            raise HTTPException(
                status_code=403,
                detail="غير مصرح: اعتماد المدير العام للإدارة (GM) مخصص لمدير عام الإدارة فقط"
            )
        if not actor["is_real_admin"] and item_dept not in actor.get("managed_gm_depts", []):
            raise HTTPException(
                status_code=403,
                detail=f"غير مصرح: المدير العام معتمد للإدارات ({', '.join(actor.get('managed_gm_depts', []))}) ولا يمكنه اعتماد بند لإدارة أخرى ({item_dept})"
            )
        if payload.gm_approved and not item.gm_approved:
            item.gm_approved = True
            item.gm_approved_by = str(actor["emp_id"])
            item.gm_approved_at = datetime.utcnow()
        elif not payload.gm_approved:
            item.gm_approved = False
            item.gm_approved_by = None
            item.gm_approved_at = None

    if new_status in HSE_GATED_STATUSES and not payload.hse_approved:
        raise HTTPException(
            status_code=400,
            detail="بوابة السلامة (HSE): لا يمكن اعتماد المبادرة أو المتابعة أو توثيق الوفر قبل اعتماد HSE"
        )

    old_state = {
        "status": item.workflow_status,
        "gm": item.gm_approved,
        "hse": item.hse_approved,
        "cost_avoidance": item.cost_avoidance_amount
    }

    if payload.hse_approved and not item.hse_approved:
        item.hse_approved_by = str(actor["emp_id"])
        item.hse_approved_at = datetime.utcnow()
    elif not payload.hse_approved:
        item.hse_approved_by = None
        item.hse_approved_at = None

    item.hse_approved = payload.hse_approved
    item.workflow_status = new_status
    item.cost_avoidance_amount = float(payload.cost_avoidance_amount or 0.0)

    try:
        log_system_action(
            db=db, user_id=str(actor["emp_id"]), action="UPDATE_BUDGET_GOVERNANCE", entity="BudgetModule",
            details=f"{item.item_name}: {old_state} -> status={new_status}, gm={item.gm_approved}, hse={payload.hse_approved}, "
                    f"cost_avoidance={item.cost_avoidance_amount}"
        )
    except Exception:
        pass

    db.commit()
    return {"status": "success", "message": "تم تحديث حوكمة البند بنجاح"}


@budget_router.post("/line-item/{item_id}/variance")
def log_item_variance(
    item_id: int,
    payload: VariancePayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """Log root cause and corrective action plan for an over-budget line item."""
    actor = resolve_budget_actor(
        request, db,
        simulate_role=payload.simulate_role,
        simulate_dept=payload.simulate_dept
    )
    item = db.get(BudgetLineItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="بند الموازنة غير موجود")

    item_dept = item.budget.general_dept_name if item.budget else ""
    if not actor["can_view_all_depts"] and actor["effective_dept"] and item_dept != actor["effective_dept"]:
        raise HTTPException(status_code=403, detail="غير مصرح بتحليل انحراف لبند تابع لإدارة أخرى")

    if float(item.spent_amount or 0.0) <= float(item.allocated_amount or 0.0):
        raise HTTPException(status_code=400, detail="لا يوجد انحراف في هذا البند (المنصرف لا يتجاوز المحجوز)")

    item.variance_root_cause = payload.variance_root_cause.strip()
    item.corrective_action = payload.corrective_action.strip()
    item.corrective_owner = (payload.corrective_owner or "").strip() or None
    item.corrective_due_date = payload.corrective_due_date

    try:
        log_system_action(
            db=db, user_id=str(actor["emp_id"]), action="LOG_BUDGET_VARIANCE", entity="BudgetModule",
            details=f"{item.item_name}: انحراف {round(item.spent_amount - item.allocated_amount, 2)} - السبب: {item.variance_root_cause}"
        )
    except Exception:
        pass

    db.commit()
    return {"status": "success", "message": "تم تسجيل تحليل الانحراف وخطة الإجراء التصحيحي"}


# ==============================================================================
# 👥 User & Employee Management Endpoints (Admin Controlled RBAC)
# ==============================================================================

@budget_router.get("/users")
def list_budget_users(
    search: Optional[str] = None,
    dept_name: Optional[str] = None,
    role: Optional[str] = None,
    work_location: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Returns complete searchable/filterable directory of users/employees.
    Restricted strictly to System Admin (7071).
    """
    if hasattr(search, "default"):
        search = None
    if hasattr(dept_name, "default"):
        dept_name = None
    if hasattr(role, "default"):
        role = None
    if hasattr(work_location, "default"):
        work_location = None

    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: استعراض دليل الموظفين مخصص لمدير النظام فقط")

    query = db.query(BudgetUser)

    if dept_name and dept_name.strip():
        query = query.filter(BudgetUser.general_dept_name == dept_name.strip())

    if role and role.strip():
        query = query.filter(BudgetUser.role == role.strip().lower())

    if work_location and work_location.strip():
        query = query.filter(BudgetUser.work_location == work_location.strip())

    if search and search.strip():
        s = f"%{search.strip()}%"
        query = query.filter(
            (BudgetUser.name.ilike(s)) |
            (BudgetUser.emp_id.cast(String).ilike(s)) |
            (BudgetUser.phone.ilike(s)) |
            (BudgetUser.email.ilike(s)) |
            (BudgetUser.job_title.ilike(s))
        )

    users = query.order_by(BudgetUser.emp_id).all()

    # Read governance configs to identify designated roles
    configs = db.query(BudgetGovernanceConfig).all()
    hse_id = next(
        (c.assigned_emp_id for c in configs if c.config_type == "HSE_OFFICER" and c.scope_key == "GLOBAL"),
        None
    )
    gm_depts_by_emp: Dict[int, List[str]] = {}
    for c in configs:
        if c.config_type == "DEPT_GM" and c.assigned_emp_id:
            gm_depts_by_emp.setdefault(int(c.assigned_emp_id), []).append(c.scope_key)

    user_list = []
    for u in users:
        user_list.append({
            "emp_id": u.emp_id,
            "name": u.name,
            "role": u.role,
            "general_dept_name": u.general_dept_name or "",
            "dept_name": u.dept_name or "",
            "job_title": u.job_title or "",
            "work_location": u.work_location or "",
            "phone": u.phone or "",
            "email": u.email or "",
            "is_active": u.is_active,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else None,
            "is_designated_hse": (hse_id is not None and int(hse_id) == int(u.emp_id)),
            "designated_gm_depts": gm_depts_by_emp.get(int(u.emp_id), []),
        })

    lookups = get_dynamic_lookups(db)

    return {
        "status": "success",
        "total": len(user_list),
        "users": user_list,
        "available_departments": lookups["departments"],
        "available_sub_departments": lookups["sub_departments"],
        "available_locations": lookups["work_locations"],
        "available_job_titles": lookups["job_titles"],
        "available_roles": lookups["roles"],
        "lookup_options": lookups["options"],
    }


@budget_router.post("/users")
def create_budget_user(
    payload: UserCreatePayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Creates a new user/employee with password hashing, contact details, and RBAC governance sync.
    Restricted strictly to System Admin (7071).
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: إضافة موظف مخصصة لمدير النظام فقط")

    existing = db.get(BudgetUser, int(payload.emp_id))
    if existing:
        raise HTTPException(status_code=400, detail=f"رقم الموظف ({payload.emp_id}) مسجل بالفعل مسبقاً")

    raw_password = (payload.password or "123456").strip()
    pwd_hash = generate_password_hash(raw_password)

    role_clean = payload.role.strip().lower()
    dept_clean = (payload.general_dept_name or "").strip() or None

    new_user = BudgetUser(
        emp_id=int(payload.emp_id),
        name=payload.name.strip(),
        password_hash=pwd_hash,
        role=role_clean,
        general_dept_name=dept_clean,
        dept_name=(payload.dept_name or "").strip() or None,
        job_title=(payload.job_title or "").strip() or None,
        work_location=(payload.work_location or "").strip() or None,
        phone=(payload.phone or "").strip() or None,
        email=(payload.email or "").strip() or None,
        is_active=payload.is_active,
    )
    db.add(new_user)
    db.flush()

    # Governance auto-sync for HSE Officer or Department GM
    if role_clean == "hse_officer":
        hse_cfg = db.query(BudgetGovernanceConfig).filter(
            BudgetGovernanceConfig.config_type == "HSE_OFFICER",
            BudgetGovernanceConfig.scope_key == "GLOBAL"
        ).first()
        if not hse_cfg:
            hse_cfg = BudgetGovernanceConfig(config_type="HSE_OFFICER", scope_key="GLOBAL")
            db.add(hse_cfg)
        hse_cfg.assigned_emp_id = new_user.emp_id
        hse_cfg.assigned_emp_name = new_user.name
        hse_cfg.updated_by = str(actor["emp_id"])

    elif role_clean in ("dept_gm", "manager") and dept_clean:
        gm_cfg = db.query(BudgetGovernanceConfig).filter(
            BudgetGovernanceConfig.config_type == "DEPT_GM",
            BudgetGovernanceConfig.scope_key == dept_clean
        ).first()
        if not gm_cfg:
            gm_cfg = BudgetGovernanceConfig(config_type="DEPT_GM", scope_key=dept_clean)
            db.add(gm_cfg)
        gm_cfg.assigned_emp_id = new_user.emp_id
        gm_cfg.assigned_emp_name = new_user.name
        gm_cfg.updated_by = str(actor["emp_id"])

    try:
        log_system_action(
            db=db,
            user_id=str(actor["emp_id"]),
            action="CREATE_USER",
            entity="UserManagement",
            details=f"إضافة موظف: {new_user.name} ({new_user.emp_id}) - الإدارة: {new_user.general_dept_name} - الدور: {new_user.role}"
        )
    except Exception:
        pass

    db.commit()
    db.refresh(new_user)

    return {
        "status": "success",
        "message": f"تمت إضافة الموظف ({new_user.name}) بنجاح",
        "user": {
            "emp_id": new_user.emp_id,
            "name": new_user.name,
            "role": new_user.role,
            "general_dept_name": new_user.general_dept_name,
            "work_location": new_user.work_location,
            "phone": new_user.phone,
            "email": new_user.email,
        }
    }


@budget_router.put("/users/{emp_id}")
def update_budget_user(
    emp_id: int,
    payload: UserUpdatePayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Updates user/employee fields and syncs governance designations.
    Restricted strictly to System Admin (7071).
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: تعديل بيانات الموظف مخصص لمدير النظام فقط")

    user = db.get(BudgetUser, int(emp_id))
    if not user:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")

    if payload.name is not None and payload.name.strip():
        user.name = payload.name.strip()

    if payload.role is not None and payload.role.strip():
        role_req = payload.role.strip().lower()
        if int(emp_id) == 7071 and role_req != "admin":
            raise HTTPException(status_code=400, detail="لا يمكن تغيير دور مدير النظام الأساسي (7071)")
        user.role = role_req

    if payload.general_dept_name is not None:
        user.general_dept_name = payload.general_dept_name.strip() or None

    if payload.dept_name is not None:
        user.dept_name = payload.dept_name.strip() or None

    if payload.job_title is not None:
        user.job_title = payload.job_title.strip() or None

    if payload.work_location is not None:
        user.work_location = payload.work_location.strip() or None

    if payload.phone is not None:
        user.phone = payload.phone.strip() or None

    if payload.email is not None:
        user.email = payload.email.strip() or None

    if payload.is_active is not None:
        if int(emp_id) == 7071 and not payload.is_active:
            raise HTTPException(status_code=400, detail="لا يمكن تعطيل حساب مدير النظام الأساسي (7071)")
        user.is_active = payload.is_active

    if payload.password is not None and payload.password.strip():
        user.password_hash = generate_password_hash(payload.password.strip())

    # Governance auto-sync for HSE Officer
    if user.role == "hse_officer":
        hse_cfg = db.query(BudgetGovernanceConfig).filter(
            BudgetGovernanceConfig.config_type == "HSE_OFFICER",
            BudgetGovernanceConfig.scope_key == "GLOBAL"
        ).first()
        if not hse_cfg:
            hse_cfg = BudgetGovernanceConfig(config_type="HSE_OFFICER", scope_key="GLOBAL")
            db.add(hse_cfg)
        hse_cfg.assigned_emp_id = user.emp_id
        hse_cfg.assigned_emp_name = user.name
        hse_cfg.updated_by = str(actor["emp_id"])

    elif user.role in ("dept_gm", "manager") and user.general_dept_name:
        gm_cfg = db.query(BudgetGovernanceConfig).filter(
            BudgetGovernanceConfig.config_type == "DEPT_GM",
            BudgetGovernanceConfig.scope_key == user.general_dept_name
        ).first()
        if not gm_cfg:
            gm_cfg = BudgetGovernanceConfig(config_type="DEPT_GM", scope_key=user.general_dept_name)
            db.add(gm_cfg)
        gm_cfg.assigned_emp_id = user.emp_id
        gm_cfg.assigned_emp_name = user.name
        gm_cfg.updated_by = str(actor["emp_id"])

    try:
        log_system_action(
            db=db,
            user_id=str(actor["emp_id"]),
            action="UPDATE_USER",
            entity="UserManagement",
            details=f"تعديل موظف: {user.name} ({user.emp_id}) - دور: {user.role}"
        )
    except Exception:
        pass

    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": f"تم تحديث بيانات الموظف ({user.name}) بنجاح",
        "user": {
            "emp_id": user.emp_id,
            "name": user.name,
            "role": user.role,
            "general_dept_name": user.general_dept_name,
            "work_location": user.work_location,
            "phone": user.phone,
            "email": user.email,
            "is_active": user.is_active,
        }
    }


@budget_router.delete("/users/{emp_id}")
def delete_budget_user(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Deletes an employee account and clears associated governance roles.
    Prevented strictly for primary admin 7071.
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: حذف الموظف مخصص لمدير النظام فقط")

    if int(emp_id) == 7071:
        raise HTTPException(status_code=400, detail="محظور: لا يمكن حذف حساب مدير النظام الأساسي (7071)")

    user = db.get(BudgetUser, int(emp_id))
    if not user:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")

    user_name = user.name

    # Clear governance links
    gov_cfgs = db.query(BudgetGovernanceConfig).filter(
        BudgetGovernanceConfig.assigned_emp_id == int(emp_id)
    ).all()
    for cfg in gov_cfgs:
        cfg.assigned_emp_id = None
        cfg.assigned_emp_name = None

    db.delete(user)

    try:
        log_system_action(
            db=db,
            user_id=str(actor["emp_id"]),
            action="DELETE_USER",
            entity="UserManagement",
            details=f"حذف حساب الموظف: {user_name} ({emp_id})"
        )
    except Exception:
        pass

    db.commit()

    return {
        "status": "success",
        "message": f"تم حذف حساب الموظف ({user_name}) بنجاح"
    }


@budget_router.post("/users/{emp_id}/reset-password")
def reset_user_password(
    emp_id: int,
    payload: UserResetPasswordPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Allows Admin to reset any employee's password cleanly.
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: إعادة تعيين كلمة المرور مخصصة لمدير النظام فقط")

    user = db.get(BudgetUser, int(emp_id))
    if not user:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")

    user.password_hash = generate_password_hash(payload.new_password.strip())

    try:
        log_system_action(
            db=db,
            user_id=str(actor["emp_id"]),
            action="RESET_PASSWORD",
            entity="UserManagement",
            details=f"إعادة تعيين كلمة المرور للموظف: {user.name} ({emp_id})"
        )
    except Exception:
        pass

    db.commit()

    return {
        "status": "success",
        "message": f"تمت إعادة تعيين كلمة المرور للموظف ({user.name}) بنجاح"
    }


# ==============================================================================
# 📋 Dynamic Lookup Options Management (Departments, Work Locations, Job Titles)
# ==============================================================================

VALID_LOOKUP_CATEGORIES = {"DEPARTMENT", "SUB_DEPARTMENT", "WORK_LOCATION", "JOB_TITLE", "ROLE"}


@budget_router.get("/lookups")
def list_system_lookups(
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Returns all dynamic dropdown options (Departments, Sub-Departments, Work Locations, Job Titles, Job Roles).
    """
    data = get_dynamic_lookups(db)
    return {
        "status": "success",
        **data
    }


@budget_router.post("/lookups")
def create_system_lookup(
    payload: LookupCreatePayload,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Adds a new dynamic option to DEPARTMENT, SUB_DEPARTMENT, WORK_LOCATION, JOB_TITLE, or ROLE.
    Restricted to System Admin.
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: إدارة القوائم المنسدلة مخصصة لمدير النظام فقط")

    cat = (payload.category or "").strip().upper()
    val = (payload.value or "").strip()
    if cat not in VALID_LOOKUP_CATEGORIES:
        raise HTTPException(status_code=400, detail="تصنيف القائمة غير صالح")
    if len(val) < 2:
        raise HTTPException(status_code=400, detail="يرجى إدخال اسم صالح لا يقل عن حرفين")

    existing = db.query(SystemLookupOption).filter_by(category=cat, value=val).first()
    if existing:
        existing.is_active = True
        opt = existing
    else:
        opt = SystemLookupOption(category=cat, value=val, is_active=True)
        db.add(opt)

    if cat == "DEPARTMENT":
        dept_lookup = db.query(GeneralDepartmentLookup).filter_by(name=val).first()
        if not dept_lookup:
            db.add(GeneralDepartmentLookup(name=val, is_active=True))
        else:
            dept_lookup.is_active = True

    db.commit()
    db.refresh(opt)

    return {
        "status": "success",
        "message": f"تمت إضافة ({val}) بنجاح إلى القائمة",
        "option": {
            "id": opt.id,
            "category": opt.category,
            "value": opt.value,
            "is_active": opt.is_active
        },
        **get_dynamic_lookups(db)
    }


@budget_router.put("/lookups/{lookup_id}")
def update_system_lookup(
    lookup_id: int,
    payload: LookupUpdatePayload,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Renames or updates an existing lookup option and cascades the rename across matching records.
    Restricted to System Admin.
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: تعديل القوائم المنسدلة مخصص لمدير النظام فقط")

    opt = db.get(SystemLookupOption, int(lookup_id))
    if not opt:
        raise HTTPException(status_code=404, detail="العنصر غير موجود في القائمة")

    old_val = opt.value
    new_val = (payload.value or "").strip()
    if len(new_val) < 2:
        raise HTTPException(status_code=400, detail="القيمة الجديدة غير صالحة")

    if new_val != old_val:
        dup = db.query(SystemLookupOption).filter(
            SystemLookupOption.category == opt.category,
            SystemLookupOption.value == new_val,
            SystemLookupOption.id != opt.id
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"الاسم ({new_val}) موجود بالفعل في نفس القائمة")

        opt.value = new_val

        # Cascade rename to maintain relational data integrity
        if opt.category == "DEPARTMENT":
            dept_row = db.query(GeneralDepartmentLookup).filter_by(name=old_val).first()
            if dept_row:
                dept_row.name = new_val
            db.query(BudgetUser).filter(BudgetUser.general_dept_name == old_val).update(
                {"general_dept_name": new_val}, synchronize_session=False
            )
            db.query(DepartmentBudget).filter(DepartmentBudget.general_dept_name == old_val).update(
                {"general_dept_name": new_val}, synchronize_session=False
            )
            db.query(BudgetGovernanceConfig).filter(
                BudgetGovernanceConfig.config_type == "DEPT_GM",
                BudgetGovernanceConfig.scope_key == old_val
            ).update({"scope_key": new_val}, synchronize_session=False)
        elif opt.category == "SUB_DEPARTMENT":
            db.query(BudgetUser).filter(BudgetUser.dept_name == old_val).update(
                {"dept_name": new_val}, synchronize_session=False
            )
        elif opt.category == "WORK_LOCATION":
            db.query(BudgetUser).filter(BudgetUser.work_location == old_val).update(
                {"work_location": new_val}, synchronize_session=False
            )
        elif opt.category == "JOB_TITLE":
            db.query(BudgetUser).filter(BudgetUser.job_title == old_val).update(
                {"job_title": new_val}, synchronize_session=False
            )
        elif opt.category == "ROLE":
            db.query(BudgetUser).filter(BudgetUser.role == old_val).update(
                {"role": new_val}, synchronize_session=False
            )

    if payload.is_active is not None:
        opt.is_active = payload.is_active

    db.commit()
    db.refresh(opt)

    return {
        "status": "success",
        "message": f"تم تحديث ({old_val}) إلى ({new_val}) بنجاح",
        "option": {
            "id": opt.id,
            "category": opt.category,
            "value": opt.value,
            "is_active": opt.is_active
        },
        **get_dynamic_lookups(db)
    }


@budget_router.delete("/lookups/{lookup_id}")
def delete_system_lookup(
    lookup_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Removes an option from the dynamic dropdown list.
    Restricted to System Admin.
    """
    actor = resolve_budget_actor(request, db)
    if not actor["is_real_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح: حذف عناصر القوائم المنسدلة مخصص لمدير النظام فقط")

    opt = db.get(SystemLookupOption, int(lookup_id))
    if not opt:
        raise HTTPException(status_code=404, detail="العنصر غير موجود")

    cat = opt.category
    val = opt.value
    db.delete(opt)

    if cat == "DEPARTMENT":
        dept_row = db.query(GeneralDepartmentLookup).filter_by(name=val).first()
        if dept_row:
            dept_row.is_active = False

    db.commit()

    return {
        "status": "success",
        "message": f"تم حذف ({val}) من القائمة بنجاح",
        **get_dynamic_lookups(db)
    }
