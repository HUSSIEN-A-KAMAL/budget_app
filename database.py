from typing import Generator, Dict, List, Optional, Tuple, Any
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from werkzeug.security import generate_password_hash, check_password_hash
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

@event.listens_for(engine, "connect")
def _enable_sqlite_fks(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_schema_up_to_date():
    """
    Creates all SQLite tables for the standalone Budget & Savings Analytics app
    and safely applies schema migrations for newly added columns.
    """
    import models  # noqa: F401
    from models.base import Base
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)

    # Safe SQLite column migration for users table
    with engine.connect() as conn:
        try:
            existing_cols = {
                row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
            }
            if "work_location" not in existing_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN work_location VARCHAR(120)"))
            if "phone" not in existing_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(50)"))
            if "email" not in existing_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(120)"))
            conn.commit()
        except Exception as _mig_err:
            print(f"[SCHEMA MIGRATION WARNING] {_mig_err}")


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a SQLAlchemy session connected to budget_standalone.db.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_all_general_departments(db: Optional[Session] = None) -> List[str]:
    """
    Returns all unique general departments from the standalone SQLite database
    (SystemLookupOption + GeneralDepartmentLookup + DepartmentBudget + BudgetUser).
    """
    from models.user import GeneralDepartmentLookup, BudgetUser, SystemLookupOption
    from models.budget import DepartmentBudget

    close_after = False
    if db is None:
        db = SessionLocal()
        close_after = True
    try:
        depts = set()
        for (val,) in db.query(SystemLookupOption.value).filter(
            SystemLookupOption.category == "DEPARTMENT",
            SystemLookupOption.is_active == True
        ).all():
            if val and str(val).strip():
                depts.add(str(val).strip())
        for (name,) in db.query(GeneralDepartmentLookup.name).filter(GeneralDepartmentLookup.is_active == True).all():
            if name and str(name).strip():
                depts.add(str(name).strip())
        for (name,) in db.query(DepartmentBudget.general_dept_name).distinct().all():
            if name and str(name).strip():
                depts.add(str(name).strip())
        for (name,) in db.query(BudgetUser.general_dept_name).distinct().all():
            if name and str(name).strip():
                depts.add(str(name).strip())
        return sorted(list(depts))
    finally:
        if close_after:
            db.close()


def get_dynamic_lookups(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Returns dynamic admin-controlled lookup lists for:
    - Departments (DEPARTMENT)
    - Sub-Departments (SUB_DEPARTMENT)
    - Work Locations (WORK_LOCATION)
    - Job Titles (JOB_TITLE)
    - Job Roles / RBAC (ROLE)
    """
    from models.user import SystemLookupOption, BudgetUser

    close_after = False
    if db is None:
        db = SessionLocal()
        close_after = True
    try:
        rows = db.query(SystemLookupOption).filter(SystemLookupOption.is_active == True).order_by(
            SystemLookupOption.category, SystemLookupOption.value
        ).all()

        depts = set(get_all_general_departments(db))
        sub_depts = set()
        locs = set()
        titles = set()
        roles = set()
        raw_items = []

        for r in rows:
            val_clean = (r.value or "").strip()
            if not val_clean:
                continue
            raw_items.append({
                "id": r.id,
                "category": r.category,
                "value": val_clean,
                "is_active": r.is_active
            })
            if r.category == "DEPARTMENT":
                depts.add(val_clean)
            elif r.category == "SUB_DEPARTMENT":
                sub_depts.add(val_clean)
            elif r.category == "WORK_LOCATION":
                locs.add(val_clean)
            elif r.category == "JOB_TITLE":
                titles.add(val_clean)
            elif r.category == "ROLE":
                roles.add(val_clean)

        # Enrich with any existing distinct values on users
        for (sd,) in db.query(BudgetUser.dept_name).distinct().all():
            if sd and str(sd).strip():
                sub_depts.add(str(sd).strip())
        for (loc,) in db.query(BudgetUser.work_location).distinct().all():
            if loc and str(loc).strip():
                locs.add(str(loc).strip())
        for (jt,) in db.query(BudgetUser.job_title).distinct().all():
            if jt and str(jt).strip():
                titles.add(str(jt).strip())
        for (rl,) in db.query(BudgetUser.role).distinct().all():
            if rl and str(rl).strip():
                roles.add(str(rl).strip())

        return {
            "departments": sorted(list(depts)),
            "sub_departments": sorted(list(sub_depts)),
            "work_locations": sorted(list(locs)),
            "job_titles": sorted(list(titles)),
            "roles": sorted(list(roles)),
            "options": raw_items,
        }
    finally:
        if close_after:
            db.close()


def get_employee_names_map(db: Optional[Session] = None) -> Dict[int, str]:
    """
    Returns {emp_id: name} from the standalone SQLite users table.
    """
    from models.user import BudgetUser

    close_after = False
    if db is None:
        db = SessionLocal()
        close_after = True
    try:
        rows = db.query(BudgetUser.emp_id, BudgetUser.name).all()
        return {int(eid): (name or f"موظف {eid}") for eid, name in rows if eid is not None}
    finally:
        if close_after:
            db.close()


def verify_standalone_user(emp_id: int, password: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Verifies user credentials against the standalone SQLite users table.
    Supports hashed passwords (werkzeug) or initial first-time password setup if 'UNREGISTERED'.
    """
    from models.user import BudgetUser

    db = SessionLocal()
    try:
        user = db.get(BudgetUser, int(emp_id))
        if not user:
            return False, "الرقم الوظيفي غير مسجل في قاعدة بيانات نظام الموازنة المستقل", None

        if user.password_hash == "UNREGISTERED":
            user.password_hash = generate_password_hash(password)
            db.commit()
            db.refresh(user)
        elif not check_password_hash(user.password_hash, password):
            return False, "كلمة المرور غير صحيحة", None

        return True, "تم تسجيل الدخول بنجاح", {
            "emp_id": user.emp_id,
            "name": user.name,
            "role": user.role,
            "general_dept_name": user.general_dept_name or "",
            "dept_name": user.dept_name or "",
            "job_title": user.job_title or "",
            "work_location": user.work_location or "",
            "phone": user.phone or "",
            "email": user.email or "",
        }
    finally:
        db.close()
