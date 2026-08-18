"""
Module de gestion du stockage des invités et des organisateurs. Il fournit des fonctions pour charger, sauvegarder et synchroniser les données des invités depuis un fichier CSV ou une base de données SQL Server, ainsi que pour gérer les organisateurs et leurs mots de passe. Les informations sont stockées dans des fichiers YAML pour la persistance.
Fonctionnalités principales :
- Chargement des invités depuis un fichier CSV ou une base de données SQL Server.
- Synchronisation des invités avec un fichier de log YAML.
- Gestion des organisateurs et de leurs mots de passe.
"""
import csv
import logging
import os
from datetime import datetime
from typing import Optional

import qrcode
import yaml
from filelock import FileLock

from app import config

logger = logging.getLogger(__name__)
from app.models import (
    Invite,
    Logement,
    OuiNon,
    PresenceAfter,
    PresenceStatus,
    RestrictionAlimentaire,
    Sexe,
    TransportMode,
    generate_invite_token,
    generate_qr_uuid,
    natural_key,
    slugify,
)

LOCK_TIMEOUT = 10  # secondes


# ---------- Invités ----------
def _guests_lock() -> FileLock:
    return FileLock(config.GUESTS_LOG_PATH + ".lock", timeout=LOCK_TIMEOUT)


def _read_log() -> dict:
    if not os.path.exists(config.GUESTS_LOG_PATH):
        with open(config.GUESTS_LOG_PATH, "w", encoding="utf-8") as f:
            yaml.dump([], f, allow_unicode=True, sort_keys=False)

    with open(config.GUESTS_LOG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_log(log: dict) -> None:
    os.makedirs(os.path.dirname(config.GUESTS_LOG_PATH), exist_ok=True)
    with open(config.GUESTS_LOG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(log, f, allow_unicode=True, sort_keys=True)


def _read_guests_csv() -> list[dict]:
    if not os.path.exists(config.GUESTS_PATH):
        return []
    rows = []
    with open(config.GUESTS_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            if row.get("prenom") and row.get("nom"):
                rows.append(row)
    return rows

def _read_guests_sql() -> list[dict]:
    if not config.SQL_DB:
        return []
    rows = []
    try:
        with config.engine.connect() as conn:
            result = conn.execute(config.text("SELECT * FROM guests;"))
            for row in result:
                rows.append({
                    "prenom": row.prenom,
                    "nom": row.nom,
                    "sexe": row.sexe,
                    "categorie": row.categorie,
                    "role": row.role,
                    "mail": row.mail,
                    "contact": row.contact,
                })
    except Exception as e:
        logger.error(f"Erreur lors de la lecture des invités depuis la base de données {config.SQL_DATABASE} : {e}")
    return rows

def _invite_to_dict(invite: Invite) -> dict:
    return {
        "prenom": invite.prenom,
        "nom": invite.nom,
        "sexe": invite.sexe.value,
        "categorie": invite.categorie,
        "role": invite.role,
        "mail": invite.mail,
        "contact": invite.contact,
        "token": invite.token,
        "qr_uuid": invite.qr_uuid,
        "statut_presence": invite.statut_presence.value,
        "presence_mairie": invite.presence_mairie.value if invite.presence_mairie else None,
        "presence_reception": invite.presence_reception.value if invite.presence_reception else None,
        "presence_after": invite.presence_after.value if invite.presence_after else None,
        "mode_transport": invite.mode_transport.value if invite.mode_transport else None,
        "transport_details": invite.transport_details,
        "covoiturage_possible": invite.covoiturage_possible.value if invite.covoiturage_possible else None,
        "navette_souhaitee": invite.navette_souhaitee.value if invite.navette_souhaitee else None,
        "logement": invite.logement.value if invite.logement else None,
        "consomme_alcool": invite.consomme_alcool.value if invite.consomme_alcool else None,
        "restriction_alimentaire": invite.restriction_alimentaire.value if invite.restriction_alimentaire else None,
        "restriction_alimentaire_autre": invite.restriction_alimentaire_autre,
        "chanson_1": invite.chanson_1,
        "chanson_2": invite.chanson_2,
        "chanson_3": invite.chanson_3,
        "questionnaire_rempli": invite.questionnaire_rempli,
        "questionnaire_rempli_le": invite.questionnaire_rempli_le.isoformat()
        if invite.questionnaire_rempli_le
        else None,
        "checked_in_mairie": invite.checked_in_mairie,
        "checked_in_mairie_at": invite.checked_in_mairie_at.isoformat() if invite.checked_in_mairie_at else None,
        "checked_in_mairie_by": invite.checked_in_mairie_by,
        "checked_in_reception": invite.checked_in_reception,
        "checked_in_reception_at": invite.checked_in_reception_at.isoformat() if invite.checked_in_reception_at else None,
        "checked_in_reception_by": invite.checked_in_reception_by,
        "checked_in_after": invite.checked_in_after,
        "checked_in_after_at": invite.checked_in_after_at.isoformat() if invite.checked_in_after_at else None,
        "checked_in_after_by": invite.checked_in_after_by,
        "place_mairie": invite.place_mairie,
        "place_reception": invite.place_reception,
        "place_after": invite.place_after,
        "created_at": invite.created_at.isoformat(),
    }


def _invite_from_dict(data: dict) -> Invite:
    return Invite(
        prenom=data["prenom"],
        nom=data["nom"],
        sexe=Sexe(data.get("sexe") or "homme"),
        categorie=data.get("categorie"),
        role=data.get("role"),
        mail=data.get("mail"),
        contact=data.get("contact"),
        token=data["token"],
        qr_uuid=data["qr_uuid"],
        statut_presence=PresenceStatus(data.get("statut_presence") or "en_attente"),
        presence_mairie=OuiNon(data["presence_mairie"]) if data.get("presence_mairie") else None,
        presence_reception=OuiNon(data["presence_reception"]) if data.get("presence_reception") else None,
        presence_after=PresenceAfter(data["presence_after"]) if data.get("presence_after") else None,
        mode_transport=TransportMode(data["mode_transport"]) if data.get("mode_transport") else None,
        transport_details=data.get("transport_details"),
        covoiturage_possible=OuiNon(data["covoiturage_possible"]) if data.get("covoiturage_possible") else None,
        navette_souhaitee=OuiNon(data["navette_souhaitee"]) if data.get("navette_souhaitee") else None,
        logement=Logement(data["logement"]) if data.get("logement") else None,
        consomme_alcool=OuiNon(data["consomme_alcool"]) if data.get("consomme_alcool") else None,
        restriction_alimentaire=RestrictionAlimentaire(data["restriction_alimentaire"]) if data.get("restriction_alimentaire") else None,
        restriction_alimentaire_autre=data.get("restriction_alimentaire_autre"),
        chanson_1=data.get("chanson_1"),
        chanson_2=data.get("chanson_2"),
        chanson_3=data.get("chanson_3"),
        questionnaire_rempli=bool(data.get("questionnaire_rempli", False)),
        questionnaire_rempli_le=datetime.fromisoformat(data["questionnaire_rempli_le"])
        if data.get("questionnaire_rempli_le")
        else None,
        checked_in_mairie=bool(data.get("checked_in_mairie", False)),
        checked_in_mairie_at=datetime.fromisoformat(data["checked_in_mairie_at"]) if data.get("checked_in_mairie_at") else None,
        checked_in_mairie_by=data.get("checked_in_mairie_by"),
        checked_in_reception=bool(data.get("checked_in_reception", False)),
        checked_in_reception_at=datetime.fromisoformat(data["checked_in_reception_at"]) if data.get("checked_in_reception_at") else None,
        checked_in_reception_by=data.get("checked_in_reception_by"),
        checked_in_after=bool(data.get("checked_in_after", False)),
        checked_in_after_at=datetime.fromisoformat(data["checked_in_after_at"]) if data.get("checked_in_after_at") else None,
        checked_in_after_by=data.get("checked_in_after_by"),
        place_mairie=data.get("place_mairie"),
        place_reception=data.get("place_reception"),
        place_after=data.get("place_after"),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
    )

def qr_code_path(invite: Invite) -> str:
    filename = f"{slugify(invite.nom)}-{slugify(invite.prenom)}-qrcode.png"
    return os.path.join(config.QR_OUTPUT_DIR, filename)

def qr_code_url(invite: Invite) -> str:
    """URL web du QR (le mount /static sert le contenu de app/static, cf. app/main.py)."""
    filename = f"{slugify(invite.nom)}-{slugify(invite.prenom)}-qrcode.png"
    #relative_dir = os.path.relpath(config.QR_OUTPUT_DIR, "app/static").replace(os.sep, "/")
    #return f"/static/{relative_dir}/{filename}"
    return f"/{config.QR_OUTPUT_DIR}/{filename}".replace('app/','')

def _write_qr_file(invite: Invite) -> None:
    os.makedirs(config.QR_OUTPUT_DIR, exist_ok=True)
    img = qrcode.make(invite.qr_uuid)
    img.save(qr_code_path(invite))

def _delete_qr_file(filename: str) -> None:
    full_path = os.path.join(config.QR_OUTPUT_DIR, filename)
    if os.path.exists(full_path):
        os.remove(full_path)

def load_guests(organizer_only: bool = False) -> list[Invite]:
    """Charge la liste des invités depuis le CSV ou la base de données SQL Server, synchronise les logs et retourne la liste des objets Invite.
    """
    if config.SQL_DB:
        guests_data = _read_guests_sql()
    else:  
        guests_data = _read_guests_csv()

    with _guests_lock(): # Lock the log file to prevent concurrent modifications
        log = _read_log()
        changed = False

        # Clean log des invités qui ne sont plus dans le CSV ou la base de données SQL Server.
        # Ne jamais faire ce nettoyage si la lecture n'a rien renvoyé : ça peut vouloir dire
        # que le CSV/la connexion SQL a échoué, pas que tout le monde a été supprimé.
        if guests_data:
            current_keys = {natural_key(row["prenom"], row["nom"]) for row in guests_data}
            keys_to_remove = [key for key in log if key not in current_keys]
            for key in keys_to_remove:
                _delete_qr_file(f"{key}-qrcode.png")
                del log[key]
                changed = True
        elif log:
            logger.warning("Attention : aucun invité lu (CSV/SQL vide ou en erreur) — synchronisation ignorée pour éviter de tout supprimer.")

        # Synchronise les invités du CSV ou de la base de données SQL Server avec le log YAML
        for row in guests_data:
            key = natural_key(row["prenom"], row["nom"])
            sexe = Sexe.femme if row.get("sexe", "").lower() == "femme" else Sexe.homme
            categorie = row.get("categorie").lower()
            role = row.get("role").lower()if row.get("role") else None
            mail = row.get("mail").lower() if row.get("mail") else None
            contact = (row.get("contact") or "").strip() or None

            #Add new guests infos
            if key not in log:
                invite = Invite(
                    prenom=row["prenom"],
                    nom=row["nom"],
                    sexe=sexe,
                    categorie=categorie,
                    role=role,
                    mail=mail,
                    contact=contact,
                    token=generate_invite_token(
                        row["prenom"], row["nom"], categorie, config.WEDDING_NAME1, config.WEDDING_DATE
                    ),
                    qr_uuid=generate_qr_uuid(),
                )
                _write_qr_file(invite)
                log[key] = _invite_to_dict(invite)
                changed = True

            #Update existing guests infos
            else:
                entry = log[key]
                if (  entry.get("sexe") != sexe.value
                or entry.get("categorie") != categorie
                or entry.get("role") != role
                or entry.get("mail") != mail
                or entry.get("contact") != contact):
                    entry["sexe"] = sexe.value
                    entry["categorie"] = categorie
                    entry["role"] = role
                    entry["mail"] = mail
                    entry["contact"] = contact
                    changed = True

        if changed:
            _write_log(log)

        if organizer_only==False:
            return [_invite_from_dict(data) for data in log.values()]
        else:
            return [_invite_from_dict(data) for data in log.values() if data.get("role") in config.ORGANIZER_ROLES]


def list_guests() -> list[Invite]:
    return sorted(load_guests(), key=lambda g: (g.prenom, g.nom))


def get_by_token(token: str) -> Optional[Invite]:
    return next((g for g in load_guests() if g.token == token), None)


def get_by_qr_uuid(qr_uuid: str) -> Optional[Invite]:
    return next((g for g in load_guests() if g.qr_uuid == qr_uuid), None)


def get_by_token_suffix(suffix: str) -> Optional[Invite]:
    """Retrouve un invité à partir des derniers caractères de son token
    (ex : le code à 4 caractères que le site d'accueil demande aux invités)."""
    suffix = (suffix or "").strip().lower()
    if not suffix:
        return None
    return next((g for g in load_guests() if g.token.lower().endswith(suffix)), None)


def save_guest(invite: Invite) -> None:
    """Persiste l'état (réponses, check-in...) d'un invité dans le log YAML."""
    key = natural_key(invite.prenom, invite.nom)
    with _guests_lock():
        log = _read_log()
        log[key] = _invite_to_dict(invite)
        _write_log(log)


# ---------- Organisateurs ----------
def _organizers_lock() -> FileLock:
    return FileLock(config.ORGANIZERS_PATH + ".lock", timeout=LOCK_TIMEOUT)


def _read_organizers() -> dict:
    if not os.path.exists(config.ORGANIZERS_PATH):
        with open(config.ORGANIZERS_PATH, "w", encoding="utf-8") as f:
            yaml.dump({}, f, allow_unicode=True, sort_keys=True)

    with open(config.ORGANIZERS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_organizers(organizers: dict) -> None:
    os.makedirs(os.path.dirname(config.ORGANIZERS_PATH), exist_ok=True)
    with open(config.ORGANIZERS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(organizers, f, allow_unicode=True, sort_keys=True)


def get_organizer_password_hash(login: str) -> Optional[str]:
    with _organizers_lock():
        organizers = _read_organizers()
    entry = organizers.get(login)
    return entry.get("password_hash") if entry else None


def create_organizer(login: str, password_hash: str) -> bool:
    """Crée un compte organisateur. Retourne False si le login existe déjà."""
    with _organizers_lock():
        organizers = _read_organizers()
        if login in organizers:
            return False
        organizers[login] = {"password_hash": password_hash}
        _write_organizers(organizers)
        return True


def accepted_organizers() -> list[Invite]:
    """Retourne la liste des invités organisateurs acceptés."""
    return load_guests(organizer_only=True)


def find_accepted_organizer_by_mail(mail: str) -> Optional[Invite]:
    """Retourne l'invité organisateur accepté correspondant à cet email, sinon None."""
    mail = (mail or "").strip().lower()
    if not mail:
        return None
    return next((o for o in accepted_organizers() if o.mail == mail), None)


def set_organizer_password(login: str, password_hash: str) -> None:
    """Crée ou met à jour le mot de passe d'un organisateur (contrairement à
    create_organizer, écrase le mot de passe existant s'il y en a déjà un)."""
    with _organizers_lock():
        organizers = _read_organizers()
        organizers[login] = {"password_hash": password_hash}
        _write_organizers(organizers)

if __name__ =="__main__":
    a = load_guests(True)
    print("A")