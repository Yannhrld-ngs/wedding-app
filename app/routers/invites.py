from typing import List

from fastapi import APIRouter, Request, Response, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from app import store, config, calendar
from app.mailer import send_email
from app.models import Invite, OuiNon, Sexe, get_key, generate_qr_uuid

router = APIRouter(prefix="/16mesures/invites", tags=["invites"])
templates = Jinja2Templates(directory="app/templates")


def get_invite_or_404(token: str) -> Invite:
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    return invite


@router.get("/inscription")
def inscription_form(request: Request, nb: int = 0):
    nb_accompagnateurs = max(0, min(nb, 50))
    all_invite = store.list_guests()

    if len(all_invite) > 98:
            return templates.TemplateResponse(
        "questionnaire.html",
        {
            "request": request,
            "full": True,
            "nb_accompagnateurs": nb_accompagnateurs,
        },
            )

    # Le formulaire est en method="get" par défaut (cf. questionnaire.html) : cliquer sur
    # "Valider le nombre" recharge cette page en renvoyant tous les champs déjà remplis
    # dans la query string. On les relit ici pour les rendre à nouveau dans le formulaire,
    # afin que changer le nombre d'accompagnateurs ne fasse perdre aucune saisie.
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
        "accompagnateur_prenom": _padded(qp.getlist("accompagnateur_prenom")),
        "accompagnateur_nom": _padded(qp.getlist("accompagnateur_nom")),
        "accompagnateur_sexe": _padded(qp.getlist("accompagnateur_sexe")),
    }

    return templates.TemplateResponse(
        "questionnaire.html",
        {
            "request": request,
            "merci": bool(qp.get("merci")),
            "nb_accompagnateurs": nb_accompagnateurs,
            "form_data": form_data,
        },
    )


@router.post("/inscription")
def inscription_submit(
    request: Request,
    prenom: str = Form(""),
    nom: str = Form(""),
    email: str = Form(""),
    telephone: str = Form(""),
    sexe: str = Form(""),
    categorie: str = Form(""),
    accompagnateur_prenom: List[str] = Form([]),
    accompagnateur_nom: List[str] = Form([]),
    accompagnateur_sexe: List[str] = Form([]),
    force: str = Form(""),
):
    prenom = prenom.strip()
    nom = nom.strip()
    email = email.strip()

    if not prenom or not nom or not email or not sexe or not categorie:
        return templates.TemplateResponse(
            "questionnaire.html",
            {
                "request": request,
                "error": "Merci de remplir tous les champs obligatoires avant de vous inscrire.",
                "nb_accompagnateurs": len(accompagnateur_prenom),
                "form_data": {
                    "prenom": prenom,
                    "nom": nom,
                    "email": email,
                    "telephone": telephone,
                    "sexe": sexe,
                    "categorie": categorie,
                    "accompagnateur_prenom": accompagnateur_prenom,
                    "accompagnateur_nom": accompagnateur_nom,
                    "accompagnateur_sexe": accompagnateur_sexe,
                },
            },
        )

    existing = store.find_by_email(email)
    if existing and not force:
        return templates.TemplateResponse(
            "questionnaire.html",
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
        mail=email,
        contact=telephone.strip() or None,
        presence_diffusion=OuiNon.oui,
    )
    invite.token = get_key(invite)
    # Un accompagnateur = son propre Invite (même code que pour l'inscrit principal),
    # rattaché à l'inscrit principal via une liste de tokens séparés par des virgules.
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
            categorie=f"accompagnateur - {invite.categorie}",
            mail=None,
            contact=None,
            presence_diffusion=OuiNon.oui,
        )
        companion.token = get_key(companion)
        store._write_qr_file(companion)
        store.save_guest(companion)
        accompagnateur_tokens.append(companion.token)

    if accompagnateur_tokens:
        invite.accompagnateur = ",".join(accompagnateur_tokens)

    store._write_qr_file(invite)
    store.save_guest(invite)
    confirm_link = f"{config.BASE_URL}/16mesures/invites/confirmation-inscription/{invite.token}"
    
    send_email(
        to=invite.mail,
        subject="Confirmation présence - 16 mesures",
        body=(
            f"Bonjour {invite.prenom} {invite.nom},\n\n"
            "Vous avez manifesté votre souhait de prendre part à la diffusion du film 16 mesures."
            f"\nVotre code spectacteur est : {invite.token}\n\n"
            f"Il vous sera demandé pour vous connecter depuis {config.BASE_URL}/16mesures. Veuillez ouvrir le lien ci dessous pour l'activer. \n"
            f"{confirm_link} \n\n"
            "Ceci est un mail automatique. Veuillez ne pas répondre."
        ),
    )

    return RedirectResponse(url="/16mesures/invites/inscription?merci=1", status_code=303)


@router.get("/confirmation/{token}")
def confirmation_presence(token: str, request: Request):
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Inscription introuvable")

    if not invite.confirmation_mail:
        return templates.TemplateResponse("questionnaire.html",{"request":request, "unvalidated": True}, )

    accompagnateurs = [
        accomp
        for accomp in (store.get_by_token(tok) for tok in (invite.accompagnateur or "").split(",") if tok)
        if accomp is not None
    ]

    return templates.TemplateResponse(
        "invite_card.html",
        {
            "request": request,
            "invite": invite,
            "url_qr_invite": store.qr_code_url(invite),
            "accomagnateurs": accompagnateurs,
            "url_qr_accompagnateurs": {accomp.token : store.qr_code_url(accomp) for accomp in accompagnateurs} ,
            "lieu": config.VENUE_NAME,
            "adresse": config.VENUE_RECEPTION,
            "date": config.WEDDING_DATE,
            "heure": config.WEDDING_HOUR,
            "cover_image_url": "/static/Images/16mesures.png",
        },
    )

@router.get("/confirmation-inscription/{token}")
def inscription_confirmation(token:str, request: Request):
    invite = store.get_by_token(token)
    if not invite.confirmation_mail:
        invite.confirmation_mail = True
        store.save_guest(invite)
    return RedirectResponse(url=f"/16mesures/invites/confirmation/{token}", status_code=303)

    
@router.get("/{token}/calendrier.ics")
def download_calendrier_is(token: str):
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Inscription introuvable")

    return Response(
                content=calendar._create(
                    summary="16 mesures — Diffusion",
                    description=f"Bonjour {invite.prenom}, votre place pour la diffusion de 16 mesures est confirmée.",
                    location=f"{config.VENUE_NAME}, {config.VENUE_RECEPTION}",
                    date=config.WEDDING_DATE,
                    heure=config.WEDDING_HOUR),
                    media_type="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=16mesures.ics"},
                )