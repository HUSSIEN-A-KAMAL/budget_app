from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError
import uvicorn

from config import settings
from database import ensure_schema_up_to_date, verify_standalone_user
from seeds.seed_standalone_db import initialize_and_seed_standalone_db
from api.budget_routes import budget_router

BASE_DIR = Path(__file__).resolve().parent

# Initialize schema and seed standalone SQLite DB on startup
ensure_schema_up_to_date()
try:
    initialize_and_seed_standalone_db()
except Exception as _seed_err:
    print(f"[STARTUP SEED WARNING] {_seed_err}")

app = FastAPI(
    title=settings.APP_TITLE,
    description="Isolated Standalone Departmental Budget Allocation, Actual Spend & Savings Analytics System"
)

app.include_router(budget_router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get("access_token")
    if not token:
        auth_hdr = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_hdr and auth_hdr.startswith("Bearer "):
            token = auth_hdr
        else:
            return None
    try:
        if token.startswith("Bearer "):
            token = token.split(" ")[1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        emp_id = payload.get("sub")
        if emp_id is None:
            return None

        # Validate against standalone database to verify active user & fresh roles
        from database import SessionLocal
        from models.user import BudgetUser
        db = SessionLocal()
        try:
            db_user = db.get(BudgetUser, int(emp_id))
            if not db_user or not db_user.is_active:
                return None
            return {
                "emp_id": db_user.emp_id,
                "role": db_user.role,
                "name": db_user.name,
                "job_title": db_user.job_title or "",
                "department": db_user.general_dept_name or db_user.dept_name or "",
                "work_location": db_user.work_location or "",
                "phone": db_user.phone or "",
                "email": db_user.email or "",
            }
        finally:
            db.close()
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
async def root_redirect(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/budget-dashboard", status_code=303)


@app.get("/budget", response_class=HTMLResponse)
@app.get("/v2/budget", response_class=HTMLResponse)
@app.get("/budget-dashboard", response_class=HTMLResponse)
@app.get("/v2/budget-dashboard", response_class=HTMLResponse)
async def budget_dashboard_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("budget_dashboard.html", {
        "request": request,
        "user": user
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/budget-dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_class=HTMLResponse)
async def handle_login(
    request: Request,
    response: Response,
    emp_id: int = Form(...),
    password: str = Form(...)
):
    success, message, user_info = verify_standalone_user(emp_id, password)
    if not success or not user_info:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": message, "emp_id": emp_id}
        )

    token_data = {
        "sub": str(user_info["emp_id"]),
        "role": user_info["role"],
        "name": user_info["name"],
        "job_title": user_info["job_title"],
        "department": user_info["general_dept_name"] or user_info["dept_name"],
    }
    access_token = create_access_token(token_data)

    redirect_res = RedirectResponse(url="/budget-dashboard", status_code=303)
    redirect_res.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7
    )
    return redirect_res


@app.get("/logout")
async def logout_get():
    res = RedirectResponse(url="/login", status_code=303)
    res.delete_cookie("access_token")
    return res


@app.post("/api/auth/logout")
async def logout_api():
    res = JSONResponse(content={"message": "تم تسجيل الخروج بنجاح"})
    res.delete_cookie("access_token")
    return res


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
