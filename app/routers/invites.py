from datetime import datetime

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import store, config
from app.models import Invite, PresenceStatus, TransportMode

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
        },
    )


@router.post("/{token}/questionnaire")
def questionnaire_submit(
    token: str,
    request: Request,
    presence: str = Form(...),
    allergies: str = Form(""),
    mode_transport: str = Form(""),
    transport_details: str = Form(""),
):
    invite = get_invite_or_404(token)

    invite.statut_presence = (
        PresenceStatus.present if presence == "present" else PresenceStatus.absent
    )
    invite.allergies = allergies or None
    invite.mode_transport = TransportMode(mode_transport) if mode_transport else None
    invite.transport_details = transport_details or None
    invite.questionnaire_rempli = True
    invite.questionnaire_rempli_le = datetime.utcnow()

    store.save_guest(invite)

    return RedirectResponse(url=f"/invite/{token}?merci=1", status_code=303)