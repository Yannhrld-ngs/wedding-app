"""
Synchronise la liste des invités (voir GUESTS_PATH dans app/config.py) vers
le log YAML : crée token, QR de check-in et fichier QR pour chaque nouvel
invité, puis affiche le lien de carte de chacun.

Cette synchronisation se fait aussi automatiquement à chaque requête de
l'application (dashboard, carte d'invitation...) — ce script n'est utile que
pour obtenir d'un coup la liste des liens à envoyer, sans lancer le serveur.

Usage :
    python scripts/sync_guests.py
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app import store
from app.config import BASE_URL


def main():
    invites = store.list_guests()
    for invite in invites:
        print(f"{invite.prenom} {invite.nom}")
        print(f"  Lien invitation : {BASE_URL}/invite/{invite.token}")
        print(f"  QR code check-in : {store.qr_code_path(invite)}")
    print(f"\n{len(invites)} invité(s) au total.")


if __name__ == "__main__":
    main()
