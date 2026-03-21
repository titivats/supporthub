from typing import Optional

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def register_auth_user_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    User = ctx["User"]
    SECURE_COOKIES = ctx["SECURE_COOKIES"]
    SESSION_AGE = ctx["SESSION_AGE"]
    make_session_token = ctx["make_session_token"]
    sha256 = ctx["sha256"]
    verify_password = ctx["verify_password"]
    fmt_th = ctx["fmt_th"]
    _is_valid_manage_username = ctx["_is_valid_manage_username"]
    _is_valid_manage_password = ctx["_is_valid_manage_password"]
    _normalize_role = ctx["_normalize_role"]
    _require_admin_user = ctx["_require_admin_user"]

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        created = request.query_params.get("created") == "1"
        return templates.TemplateResponse("login.html", {"request": request, "error": None, "created": created})

    @app.post("/login")
    def do_login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
        user = db.query(User).filter(User.username == username.strip()).first()
        if not user or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "\u0e0a\u0e37\u0e48\u0e2d\u0e1c\u0e39\u0e49\u0e43\u0e0a\u0e49\u0e2b\u0e23\u0e37\u0e2d\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e44\u0e21\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07",
                    "created": False,
                },
                status_code=400,
            )
        token = make_session_token(user.username)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("session", token, httponly=True, samesite="lax", secure=SECURE_COOKIES, max_age=SESSION_AGE)
        return resp

    @app.get("/logout")
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie("session")
        return resp

    @app.get("/signup", response_class=HTMLResponse)
    def signup_page(request: Request):
        return templates.TemplateResponse("add_user.html", {"request": request, "error": None})

    @app.post("/signup")
    def do_signup(request: Request,
                  username: str = Form(...),
                  password: str = Form(...),
                  confirm_password: str = Form(...),
                  role: str = Form("Operator"),
                  db: Session = Depends(get_db)):
        username = username.strip()
        if not username or not password or not confirm_password:
            return templates.TemplateResponse("add_user.html", {"request": request, "error": "Please fill all required fields."}, status_code=400)
        if not _is_valid_manage_username(username):
            return templates.TemplateResponse("add_user.html", {"request": request, "error": "Username must be numbers only (exactly 6 digits)."}, status_code=400)
        if not _is_valid_manage_password(password) or not _is_valid_manage_password(confirm_password):
            return templates.TemplateResponse("add_user.html", {"request": request, "error": "Password must be up to 12 characters."}, status_code=400)
        if password != confirm_password:
            return templates.TemplateResponse("add_user.html", {"request": request, "error": "Password and Confirm Password do not match."}, status_code=400)
        if db.query(User).filter(User.username == username).first():
            return templates.TemplateResponse("add_user.html", {"request": request, "error": "Username already exists."}, status_code=400)
        role = _normalize_role(role, allow_admin=False) or "Operator"
        db.add(User(username=username, password_hash=sha256(password), role=role))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return templates.TemplateResponse("add_user.html", {"request": request, "error": "Username already exists."}, status_code=400)
        return RedirectResponse("/login?created=1", status_code=303)

    @app.get("/admin/users", response_class=HTMLResponse)
    def admin_users(request: Request, db: Session = Depends(get_db)):
        user = _require_admin_user(request, db)
        users = db.query(User).order_by(User.username.asc()).all()
        users_sorted = sorted(users, key=lambda u: (u.username.upper() != "ADMIN", u.username.lower()))
        pw_updated = request.query_params.get("pw_updated") == "1"
        return templates.TemplateResponse("manage_users.html", {
            "request": request, "me": user, "users": users_sorted, "pw_updated": pw_updated, "fmt_th": fmt_th,
        })

    @app.post("/admin/users/create")
    def admin_create_user(request: Request,
                          username: str = Form(...),
                          password: str = Form(...),
                          role: str = Form(...),
                          db: Session = Depends(get_db)):
        _require_admin_user(request, db)
        username = username.strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="invalid params")
        if not _is_valid_manage_username(username):
            raise HTTPException(status_code=400, detail="username must be numeric only and exactly 6 digits")
        if not _is_valid_manage_password(password):
            raise HTTPException(status_code=400, detail="password must be up to 12 characters")
        if db.query(User).filter(User.username == username).first():
            raise HTTPException(status_code=400, detail="duplicated")
        role = _normalize_role(role, allow_admin=True)
        if not role:
            raise HTTPException(status_code=400, detail="invalid role")
        u = User(username=username, password_hash=sha256(password), role=role)
        db.add(u)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="duplicated")
        return RedirectResponse("/admin/users", status_code=303)

    @app.post("/admin/users/update/{user_id}")
    def admin_update_user(user_id: int,
                          request: Request,
                          role: str = Form(...),
                          new_password: Optional[str] = Form(None),
                          db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="not found")
        if u.username.upper() == "ADMIN" and (me.username.upper() != "ADMIN"):
            raise HTTPException(status_code=403, detail="Cannot edit ADMIN")

        role = _normalize_role(role, allow_admin=True)
        if not role:
            raise HTTPException(status_code=400, detail="invalid role")
        u.role = role
        new_password_val = (new_password or "").strip()
        if new_password_val:
            if not _is_valid_manage_password(new_password_val):
                raise HTTPException(status_code=400, detail="password must be up to 12 characters")
            u.password_hash = sha256(new_password_val)
            db.add(u)
            db.commit()
            return RedirectResponse("/admin/users?pw_updated=1", status_code=303)

        db.add(u)
        db.commit()
        return RedirectResponse("/admin/users", status_code=303)

    @app.post("/admin/users/delete/{user_id}")
    def admin_delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
        _require_admin_user(request, db)
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="not found")
        if u.username.upper() == "ADMIN":
            raise HTTPException(status_code=400, detail="ADMIN cannot be deleted")
        db.delete(u)
        db.commit()
        return RedirectResponse("/admin/users", status_code=303)
