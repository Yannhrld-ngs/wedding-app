from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.routers import invites, organizers
from app import config, store

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(title="Wedding App")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(invites.router)
app.include_router(organizers.router)

GUEST_CODE_SUBMIT_URL = "/guest-access"


def _home_context(request: Request, **extra):
    return {
        "request": request,
        "wedding_name_1": config.WEDDING_NAME1,
        "wedding_name_2": config.WEDDING_NAME2,
        "home_image_url": config.HOME_IMAGE_URL,
        "GUEST_CODE_SUBMIT_URL": GUEST_CODE_SUBMIT_URL,
        **extra,
    }


@app.get("/")
def racine(request: Request):
    return templates.TemplateResponse("home.html", _home_context(request))


@app.post("/guest-access")
def guest_access(request: Request, guest_code: str = Form(...)):
    invite = store.get_by_token_suffix(guest_code)
    if invite:
        return RedirectResponse(url=f"/invite/{invite.token}", status_code=303)

    return templates.TemplateResponse(
        "home.html",
        _home_context(request, GUEST_CODE_ERROR="Code non reconnu."),
        status_code=404,
    )
