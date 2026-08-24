import hashlib
import re
import unicodedata
import uuid
import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

SLUG_SUFFIX_LENGTH = 6


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "invite"


def natural_key(prenom: str, nom: str) -> str:
    """Clé stable qui relie une ligne du CSV à son entrée dans le log YAML."""
    return f"{slugify(nom)}-{slugify(prenom)}"


def generate_invite_token(
    prenom: str, nom: str, categorie: str, wedding_name1: str, wedding_date: str
) -> str:
    """Endpoint lisible (nom-prenom) suivi d'un suffixe déterministe : le token
    reste toujours le même pour un invité donné, même si le log YAML est vidé
    et régénéré. Le sel n'utilise que des fragments de nom/prénom (pas les
    valeurs complètes, déjà visibles dans l'URL) combinés à des infos propres
    au mariage (nom1, date), pour rendre le suffixe plus difficile à deviner
    qu'un simple hash de nom/prénom/catégorie en clair."""
    base = f"{slugify(nom)}-{slugify(prenom)}"
    seed = "|".join(
        [
            slugify(nom)[:3],
            slugify(prenom)[-5:],
            slugify(categorie),
            slugify(wedding_name1)[-5:],
            str(wedding_date),
        ]
    )
    suffix = hashlib.sha256(seed.encode()).hexdigest()[:SLUG_SUFFIX_LENGTH]
    return f"{base}-{suffix}"


def generate_qr_uuid() -> str:
    """Identifiant encodé dans le QR code, distinct du token de la carte (par sécurité)."""
    return str(uuid.uuid4())


class PresenceStatus(str, enum.Enum):
    en_attente = "en_attente"
    present = "present"
    absent = "absent"


class TransportMode(str, enum.Enum):
    pas_concerne = "pas_concerne"
    voiture = "voiture"
    train = "train"
    covoiturage = "covoiturage"
    en_reflexion = "en_reflexion"
    autre = "autre"


class Sexe(str, enum.Enum):
    homme = "homme"
    femme = "femme"


class OuiNon(str, enum.Enum):
    oui = "oui"
    non = "non"


class PresenceAfter(str, enum.Enum):
    oui = "oui"
    non = "non"
    en_reflexion = "en_reflexion"


class RestrictionAlimentaire(str, enum.Enum):
    aucune = "aucune"
    halal = "halal"
    vegetarien = "vegetarien"
    vegetalien = "vegetalien"
    autre = "autre"


class Logement(str, enum.Enum):
    pas_concerne = "pas_concerne"
    oui = "oui"
    toujours_en_recherche = "toujours_en_recherche"
    ne_sait_pas = "ne_sait_pas"


@dataclass
class Invite:
    prenom: str
    nom: str
    categorie: str
    token: str
    qr_uuid: str
    sexe: Sexe = Sexe.homme
    role: Optional[str] = None
    mail: Optional[str] = None
    contact: Optional[str] = None
    statut_presence: PresenceStatus = PresenceStatus.en_attente

    # Questionnaire
    presence_diffusion: Optional[OuiNon] = None #Force to be oui
    presence_debat: Optional[OuiNon] = None

    # Check-in jour J, 
    checked_in_diffusion: bool = False
    checked_in_diffusion_at: Optional[datetime] = None
    checked_in_diffusion_by: Optional[str] = None
    place_diffusion: Optional[str] = None

    checked_in_debat: bool = False
    checked_in_debat_at: Optional[datetime] = None
    checked_in_debat_by: Optional[str] = None
    place_debat: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.utcnow)
    confirmation_mail: bool = False

    def accord(self, masculin: str, feminin: str) -> str:
        """Forme accordée selon le sexe de l'invité (masculin par défaut)."""
        return feminin if self.sexe == Sexe.femme else masculin


@dataclass
class Organisateur:
    prenom: str
    nom: str
    categorie: str
    sexe: Sexe = Sexe.homme
    role: Optional[str] = None
    mail: Optional[str] = None
    contact: Optional[str] = None
    

    def accord(self, masculin: str, feminin: str) -> str:
        """Forme accordée selon le sexe de l'invité (masculin par défaut)."""
        return feminin if self.sexe == Sexe.femme else masculin