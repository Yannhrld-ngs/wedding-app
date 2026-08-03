import re
import secrets
import unicodedata
import uuid
import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

SLUG_SUFFIX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
SLUG_SUFFIX_LENGTH = 4


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "invite"


def natural_key(prenom: str, nom: str) -> str:
    """Clé stable qui relie une ligne du CSV à son entrée dans le log YAML."""
    return f"{slugify(nom)}-{slugify(prenom)}"


def generate_invite_token(prenom: str, nom: str) -> str:
    """Endpoint lisible (nom-prenom) suivi d'un court suffixe aléatoire, pour que
    l'URL de la carte d'invitation reste difficile à deviner à partir du seul nom."""
    base = f"{slugify(nom)}-{slugify(prenom)}"
    suffix = "".join(secrets.choice(SLUG_SUFFIX_ALPHABET) for _ in range(SLUG_SUFFIX_LENGTH))
    return f"{base}-{suffix}"


def generate_qr_uuid() -> str:
    """Identifiant encodé dans le QR code, distinct du token de la carte (par sécurité)."""
    return str(uuid.uuid4())


class PresenceStatus(str, enum.Enum):
    en_attente = "en_attente"
    present = "present"
    absent = "absent"


class TransportMode(str, enum.Enum):
    voiture = "voiture"
    train = "train"
    covoiturage = "covoiturage"
    autre = "autre"


class Sexe(str, enum.Enum):
    homme = "homme"
    femme = "femme"


@dataclass
class Invite:
    prenom: str
    nom: str
    token: str
    qr_uuid: str
    email: Optional[str] = None
    sexe: Sexe = Sexe.homme
    categorie: Optional[str] = None

    statut_presence: PresenceStatus = PresenceStatus.en_attente
    allergies: Optional[str] = None
    mode_transport: Optional[TransportMode] = None
    transport_details: Optional[str] = None
    questionnaire_rempli: bool = False
    questionnaire_rempli_le: Optional[datetime] = None

    checked_in: bool = False
    checked_in_at: Optional[datetime] = None
    checked_in_by: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.utcnow)

    def accord(self, masculin: str, feminin: str) -> str:
        """Forme accordée selon le sexe de l'invité (masculin par défaut)."""
        return feminin if self.sexe == Sexe.femme else masculin
