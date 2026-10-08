"""
Simulation de charge du quiz en direct : N "téléphones" jouent en même temps contre le serveur.

Chaque joueur fait exactement ce que fait la page du quiz : il interroge l'état toutes les 2 s
et répond à chaque question après un temps de réflexion aléatoire. Un superviseur simulé
démarre la partie, révèle les réponses et passe aux questions suivantes.

Mesures : temps de réponse, erreurs, données échangées, CPU / mémoire du serveur.

Utilisation (le serveur doit tourner, et le quiz doit avoir des questions) :
    .venv/Scripts/python.exe tools/simulation_quiz.py
    .venv/Scripts/python.exe tools/simulation_quiz.py --joueurs 50 --questions 3 --url http://127.0.0.1:8000

⚠️ Écrit dans la vraie base : les réponses simulées sont effacées à la fin (Réinitialiser),
   mais ne lancez pas ce test pendant une vraie partie.
"""

import argparse
import asyncio
import random
import statistics
import sys
import time
from pathlib import Path

import httpx
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, store  # noqa: E402
from app.security import create_session_token  # noqa: E402

INTERVALLE_SONDAGE = 2.0  # same polling interval as the quiz page
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console defaults to cp1252


class Mesures:
    def __init__(self):
        self.temps = {"etat": [], "repondre": []}
        self.erreurs = {"etat": 0, "repondre": 0}
        self.octets = 0
        self.debut = time.perf_counter()

    def ajouter(self, type_requete: str, duree: float, reponse: httpx.Response | None):
        if reponse is None or reponse.status_code >= 500:
            self.erreurs[type_requete] += 1
            return
        self.temps[type_requete].append(duree)
        self.octets += len(reponse.content) + len(reponse.request.content or b"")


async def joueur(client: httpx.AsyncClient, token: str, mesures: Mesures, fin: asyncio.Event):
    await asyncio.sleep(random.uniform(0, INTERVALLE_SONDAGE))  # phones don't all start at the same ms
    deja_repondu = set()
    while not fin.is_set():
        t0 = time.perf_counter()
        try:
            r = await client.get(f"/organisateur/animation/quiz/etat/{token}")
            mesures.ajouter("etat", time.perf_counter() - t0, r)
            etat = r.json() if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            mesures.ajouter("etat", time.perf_counter() - t0, None)
            etat = {}

        numero = etat.get("numero")
        if etat.get("phase") == "question" and numero not in deja_repondu and etat.get("question"):
            deja_repondu.add(numero)
            asyncio.create_task(repondre(client, token, numero, etat["question"]["reponses"], mesures))
        await asyncio.sleep(INTERVALLE_SONDAGE)


async def repondre(client: httpx.AsyncClient, token: str, numero: int, reponses: list, mesures: Mesures):
    await asyncio.sleep(random.uniform(1, 8))  # thinking time
    t0 = time.perf_counter()
    try:
        r = await client.post(f"/organisateur/animation/quiz/repondre/{token}",
                              data={"numero": numero, "choix": random.choice(reponses)["id"]})
        mesures.ajouter("repondre", time.perf_counter() - t0, r)
    except httpx.HTTPError:
        mesures.ajouter("repondre", time.perf_counter() - t0, None)


def processus_serveur(port: int):
    """The process listening on the port, plus its children (uvicorn --reload / gunicorn workers)."""
    for connexion in psutil.net_connections(kind="tcp"):
        if connexion.laddr and connexion.laddr.port == port and connexion.status == psutil.CONN_LISTEN and connexion.pid:
            parent = psutil.Process(connexion.pid)
            return [parent, *parent.children(recursive=True)]
    return []


async def surveiller_serveur(processus: list, releves: list, fin: asyncio.Event):
    for p in processus:
        p.cpu_percent(None)  # first call only starts the measurement
    while not fin.is_set():
        await asyncio.sleep(1)
        try:
            cpu = sum(p.cpu_percent(None) for p in processus) / psutil.cpu_count()
            ram = sum(p.memory_info().rss for p in processus) / 1024 / 1024
            releves.append((cpu, ram))
        except psutil.Error:
            pass


def centile(valeurs: list, c: float) -> float:
    return sorted(valeurs)[min(len(valeurs) - 1, int(len(valeurs) * c))] if valeurs else 0


