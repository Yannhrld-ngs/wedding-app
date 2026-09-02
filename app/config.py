import logging
import os
import yaml
from dotenv import load_dotenv

# If environment variable not exist, default values are provided below.
load_dotenv()

import urllib.parse
from sqlalchemy import create_engine, text

# --- Logs ---
LOGS_PATH = "data/logs.log"
os.makedirs(os.path.dirname(LOGS_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# --- Sécurité ---
SECRET_KEY = os.getenv("SECRET_KEY", default="secret")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", default="wedding_organizer_session")

# --- Connection à la base de donnée (PostgreSQL — ex. Neon) ---
SQL_DATABASE = os.getenv("SQL_DATABASE", default=None)
SQL_USERNAME = os.getenv("SQL_USERNAME", default=None)
SQL_PASSWORD = os.getenv("SQL_PASSWORD", default=None)
SQL_SERVER = os.getenv("SQL_SERVER", default=None)
SQL_DB = False
engine = None 

if SQL_USERNAME and SQL_PASSWORD and SQL_DATABASE and SQL_SERVER:
    conn_str = (
        f"postgresql://{SQL_USERNAME}:{urllib.parse.quote_plus(SQL_PASSWORD)}"
        f"@{SQL_SERVER}/{SQL_DATABASE}?sslmode=require&channel_binding=require"
    )
    try:
        engine = create_engine(conn_str, echo=False,pool_pre_ping=True, pool_recycle=1800)
    except Exception as e:
        logger.error(f"Erreur lors de la connexion à la base de données {SQL_DATABASE} : {e}")
    SQL_DB = True


# --- Infos du mariage --- 
with open("inputs/config.yaml", "r", encoding="utf-8") as f:
    default_config = yaml.safe_load(f) 

WEDDING_NAME1 = os.getenv("WEDDING_NAME1", default=default_config["inputs"]["WEDDING_NAME1"])
WEDDING_NAME2 = os.getenv("WEDDING_NAME2", default=default_config["inputs"]["WEDDING_NAME2"])
WEDDING_DATE = os.getenv("WEDDING_DATE", default=default_config["inputs"]["WEDDING_DATE"])
WEDDING_HOUR = os.getenv("WEDDING_HOUR", default=default_config["inputs"]["WEDDING_HOUR"])
DAYS_BEFORE_CLOSING_POLL = 7

VENUE_NAME = os.getenv("VENUE_NAME", default=default_config["inputs"]["VENUE_NAME"])
VENUE_RECEPTION = os.getenv("VENUE_RECEPTION", default=default_config["inputs"]["VENUE_RECEPTION"])

PLANNING = [
    {"heure": WEDDING_HOUR, "moment": "Ouverture des portes"},
    {"heure": "à confirmer", "moment": "Diffusion du film"},
]

# --- Local files  ---
QR_OUTPUT_DIR = os.getenv("QR_OUTPUT_DIR", default="app/static/qrcodes")

# Images
COVER_IMAGE_URL = os.getenv("COVER_IMAGE_URL", default="/static/Images/couverture-invitation.png")
WEDDING_COLORS_URL= os.getenv("WEDDING_COLORS_URL", default="/static/Images/couleur-mariage.png")
HOME_IMAGE_URL = os.getenv("HOME_IMAGE_URL", default="/static/Images/home.png")
ABOUT_IMAGE_URL = os.getenv(
    "ABOUT_IMAGE_URL",
    default="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='500'%3E"
    "%3Crect width='400' height='500' fill='%23e8e0d2'/%3E"
    "%3Ctext x='50%25' y='50%25' font-family='sans-serif' font-size='18' fill='%23968a76' "
    "text-anchor='middle' dominant-baseline='middle'%3EVotre photo%3C/text%3E%3C/svg%3E",
)

# Réseaux sociaux (page d'accueil, section Contact)
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", default="https://www.instagram.com/")

# URL de base utilisée pour générer les liens dans les QR codes
BASE_URL = os.getenv("BASE_URL", default="http://localhost:80")

# List des personnes autorisées à se connecter à l'interface organisateur (login, mot de passe)
ORGANIZER_ROLES = ["accueil", "décoration", "organisation","testeur","admin"]

# --- Envoi d'email (création / réinitialisation de mot de passe organisateur) ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY", default=None)
SMTP_FROM = os.getenv("SMTP_FROM", default=f"no-reply@mariage-{WEDDING_NAME1}-et-{WEDDING_NAME2}.org")


# --- Analytics (app/analytics.py) ---
_COLUMNS = [
    "nom_complet",
    "contact",
    "presence_diffusion",
    "checked_in_diffusion",
]
PHASES = ["diffusion"]
OUI_NON = ['oui', "non"]

PHASE_LABELS = {name: name.capitalize() for name in PHASES}
OUI_NON_LABELS = {
    name: name.capitalize() for name in OUI_NON
    }
PRESENCE_AFTER_LABELS = {
    "oui": "Oui",
    "en_reflexion": "En réflexion",
    "non": "Non",
    }
CONSOMME_ALCOOL_LABELS = {
    "oui": "Oui",
    "non": "Non",
    "sans_reponse": "Sans réponse",
    }
RESTRICTION_LABELS = {
    "aucune": "Pas concerné(e)",
    "halal": "Halal",
    "vegetarien": "Végétarien",
    "vegetalien": "Vegan",
    "autre": "Autres",
    }
TRANSPORT_LABELS = {
    "pas_concerne": "Pas concerné(e)",
    "voiture": "Voiture personnelle",
    "train": "Train",
    "covoiturage": "Covoiturage",
    "en_reflexion": "En réflexion",
    "autre": "Autre",
    }
LOGEMENT_LABELS = {
    "pas_concerne": "Pas concerné(e)",
    "oui": "Oui",
    "ne_sait_pas": "Non",
    "toujours_en_recherche": "En recherche",
}
LOGEMENT_BUCKET_LABELS = {
    "trouve": "Logement trouvé",
    "besoin_aide": "Besoin d'aide",
    "pas_concerne": "Pas concerné",
}
_BOOL_COLUMNS = {"checked_in_diffusion"}
