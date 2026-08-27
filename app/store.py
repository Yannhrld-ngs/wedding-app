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
from dataclasses import asdict
from app.database import SqlRepository
from app.models import (
    Invite,
    Organisateur,
    OuiNon,
    PresenceStatus,
    Sexe,
    generate_qr_uuid,
    get_key,
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
        return {f"{get_key(guest)}":asdict(guest) for guest in all_guests}
    else:
        if not os.path.exists(config.GUESTS_LOG_PATH):#create if not exist
            with open(config.GUESTS_LOG_PATH, "w", encoding="utf-8") as f:
                yaml.dump([], f, allow_unicode=True, sort_keys=False)

        with open(config.GUESTS_LOG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


def _write_log(log: dict, invites:list[Invite]) -> None:
    """
    Should : add new guest, update guest infos, delete guest info. 
    """
    if config.SQL_DB:
        table = SQL_REPO.create(Invite, table_name="guests", primary_key="token")
        table_content = SQL_REPO.load(Invite, table_name="guests")
        table_key = [guest.token for guest in table_content] if table_content else []
        for guest in invites:
            if guest.token not in log.keys():
                print("here")
                SQL_REPO.delete(guest, table,primary_key="token") 
                return None
            elif guest.token in table_key:
                SQL_REPO.update(guest, table,primary_key="token") 
            else:
                SQL_REPO.insert(guest, table) 
    else:
        os.makedirs(os.path.dirname(config.GUESTS_LOG_PATH), exist_ok=True)
        with open(config.GUESTS_LOG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(log, f, allow_unicode=True, sort_keys=True)


def _read_guests() -> list[Invite]:
    '''
    Read guest as a list of dict, either from SQL database or from yaml file.
    '''
    if config.SQL_DB:
        results = SQL_REPO.load(Invite, table_name="guests")
        return results

    else:
        rows = []
        if not os.path.exists(config.GUESTS_PATH):
            return rows 
        
        with open(config.GUESTS_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
                rows.append(
                    Invite(
                        prenom=row.get("prenom"),
                        nom=row.get("nom"),
                        sexe=row.get("sexe"),
                        categorie=row.get("categorie"),
                        role=row.get("role"),
                        mail=row.get("mail"),
                        contact=row.get("contact"),
                        token=""
                    )
                )
        return rows

def _invite_from_dict(data: dict) -> Invite:
    return Invite(
        prenom=data["prenom"],
        nom=data["nom"],
        sexe=Sexe(data.get("sexe") or "homme"),
        categorie=data.get("categorie"),
        role=data.get("role"),
        mail=data.get("mail"),
        contact=data.get("contact"),
        accompagnateur=data.get("accompagnateur"),
        token=data["token"],
        qr_uuid=data["qr_uuid"],
        statut_presence=PresenceStatus(data.get("statut_presence") or "en_attente"),
        presence_diffusion=OuiNon(data["presence_diffusion"]) if data.get("presence_diffusion") else None,
        checked_in_diffusion=bool(data.get("checked_in_diffusion", False)),
        checked_in_diffusion_at=datetime.fromisoformat(str(data["checked_in_diffusion_at"])) if data.get("checked_in_diffusion_at") else None,
        checked_in_diffusion_by=data.get("checked_in_diffusion_by"),
        place_diffusion=data.get("place_diffusion"),
        created_at=datetime.fromisoformat(str(data["created_at"])) if data.get("created_at") else datetime.utcnow(),
        confirmation_mail=bool(data.get("confirmation_mail", False)),
    )

def qr_code_path(invite: Invite) -> str:
    filename = f"{invite.token}-qrcode.png"
    return os.path.join(config.QR_OUTPUT_DIR, filename)

def qr_code_url(invite: Invite) -> str:
    """URL web du QR (le mount /static sert le contenu de app/static, cf. app/main.py)."""
    filename = f"{invite.token}-qrcode.png"
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
            current_keys = [get_key(row) for row in guests_data]
            keys_to_remove = [ key for key in log.keys() if key not in current_keys ]
            for key in keys_to_remove:
                entry = log[key]
                _delete_qr_file(f"{key}-qrcode.png")
                del log[key]
                changed = True
        elif log:
            logger.warning("Attention : aucun invité lu (CSV/SQL vide ou en erreur) — synchronisation ignorée pour éviter de tout supprimer.")

        # Synchronise les invités du CSV ou de la base de données SQL Server avec le log YAML
        for row in guests_data:
            key = get_key(row)
            
            #Add new guests infos
            if key not in log:
                row.token = key
                row.qr_uuid=generate_qr_uuid()
                _write_qr_file(row)
                log[key] = asdict(row)
                changed = True

            #Update existing guests infos
            else:
                entry = log[key]
                if (  entry.get("sexe") != row.sexe
                or entry.get("categorie") != row.categorie
                or entry.get("role") != row.role
                or entry.get("mail") != row.mail
                or entry.get("contact") != row.contact):
                    entry["sexe"] = row.sexe
                    entry["categorie"] = row.categorie
                    entry["role"] = row.role
                    entry["mail"] = row.mail
                    entry["contact"] = row.contact
                    changed = True

        output = [_invite_from_dict(data) for data in log.values()]
                
        if changed:
            _write_log(log, output)

        return output 


def list_guests() -> list[Invite]:
    '''
    Trier liste inviter par ordre croisson de (prenom, nom)
    '''
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
            None,)
        key = existing_key or invite.token
        log[key] = asdict(invite)
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
    if config.SQL_DB:
        organizers = SQL_REPO.load(Organisateur, table_name="Organizers")
        if organizers:
            return {org.mail:asdict(org) for org in organizers}
        else:
            return {}
    else:
        rows = {}
        if not os.path.exists(config.ORGANIZERS_PATH):
            return rows 
        
        with open(config.ORGANIZERS_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
                rows.append({raw['mail']:row.get("mail")})
                
        return rows
#
def _write_organizers(organizers: dict) -> None:
    if config.SQL_DB:
        table = SQL_REPO.create(Organisateur, table_name="organizers", primary_key="mail")
        table_content = SQL_REPO.load(Organisateur, table_name="organizers")
        for key, data in organizers.items(): #insert or delete
            organisateur = [org for org in table_content if org.mail==key][0] #mail is unique, so no duplicates
            organisateur.password_hash = data.get("password_hash")
            SQL_REPO.update(organisateur, table, primary_key='mail') 
    else:
        os.makedirs(os.path.dirname(config.ORGANIZERS_LOG_PATH), exist_ok=True)
        with open(config.ORGANIZERS_LOG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(organizers, f, allow_unicode=True, sort_keys=True)

def _organisateur_from_dict(data: dict) -> Organisateur:
    return Organisateur(
        prenom=data["prenom"],
        nom=data["nom"],
        sexe=Sexe(data.get("sexe") or "homme"),
        password_hash=data.get("password_hash"),
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
        if login in organizers.keys():
            return False
        organizers[login] = {"password_hash": password_hash}
        _write_organizers(organizers)
        return True


def accepted_organizers() -> list[Organisateur]:
    """Retourne la liste des invités organisateurs acceptés."""
    if config.SQL_DB:
        return SQL_REPO.load(Organisateur, table_name="organizers") 
    else:
        rows = []
        if not os.path.exists(config.ORGANIZERS_PATH):
            return rows
        
        with open(config.ORGANIZERS_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for data in reader:
                rows.append(  _organisateur_from_dict(data) )
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
    b = load_guests()
    url = qr_code_url( b[0] )
    path = _write_qr_file(b[0])
    print('ww')