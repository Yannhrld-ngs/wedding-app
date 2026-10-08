import json
import logging
import re
import os
import random
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Form, UploadFile
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile as StarletteUploadFile  # the class FastAPI actually passes
from app.database import SqlRepository  
from uuid import uuid4
from app import store, config, reset, storage
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
from app.models import (
    Invite,
    Prestataire,
    QuizCreator,
    QuizSession,
    QuizReponse,
    DefiCreator,
    DefiTirage,
    PlanningEvent,
    PlanningDiscours,
    PlanningPhoto,
    MOMENTS_MARIAGE,
    OuiNon,
    PresenceAfter,
    Sexe,
    generate_invite_token,
    generate_qr_uuid,
    natural_key,
    slugify,
)
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
logger = logging.getLogger(__name__)


# ---------- Accès par rôle ----------
ROLES_ANIMATION = ("admin", "mc", "acceuil", "media")
ROLES_SCAN = ("admin", "acceuil")

def _role_organisateur(login: str):
    organizer = store.find_accepted_organizer_by_mail(login)
    return organizer.role if organizer else None

def _role_requis(*roles: str):
    """Dependency: logged-in organizer whose role is in roles, else back to the dashboard. Returns the role."""
    def verifier(login: str = Depends(get_current_organizer_login)) -> str:
        role = _role_organisateur(login)
        if role not in roles:
            raise HTTPException(status_code=303, headers={"Location": "/organisateur/dashboard"})
        return role
    return verifier

acces_animation = _role_requis(*ROLES_ANIMATION)
acces_admin = _role_requis("admin")  # adding guests, editing quiz questions and challenges
acces_scan = _role_requis(*ROLES_SCAN)


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "dashboard/organizer_login.html", {"request": request})


