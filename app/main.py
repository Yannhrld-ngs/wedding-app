from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import invites, organizers

app = FastAPI(title="Wedding App")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(invites.router)
app.include_router(organizers.router)

@app.get("/")
def racine():
    return {"message": "Wedding Organizer API"} 
