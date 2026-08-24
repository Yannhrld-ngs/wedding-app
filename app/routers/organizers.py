import json
import re
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import store, config, reset
from app.analytics import (
    chart_alcool,
    chart_ambiance,
    chart_logement,
    chart_presence,
    chart_restrictions,
    chart_scans_non_prevus,
    chart_transport,
    compute_alimentaire_analytics,
    compute_ambiance_analytics,
    compute_logement_analytics,
    compute_presence_analytics,
    compute_transport_analytics,
)
from app.config import PHASE_LABELS as CHART_PHASE_LABELS, RESTRICTION_LABELS, TRANSPORT_LABELS
from app.mailer import send_email
from app.models import OuiNon, PresenceAfter
from app.security import (
    verify_password,
    hash_password,
    create_session_token,
    create_password_reset_token,
    read_password_reset_token,
    get_current_organizer_login,
)
from app.config import SESSION_COOKIE_NAME

router = APIRouter(prefix="/16mesures/organisation", tags=["organizers"])
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
    response = RedirectResponse(url="/16mesures/organisation/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, httponly=True, samesite="lax", secure=False  # secure=True en prod (HTTPS)
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/16mesures/organisation/login", status_code=303)
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
        reset_link = f"{config.BASE_URL}/16mesures/organisation/reset-password/{token}"
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
            },
        )
    else:
        return templates.TemplateResponse(
            "organizer_request_password_reset.html",
            {
                "request": request,
                "confirmation": "Vous ne figurez pas parmi les organisateurs.",
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
        {"request": request, "token": token, "invalide": False},
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
    return RedirectResponse(url="/16mesures/organisation/login?mot_de_passe_defini=1", status_code=303)


@router.get("/dashboard")
def dashboard(
    request: Request,
    login: str = Depends(get_current_organizer_login),
):
    invites = store.list_guests()
    total = len(invites)
    #presents_mairie = sum(1 for i in invites if i.presence_mairie == OuiNon.oui)
    #presents_reception = sum(1 for i in invites if i.presence_reception == OuiNon.oui)
    #presents_after = sum(1 for i in invites if i.presence_after == PresenceAfter.oui)
    #confirmed_mairie = sum(1 for i in invites if i.checked_in_mairie)
    #confirmed_reception = sum(1 for i in invites if i.checked_in_reception)
    #confirmed_after = sum(1 for i in invites if i.checked_in_after)

    organizer = store.find_accepted_organizer_by_mail(login)
    
    return templates.TemplateResponse(
        "organizer_dashboard.html",
        {
            "request": request,
            "invites": invites,
            "total": total,
            "presents_after": 1,
            "confirmed_mairie": 1,
            "confirmed_reception": 1,
            "confirmed_after": 1,
            "organizer_login": login,
            "organizer_name": f"{organizer.prenom} {organizer.nom}" if organizer else login,
            "organizer_role": organizer.role if organizer else None,
            "phase_labels": None,
            "restriction_labels": None,
            "transport_labels": None,
        },
    )

@router.post("/place/{token}")
def update_place(
    token: str,
    place_mairie: str = Form(""),
    place_reception: str = Form(""),
    place_after: str = Form(""),
    login: str = Depends(get_current_organizer_login),
):
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invité introuvable")

    invite.place_mairie = place_mairie.strip() or None
    invite.place_reception = place_reception.strip() or None
    invite.place_after = place_after.strip() or None
    store.save_guest(invite)

    return RedirectResponse(url="/16mesures/organisation/dashboard", status_code=303)


_PLACE_RE = re.compile(r"^(.*) #(\d+)$")


def _group_places(invites: list, place_attr: str) -> list[dict]:
    """Reconstruit les repères (ex. "Table 1" -> [token1, token2, ...]) à
    partir des places déjà enregistrées, pour préremplir l'éditeur."""
    groups: dict[str, list[tuple[int, str]]] = {}
    for invite in invites:
        value = getattr(invite, place_attr)
        match = _PLACE_RE.match(value) if value else None
        if not match:
            continue
        groups.setdefault(match.group(1), []).append((int(match.group(2)), invite.token))

    return [
        {"repere": repere, "tokens": [token for _, token in sorted(entries)]}
        for repere, entries in sorted(groups.items())
    ]


@router.get("/choix-des-places")
def choix_des_places_form(request: Request, login: str = Depends(get_current_organizer_login)):
    invites = store.list_guests()

    def as_options(filtered: list) -> list[dict]:
        return [{"token": i.token, "nom": f"{i.prenom} {i.nom}"} for i in filtered]

    invites_mairie = [i for i in invites if i.presence_mairie == OuiNon.oui]
    invites_reception = [i for i in invites if i.presence_reception == OuiNon.oui]
    invites_after = [i for i in invites if i.presence_after == PresenceAfter.oui]

    return templates.TemplateResponse(
        "organizer_choix_des_places.html",
        {
            "request": request,
            "guests_mairie": as_options(invites_mairie),
            "guests_reception": as_options(invites_reception),
            "guests_after": as_options(invites_after),
            "groups_mairie": _group_places(invites, "place_mairie"),
            "groups_reception": _group_places(invites, "place_reception"),
            "groups_after": _group_places(invites, "place_after"),
        },
    )


@router.post("/choix-des-places")
def choix_des_places_submit(
    data_mairie: str = Form("[]"),
    data_reception: str = Form("[]"),
    data_after: str = Form("[]"),
    login: str = Depends(get_current_organizer_login),
):
    raw_by_phase = {"mairie": data_mairie, "reception": data_reception, "after": data_after}
    invites = store.list_guests()

    for phase, raw in raw_by_phase.items():
        try:
            groups = json.loads(raw)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Données invalides")

        place_by_token = {}
        for group in groups:
            repere = (group.get("repere") or "").strip()
            if not repere:
                continue
            for i, token in enumerate(group.get("tokens") or []):
                place_by_token[token] = f"{repere} #{i + 1}"

        attr = f"place_{phase}"
        for invite in invites:
            new_value = place_by_token.get(invite.token)
            if getattr(invite, attr) != new_value:
                setattr(invite, attr, new_value)
                store.save_guest(invite)

    return RedirectResponse(url="/16mesures/organisation/choix-des-places", status_code=303)


@router.get("/reinitialiser")
def reinitialiser_confirm(request: Request, login: str = Depends(get_current_organizer_login)):
    return templates.TemplateResponse("organizer_reinit_poll.html", {"request": request})


@router.post("/reinitialiser")
def reinitialiser_submit(request: Request, login: str = Depends(get_current_organizer_login)):
    reset._reset_yaml_file(config.GUESTS_LOG_PATH)
    return RedirectResponse(url="/16mesures/organisation/dashboard", status_code=303)


@router.get("/info-pratiques")
def info_pratiques(request: Request, login: str = Depends(get_current_organizer_login)):
    return templates.TemplateResponse(
        "organizer_info_pratiques.html",
        {
            "request": request,
            "planning": config.PLANNING,
            "organizers": store.accepted_organizers(),
        },
    )


@router.get("/statistiques-detaillees")
def statistiques_detaillees(request: Request, login: str = Depends(get_current_organizer_login)):
    invites = store.list_guests()

    presence = compute_presence_analytics(invites)
    alimentaire = compute_alimentaire_analytics(invites)
    transport = compute_transport_analytics(invites)
    logement = compute_logement_analytics(invites)
    ambiance = compute_ambiance_analytics(invites)

    charts = {
        "presence": chart_presence(presence).to_dict(),
        "scans_non_prevus": chart_scans_non_prevus(presence).to_dict(),
        "restrictions": chart_restrictions(alimentaire).to_dict(),
        "alcool": chart_alcool(alimentaire).to_dict(),
        "transport": chart_transport(transport).to_dict(),
        "logement": chart_logement(logement).to_dict(),
        "ambiance": chart_ambiance(ambiance).to_dict(),
    }

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "presence": presence,
            "alimentaire": alimentaire,
            "transport": transport,
            "logement": logement,
            "ambiance": ambiance,
            "charts": charts,
            "generated_at": datetime.now().strftime("%H:%M:%S"),
        },
    )