@router.post("/login")
def login_submit(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    password_hash = store.get_organizer_password_hash(login)
    if not password_hash or not verify_password(password, password_hash):
        return templates.TemplateResponse(
            request, "dashboard/organizer_login.html",
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
    return templates.TemplateResponse(request, "dashboard/organizer_request_password_reset.html", {"request": request})


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
            request, "dashboard/organizer_request_password_reset.html",
            {
                "request": request,
                "confirmation": "Un lien vient de vous être envoyé sur l'adresse email renseignée."
                "En cas de non réception veuillez patienter quelque secondes ou consulter vos SPAM",
            },
        )
    else:
        return templates.TemplateResponse(
            request, "dashboard/organizer_request_password_reset.html",
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
            request, "dashboard/organizer_reset_password.html",
            {"request": request, "invalide": True},
            status_code=400,
        )

    return templates.TemplateResponse(
        request, "dashboard/organizer_reset_password.html",
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
            request, "dashboard/organizer_reset_password.html",
            {"request": request, "invalide": True},
            status_code=400,
        )

    if password != password_confirmation:
        return templates.TemplateResponse(
            request, "dashboard/organizer_reset_password.html",
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
    #actualize QR after false delete
    for inv in invites:
        if not os.path.exists(store.qr_code_path(inv)):
            store._write_qr_file(inv) 

    total = len(invites)
    presents_mairie = sum(1 for i in invites if i.presence_mairie == OuiNon.oui)
    presents_reception = sum(1 for i in invites if i.presence_reception == OuiNon.oui)
    presents_after = sum(1 for i in invites if i.presence_after == PresenceAfter.oui)
    confirmed_mairie = sum(1 for i in invites if i.checked_in_mairie)
    confirmed_reception = sum(1 for i in invites if i.checked_in_reception)
    confirmed_after = sum(1 for i in invites if i.checked_in_after)

    organizer = store.find_accepted_organizer_by_mail(login)

    return templates.TemplateResponse(
        request, "dashboard/organizer_dashboard.html",
        {
            "request": request,
            "invites": invites,
            "get_by_token":store.get_by_token,
            "total": total,
            "presents_mairie": presents_mairie,
            "presents_reception": presents_reception,
            "presents_after": presents_after,
            "confirmed_mairie": confirmed_mairie,
            "confirmed_reception": confirmed_reception,
            "confirmed_after": confirmed_after,
            "organizer_login": login,
            "organizer_name": f"{organizer.prenom} {organizer.nom}" if organizer else login,
            "organizer_role": organizer.role if organizer else None,
            "phase_labels": CHART_PHASE_LABELS,
            "restriction_labels": RESTRICTION_LABELS,
            "transport_labels": TRANSPORT_LABELS,
        },
    )

def _make_invite_token(invite: Invite) -> str:
    suffix = generate_invite_token(
        invite.prenom, invite.nom, invite.categorie, config.WEDDING_NAME1, config.WEDDING_DATE
    )
    return suffix


@router.get("/ajouter-invité")
def invite_add(request: Request, nb: int = 0, role: str = Depends(acces_admin)):
    nb_accompagnateurs = max(0, min(nb, 50))
    all_invite = store.list_guests()

    if len(all_invite) > 65:
            return templates.TemplateResponse(
        request, "invite/invite_add.html",
        {
            "request": request,
            "full": True,
            "nb_accompagnateurs": nb_accompagnateurs,
        },
            )

    qp = request.query_params

    def _padded(values: list[str]) -> list[str]:
        values = list(values)[:nb_accompagnateurs]
        values += [""] * (nb_accompagnateurs - len(values))
        return values

    form_data = {
        "prenom": qp.get("prenom", ""),
        "nom": qp.get("nom", ""),
        "email": qp.get("email", ""),
        "telephone": qp.get("telephone", ""),
        "sexe": qp.get("sexe", ""),
        "categorie": qp.get("categorie", ""),
        "role": qp.get("role", ""),
        "accompagnateur_prenom": _padded(qp.getlist("accompagnateur_prenom")),
        "accompagnateur_nom": _padded(qp.getlist("accompagnateur_nom")),
        "accompagnateur_sexe": _padded(qp.getlist("accompagnateur_sexe")),
    }

    return templates.TemplateResponse(
        request, "invite/invite_add.html",
        {
            "request": request,
            "merci": bool(qp.get("merci")),
            "nb_accompagnateurs": nb_accompagnateurs,
            "form_data": form_data,
        },
    )

@router.post("/ajouter-invité")
def invite_submit(
    request: Request,
    prenom: str = Form(""),
    nom: str = Form(""),
    email: str = Form(""),
    telephone: str = Form(""),
    sexe: str = Form(""),
    categorie: str = Form(""),
    role: str = Form(""),
    force: str = Form(""),
    accompagnateur_prenom: list[str] = Form([]),
    accompagnateur_nom: list[str] = Form([]),
    accompagnateur_sexe: list[str] = Form([]),
    organisateur_role: str = Depends(acces_admin),  # "role" is already the guest's role field
):
    prenom = prenom.strip()
    nom = nom.strip()
    email = email.strip()

    if not prenom or not nom or not sexe or not categorie:
        return templates.TemplateResponse(
            request, "invite/invite_add.html",
            {
                "request": request,
                "error": "Merci de remplir tous les champs obligatoires.",
                "nb_accompagnateurs": len(accompagnateur_prenom),
                "form_data": {
                    "prenom": prenom,
                    "nom": nom,
                    "email": email,
                    "telephone": telephone,
                    "sexe": sexe,
                    "categorie": categorie,
                    "role": role,
                    "accompagnateur_prenom": accompagnateur_prenom,
                    "accompagnateur_nom": accompagnateur_nom,
                    "accompagnateur_sexe": accompagnateur_sexe,
                },
            },
        )

    existing = store.find_by_email(email)
    if existing and not force:
        return templates.TemplateResponse(
            request, "invite/invite_add.html",
            {
                "request": request,
                "duplicate": True,
                "form_data": {
                    "prenom": prenom,
                    "nom": nom,
                    "email": email,
                    "telephone": telephone,
                    "sexe": sexe,
                    "categorie": categorie,
                    "role": role,
                    "accompagnateur_prenom": accompagnateur_prenom,
                    "accompagnateur_nom": accompagnateur_nom,
                    "accompagnateur_sexe": accompagnateur_sexe,
                },
            },
        )

    if existing and force:
        store.delete_guest(existing.token)

    invite = Invite(
        prenom=prenom,
        nom=nom,
        token="",
        qr_uuid=generate_qr_uuid(),
        sexe=Sexe(sexe),
        categorie=categorie,
        role=role.strip() or None,
        mail=email or None,
        contact=telephone.strip() or None,
    )
    invite.token = _make_invite_token(invite)
    accompagnateur_tokens = []
    for comp_prenom, comp_nom, comp_sexe in zip(
        accompagnateur_prenom, accompagnateur_nom, accompagnateur_sexe
    ):
        comp_prenom = comp_prenom.strip()
        comp_nom = comp_nom.strip()
        if not comp_prenom or not comp_nom:
            continue
        companion = Invite(
            prenom=comp_prenom,
            nom=comp_nom,
            token="",
            qr_uuid=generate_qr_uuid(),
            sexe=Sexe(comp_sexe) if comp_sexe in ("homme", "femme") else Sexe.homme,
            categorie=f"accompagnant - {invite.categorie}",
            mail=None,
            contact=None,
        )
        companion.token = _make_invite_token(companion)
        store._write_qr_file(companion)
        store.save_guest(companion)
        accompagnateur_tokens.append(companion.token)

    if accompagnateur_tokens:
        invite.accompagnateur = ",".join(accompagnateur_tokens)

    store._write_qr_file(invite)
    store.save_guest(invite)    

    return RedirectResponse(url="/organisateur/dashboard", status_code=303)


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

    return RedirectResponse(url="/organisateur/dashboard", status_code=303)


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
    notes = store.get_repere_notes()

    def as_options(filtered: list) -> list[dict]:
        return [{"token": i.token, "nom": f"{i.prenom} {i.nom}"} for i in filtered]

    def with_notes(groups: list[dict], phase: str) -> list[dict]:
        phase_notes = notes.get(phase, {})
        return [dict(g, note=phase_notes.get(g["repere"], "")) for g in groups]

    invites_mairie = [i for i in invites if i.presence_mairie == OuiNon.oui]
    invites_reception = [i for i in invites if i.presence_reception == OuiNon.oui]
    invites_after = [i for i in invites if i.presence_after == PresenceAfter.oui]

    return templates.TemplateResponse(
        request, "dashboard/organizer_choix_des_places.html",
        {
            "request": request,
            "guests_mairie": as_options(invites_mairie),
            "guests_reception": as_options(invites_reception),
            "guests_after": as_options(invites_after),
            "groups_mairie": with_notes(_group_places(invites, "place_mairie"), "mairie"),
            "groups_reception": with_notes(_group_places(invites, "place_reception"), "reception"),
            "groups_after": with_notes(_group_places(invites, "place_after"), "after"),
        },
    )


@router.get("/choix-des-places/repartition/{phase}")
def repartition(phase: str, request: Request, login: str = Depends(get_current_organizer_login)):
    if phase not in config.PHASES:
        raise HTTPException(status_code=404, detail="Phase inconnue")

    invites = store.list_guests()
    token_to_nom = {i.token: f"{i.prenom} {i.nom}" for i in invites}
    phase_notes = store.get_repere_notes().get(phase, {})

    raw_groups = _group_places(invites, f"place_{phase}")
    groups = [
        {
            "repere": g["repere"],
            "noms": [token_to_nom.get(t, t) for t in g["tokens"]],
            "note": phase_notes.get(g["repere"], ""),
        }
        for g in raw_groups
    ]

    presence_attr = "presence_after" if phase == "after" else f"presence_{phase}"
    expected_value = PresenceAfter.oui if phase == "after" else OuiNon.oui
    placed_tokens = {t for g in raw_groups for t in g["tokens"]}
    sans_repere = [
        f"{i.prenom} {i.nom}"
        for i in invites
        if getattr(i, presence_attr) == expected_value and i.token not in placed_tokens
    ]

    return templates.TemplateResponse(
        request, "invite/invite_repartition.html",
        {
            "request": request,
            "phase": phase,
            "phase_label": CHART_PHASE_LABELS[phase],
            "groups": groups,
            "sans_repere": sans_repere,
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
    notes_by_phase = {}

    for phase, raw in raw_by_phase.items():
        try:
            groups = json.loads(raw)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Données invalides")

        place_by_token = {}
        phase_notes = {}
        for group in groups:
            repere = (group.get("repere") or "").strip()
            if not repere:
                continue
            note = (group.get("note") or "").strip()
            if note:
                phase_notes[repere] = note
            for i, token in enumerate(group.get("tokens") or []):
                place_by_token[token] = f"{repere} #{i + 1}"
        notes_by_phase[phase] = phase_notes

        attr = f"place_{phase}"
        for invite in invites:
            new_value = place_by_token.get(invite.token)
            if getattr(invite, attr) != new_value:
                setattr(invite, attr, new_value)
                store.save_guest(invite)

    store.save_repere_notes(notes_by_phase)

    return RedirectResponse(url="/organisateur/choix-des-places", status_code=303)

@router.get("/reinitialiser")
def reinitialiser_confirm(request: Request, login: str = Depends(get_current_organizer_login)):
    return templates.TemplateResponse(request, "dashboard/organizer_reinit_poll.html", {"request": request})

@router.post("/reinitialiser")
def reinitialiser_submit(request: Request, login: str = Depends(get_current_organizer_login)):
    reset._reset_qr_codes(which="all") #reset QR codes
    SqlRepository(
        config.engine 
    ).delete_all(table_name="guests") 
    return RedirectResponse(url="/organisateur/dashboard", status_code=303)

# "Planning discours" and "Planning photos" share the same shape: a moment of the
# day (fixed list), a category typed by the organizer, and several guests added
# one by one. "choix"/"personnes" are the model's field names for those.
PLANNINGS_INVITES = {
    "discours": {"model": PlanningDiscours, "table": "planning_discours", "choix": "moment", "personnes": "orateurs"},
    "photos": {"model": PlanningPhoto, "table": "planning_photos", "choix": "lieu", "personnes": "invites"},
}


def _split_noms(value: str | None) -> list[str]:
    return [n for n in (value or "").split(", ") if n]


@router.get("/info-pratiques")
def info_pratiques(request: Request, login: str = Depends(get_current_organizer_login)):
    db = SqlRepository(config.engine)
    
    #Planning data
    db.create(obj=PlanningEvent, table_name="detailed_planning", primary_key="moment")
    data = db.load(PlanningEvent, table_name="detailed_planning") 
    planning = [d.__dict__ for d in data]

    # Contact data
    db.create(obj=Prestataire, table_name="prestataires", primary_key="contact")
    data = db.load(Prestataire, table_name="prestataires") 
    prestataires = [d.__dict__ for d in data]

    # Discours / photos data, in the order of the day (Mairie → Bénédiction → Soirée)
    plannings_invites = {}
    for section, cfg in PLANNINGS_INVITES.items():
        db.create(obj=cfg["model"], table_name=cfg["table"], primary_key="id")
        rows = [
            {
                "id": r.id,
                "choix": getattr(r, cfg["choix"]),
                "categorie": r.categorie,
                "personnes": _split_noms(getattr(r, cfg["personnes"])),
            }
            for r in db.load(cfg["model"], table_name=cfg["table"])
        ]
        rows.sort(key=lambda x: (MOMENTS_MARIAGE.index(x["choix"]) if x["choix"] in MOMENTS_MARIAGE else len(MOMENTS_MARIAGE), x["categorie"]))
        plannings_invites[section] = {
            "rows": rows,
            # Row being built (see planning_invites)
            "draft": {
                "choix": request.query_params.get(f"{section}_choix", ""),
                "categorie": request.query_params.get(f"{section}_categorie", ""),
                "personnes": request.query_params.getlist(f"{section}_personnes"),
            },
        }

    return templates.TemplateResponse(
        request, "dashboard/organizer_info_pratiques.html",
        {
            "request": request,
            "planning": sorted(planning, key=lambda x: x['heure']),
            "prestataires": sorted(prestataires, key=lambda x: x['nom']),
            "plannings_invites": plannings_invites,
            "moments_mariage": MOMENTS_MARIAGE,
            "guests": store.list_guests(),
            "organizers": store.accepted_organizers(),
            "current_organizer": store.find_accepted_organizer_by_mail(login),
        },
    )


@router.post("/info-pratiques/planning-detaillé")
def detailed_planning(
    heure: str = Form(""),
    moment: str = Form(""),
    responsable: str = Form(""),
    notes: str = Form(""),
    add: str | None = Form(None),
    delete: str | None = Form(None),
    checkbox: str | None = Form(None),
):
    db = SqlRepository(config.engine)
    table = db.create(obj=PlanningEvent, table_name="detailed_planning", primary_key="moment")
    data = db.load(PlanningEvent, table_name="detailed_planning")
    
    if delete is not None:
        to_delete = next((e for e in data if e.moment == delete), None)
        db.delete(to_delete, table, primary_key="moment")
    
    if add: 
        to_add = PlanningEvent(done=0, heure=heure, moment=moment, responsable=responsable, notes=notes)
        db.insert(to_add, table=table)

    if checkbox: 
        to_check = next((e for e in data if e.moment == checkbox), None)
        to_check.done = 1 if to_check.done == 0 else 0
        db.update(to_check, table=table, primary_key="moment")
    return RedirectResponse(url="/organisateur/info-pratiques#planning", status_code=303)

@router.post("/info-pratiques/contacts")
def prestataires_contact(
    nom: str = Form(""),
    categorie: str = Form(""),
    contact: str = Form(""),
    add: str | None = Form(None),
    delete: str | None = Form(None),
):
    db = SqlRepository(config.engine)
    table = db.create(obj=Prestataire, table_name="prestataires", primary_key="contact")
    data = db.load(Prestataire, table_name="prestataires")

    if delete is not None:
        to_delete = next((e for e in data if e.contact == delete), None)
        db.delete(to_delete, table, primary_key="contact")
    
    if add: 
        to_add = Prestataire(nom=nom, categorie=categorie, contact=contact)
        db.insert(to_add, table=table)
    return RedirectResponse(url="/organisateur/info-pratiques#contacts", status_code=303)

@router.post("/info-pratiques/invites/{section}")
async def planning_invites(
    section: str,
    request: Request,
    choix: str = Form(""),
    categorie: str = Form(""),
    personnes: list[str] = Form([]),
    nouvelle_personne: str = Form(""),
    add_personne: str | None = Form(None),
    remove_personne: str | None = Form(None),
    add: str | None = Form(None),
    delete: str | None = Form(None),
    login: str = Depends(get_current_organizer_login),
):
    cfg = PLANNINGS_INVITES.get(section)
    if cfg is None:
        raise HTTPException(status_code=404)
    champ_personnes = cfg["personnes"]

    db = SqlRepository(config.engine)
    table = db.create(obj=cfg["model"], table_name=cfg["table"], primary_key="id")
    data = db.load(cfg["model"], table_name=cfg["table"])

    if delete is not None:
        to_delete = next((e for e in data if e.id == delete), None)
        if to_delete:
            db.delete(to_delete, table, primary_key="id")

    guest_names = {f"{g.prenom} {g.nom}" for g in store.list_guests()}

    # Saved rows: each has its own "ajout_<id>" field to add a guest, and a ✕
    # per guest ("retirer" = "<id>|<name>")
    form = await request.form()
    retirer = form.get("retirer", "")
    for row in data:
        avant = _split_noms(getattr(row, champ_personnes))
        noms = list(avant)
        ajout = (form.get(f"ajout_{row.id}") or "").strip()
        if ajout in guest_names and ajout not in noms:
            noms.append(ajout)
        if retirer.startswith(f"{row.id}|"):
            noms = [n for n in noms if n != retirer.split("|", 1)[1]]
        if noms != avant:
            setattr(row, champ_personnes, ", ".join(noms))
            db.update(row, table, primary_key="id")

    # New row: guests are added one by one, the row being built (draft) travels
    # in the query string until ➕ saves it. Only existing guests are accepted.
    personnes = [p for p in dict.fromkeys(personnes) if p in guest_names]
    nouvelle_personne = nouvelle_personne.strip()
    if (add_personne or add) and nouvelle_personne in guest_names and nouvelle_personne not in personnes:
        personnes.append(nouvelle_personne)
    if remove_personne in personnes:
        personnes.remove(remove_personne)

    if add and choix in MOMENTS_MARIAGE and categorie.strip() and personnes:
        to_add = cfg["model"](
            id=uuid4().hex,
            categorie=categorie.strip(),
            **{cfg["choix"]: choix, champ_personnes: ", ".join(personnes)},
        )
        db.insert(to_add, table=table)
        return RedirectResponse(url=f"/organisateur/info-pratiques#{section}", status_code=303)

    draft = urlencode(
        {f"{section}_choix": choix, f"{section}_categorie": categorie, f"{section}_personnes": personnes},
        doseq=True,
    )
    return RedirectResponse(url=f"/organisateur/info-pratiques?{draft}#{section}", status_code=303)


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
        request, "dashboard/organizer_analytics.html",
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
    return templates.TemplateResponse(request, "dashboard/organizer_send_invit.html", {"request": request, "invite": invite})


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
        f"Veuillez trouver votre invitation pour le mariage de {config.WEDDING_NAME1} & {config.WEDDING_NAME2} disponible sur {config.BASE_URL}\n"
        f"Votre code invité est : {invite.token.upper()}\n"
        "Afin de valider votre présence, veuillez répondre au sondage à la fin de la carte d'invitation.\n\n"
        f"En espérant vous revoir bientôt, \n{config.WEDDING_NAME1} & {config.WEDDING_NAME2}\n"
        "Dieu vous garde."
    )
    contact = "" if invite.contact is None else invite.contact.replace(" ", "").replace("+", "")

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
def scan_page(request: Request, role: str = Depends(acces_scan)):
    return templates.TemplateResponse(
        request, "dashboard/organizer_scan.html", {"request": request, "phase_labels": CHART_PHASE_LABELS}
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
    # the scan page posts with fetch and shows data["message"]: answer in JSON rather than redirect
    if _role_organisateur(login) not in ROLES_SCAN:
        return JSONResponse({"success": False, "message": "Accès réservé à l'accueil."}, status_code=403)
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

@router.get("/animation")
def animation_home(request: Request, role: str = Depends(acces_animation)):
    return templates.TemplateResponse(request, "animation/animation.html", {"request":request, "organizer_role": role})

# ---------- Animation : Le Quiz ----------
def _load_quiz(db: SqlRepository):
    table = db.create(obj=QuizCreator(), table_name="animation_quiz", primary_key="id")
    data = db.load(QuizCreator, table_name="animation_quiz")
    if not data: # first use: create the single row holding all categories
        db.insert(QuizCreator(), table)
        data = db.load(QuizCreator, table_name="animation_quiz")
    return table, data[0]

@router.get("/animation/quiz")
def animation_quiz(request: Request, role: str = Depends(acces_animation)):
    return templates.TemplateResponse(
        request, "animation/animation_quiz_admin.html",
        {
            "request": request,
            "mode": "accueil",
            "organizer_role": role,
        }
    )

@router.get("/animation/quiz/questions")
def animation_quiz_questions(request: Request, role: str = Depends(acces_admin)):
    db = SqlRepository(config.engine)
    table, quiz_row = _load_quiz(db)
    return templates.TemplateResponse(
        request, "animation/animation_quiz_admin.html",
        {
            "request": request,
            "mode": "questions",
            "quiz": quiz_row.data,
            "stockage_actif": storage.actif(),
        }
    )

# ---------- Animation : Le Quiz en direct (Kahoot) ----------
_quiz_live_tables: dict = {}

def _quiz_live_db():
    """Tables of the live quiz, created once per process (they are polled every few seconds)."""
    db = SqlRepository(config.engine)
    if not _quiz_live_tables:
        _quiz_live_tables["session"] = db.create(obj=QuizSession(), table_name="animation_quiz_session", primary_key="id")
        _quiz_live_tables["reponses"] = db.create(obj=QuizReponse, table_name="animation_quiz_reponses", primary_key="id")
    return db, _quiz_live_tables

def _load_session(db: SqlRepository, tables: dict) -> QuizSession:
    data = db.load(QuizSession, table_name="animation_quiz_session")
    if not data: # first use: create the single row holding the live state
        db.insert(QuizSession(), tables["session"])
        data = db.load(QuizSession, table_name="animation_quiz_session")
    return data[0]

def _quiz_questions(quiz_row: QuizCreator) -> list[dict]:
    """All questions in a single list, keeping their category name."""
    return [
        {**question, "categorie": cat["nom"]}
        for cat in quiz_row.data["categories"]
        for question in cat["questions"]
    ]

def _current_question(session: dict, questions: list[dict]):
    numero = session.get("numero")
    if session["phase"] in ("question", "reponse") and numero is not None and 0 <= numero < len(questions):
        return questions[numero]
    return None

def _point_revele(reponse: QuizReponse, session: dict) -> bool:
    """A point only counts once its answer is revealed, so scores don't leak the right answer."""
    return reponse.correct and not (session["phase"] == "question" and reponse.numero == session.get("numero"))

def _classement(reponses: list[QuizReponse], session: dict) -> list[dict]:
    scores: dict[str, int] = {}
    for r in reponses:
        scores[r.token] = scores.get(r.token, 0) + int(_point_revele(r, session))
    guests = {g.token: g for g in store.load_guests()}
    classement = [
        {"token": token, "nom": f"{guests[token].prenom} {guests[token].nom}", "score": score}
        for token, score in scores.items() if token in guests
    ]
    classement.sort(key=lambda j: (-j["score"], j["nom"]))
    for j in classement: # ex aequo share the same rank
        j["rang"] = 1 + sum(1 for autre in classement if autre["score"] > j["score"])
    return classement

def _quiz_media(url: str | None):
    """Guess how to display a question's content: YouTube embed, video file or image."""
    if not url:
        return None
    lien = storage.url(url)
    if not lien: # b2:// reference while B2 isn't configured
        return None
    youtube = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})", url)
    if youtube:
        return {"type": "youtube", "url": f"https://www.youtube.com/embed/{youtube.group(1)}"}
    if re.search(r"\.(mp4|webm|ogg|mov|m4v)(\?|$)", url, re.IGNORECASE):
        return {"type": "video", "url": lien}
    return {"type": "image", "url": lien}

# --- Côté invité ---
@router.get("/animation/quiz/lancer")
def animation_quiz_code(request: Request):
    return templates.TemplateResponse(request, "animation/animation_quiz.html", {"request": request, "invite": None})

@router.post("/animation/quiz/lancer")
def animation_quiz_code_submit(request: Request, guest_code: str = Form(...)):
    invite = store.get_by_token_suffix(guest_code)
    if not invite:
        return templates.TemplateResponse(
            request, "animation/animation_quiz.html",
            {"request": request, "invite": None, "erreur": "Code non reconnu."},
            status_code=404,
        )
    return RedirectResponse(url=f"/organisateur/animation/quiz/jouer/{invite.token}", status_code=303)

@router.get("/animation/quiz/jouer/{token}")
def animation_quiz_jouer(request: Request, token: str):
    invite = store.get_by_token(token)
    if not invite:
        return RedirectResponse(url="/organisateur/animation/quiz/lancer", status_code=303)
    return templates.TemplateResponse(request, "animation/animation_quiz.html", {"request": request, "invite": invite})

@router.get("/animation/quiz/etat/{token}")
def animation_quiz_etat(token: str):
    db, tables = _quiz_live_db()
    session = _load_session(db, tables).data
    table, quiz_row = _load_quiz(db)
    questions = _quiz_questions(quiz_row)
    mes_reponses = db.load_where(QuizReponse, table_name="animation_quiz_reponses", token=token)

    etat = {
        "phase": session["phase"],
        "numero": session.get("numero"),
        "total": len(questions),
        "score": sum(1 for r in mes_reponses if _point_revele(r, session)),
    }
    question = _current_question(session, questions)
    if question:
        etat["question"] = {
            "categorie": question["categorie"],
            "enonce": question["enonce"],
            "reponses": question["reponses"],
        }
        etat["choix"] = next((r.choix for r in mes_reponses if r.numero == session["numero"]), None)
        if session["phase"] == "reponse": # the right answer is only sent once revealed
            etat["correct"] = question["correct"]
            etat["media"] = _quiz_media(question.get("contenu"))
    if session["phase"] == "fin":
        classement = _classement(db.load(QuizReponse, table_name="animation_quiz_reponses"), session)
        moi = next((j for j in classement if j["token"] == token), None)
        etat["rang"] = moi["rang"] if moi else None
        etat["joueurs"] = len(classement)
    return JSONResponse(etat)

@router.post("/animation/quiz/repondre/{token}")
def animation_quiz_repondre(token: str, numero: int = Form(...), choix: str = Form(...)):
    db, tables = _quiz_live_db()
    session = _load_session(db, tables).data
    table, quiz_row = _load_quiz(db)
    question = _current_question(session, _quiz_questions(quiz_row))
    if session["phase"] != "question" or session.get("numero") != numero or not question:
        return JSONResponse({"ok": False, "message": "Trop tard, la question est terminée !"}, status_code=409)
    if choix not in [r["id"] for r in question["reponses"]]:
        return JSONResponse({"ok": False, "message": "Réponse inconnue."}, status_code=400)
    if not store.get_by_token(token):
        return JSONResponse({"ok": False, "message": "Invité inconnu."}, status_code=404)

    reponse = QuizReponse(id=f"{token}:{numero}", token=token, numero=numero, choix=choix, correct=choix in question["correct"])
    if db.insert(reponse, tables["reponses"]) is False: # primary key: only one answer per question
        return JSONResponse({"ok": False, "message": "Vous avez déjà répondu."}, status_code=409)
    return JSONResponse({"ok": True, "choix": choix})

# --- Côté superviseur ---
@router.get("/animation/quiz/superviser")
def animation_quiz_superviser(request: Request, role: str = Depends(acces_animation)):
    db, tables = _quiz_live_db()
    session = _load_session(db, tables).data
    table, quiz_row = _load_quiz(db)
    questions = _quiz_questions(quiz_row)
    question = _current_question(session, questions)
    return templates.TemplateResponse(
        request, "animation/animation_quiz_superviser.html",
        {
            "request": request,
            "phase": session["phase"],
            "numero": session.get("numero"),
            "total": len(questions),
            "question": question,
            "media": _quiz_media(question.get("contenu")) if question and session["phase"] == "reponse" else None,
            "organizer_role": role,
        }
    )

@router.get("/animation/quiz/superviser/etat")
def animation_quiz_superviser_etat(role: str = Depends(acces_animation)):
    db, tables = _quiz_live_db()
    session = _load_session(db, tables).data
    reponses = db.load(QuizReponse, table_name="animation_quiz_reponses")
    en_cours = [r for r in reponses if r.numero == session.get("numero")]
    etat = {
        "phase": session["phase"],
        "numero": session.get("numero"),
        "nb_reponses": len(en_cours),
        "classement": [{k: j[k] for k in ("nom", "score", "rang")} for j in _classement(reponses, session)],
    }
    if session["phase"] == "reponse": # answer distribution, only once revealed
        etat["repartition"] = {}
        for r in en_cours:
            etat["repartition"][r.choix] = etat["repartition"].get(r.choix, 0) + 1
    return JSONResponse(etat)

@router.post("/animation/quiz/superviser/{action}")
def animation_quiz_superviser_action(action: str, role: str = Depends(acces_animation)):
    db, tables = _quiz_live_db()
    session_row = _load_session(db, tables)
    session = session_row.data
    table, quiz_row = _load_quiz(db)
    total = len(_quiz_questions(quiz_row))

    if action in ("demarrer", "reinitialiser"): # a new game starts from a clean slate
        db.delete_all("animation_quiz_reponses")
    if action == "demarrer" and total:
        session.update(phase="question", numero=0)
    elif action == "reveler" and session["phase"] == "question":
        session["phase"] = "reponse"
    elif action == "suivante" and session["phase"] == "reponse":
        if session["numero"] + 1 < total:
            session.update(phase="question", numero=session["numero"] + 1)
        else:
            session["phase"] = "fin"
    elif action == "reinitialiser":
        session.update(phase="attente", numero=None)
    db.update(session_row, table=tables["session"], primary_key="id")
    return RedirectResponse(url="/organisateur/animation/quiz/superviser", status_code=303)

@router.post("/animation/quiz/ajouter-categorie")
def animation_quiz_add_categorie(request: Request, nom: str = Form(...), role: str = Depends(acces_admin)):
    #SQL query for inserting a new category
    db = SqlRepository(config.engine)
    table, quiz_row = _load_quiz(db)
    quiz = quiz_row.data
    quiz["categories"].append(
        {
            "id": str(uuid4()), 
            "nom": nom, 
            "questions": []
        }
        )
    db.update(quiz_row, table=table, primary_key="id")
    return RedirectResponse(url="/organisateur/animation/quiz/questions", status_code=303)

@router.post("/animation/quiz/ajouter-question/{cat_id}")
def animation_quiz_add_question(
    request: Request,
    cat_id: str,
    enonce: str = Form(...),
    correct: list[str] = Form(...),
    reponse_a: str = Form(...),
    reponse_b: str = Form(...),
    reponse_c: str = Form(""),
    reponse_d: str = Form(""),
    contenu: str = Form(None),
    fichier: UploadFile | str | None = File(None),  # str: browsers send "" when no file is chosen
    role: str = Depends(acces_admin),
):
    #SQL query for inserting a new question in a category
    if isinstance(fichier, StarletteUploadFile) and fichier.filename and storage.actif(): # an uploaded file wins over the URL field
        extension = Path(fichier.filename).suffix.lower()
        contenu = storage.envoyer(fichier.file, f"quiz/{uuid4().hex}{extension}", fichier.content_type)
    db = SqlRepository(config.engine)
    table, quiz_row = _load_quiz(db)
    quiz = quiz_row.data

    reponses = [{"id": "a", "texte": reponse_a}, {"id": "b", "texte": reponse_b}]
    if reponse_c:
        reponses.append({"id": "c", "texte": reponse_c})
    if reponse_d:
        reponses.append({"id": "d", "texte": reponse_d})

    for cat in quiz["categories"]: #search a cat id and add question to the right one
        if cat["id"] == str(cat_id):
            cat["questions"].append(
                {
                    "id": str(uuid4()),
                    "enonce": enonce, 
                    "reponses": reponses,
                    "correct": correct,
                    "contenu": contenu
                }
            )
            break
    db.update(quiz_row, table=table, primary_key="id")
    return RedirectResponse(url="/organisateur/animation/quiz/questions", status_code=303)

@router.post("/animation/quiz/supprimer-categorie/{cat_id}")
def animation_quiz_delete_categorie(request: Request, cat_id: str, role: str = Depends(acces_admin)):
    #SQL query for deleting a category by id
    db = SqlRepository(config.engine)
    table, quiz_row = _load_quiz(db)
    quiz = quiz_row.data
    for cat in quiz["categories"]:
        if cat["id"] == str(cat_id):
            for q in cat["questions"]:
                storage.supprimer(q.get("contenu"))
    quiz["categories"] = [cat for cat in quiz["categories"] if cat["id"] != str(cat_id)]
    db.update(quiz_row, table=table, primary_key="id")
    return RedirectResponse(url="/organisateur/animation/quiz/questions", status_code=303)

@router.post("/animation/quiz/{cat_id}/supprimer-question/{question_id}")
def animation_quiz_delete_question(request: Request, cat_id: str, question_id: str, role: str = Depends(acces_admin)):
    #SQL query for deleting a question by id
    db = SqlRepository(config.engine)
    table, quiz_row = _load_quiz(db)
    quiz = quiz_row.data
    for cat in quiz["categories"]:
        if cat["id"] == str(cat_id):
            for q in cat["questions"]:
                if q["id"] == str(question_id):
                    storage.supprimer(q.get("contenu"))
            cat["questions"] = [q for q in cat["questions"] if q["id"] != str(question_id)]
            break
    db.update(quiz_row, table=table, primary_key="id")
    return RedirectResponse(url="/organisateur/animation/quiz/questions", status_code=303)

# ---------- Animation : Le Défi ----------
def _load_defis(db: SqlRepository):
    table = db.create(obj=DefiCreator(), table_name="animation_defi", primary_key="id")
    data = db.load(DefiCreator, table_name="animation_defi")
    if not data: # first use: create the single row holding all challenges
        db.insert(DefiCreator(), table)
        data = db.load(DefiCreator, table_name="animation_defi")
    return table, data[0]

@router.get("/animation/defis")
def animation_defi(request: Request, role: str = Depends(acces_animation)):
    return templates.TemplateResponse(
        request, "animation/animation_defi_admin.html",
        {
            "request": request,
            "mode": "accueil",
            "organizer_role": role,
        }
    )

@router.get("/animation/defis/ajouter")
def animation_defi_edit(request: Request, role: str = Depends(acces_admin)):
    db = SqlRepository(config.engine)
    table, defi = _load_defis(db)
    return templates.TemplateResponse(
        request, "animation/animation_defi_admin.html",
        {
            "request": request,
            "mode": "ajouter",
            "defis": defi.data["defis"],
        }
    )

def _tirages_table(db: SqlRepository):
    return db.create(obj=DefiTirage, table_name="animation_defi_tirages", primary_key="token")

@router.get("/animation/defis/lancer")
def animation_defi_code(request: Request):
    return templates.TemplateResponse(request, "animation/animation_defi.html", {"request": request, "invite": None})

@router.post("/animation/defis/lancer")
def animation_defi_code_submit(request: Request, guest_code: str = Form(...)):
    invite = store.get_by_token_suffix(guest_code)
    if not invite:
        return templates.TemplateResponse(
            request, "animation/animation_defi.html",
            {"request": request, "invite": None, "erreur": "Code non reconnu."},
            status_code=404,
        )
    return RedirectResponse(url=f"/organisateur/animation/defis/jouer/{invite.token}", status_code=303)

@router.get("/animation/defis/jouer/{token}")
def animation_defi_jouer(request: Request, token: str):
    invite = store.get_by_token(token)
    if not invite:
        return RedirectResponse(url="/organisateur/animation/defis/lancer", status_code=303)
    db = SqlRepository(config.engine)
    table, defi = _load_defis(db)
    _tirages_table(db)
    deja_tire = db.load_where(DefiTirage, table_name="animation_defi_tirages", token=token)
    return templates.TemplateResponse(
        request, "animation/animation_defi.html",
        {
            "request": request,
            "invite": invite,
            "defis": defi.data["defis"],
            "tirage": deja_tire[0] if deja_tire else None,
            "anime": False,
        }
    )

@router.post("/animation/defis/jouer/{token}")
def animation_defi_tirer(request: Request, token: str):
    invite = store.get_by_token(token)
    if not invite:
        return RedirectResponse(url="/organisateur/animation/defis/lancer", status_code=303)
    db = SqlRepository(config.engine)
    table, defi = _load_defis(db)
    defis = defi.data["defis"]
    tirages = _tirages_table(db)
    deja_tire = db.load_where(DefiTirage, table_name="animation_defi_tirages", token=token)
    tirage = deja_tire[0] if deja_tire else None
    anime = False
    if not deja_tire and defis: # one draw per guest: an existing one is shown, never redrawn
        tirage = DefiTirage(token=token, defi_nom=random.choice(defis)["nom"], tire_le=datetime.now())
        db.insert(tirage, tirages)
        anime = True
    # rendered directly (no redirect) so the wheel animation plays once, right after the draw
    return templates.TemplateResponse(
        request, "animation/animation_defi.html",
        {
            "request": request,
            "invite": invite,
            "defis": defis,
            "tirage": tirage,
            "anime": anime,
        }
    )

@router.get("/animation/defis/invites")
def animation_defi_invites(request: Request, role: str = Depends(acces_animation)):
    db = SqlRepository(config.engine)
    _tirages_table(db)
    guests = {g.token: g for g in store.load_guests()}
    tirages = [
        {"token": t.token, "nom": f"{guests[t.token].prenom} {guests[t.token].nom}" if t.token in guests else t.token,
         "defi": t.defi_nom, "tire_le": t.tire_le}
        for t in db.load(DefiTirage, table_name="animation_defi_tirages")
    ]
    tirages.sort(key=lambda t: t["tire_le"], reverse=True)
    return templates.TemplateResponse(
        request, "animation/animation_defi_admin.html",
        {
            "request": request,
            "mode": "invites",
            "tirages": tirages,
        }
    )

@router.post("/animation/defis/invites/reinitialiser")
def animation_defi_invites_reset(request: Request, role: str = Depends(acces_animation)):
    db = SqlRepository(config.engine)
    _tirages_table(db)
    db.delete_all("animation_defi_tirages")
    return RedirectResponse(url="/organisateur/animation/defis/invites", status_code=303)

@router.post("/animation/defis/invites/reinitialiser/{token}")
def animation_defi_invite_reset(request: Request, token: str, role: str = Depends(acces_animation)):
    db = SqlRepository(config.engine)
    table = _tirages_table(db)
    for tirage in db.load_where(DefiTirage, table_name="animation_defi_tirages", token=token):
        db.delete(tirage, table=table, primary_key="token")
    return RedirectResponse(url="/organisateur/animation/defis/invites", status_code=303)

@router.post("/animation/defis/ajouter")
def animation_defi_add(request: Request, nom: str = Form(...), role: str = Depends(acces_admin)):
    db = SqlRepository(config.engine)
    table, defi = _load_defis(db)
    defi.data["defis"].append({"id": str(uuid4()), "nom": nom})
    db.update(defi, table=table, primary_key="id")
    return RedirectResponse(url="/organisateur/animation/defis/ajouter", status_code=303)

@router.post("/animation/defis/supprimer/{defi_id}")
def animation_defi_delete(request: Request, defi_id: str, role: str = Depends(acces_admin)):
    db = SqlRepository(config.engine)
    table, defi = _load_defis(db)
    defi.data["defis"] = [d for d in defi.data["defis"] if d["id"] != str(defi_id)]
    db.update(defi, table=table, primary_key="id")
    return RedirectResponse(url="/organisateur/animation/defis/ajouter", status_code=303)

# ---------- Animation : Un mot aux mariés ----------
MOT_DOSSIER = "unmotauxmaries"
MOT_ASSEMBLAGE = f"{MOT_DOSSIER}/assemblage.mp4"
# every clip is converted to the same format so they can be joined without re-encoding
MOT_FORMAT_ASSEMBLAGE = [
    "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-ar", "48000", "-ac", "2",
]
_assemblage = {"en_cours": False, "erreur": None}

def _ffmpeg(*args: str) -> None:
    if shutil.which("ffmpeg") is None:
        import static_ffmpeg
        static_ffmpeg.add_paths()  # downloads ffmpeg on first run, then adds it to PATH
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-300:])

