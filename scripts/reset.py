"""
Réinitialise l'état local généré par l'app :
- supprime tous les QR codes dans app/static/qrcodes (config.QR_OUTPUT_DIR) ;
- vide data/invites_log.yaml (régénéré automatiquement au prochain accès) ;
- vide data/organizers.yaml (comptes organisateurs + mots de passe) — DEMANDE
  toujours une confirmation séparée, ce fichier étant le seul à contenir des
  identifiants de connexion.

Usage :
    python scripts/reset.py          # supprime QR + invites_log sans demander,
                                      # demande confirmation avant de vider organizers.yaml
    python scripts/reset.py --yes    # ne demande rien, y compris pour organizers.yaml (scripts/CI)
"""
import sys
import os
import glob

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import yaml

from app import config


def _reset_qr_codes() -> None:
    qr_files = glob.glob(os.path.join(config.QR_OUTPUT_DIR, "*.png"))
    for f in qr_files:
        os.remove(f)
    print(f"{len(qr_files)} QR code(s) supprimé(s).")


def _reset_yaml_file(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump({}, f, allow_unicode=True, sort_keys=True)


def main():
    skip_confirm = "--yes" in sys.argv

    # QR codes + invites_log.yaml : régénérables automatiquement depuis le
    # CSV/SQL, pas besoin de confirmation.
    _reset_qr_codes()
    _reset_yaml_file(config.GUESTS_LOG_PATH)
    print(f"{config.GUESTS_LOG_PATH} vidé.")

    # organizers.yaml : contient les mots de passe des organisateurs, une
    # confirmation dédiée est toujours demandée (sauf --yes explicite).
    if not skip_confirm:
        reponse = input(
            f"\nVider {config.ORGANIZERS_PATH} ? Cela supprime tous les comptes "
            "organisateurs et leurs mots de passe. (o/N) "
        ).strip().lower()
        if reponse != "o":
            print("organizers.yaml conservé tel quel.")
            return

    _reset_yaml_file(config.ORGANIZERS_PATH)
    print(f"{config.ORGANIZERS_PATH} vidé.")


if __name__ == "__main__":
    main()
