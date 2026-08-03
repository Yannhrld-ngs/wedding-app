from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import store
from app.models import PresenceStatus
from app.security import (
    verify_password,
    create_session_token,
    get_current_organizer_login,
)
from app.config import SESSION_COOKIE_NAME

router = APIRouter(prefix="/organizer", tags=["organizers"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse("organizer_login.html", {"request": request})


@router.post("/login")
def login_submit(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    password_hash = store.get_organizer_password_hash(login)
    if not password_hash or not verify_password(password, password_hash):
        return templates.TemplateResponse(
            "organizer_login.html",
            {"request": request, "erreur": "Identifiants invalides"},
            status_code=401,
        )

    token = create_session_token(login)
    response = RedirectResponse(url="/organizer/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, httponly=True, samesite="lax", secure=False  # secure=True en prod (HTTPS)
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/organizer/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/dashboard")
def dashboard(
    request: Request,
    login: str = Depends(get_current_organizer_login),
):
    invites = store.list_guests()
    total = len(invites)
    presents_prevus = sum(1 for i in invites if i.statut_presence == PresenceStatus.present)
    checked_in = sum(1 for i in invites if i.checked_in)

    return templates.TemplateResponse(
        "organizer_dashboard.html",
        {
            "request": request,
            "invites": invites,
            "total": total,
            "presents_prevus": presents_prevus,
            "checked_in": checked_in,
            "organizer_login": login,
        },
    )


@router.get("/scan")
def scan_page(request: Request, login: str = Depends(get_current_organizer_login)):
    return templates.TemplateResponse("organizer_scan.html", {"request": request})


@router.post("/scan")
def scan_checkin(
    request: Request,
    login: str = Depends(get_current_organizer_login),
    qr_uuid: str = Form(...),
):
    invite = store.get_by_qr_uuid(qr_uuid)
    if not invite:
        return JSONResponse({"success": False, "message": "QR code inconnu"}, status_code=404)

    if invite.checked_in:
        return JSONResponse(
            {
                "success": False,
                "message": f"{invite.prenom} {invite.nom} a déjà été {invite.accord('validé', 'validée')} à {invite.checked_in_at.strftime('%H:%M')}",
            },
            status_code=409,
        )

    invite.checked_in = True
    invite.checked_in_at = datetime.utcnow()
    invite.checked_in_by = login
    store.save_guest(invite)

    return JSONResponse(
        {"success": True, "message": f"{invite.prenom} {invite.nom} {invite.accord('validé', 'validée')} ✓"}
    )