def _dossier_invite(invite: Invite) -> str:
    return slugify(f"{invite.prenom} {invite.nom}")

def _traiter_video_mot(brute: str, dossier_invite: str) -> None:
    """Converts the raw upload to mp4 (max MOT_DUREE s) and sends it to B2 as <invite>/original.mp4.
    If B2 is unavailable, the video is kept in VIDEOS_DIR so the message isn't lost."""
    try:
        with tempfile.TemporaryDirectory() as dossier_temp:
            original = Path(dossier_temp) / "original.mp4"
            _ffmpeg("-i", brute, "-t", str(config.MOT_DUREE),
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-movflags", "+faststart", str(original))
            try:
                if not storage.actif():
                    raise RuntimeError("B2 n'est pas configuré")
                storage.envoyer_chemin(str(original), f"{MOT_DOSSIER}/{dossier_invite}/original.mp4", "video/mp4")
            except Exception as e:
                secours = Path(config.VIDEOS_DIR) / dossier_invite / "original.mp4"
                secours.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(original), secours)
                logger.error(f"Un mot aux mariés : envoi vers B2 impossible, vidéo gardée dans {secours} : {e}")
    except Exception as e:
        logger.error(f"Un mot aux mariés : échec du traitement de {dossier_invite} : {e}")
    finally:
        os.remove(brute)

