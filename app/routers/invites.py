from datetime import datetime

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import store, config
from app.models import (
    Invite,
    Logement,
    OuiNon,
    OuiNonPasConcerne,
    PresenceStatus,
    RestrictionAlimentaire,
    TransportMode,
)

router = APIRouter(prefix="/invite", tags=["invites"])
templates = Jinja2Templates(directory="app/templates")


def get_invite_or_404(token: str) -> Invite:
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    return invite


@router.get("/{token}")
def carte_invitation(token: str, request: Request):
    invite = get_invite_or_404(token)
    return templates.TemplateResponse(
        "invite_card_1.html",
        {
            "request": request,
            "invite": invite,
            "wedding_name1": config.WEDDING_NAME1,
            "wedding_name2": config.WEDDING_NAME2,
            "wedding_date": config.WEDDING_DATE,
            "venue_name": config.VENUE_NAME,
            "venue_civil": config.VENUE_CIVIL,
            "venue_reception": config.VENUE_RECEPTION,
            "venue_schedule": config.VENUE_SCHEDULE,
            "cover_image_url": config.COVER_IMAGE_URL,
            "wedding_colors_url":config.WEDDING_COLORS_URL,
            "qr_code_url": store.qr_code_url(invite),
        },
    )


@router.get("/{token}/questionnaire")
def questionnaire_form(token: str, request: Request):
    invite = get_invite_or_404(token)
    return templates.TemplateResponse(
        "questionnaire.html",
        {
            "request": request,
            "invite": invite,
            "transport_modes": list(TransportMode),
            "venue_name": config.VENUE_NAME,
        },
    )


@router.post("/{token}/questionnaire")
def questionnaire_submit(
    token: str,
    request: Request,
    presence_mairie: str = Form(...),
    presence_reception: str = Form(...),
    presence_after: str = Form(...),
    nombre_enfants: int = Form(0),
    mode_transport: str = Form(...),
    transport_details: str = Form(""),
    covoiturage_possible: str = Form(...),
    navette_souhaitee: str = Form(...),
    logement: str = Form(...),
    restriction_alimentaire: str = Form(...),
    restriction_alimentaire_autre: str = Form(""),
):
    invite = get_invite_or_404(token)

    invite.presence_mairie = OuiNon(presence_mairie)
    invite.presence_reception = OuiNon(presence_reception)
    invite.presence_after = OuiNon(presence_after)
    invite.nombre_enfants = max(0, nombre_enfants)
    invite.mode_transport = TransportMode(mode_transport)
    invite.transport_details = transport_details or None
    invite.covoiturage_possible = OuiNonPasConcerne(covoiturage_possible)
    invite.navette_souhaitee = OuiNonPasConcerne(navette_souhaitee)
    invite.logement = Logement(logement)
    invite.restriction_alimentaire = RestrictionAlimentaire(restriction_alimentaire)
    invite.restriction_alimentaire_autre = (
        restriction_alimentaire_autre or None
        if invite.restriction_alimentaire == RestrictionAlimentaire.autre
        else None
    )

    # Statut global dérivé des réponses détaillées : présent si présent à la
    # mairie et/ou à la réception, pas de question générique redondante.
    invite.statut_presence = (
        PresenceStatus.present
        if OuiNon.oui in (invite.presence_mairie, invite.presence_reception)
        else PresenceStatus.absent
    )
    invite.questionnaire_rempli = True
    invite.questionnaire_rempli_le = datetime.utcnow()

    store.save_guest(invite)

    return RedirectResponse(url=f"/invite/{token}?merci=1", status_code=303)