from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator

from app.models import PresenceStatus, TransportMode


class QuestionnaireInput(BaseModel):
    presence: str  # "present" | "absent", reçu du formulaire HTML
    allergies: Optional[str] = None
    mode_transport: Optional[str] = None
    transport_details: Optional[str] = None

    @field_validator("presence")
    @classmethod
    def valider_presence(cls, v: str) -> str:
        if v not in ("present", "absent"):
            raise ValueError("Valeur de présence invalide")
        return v

    @field_validator("mode_transport")
    @classmethod
    def valider_transport(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if v not in [m.value for m in TransportMode]:
            raise ValueError("Mode de transport invalide")
        return v


class OrganisateurLogin(BaseModel):
    login: str
    password: str


class ScanQRInput(BaseModel):
    qr_uuid: str


class InviteCSVRow(BaseModel):
    prenom: str
    nom: str
    email: Optional[EmailStr] = None