def _messages_mot() -> list[dict]:
    """Guests' messages stored on B2, oldest first: [{"cle", "dossier", "nom", "date"}]."""
    noms = {_dossier_invite(g): f"{g.prenom} {g.nom}" for g in store.load_guests()}
    messages = []
    for fichier in storage.lister(f"{MOT_DOSSIER}/"):
        morceaux = fichier["cle"].split("/")
        if len(morceaux) == 3 and morceaux[2] == "original.mp4":
            messages.append({**fichier, "dossier": morceaux[1], "nom": noms.get(morceaux[1], morceaux[1])})
    messages.sort(key=lambda m: m["date"])
    return messages

def _assembler_videos() -> None:
    """Joins every guest's message, oldest first, into a single video sent to B2."""
    try:
        with tempfile.TemporaryDirectory() as dossier_temp:
            dossier_temp = Path(dossier_temp)
            morceaux = []
            for i, message in enumerate(_messages_mot()):
                brut = dossier_temp / f"{i}_brut.mp4"
                storage.telecharger(message["cle"], str(brut))
                morceau = dossier_temp / f"{i}.mp4"
                _ffmpeg("-i", str(brut), *MOT_FORMAT_ASSEMBLAGE, str(morceau))
                morceaux.append(morceau)
            if not morceaux:
                raise RuntimeError("aucun message à assembler")
            liste = dossier_temp / "liste.txt"
            liste.write_text("".join(f"file '{m.as_posix()}'\n" for m in morceaux), encoding="utf-8")
            sortie = dossier_temp / "assemblage.mp4"
            _ffmpeg("-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy", "-movflags", "+faststart", str(sortie))
            storage.envoyer_chemin(str(sortie), MOT_ASSEMBLAGE, "video/mp4")
        _assemblage["erreur"] = None
    except Exception as e:
        logger.error(f"Un mot aux mariés : échec de l'assemblage : {e}")
        _assemblage["erreur"] = str(e)
    finally:
        _assemblage["en_cours"] = False

