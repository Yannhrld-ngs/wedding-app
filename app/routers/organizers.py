from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import store, config
from app.mailer import send_email
from app.models import OuiNon
from app.security import (
    verify_password,
    hash_password,
    create_session_token,
    create_password_reset_token,
    read_password_reset_token,
    get_current_organizer_login,
)
from app.config import SESSION_COOKIE_NAME

router = APIRouter(prefix="/organisateur", tags=["organizers"])
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
    response = RedirectResponse(url="/organisateur/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, httponly=True, samesite="lax", secure=False  # secure=True en prod (HTTPS)
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/organisateur/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/request-password-reset")
def request_password_reset_form(request: Request):
    return templates.TemplateResponse("organizer_request_password_reset.html", {"request": request})


@router.post("/request-password-reset")
def request_password_reset_submit(request: Request, email: str = Form(...)):
    organizer = store.find_accepted_organizer_by_mail(email)

    if organizer:
        token = create_password_reset_token(organizer.mail)
        reset_link = f"{config.BASE_URL}/organisateur/reset-password/{token}"
        send_email(
            to=organizer.mail,
            subject=f"Créer votre mot de passe organisateur — {config.WEDDING_NAME1} & {config.WEDDING_NAME2}",
            body=(
                f"Bonjour {organizer.prenom} {organizer.nom},\n\n"
                "Cliquez sur ce lien pour créer (ou réinitialiser) votre mot de passe "
                f"organisateur. Le lien est valable 1 heure :\n\n{reset_link}\n"
                f"\n\n\n\nCeci est un mail automatique. Veuillez ne pas répondre."
            ),
        )

        return templates.TemplateResponse(
            "organizer_request_password_reset.html",
            {
                "request": request,
                "confirmation": "Un lien vient de vous être envoyé sur l'adresse email renseignée."
                "En cas de non réception veuillez patienter quelque secondes ou consulter vos SPAM",
                "test":True,
            },
        )
    else:
        return templates.TemplateResponse(
            "organizer_request_password_reset.html",
            {
                "request": request,
                "confirmation": "Vous ne figurez pas parmi les organisateurs.",
                "test":True,
            },
        )  

@router.get("/reset-password/{token}")
def reset_password_form(token: str, request: Request):
    is_mail_valid = read_password_reset_token(token)

    if not is_mail_valid:
        return templates.TemplateResponse(
            "organizer_reset_password.html",
            {"request": request, "invalide": True},
            status_code=400,
        )

    return templates.TemplateResponse(
        "organizer_reset_password.html",
        {"request": request, "token": token, "invalide": False, "inexist": False},
    )


@router.post("/reset-password/{token}")
def reset_password_submit(
    token: str,
    request: Request,
    password: str = Form(...),
    password_confirmation: str = Form(...),
):
    email = read_password_reset_token(token)
    if not email:
        return templates.TemplateResponse(
            "organizer_reset_password.html",
            {"request": request, "invalide": True},
            status_code=400,
        )

    if password != password_confirmation:
        return templates.TemplateResponse(
            "organizer_reset_password.html",
            {
                "request": request,
                "token": token,
                "invalide": False,
                "erreur": "Les mots de passe ne correspondent pas.",
            },
        )

    store.set_organizer_password(email, hash_password(password))
    return RedirectResponse(url="/organisateur/login?mot_de_passe_defini=1", status_code=303)


@router.get("/dashboard")
def dashboard(
    request: Request,
    login: str = Depends(get_current_organizer_login),
):
    invites = store.list_guests()
    total = len(invites)
    presents_mairie = sum(1 for i in invites if i.presence_mairie == OuiNon.oui)
    presents_reception = sum(1 for i in invites if i.presence_reception == OuiNon.oui)
    presents_after = sum(1 for i in invites if i.presence_after == OuiNon.oui)
    confirmed_mairie = sum(1 for i in invites if i.checked_in_mairie)
    confirmed_reception = sum(1 for i in invites if i.checked_in_reception)
    confirmed_after = sum(1 for i in invites if i.checked_in_after)

    organizer = store.find_accepted_organizer_by_mail(login)

    user_agent = request.headers.get("user-agent", "").lower()
    if any(kw in user_agent for kw in ["iphone", "ipad", "ipod"]):
        device = "ios"
    elif "android" in user_agent:
        device = "android"
    else:
        device = "other"

    return templates.TemplateResponse(
        "organizer_dashboard.html",
        {
            "request": request,
            "invites": invites,
            "wedding_name1": config.WEDDING_NAME1,
            "wedding_name2": config.WEDDING_NAME2,
            "domain": config.BASE_URL,
            "total": total,
            "presents_mairie": presents_mairie,
            "presents_reception": presents_reception,
            "presents_after": presents_after,
            "confirmed_mairie": confirmed_mairie,
            "confirmed_reception": confirmed_reception,
            "confirmed_after": confirmed_after,
            "organizer_login": login,
            "device":device,
            "organizer_name": f"{organizer.prenom} {organizer.nom}" if organizer else login,
            "organizer_role": organizer.role if organizer else None,
        },
    )


@router.get("/scan")
def scan_page(request: Request, login: str = Depends(get_current_organizer_login)):
    return templates.TemplateResponse("organizer_scan.html", {"request": request})


PHASE_LABELS = {"mairie": "la mairie", "reception": "la réception", "after": "l'after"}


@router.post("/scan")
def scan_checkin(
    request: Request,
    login: str = Depends(get_current_organizer_login),
    qr_uuid: str = Form(...),
    phase: str = Form(...),
):
    if phase not in PHASE_LABELS:
        return JSONResponse({"success": False, "message": "Phase inconnue"}, status_code=400)

    invite = store.get_by_qr_uuid(qr_uuid)
    if not invite:
        return JSONResponse({"success": False, "message": "QR code inconnu"}, status_code=404)

    already_at = getattr(invite, f"checked_in_{phase}_at")
    if already_at:
        return JSONResponse(
            {
                "success": False,
                "message": f"{invite.prenom} {invite.nom} a déjà été {invite.accord('validé', 'validée')} "
                f"pour {PHASE_LABELS[phase]} à {already_at.strftime('%H:%M')}",
            },
            status_code=409,
        )

    setattr(invite, f"checked_in_{phase}", True)
    setattr(invite, f"checked_in_{phase}_at", datetime.utcnow())
    setattr(invite, f"checked_in_{phase}_by", login)
    store.save_guest(invite)

    return JSONResponse(
        {
            "success": True,
            "message": f"{invite.prenom} {invite.nom} {invite.accord('validé', 'validée')} pour {PHASE_LABELS[phase]} ✓",
        }
    )
