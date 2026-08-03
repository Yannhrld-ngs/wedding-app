"""
Persistance sans base de données :
- la liste des invités est un CSV (identité : prenom,nom,email,sexe,categorie),
  édité à la main et considéré comme la source de vérité pour ces champs ;
- l'état par invité (token, QR, réponses au questionnaire, check-in) vit dans
  un log YAML, synchronisé automatiquement avec le CSV à chaque lecture ;
- les comptes organisateurs vivent dans un second fichier YAML.

Toute lecture-modification-écriture des fichiers YAML est protégée par un
verrou de fichier (filelock), pour rester correcte si plusieurs requêtes
(scans de QR code au check-in, réponses au questionnaire) arrivent en même
temps.
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
        return {}
    with open(config.GUESTS_LOG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_log(log: dict) -> None:
    os.makedirs(os.path.dirname(config.GUESTS_LOG_PATH), exist_ok=True)
    with open(config.GUESTS_LOG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(log, f, allow_unicode=True, sort_keys=True)


def _read_guests_csv() -> list[dict]:
    if not os.path.exists(config.GUESTS_CSV_PATH):
        return []
    rows = []
    with open(config.GUESTS_CSV_PATH, newline="", encoding="utf-8") as f:
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
        "email": invite.email,
        "sexe": invite.sexe.value,
        "categorie": invite.categorie,
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
        email=data.get("email"),
        sexe=Sexe(data.get("sexe") or "homme"),
        categorie=data.get("categorie"),
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
    filename = f"{slugify(invite.nom)}-{slugify(invite.prenom)}-qrcode.png"
    return f"/static/qrcodes/{filename}"


def _write_qr_file(invite: Invite) -> None:
    os.makedirs(config.QR_OUTPUT_DIR, exist_ok=True)
    img = qrcode.make(invite.qr_uuid)
    img.save(qr_code_path(invite))


def load_guests() -> list[Invite]:
    """Synchronise le CSV (identité) vers le log YAML (état) et retourne la liste
    à jour des invités. Crée token/qr_uuid/QR code pour les nouvelles lignes du
    CSV ; met à jour email/sexe/categorie pour les lignes déjà connues.
    """
    csv_rows = _read_guests_csv()

    with _guests_lock():
        log = _read_log()
        changed = False

        for row in csv_rows:
            key = natural_key(row["prenom"], row["nom"])
            sexe = Sexe.femme if row.get("sexe", "").lower() == "femme" else Sexe.homme
            categorie = row.get("categorie") or None
            email = row.get("email") or None

            if key not in log:
                invite = Invite(
                    prenom=row["prenom"],
                    nom=row["nom"],
                    email=email,
                    sexe=sexe,
                    categorie=categorie,
                    token=generate_invite_token(row["prenom"], row["nom"]),
                    qr_uuid=generate_qr_uuid(),
                )
                _write_qr_file(invite)
                log[key] = _invite_to_dict(invite)
                changed = True
            else:
                entry = log[key]
                if (
                    entry.get("email") != email
                    or entry.get("sexe") != sexe.value
                    or entry.get("categorie") != categorie
                ):
                    entry["email"] = email
                    entry["sexe"] = sexe.value
                    entry["categorie"] = categorie
                    changed = True

        if changed:
            _write_log(log)

        return [_invite_from_dict(data) for data in log.values()]


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
        return {}
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
