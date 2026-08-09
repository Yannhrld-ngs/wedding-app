"""
Module de gestion du stockage des invités et des organisateurs. Il fournit des fonctions pour charger, sauvegarder et synchroniser les données des invités depuis un fichier CSV ou une base de données SQL Server, ainsi que pour gérer les organisateurs et leurs mots de passe. Les informations sont stockées dans des fichiers YAML pour la persistance.
Fonctionnalités principales :
- Chargement des invités depuis un fichier CSV ou une base de données SQL Server.
- Synchronisation des invités avec un fichier de log YAML.
- Gestion des organisateurs et de leurs mots de passe.
"""
import csv
import os
from datetime import datetime
from typing import Optional

import qrcode
import yaml
from filelock import FileLock

from app import config
from app.models import (
    Invite,
    PresenceStatus,
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
            result = conn.execute(config.text("SELECT * FROM test_guests;"))
            for row in result:
                rows.append({
                    "prenom": row.prenom,
                    "nom": row.nom,
                    "sexe": row.sexe,
                    "categorie": row.categorie,
                    "role": row.role,
                    "mail": row.mail
                })
    except Exception as e:
        print(f"Erreur lors de la lecture des invités depuis la base de données {config.SQL_DATABASE} :", e)
    return rows

def _invite_to_dict(invite: Invite) -> dict:
    return {
        "prenom": invite.prenom,
        "nom": invite.nom,
        "sexe": invite.sexe.value,
        "categorie": invite.categorie,
        "role": invite.role,
        "mail": invite.mail,
        "token": invite.token,
        "qr_uuid": invite.qr_uuid,
        "statut_presence": invite.statut_presence.value,
        "allergies": invite.allergies,
        "mode_transport": invite.mode_transport.value if invite.mode_transport else None,
        "transport_details": invite.transport_details,
        "questionnaire_rempli": invite.questionnaire_rempli,
        "questionnaire_rempli_le": invite.questionnaire_rempli_le.isoformat()
        if invite.questionnaire_rempli_le
        else None,
        "checked_in": invite.checked_in,
        "checked_in_at": invite.checked_in_at.isoformat() if invite.checked_in_at else None,
        "checked_in_by": invite.checked_in_by,
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
        token=data["token"],
        qr_uuid=data["qr_uuid"],
        statut_presence=PresenceStatus(data.get("statut_presence") or "en_attente"),
        allergies=data.get("allergies"),
        mode_transport=TransportMode(data["mode_transport"]) if data.get("mode_transport") else None,
        transport_details=data.get("transport_details"),
        questionnaire_rempli=bool(data.get("questionnaire_rempli", False)),
        questionnaire_rempli_le=datetime.fromisoformat(data["questionnaire_rempli_le"])
        if data.get("questionnaire_rempli_le")
        else None,
        checked_in=bool(data.get("checked_in", False)),
        checked_in_at=datetime.fromisoformat(data["checked_in_at"]) if data.get("checked_in_at") else None,
        checked_in_by=data.get("checked_in_by"),
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
            print("Attention : aucun invité lu (CSV/SQL vide ou en erreur) — synchronisation ignorée pour éviter de tout supprimer.")

        # Synchronise les invités du CSV ou de la base de données SQL Server avec le log YAML
        for row in guests_data:
            key = natural_key(row["prenom"], row["nom"])
            sexe = Sexe.femme if row.get("sexe", "").lower() == "femme" else Sexe.homme
            categorie = row.get("categorie").lower()
            role = row.get("role").lower()if row.get("role") else None
            mail = row.get("mail").lower() if row.get("mail") else None

            #Add new guests infos
            if key not in log: 
                invite = Invite(
                    prenom=row["prenom"],
                    nom=row["nom"],
                    sexe=sexe,
                    categorie=categorie,
                    role=role,
                    mail=mail,
                    token=generate_invite_token(row["prenom"], row["nom"]),
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
                or entry.get("mail") != mail):
                    entry["sexe"] = sexe.value
                    entry["categorie"] = categorie
                    entry["role"] = role
                    entry["mail"] = mail
                    changed = True

        if changed:
            _write_log(log)

        if organizer_only==False:
            return [_invite_from_dict(data) for data in log.values()]
        else:
            return [_invite_from_dict(data) for data in log.values() if data.get("role") in config.ORGANIZER_ROLES]


def list_guests() -> list[Invite]:
    return sorted(load_guests(), key=lambda g: (g.nom, g.prenom))


def get_by_token(token: str) -> Optional[Invite]:
    return next((g for g in load_guests() if g.token == token), None)


def get_by_qr_uuid(qr_uuid: str) -> Optional[Invite]:
    return next((g for g in load_guests() if g.qr_uuid == qr_uuid), None)


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

if __name__ == "__main__":
    # Test de lecture des invités depuis la base de données SQL Server
    test = load_guests(organizer_only=True)
    qr_code_url(test[0]) if test else None
    a=1
    print("Invités depuis SQL Server :", test)