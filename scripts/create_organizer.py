"""
Crée un compte organisateur (stocké dans le fichier YAML des organisateurs).

Usage :
    python scripts/create_organizer.py <login> <mot_de_passe>
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app import store
from app.security import hash_password


def main(login: str, password: str):
    if not store.create_organizer(login, hash_password(password)):
        print(f"Le login '{login}' existe déjà.")
        return
    print(f"Organisateur '{login}' créé avec succès.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage : python scripts/create_organizer.py <login> <mot_de_passe>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
