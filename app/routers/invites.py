from fastapi import APIRouter, Request, Response, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from app import store, config, calendar, song_search
from app.mailer import send_email
from app.models import Invite, OuiNon, Sexe, generate_invite_token, generate_qr_uuid

router = APIRouter(prefix="/16mesures/invites", tags=["invites"])
templates = Jinja2Templates(directory="app/templates")


def get_invite_or_404(token: str) -> Invite:
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    return invite


@router.get("/inscription")
def inscription_form(request: Request):
    return templates.TemplateResponse(
        "questionnaire.html",
        {
            "request": request,
            "merci": bool(request.query_params.get("merci")),
        },
    )


@router.post("/inscription")
def inscription_submit(
    request: Request,
    prenom: str = Form(...),
    nom: str = Form(...),
    email: str = Form(...),
    telephone: str = Form(""),
    sexe: str = Form(...),
    debat: str = Form(...),
    force: str = Form(""),
):
    prenom = prenom.strip()
    nom = nom.strip()
    email = email.strip()

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
                    "debat": debat,
                },
            },
        )

    if existing and force:
        store.delete_guest(existing.token)

    invite = Invite(
        prenom=prenom,
        nom=nom,
        categorie="spectateur",
        token=generate_invite_token(prenom, nom, "spectateur", "16-mesures", datetime.utcnow().isoformat()),
        qr_uuid=generate_qr_uuid(),
        sexe=Sexe(sexe),
        mail=email,
        contact=telephone.strip() or None,
        presence_diffusion=OuiNon.oui,
        presence_debat=OuiNon(debat),
    )
    store._write_qr_file(invite)
    store.save_guest(invite)

    confirm_link = f"{config.BASE_URL}/16mesures/invites/confirmation-presence/{invite.token}"
    send_email(
        to=invite.mail,
        subject="Confirmation présence - 16 mesures",
        body=(
            f"Bonjour {invite.prenom} {invite.nom},\n\n"
            "Vous avez manifesté votre souhait de prendre part à la diffusion de 16 mesures.\n"
            f"Votre code spectateur est : {invite.token[-6:]}\n\n"
            "Cliquez sur ce lien pour confirmer votre présence :\n"
            f"{confirm_link}\n\n"
            "Ceci est un mail automatique. Veuillez ne pas répondre."
        ),
    )

    return RedirectResponse(url="/16mesures/invites/inscription?merci=1", status_code=303)


@router.get("/confirmation-presence/{token}")
def confirmation_presence(token: str, request: Request):
    invite = store.get_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Inscription introuvable")

    if not invite.confirmation_mail:
        invite.confirmation_mail = True
        store.save_guest(invite)

    return templates.TemplateResponse(
        "invite_card.html",
        {
            "request": request,
            "invite": invite,
            "lieu": config.VENUE_NAME,
            "adresse": config.VENUE_RECEPTION,
            "date": config.WEDDING_DATE,
            "heure": config.WEDDING_HOUR,
            "cover_image_url": "/static/Images/16mesures.png",
            "qr_code_url": store.qr_code_url(invite),
        },
    )

@router.get("/{token}/song-search")
def song_search_endpoint(token: str, q: str = ""):
    """Proxy vers l'iTunes Search API pour l'autocomplétion des morceaux."""
    get_invite_or_404(token)
    return JSONResponse({"results": song_search.search_songs(q)})


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