async def main():
    parser = argparse.ArgumentParser(description="Simule N joueurs sur le quiz en direct.")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--joueurs", type=int, default=50)
    parser.add_argument("--questions", type=int, default=3, help="nombre de questions jouées")
    parser.add_argument("--duree-question", type=float, default=15, help="secondes avant d'afficher la réponse")
    parser.add_argument("--duree-reponse", type=float, default=6, help="secondes sur la réponse avant la suivante")
    args = parser.parse_args()

    invites = store.list_guests()
    admin = next((o for o in store.accepted_organizers() if o.role == "admin"), None)
    if not invites or not admin:
        sys.exit("Il faut au moins un invité et un organisateur admin dans la base.")
    tokens = [invites[i % len(invites)].token for i in range(args.joueurs)]
    if len(invites) < args.joueurs:
        print(f"ℹ️  {len(invites)} invités en base pour {args.joueurs} joueurs : certains appareils partagent un invité "
              f"(la charge de sondage est la même, seules {len(invites)} réponses par question seront acceptées).")

    limites = httpx.Limits(max_connections=args.joueurs * 2)
    async with httpx.AsyncClient(base_url=args.url, timeout=30, limits=limites) as client, \
               httpx.AsyncClient(base_url=args.url, timeout=30,
                                 cookies={config.SESSION_COOKIE_NAME: create_session_token(admin.mail)}) as superviseur:

        async def action(nom: str):
            r = await superviseur.post(f"/organisateur/animation/quiz/superviser/{nom}", follow_redirects=False)
            if r.status_code != 303 or "dashboard" in r.headers.get("location", "") or "login" in r.headers.get("location", ""):
                sys.exit(f"Action superviseur « {nom} » refusée ({r.status_code}). Le serveur tourne-t-il sur {args.url} ?")

        etat = (await client.get(f"/organisateur/animation/quiz/etat/{tokens[0]}")).json()
        nb_questions = min(args.questions, etat["total"])
        if not nb_questions:
            sys.exit("Le quiz n'a aucune question : ajoutez-en avant la simulation.")

        processus = processus_serveur(int(httpx.URL(args.url).port or 80))
        mesures, releves, fin = Mesures(), [], asyncio.Event()
        print(f"▶ {args.joueurs} joueurs, {nb_questions} question(s), serveur {args.url} "
              f"({'CPU/RAM mesurés' if processus else 'processus serveur introuvable : CPU/RAM non mesurés'})")

        await action("reinitialiser")
        taches = [asyncio.create_task(joueur(client, t, mesures, fin)) for t in tokens]
        surveillance = asyncio.create_task(surveiller_serveur(processus, releves, fin))
        try:
            await action("demarrer")
            for i in range(nb_questions):
                print(f"  question {i + 1}/{nb_questions}…")
                await asyncio.sleep(args.duree_question)
                await action("reveler")
                await asyncio.sleep(args.duree_reponse)
                await action("suivante")
            await asyncio.sleep(INTERVALLE_SONDAGE * 2)  # players see the end screen
        finally:
            fin.set()
            await asyncio.gather(*taches, surveillance, return_exceptions=True)
            await action("reinitialiser")  # simulated answers are removed

    duree = time.perf_counter() - mesures.debut
    etats, reps = mesures.temps["etat"], mesures.temps["repondre"]
    print("\n=== Résultats ===")
    print(f"Durée : {duree:.0f} s | requêtes : {len(etats) + len(reps)} ({(len(etats) + len(reps)) / duree:.1f}/s)")
    for nom, valeurs in (("état (sondage)", etats), ("réponse", reps)):
        if valeurs:
            print(f"Temps de réponse {nom:15}: médiane {statistics.median(valeurs) * 1000:.0f} ms | "
                  f"95 % < {centile(valeurs, 0.95) * 1000:.0f} ms | max {max(valeurs) * 1000:.0f} ms")
    print(f"Erreurs : {mesures.erreurs['etat']} sur l'état, {mesures.erreurs['repondre']} sur les réponses")
    print(f"Données échangées : {mesures.octets / 1024:.0f} Ko au total, "
          f"soit {mesures.octets / 1024 / duree:.1f} Ko/s ({mesures.octets * 8 / 1000 / duree:.0f} kbit/s)")
    if releves:
        cpus, rams = [r[0] for r in releves], [r[1] for r in releves]
        print(f"Serveur : CPU moyen {statistics.mean(cpus):.0f} % (pic {max(cpus):.0f} %) de la machine | "
              f"RAM {max(rams):.0f} Mo max")
    print("\nℹ️  Les images et vidéos du quiz sont lues directement sur Backblaze par les téléphones :"
          "\n   elles ne passent pas par votre machine et ne sont pas comptées ici.")


if __name__ == "__main__":
    asyncio.run(main())
