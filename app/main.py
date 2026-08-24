from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.routers import invites, organizers
from app import config, store

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(title="Wedding App")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

GUEST_CODE_SUBMIT_URL = "/16mesures/guest-access"


def _home_context(request: Request, **extra):
    return {
        "request": request,
        "about_image_url": "/static/Images/aboutkira.jpg",
        "film_image":"/static/Images/16mesures.png",
        "instagram_url": "https://www.instagram.com/heyckira/",#config.INSTAGRAM_URL,
        "lieu": config.VENUE_NAME,
        "adresse":config.VENUE_RECEPTION,
        "date":config.WEDDING_DATE,
        "heure":config.WEDDING_HOUR,
        "GUEST_CODE_SUBMIT_URL": GUEST_CODE_SUBMIT_URL,
        **extra,
    }


@app.get("/")
def racine(request: Request):
    return templates.TemplateResponse("home.html", _home_context(request))

@app.get("/16mesures")
def racine(request: Request):
    return templates.TemplateResponse("16mesures.html", _home_context(request))


@app.post("/16mesures/guest-access")
def guest_access(request: Request, guest_code: str = Form(...)):
    invite = store.get_by_token_suffix(guest_code)
    if invite:
        return RedirectResponse(url=f"/16mesures/invites/confirmation-presence/{invite.token}", status_code=303)

    return templates.TemplateResponse(
        "16mesures.html",
        _home_context(request, GUEST_CODE_ERROR="Code non reconnu."),
        status_code=404,
    )

app.include_router(invites.router)
app.include_router(organizers.router)