# --- Accueil et page des messages (organisateurs) ---
@router.get("/animation/mot-aux-maries")
def animation_mot(request: Request, role: str = Depends(acces_animation)):
    return templates.TemplateResponse(request, "animation/animation_mot_admin.html", {"request": request, "mode": "accueil"})

@router.get("/animation/mot-aux-maries/messages")
def animation_mot_messages(request: Request, role: str = Depends(acces_animation)):
    messages, assemblage, erreur = [], None, None
    if storage.actif():
        try:
            messages = [{**m, "lien": storage.url(storage.PREFIXE + m["cle"])} for m in _messages_mot()]
            existant = [f for f in storage.lister(MOT_ASSEMBLAGE) if f["cle"] == MOT_ASSEMBLAGE]
            if existant:
                assemblage = {"date": existant[0]["date"], "lien": storage.url(storage.PREFIXE + MOT_ASSEMBLAGE)}
        except Exception as e:
            logger.error(f"Un mot aux mariés : lecture de B2 impossible : {e}")
            erreur = "Impossible de lire Backblaze B2 : vérifiez la clé dans le .env."
    else:
        erreur = "Backblaze B2 n'est pas configuré dans le .env."
    return templates.TemplateResponse(
        request, "animation/animation_mot_admin.html",
        {
            "request": request,
            "mode": "messages",
            "messages": messages,
            "assemblage": assemblage,
            "assemblage_en_cours": _assemblage["en_cours"],
            "assemblage_erreur": _assemblage["erreur"],
            "erreur": erreur,
        }
    )

