"""
Réinitialise l'état local généré par l'app :
- supprime tous les QR codes dans app/static/qrcodes (config.QR_OUTPUT_DIR) ;
- supprime tous les fichiers dans data/ (log des invités, organisateurs...).


Usage :
    python scripts/reset.py          # liste les fichiers et demande confirmation
    python scripts/reset.py --yes    # supprime sans demander (scripts/CI)
"""
import sys
import os
import glob

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app import config


def _files_to_delete() -> list[str]:
    qr_files = glob.glob(os.path.join(config.QR_OUTPUT_DIR, "*.png"))

    data_dir = os.path.dirname(config.GUESTS_LOG_PATH)
    data_files = []
    if os.path.isdir(data_dir):
        data_files = [
            os.path.join(data_dir, name)
            for name in os.listdir(data_dir)
            if os.path.isfile(os.path.join(data_dir, name))
        ]

    return sorted(set(qr_files) | set(data_files))


def main():
    skip_confirm = "--yes" in sys.argv
    files = _files_to_delete()

    if not files:
        print("Rien à supprimer.")
        return

    print(f"{len(files)} fichier(s) seront supprimés :")
    for f in files:
        print(f"  - {f}")

    if not skip_confirm:
        reponse = input("\nConfirmer la suppression ? (o/N) ").strip().lower()
        if reponse != "o":
            print("Annulé.")
            return

    for f in files:
        os.remove(f)

    print(f"\n{len(files)} fichier(s) supprimé(s).")


if __name__ == "__main__":
    main()
