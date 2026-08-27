"""
Réinitialise l'état local généré par l'app :
- supprime tous les QR codes dans app/static/qrcodes (config.QR_OUTPUT_DIR) ;
- vide la table des invités en base de données (store.reset_guests) ;
- vide la table des organisateurs (comptes + mots de passe) — DEMANDE
  toujours une confirmation séparée, cette table étant la seule à contenir
  des identifiants de connexion.

Usage :
    python -m app.reset          # supprime QR + invités sans demander,
                                  # demande confirmation avant de vider les organisateurs
    python -m app.reset --yes    # ne demande rien, y compris pour les organisateurs (scripts/CI)
"""
import sys
import os
import glob
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app import config, store
from app.models import Organisateur

logger = logging.getLogger(__name__)


def _reset_qr_codes(which: str = "all") -> None:
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


def _reset_organizers() -> None:
    """Vide la table des organisateurs (comptes + mots de passe)."""
    table = store.SQL_REPO.create(Organisateur, table_name=store.ORGANIZERS_TABLE, primary_key="mail")
    for organizer in store.accepted_organizers():
        store.SQL_REPO.delete(organizer, table, primary_key="mail")


if __name__ == "__main__":
    skip_confirm = "--yes" in sys.argv

    _reset_qr_codes()
    store.reset_guests()

    if skip_confirm or input("Vider aussi la table des organisateurs (comptes + mots de passe) ? [y/N] ").lower() == "y":
        _reset_organizers()