@router.post("/animation/mot-aux-maries/messages/assembler")
def animation_mot_assembler(background_tasks: BackgroundTasks, role: str = Depends(acces_animation)):
    if storage.actif() and not _assemblage["en_cours"]:
        _assemblage.update(en_cours=True, erreur=None)
        background_tasks.add_task(_assembler_videos)
    return RedirectResponse(url="/organisateur/animation/mot-aux-maries/messages", status_code=303)

@router.post("/animation/mot-aux-maries/messages/supprimer/{dossier}")
def animation_mot_supprimer(dossier: str, role: str = Depends(acces_animation)):
    storage.supprimer(f"{storage.PREFIXE}{MOT_DOSSIER}/{dossier}/original.mp4")
    return RedirectResponse(url="/organisateur/animation/mot-aux-maries/messages", status_code=303)

# --- Enregistrement (invités) ---
@router.get("/animation/mot-aux-maries/enregistrer")
def animation_mot_code(request: Request):
    return templates.TemplateResponse(request, "animation/animation_mot.html", {"request": request, "invite": None})

@router.post("/animation/mot-aux-maries/enregistrer")
def animation_mot_code_submit(request: Request, guest_code: str = Form(...)):
    invite = store.get_by_token_suffix(guest_code)
    if not invite:
        return templates.TemplateResponse(
            request, "animation/animation_mot.html",
            {"request": request, "invite": None, "erreur": "Code non reconnu."},
            status_code=404,
        )
    return RedirectResponse(url=f"/organisateur/animation/mot-aux-maries/enregistrer/{invite.token}", status_code=303)

@router.get("/animation/mot-aux-maries/enregistrer/{token}")
def animation_mot_enregistrer(request: Request, token: str):
    invite = store.get_by_token(token)
    if not invite:
        return RedirectResponse(url="/organisateur/animation/mot-aux-maries/enregistrer", status_code=303)
    return templates.TemplateResponse(
        request, "animation/animation_mot.html",
        {"request": request, "invite": invite, "duree": config.MOT_DUREE},
    )

@router.post("/animation/mot-aux-maries/enregistrer/{token}")
def animation_mot_video(token: str, background_tasks: BackgroundTasks, video: UploadFile = File(...)):
    invite = store.get_by_token(token)
    if not invite:
        return JSONResponse({"ok": False, "message": "Invité inconnu."}, status_code=404)
    extension = ".mp4" if "mp4" in (video.content_type or "") else ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as brute:
        shutil.copyfileobj(video.file, brute)
    # ffmpeg and the upload take a few seconds: the guest gets their answer right away
    background_tasks.add_task(_traiter_video_mot, brute.name, _dossier_invite(invite))
    return JSONResponse({"ok": True})
