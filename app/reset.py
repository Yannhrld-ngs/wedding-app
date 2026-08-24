"""
Réinitialise l'état local généré par l'app :
- supprime tous les QR codes dans app/static/qrcodes (config.QR_OUTPUT_DIR) ;
- vide data/invites.yaml (régénéré automatiquement au prochain accès) ;
- vide data/organizers.yaml (comptes organisateurs + mots de passe) — DEMANDE
  toujours une confirmation séparée, ce fichier étant le seul à contenir des
  identifiants de connexion.

Usage :
    python -m app.reset          # supprime QR + invites.yaml sans demander,
                                  # demande confirmation avant de vider organizers.yaml
    python -m app.reset --yes    # ne demande rien, y compris pour organizers.yaml (scripts/CI)
"""
import sys
import os
import glob
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import yaml

from app import config

logger = logging.getLogger(__name__)


def _reset_qr_codes(which:str = "all" ) -> None:
    '''
    Réinitialiser les QR codes invités. 
    '''
    if which == "all":
        qr_files = glob.glob(os.path.join(config.QR_OUTPUT_DIR, "*.png"))
    else:
        qr_files = glob.glob(os.path.join(config.QR_OUTPUT_DIR, f"{which}-qrcode.png"))

    for f in qr_files:
        os.remove(f)
        logger.info(f"{f} a bien été supprimé")

def _reset_yaml_file(path: str) -> None:
    '''
    Empty a yaml file.
    '''
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump({}, f, allow_unicode=True, sort_keys=True)


if __name__ == "__main__":
    _reset_qr_codes()
    _reset_yaml_file(config.GUESTS_LOG_PATH)
    _reset_yaml_file(config.ORGANIZERS_LOG_PATH)
