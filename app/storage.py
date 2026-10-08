"""
Stockage des fichiers (images, vidéos) sur Backblaze B2, via son API compatible S3.

Le bucket est privé : on enregistre une référence "b2://<dossier>/<fichier>" et on
génère un lien temporaire signé au moment de l'afficher.
"""

import logging
from functools import lru_cache
from typing import BinaryIO, Optional

from app import config

logger = logging.getLogger(__name__)

PREFIXE = "b2://"
DOSSIERS = ("quiz", "unmotauxmaries", "sharedphotos")
DUREE_LIEN = 6 * 3600  # validité d'un lien signé, en secondes


def actif() -> bool:
    """True si B2 est configuré dans le .env."""
    return all((config.B2_KEY_ID, config.B2_APPLICATION_KEY, config.B2_BUCKET, config.B2_ENDPOINT))


@lru_cache(maxsize=1)
def _client():
    import boto3
    from botocore.config import Config
    client = boto3.client(
        "s3",
        endpoint_url=config.B2_ENDPOINT,
        aws_access_key_id=config.B2_KEY_ID,
        aws_secret_access_key=config.B2_APPLICATION_KEY,
        # region taken from the endpoint (https://s3.<region>.backblazeb2.com): signed links need it
        region_name=config.B2_ENDPOINT.split("//")[-1].split(".")[1],
        config=Config(
            signature_version="s3v4",  # B2 rejects the legacy signature boto3 uses for links by default
            # recent boto3 adds checksums B2 doesn't always accept: only send them when required
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    # B2 only shows a folder once it contains a file: an empty placeholder creates them
    try:
        for dossier in DOSSIERS:
            client.put_object(Bucket=config.B2_BUCKET, Key=f"{dossier}/.bzEmpty", Body=b"")
    except Exception as e:
        logger.error(f"B2 : impossible de créer les dossiers (vérifiez la clé dans le .env) : {e}")
    return client


def envoyer(fichier: BinaryIO, cle: str, content_type: Optional[str] = None) -> str:
    """Envoie un fichier dans le bucket et retourne sa référence "b2://<cle>"."""
    extra = {"ContentType": content_type} if content_type else {}
    _client().upload_fileobj(fichier, config.B2_BUCKET, cle, ExtraArgs=extra)
    return PREFIXE + cle


def envoyer_chemin(chemin: str, cle: str, content_type: Optional[str] = None) -> str:
    with open(chemin, "rb") as fichier:
        return envoyer(fichier, cle, content_type)


def lister(prefixe: str) -> list[dict]:
    """Fichiers dont la clé commence par prefixe : [{"cle", "date"}]."""
    fichiers = []
    for page in _client().get_paginator("list_objects_v2").paginate(Bucket=config.B2_BUCKET, Prefix=prefixe):
        for objet in page.get("Contents", []):
            fichiers.append({"cle": objet["Key"], "date": objet["LastModified"]})
    return fichiers


def telecharger(cle: str, chemin: str) -> None:
    _client().download_file(config.B2_BUCKET, cle, chemin)


def url(contenu: Optional[str]) -> Optional[str]:
    """Lien affichable : signé pour une référence b2://, inchangé pour une URL classique."""
    if not contenu or not contenu.startswith(PREFIXE):
        return contenu
    if not actif():
        return None
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": config.B2_BUCKET, "Key": contenu[len(PREFIXE):]},
        ExpiresIn=DUREE_LIEN,
    )


def supprimer(contenu: Optional[str]) -> None:
    """Supprime le fichier d'une référence b2:// (ne fait rien pour une URL classique)."""
    if not contenu or not contenu.startswith(PREFIXE) or not actif():
        return
    try:
        _client().delete_object(Bucket=config.B2_BUCKET, Key=contenu[len(PREFIXE):])
    except Exception as e:
        logger.error(f"B2 : échec de la suppression de {contenu} : {e}")
