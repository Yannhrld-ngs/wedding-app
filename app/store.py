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
from app.database import SqlRepository

from app.models import (
    Invite,
    Organisateur,
    OuiNon,
    PresenceStatus,
    Sexe,
    generate_invite_token,
    generate_qr_uuid,
    natural_key,
    slugify,
)

logger = logging.getLogger(__name__)
LOCK_TIMEOUT = 10  # secondes
SQL_REPO = SqlRepository(config.engine)

# ---------- Invités ----------
def _guests_lock() -> FileLock:
    return FileLock(config.GUESTS_LOG_PATH + ".lock", timeout=LOCK_TIMEOUT)


def _read_log() -> dict:
    if config.SQL_DB:
        all_guests = SQL_REPO.load(Invite, table_name="guests")
        return {f"{natural_key(guest.prenom, guest.nom) }":_invite_to_dict(guest) for guest in all_guests}
    else:
        if not os.path.exists(config.GUESTS_LOG_PATH):#create if not exist
            with open(config.GUESTS_LOG_PATH, "w", encoding="utf-8") as f:
                yaml.dump([], f, allow_unicode=True, sort_keys=False)

        with open(config.GUESTS_LOG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


def _write_log(log: dict, obj:list[Invite]) -> None:
    if config.SQL_DB:
        all_guests = obj
        table = SQL_REPO.create(Invite, table_name="guests", primary_key="token")
        for guest in all_guests:
            SQL_REPO.update(guest, table, primary_key="token") 
    else:
        os.makedirs(os.path.dirname(config.GUESTS_LOG_PATH), exist_ok=True)
        with open(config.GUESTS_LOG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(log, f, allow_unicode=True, sort_keys=True)


def _read_guests() -> list[dict]:
    '''
    Read guest as a list of dict, either from SQL database or from yaml file.
    '''
    rows = []
    if config.SQL_DB:
        results = SQL_REPO.load(Invite, table_name="guests")
        if not results:
            return rows

        for row in results:
            rows.append({
                "prenom": row.prenom,
                "nom": row.nom,
                "sexe": row.sexe,
                "categorie": row.categorie,
                "role": row.role,
                "mail": row.mail,
                "contact": row.contact,
                })
    else:
        if not os.path.exists(config.GUESTS_PATH):
            return rows 
        
        with open(config.GUESTS_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
                if row.get("prenom") and row.get("nom"):
                    rows.append(row)
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
        "presence_diffusion": invite.presence_diffusion.value if invite.presence_diffusion else None,
        "presence_debat": invite.presence_debat.value if invite.presence_debat else None,
        "checked_in_diffusion": invite.checked_in_diffusion,
        "checked_in_diffusion_at": invite.checked_in_diffusion_at.isoformat() if invite.checked_in_diffusion_at else None,
        "checked_in_diffusion_by": invite.checked_in_diffusion_by,
        "checked_in_debat": invite.checked_in_debat,
        "checked_in_debat_at": invite.checked_in_debat_at.isoformat() if invite.checked_in_debat_at else None,
        "checked_in_debat_by": invite.checked_in_debat_by,
        "created_at": invite.created_at.isoformat(),
        "confirmation_mail": invite.confirmation_mail,
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
        presence_diffusion=OuiNon(data["presence_diffusion"]) if data.get("presence_diffusion") else None,
        presence_debat=OuiNon(data["presence_debat"]) if data.get("presence_debat") else None,
        checked_in_diffusion=bool(data.get("checked_in_diffusion", False)),
        checked_in_diffusion_at=datetime.fromisoformat(data["checked_in_diffusion_at"]) if data.get("checked_in_diffusion_at") else None,
        checked_in_diffusion_by=data.get("checked_in_diffusion_by"),
        checked_in_debat=bool(data.get("checked_in_debat", False)),
        checked_in_debat_at=datetime.fromisoformat(data["checked_in_debat_at"]) if data.get("checked_in_debat_at") else None,
        checked_in_debat_by=data.get("checked_in_debat_by"),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
        confirmation_mail=bool(data.get("confirmation_mail", False)),
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

def load_guests() -> list[Invite]:
    """Charge la liste des invités depuis le CSV ou la base de données SQL Server, synchronise les logs et retourne la liste des objets Invite.
    """
    guests_data = _read_guests()

    with _guests_lock(): # Lock the log file to prevent concurrent modifications
        log = _read_log()
        changed = False

        # Clean log des invités qui ne sont plus dans le CSV ou la base de données SQL Server.
        if guests_data:
            current_keys = {natural_key(row["prenom"], row["nom"]) for row in guests_data}
            keys_to_remove = [ key for key, entry in log.items() if key not in current_keys ]
            for key in keys_to_remove:
                entry = log[key]
                _delete_qr_file(f"{slugify(entry['nom'])}-{slugify(entry['prenom'])}-qrcode.png")
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

        output = [_invite_from_dict(data) for data in log.values()]
                
        if changed:
            _write_log(log, output)

        return output 


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
    """Crée ou persiste l'état (réponses, check-in...) d'un invité dans le log"""
    with _guests_lock():
        log = _read_log()
        existing_key = next(
            (key for key, entry in log.items() if entry.get("token") == invite.token),
            None,
        )
        key = existing_key or invite.token
        log[key] = _invite_to_dict(invite)
        _write_log(log, [invite])


def find_by_email(email: str) -> Optional[Invite]:
    """Une personne ne doit avoir qu'un seul code actif : utilisé pour
    détecter un invité déjà enregistré pour cette adresse (ex. spectateur
    qui s'inscrirait deux fois)."""
    email = (email or "").strip().lower()
    if not email:
        return None
    return next((g for g in load_guests() if (g.mail or "").lower() == email), None)


def delete_guest(token: str) -> None:
    with _guests_lock():
        log = _read_log()
        key = next((key for key, entry in log.items() if entry.get("token") == token), None)
        if key is not None:
            del log[key]
            data = [_invite_from_dict(data) for data in log.values()]
            _write_log(log, data)


# ---------- Organisateurs ----------
def _organizers_lock() -> FileLock:
    return FileLock(config.ORGANIZERS_LOG_PATH + ".lock", timeout=LOCK_TIMEOUT)


def _read_organizers() -> dict:
    if not os.path.exists(config.ORGANIZERS_LOG_PATH):
        with open(config.ORGANIZERS_LOG_PATH, "w", encoding="utf-8") as f:
            yaml.dump({}, f, allow_unicode=True, sort_keys=True)

    with open(config.ORGANIZERS_LOG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_organizers(organizers: dict) -> None:
    os.makedirs(os.path.dirname(config.ORGANIZERS_LOG_PATH), exist_ok=True)
    with open(config.ORGANIZERS_LOG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(organizers, f, allow_unicode=True, sort_keys=True)

def _organisateur_to_dict(organisateur: Organisateur) -> dict:
    return {
        "prenom": organisateur.prenom,
        "nom": organisateur.nom,
        "sexe": organisateur.sexe.value,
        "categorie": organisateur.categorie,
        "role": organisateur.role,
        "mail": organisateur.mail,
        "contact": organisateur.contact,
    }


def _organisateur_from_dict(data: dict) -> Organisateur:
    return Organisateur(
        prenom=data["prenom"],
        nom=data["nom"],
        sexe=Sexe(data.get("sexe") or "homme"),
        categorie=data.get("categorie"),
        role=data.get("role"),
        mail=data.get("mail"),
        contact=data.get("contact"),
    )

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


def accepted_organizers() -> list[Organisateur]:
    """Retourne la liste des invités organisateurs acceptés."""
    if config.SQL_DB:
        return SQL_REPO.load(Organisateur, table_name="organizers") 
    else:
        if not os.path.exists(config.ORGANIZERS_PATH):
            return [] 
        
        rows = []
        with open(ORGANIZERS_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for data in reader:
                rows.append( 
                    Organisateur(
                                prenom = data['prenom'],
                                nom = data['nom'],
                                categorie= data['categorie'],
                                sexe = data['sexe'],
                                role = data['role'],
                                mail = data['mail'],
                                contact = data['contact'],
                                )
                )
        return rows

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
    print( accepted_organizers() )
    print(find_accepted_organizer_by_mail("yannhrld@gmail.com"))
    print(find_accepted_organizer_by_mail("yann656@hotma.com"))
    print('ww')