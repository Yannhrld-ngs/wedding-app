import hashlib
import re
import unicodedata
import uuid
import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

SLUG_SUFFIX_LENGTH = 4


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
    en_recherche = "en_recherche"
    autre = "autre"


class Sexe(str, enum.Enum):
    homme = "homme"
    femme = "femme"


class OuiNon(str, enum.Enum):
    oui = "oui"
    non = "non"


class OuiNonPasConcerne(str, enum.Enum):
    pas_concerne = "pas_concerne"
    oui = "oui"
    non = "non"


class RestrictionAlimentaire(str, enum.Enum):
    aucune = "aucune"
    halal = "halal"
    vegetarien = "vegetarien"
    vegetalien = "vegetalien"
    sans_gluten = "sans_gluten"
    sans_sel = "sans_sel"
    sans_sucre = "sans_sucre"
    sans_alcool = "sans_alcool"
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
    presence_mairie: Optional[OuiNon] = None
    presence_reception: Optional[OuiNon] = None
    presence_after: Optional[OuiNon] = None
    mode_transport: Optional[TransportMode] = None
    transport_details: Optional[str] = None
    covoiturage_possible: Optional[OuiNonPasConcerne] = None
    navette_souhaitee: Optional[OuiNonPasConcerne] = None
    logement: Optional[Logement] = None
    restriction_alimentaire: Optional[RestrictionAlimentaire] = None
    restriction_alimentaire_autre: Optional[str] = None

    questionnaire_rempli: bool = False
    questionnaire_rempli_le: Optional[datetime] = None

    # Check-in jour J, un par phase (le même QR peut être scanné 3 fois)
    checked_in_mairie: bool = False
    checked_in_mairie_at: Optional[datetime] = None
    checked_in_mairie_by: Optional[str] = None
    checked_in_reception: bool = False
    checked_in_reception_at: Optional[datetime] = None
    checked_in_reception_by: Optional[str] = None
    checked_in_after: bool = False
    checked_in_after_at: Optional[datetime] = None
    checked_in_after_by: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.utcnow)

    def accord(self, masculin: str, feminin: str) -> str:
        """Forme accordée selon le sexe de l'invité (masculin par défaut)."""
        return feminin if self.sexe == Sexe.femme else masculin