@router.get("/envoyer/{token}")
def envoyer_confirm(token: str, request: Request, login: str = Depends(get_current_organizer_login)):
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invité introuvable")
    return templates.TemplateResponse("organizer_send_invit.html", {"request": request, "invite": invite})


@router.post("/envoyer/{token}")
def envoyer_submit(
    token: str,
    request: Request,
    canal: str = Form(...),
    login: str = Depends(get_current_organizer_login),
):
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invité introuvable")

    message = (
        f"Bonjour {invite.prenom} {invite.nom},\n\n"
        f"Veuillez trouver votre invitation en consultant la page {config.BASE_URL}\n"
        f"Votre code invité est : {invite.token[-4:].upper()}\n\n"
        "N'oubliez pas de confirmer votre présence en répondant au sondage.\n\n"
        f"En espérant vous revoir bientôt, \n{config.WEDDING_NAME1} & {config.WEDDING_NAME2}\n"
        "Dieu vous garde."
    )
    contact = invite.contact or ""

    if canal == "whatsapp":
        url = f"https://wa.me/{contact}?text={quote(message)}"
    elif canal == "mail":
        url = f"mailto:{invite.mail or ''}?body={quote(message)}"
    elif canal == "sms":
        user_agent = request.headers.get("user-agent", "").lower()
        sep = "?" if "android" in user_agent else "&"
        url = f"sms:{contact}{sep}body={quote(message)}"
    else:
        raise HTTPException(status_code=400, detail="Canal inconnu")

    return RedirectResponse(url=url, status_code=303)

@router.get("/scan")
def scan_page(request: Request, login: str = Depends(get_current_organizer_login)):
    return templates.TemplateResponse(
        "organizer_scan.html", {"request": request, "phase_labels": CHART_PHASE_LABELS}
    )


PHASE_LABELS = {"mairie": "la mairie", "reception": "la réception", "after": "la soirée"}

# Places associées à chaque phase de scan (voir Invite.place_*).
PHASE_PLACES = {
    "mairie": [("place_mairie", "la mairie")],
    "reception": [("place_reception", "la réception")],
    "after": [("place_after", "la soirée")],
}


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
                f"pour {PHASE_LABELS[phase]} à {already_at.strftime('%H:%M')}. La place attribuée est: {getattr(invite,PHASE_PLACES[phase][0][0])}",
            },
            status_code=409,
        )

    setattr(invite, f"checked_in_{phase}", True)
    setattr(invite, f"checked_in_{phase}_at", datetime.utcnow())
    setattr(invite, f"checked_in_{phase}_by", login)
    store.save_guest(invite)

    message = f"{invite.prenom} {invite.nom} {invite.accord('validé', 'validée')} pour {PHASE_LABELS[phase]} ✓"
    for attr, label in PHASE_PLACES[phase]:
        message += f" — Votre place à {label} est : {getattr(invite, attr) or 'non attribuée'}"

    return JSONResponse({"success": True, "message": message})
