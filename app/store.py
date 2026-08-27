"""
Module de gestion du stockage des invités et des organisateurs. Toutes les
données sont lues et écrites directement dans la base de données SQL (voir
app/database.py) — il n'y a plus de fichier CSV/YAML intermédiaire.
"""
import logging
import os
from typing import Optional

import qrcode

from app import config
from app.database import SqlRepository
from app.models import Invite, Organisateur

logger = logging.getLogger(__name__)
SQL_REPO = SqlRepository(config.engine)

GUESTS_TABLE = "guests"
ORGANIZERS_TABLE = "organizers"


# ---------- Invités ----------
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
    """Charge tous les invités depuis la base de données."""
    return SQL_REPO.load(Invite, table_name=GUESTS_TABLE)


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
    """Crée ou met à jour un invité dans la base de données."""
    table = SQL_REPO.create(Invite, table_name=GUESTS_TABLE, primary_key="token")
    existing_tokens = {g.token for g in SQL_REPO.load(Invite, table_name=GUESTS_TABLE)}
    if invite.token in existing_tokens:
        SQL_REPO.update(invite, table, primary_key="token")
    else:
        SQL_REPO.insert(invite, table)


def find_by_email(email: str) -> Optional[Invite]:
    """Une personne ne doit avoir qu'un seul code actif : utilisé pour
    détecter un invité déjà enregistré pour cette adresse (ex. spectateur
    qui s'inscrirait deux fois)."""
    email = (email or "").strip().lower()
    if not email:
        return None
    return next((g for g in load_guests() if (g.mail or "").lower() == email), None)


def delete_guest(token: str) -> None:
    invite = get_by_token(token)
    if invite is None:
        return
    table = SQL_REPO.create(Invite, table_name=GUESTS_TABLE, primary_key="token")
    SQL_REPO.delete(invite, table, primary_key="token")
    _delete_qr_file(f"{token}-qrcode.png")


def reset_guests() -> None:
    """Vide entièrement la table des invités (et leurs QR codes)."""
    for invite in load_guests():
        _delete_qr_file(f"{invite.token}-qrcode.png")
    table = SQL_REPO.create(Invite, table_name=GUESTS_TABLE, primary_key="token")
    for invite in load_guests():
        SQL_REPO.delete(invite, table, primary_key="token")


# ---------- Organisateurs ----------
def get_organizer_password_hash(login: str) -> Optional[str]:
    organizer = find_accepted_organizer_by_mail(login)
    return organizer.password_hash if organizer else None


def accepted_organizers() -> list[Organisateur]:
    """Retourne la liste des organisateurs acceptés."""
    return SQL_REPO.load(Organisateur, table_name=ORGANIZERS_TABLE)


def find_accepted_organizer_by_mail(mail: str) -> Optional[Organisateur]:
    """Retourne l'organisateur accepté correspondant à cet email, sinon None."""
    mail = (mail or "").strip().lower()
    if not mail:
        return None
    return next((o for o in accepted_organizers() if (o.mail or "").lower() == mail), None)


def set_organizer_password(login: str, password_hash: str) -> None:
    """Définit le mot de passe d'un organisateur déjà accepté (présent dans la
    table organizers). N'insère pas de nouvel organisateur : celui-ci doit
    déjà exister (créé côté base de données)."""
    organizer = find_accepted_organizer_by_mail(login)
    if organizer is None:
        logger.warning(f"Tentative de définir un mot de passe pour un organisateur inconnu : {login}")
        return
    organizer.password_hash = password_hash
    table = SQL_REPO.create(Organisateur, table_name=ORGANIZERS_TABLE, primary_key="mail")
    SQL_REPO.update(organizer, table, primary_key="mail")
