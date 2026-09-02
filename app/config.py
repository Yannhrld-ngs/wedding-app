import logging
import os
import yaml
from dotenv import load_dotenv

# If environment variable not exist, default values are provided below.
load_dotenv()

import urllib.parse
from sqlalchemy import create_engine, text

# --- Logs ---
LOGS_PATH = "logs/logs.log"
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
SLUG_SUFFIX_LENGTH = 6

# --- Connection à la base de donnée (PostgreSQL — ex. Neon) ---
SQL_DATABASE = os.getenv("SQL_DATABASE", default=None)
SQL_USERNAME = os.getenv("SQL_USERNAME", default=None)
SQL_PASSWORD = os.getenv("SQL_PASSWORD", default=None)
SQL_SERVER = os.getenv("SQL_SERVER", default=None)
SQL_DB = False

if SQL_USERNAME and SQL_PASSWORD and SQL_DATABASE and SQL_SERVER:
    conn_str = (
        f"postgresql://{SQL_USERNAME}:{urllib.parse.quote_plus(SQL_PASSWORD)}"
        f"@{SQL_SERVER}/{SQL_DATABASE}?sslmode=require&channel_binding=require"
    )
    try:
        engine = create_engine(conn_str, echo=False, pool_pre_ping=True, pool_recycle=1800)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';"))
            all_tables = [row[0] for row in result]
            required_tables = ["guests"]
            missing_tables = [table for table in required_tables if table not in all_tables]
            if missing_tables:
                raise FileNotFoundError(f"Les tables suivantes sont manquantes dans la base de données {SQL_DATABASE}: {', '.join(missing_tables)}")

    except Exception as e:
        logger.error(f"Erreur lors de la connexion à la base de données {SQL_DATABASE} : {e}")
    SQL_DB = True


# --- Infos du mariage --- 
with open("inputs/config.yaml", "r") as f:
    default_config = yaml.safe_load(f) 

WEDDING_NAME1 = os.getenv("WEDDING_NAME1", default=default_config["inputs"]["WEDDING_NAME1"])
WEDDING_NAME2 = os.getenv("WEDDING_NAME2", default=default_config["inputs"]["WEDDING_NAME2"])
WEDDING_DATE = os.getenv("WEDDING_DATE", default=default_config["inputs"]["WEDDING_DATE"])
WEDDING_HOUR = os.getenv("WEDDING_HOUR", default=default_config["inputs"]["WEDDING_HOUR"])
DAYS_BEFORE_CLOSING_POLL = 7

VENUE_NAME = os.getenv("VENUE_NAME", default=default_config["inputs"]["VENUE_NAME"])
VENUE_CIVIL = os.getenv("VENUE_CIVIL", default=default_config["inputs"]["VENUE_CIVIL"])
VENUE_RECEPTION = os.getenv("VENUE_RECEPTION", default=default_config["inputs"]["VENUE_RECEPTION"])

# Planning et accès affichés sur /organisateur/info-pratiques — seule l'heure
PLANNING = [
    {"heure": "10:40", "moment": "Arrivée des invités à la mairie"},
    {"heure": WEDDING_HOUR, "moment": "Début du mariage civil"},
    {"heure": "11h30", "moment": "Séance photo avec les invités"},
    {"heure": "12h00", "moment": "Séance photo des mariés uniquement"},
    {"heure": "13h00", "moment": "Mise en beauté des mariés"},
    {"heure": "14h30", "moment": "Cocktail de bienvenue"},
    {"heure": "14h55", "moment":"Installation des invités et de la chorale"},
    {"heure": "15h00", "moment":"Première prestation chorale"},
    {"heure": "15h25", "moment":"Prise de parole du modérateur"},   
    {"heure": "15h30", "moment": "Entrée du marié"},
    {"heure": "15h40", "moment": "Entrée de la mariée"},
    {"heure": "15h50", "moment": "Bénédiction pastorale"},
    {"heure": "16h30", "moment": "Discours et échange des alliances"},
    {"heure": "16h45", "moment": "Deuxième prestation de la chorale"},
    {"heure": "17h00", "moment": "Ouverture du vin d'honneur"},
    {"heure": "17h15", "moment": "Animation 1"},
    {"heure": "17h45", "moment": "Séances photos avec les invités"},
    {"heure": "18h15", "moment": "Séances photos des mariés uniquement"},
    {"heure": "18h30", "moment": "Animation 2 et logistique"},
    {"heure": "18h50", "moment": "Installation des invités à la soirée"},
    {"heure": "19h00", "moment":"Prise de parole du modérateur"},  
    {"heure": "19h05", "moment": "Entrée de la mariée"},
    {"heure": "19h15", "moment": "Entrée du marié"},
    {"heure": "19h25", "moment": "Début du repas /  Animations / Discours"},
    {"heure": "21h00", "moment": "Slow des mariés"},
    {"heure": "21h15", "moment": "Soirée"},
    {"heure": "22h00", "moment": "Coupure du gateau"},
]

# --- Local files  ---
QR_OUTPUT_DIR = os.getenv("QR_OUTPUT_DIR", default="app/static/qrcodes") 


# Images
COVER_IMAGE_URL = os.getenv("COVER_IMAGE_URL", default="/static/Images/couverture-invitation.png")
WEDDING_COLORS_URL= os.getenv("WEDDING_COLORS_URL", default="/static/Images/couleur-mariage.png")
HOME_IMAGE_URL = os.getenv("HOME_IMAGE_URL", default="/static/Images/home.png")

# URL de base utilisée pour générer les liens dans les QR codes
BASE_URL = os.getenv("BASE_URL", default="http://localhost:8000")

# List des personnes autorisées à se connecter à l'interface organisateur (login, mot de passe)
ORGANIZER_ROLES = ["accueil", "décoration", "organisation","testeur","admin"]

# --- Envoi d'email (création / réinitialisation de mot de passe organisateur) ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY", default=None)
SMTP_FROM = os.getenv("SMTP_FROM", default=f"no-reply@mariage-{WEDDING_NAME1}-et-{WEDDING_NAME2}.org")


# --- Analytics (app/analytics.py) ---
_COLUMNS = [
    "nom_complet",
    "contact",
    "presence_mairie",
    "presence_reception",
    "presence_after",
    "checked_in_mairie",
    "checked_in_reception",
    "checked_in_after",
    "questionnaire_rempli",
    "mode_transport",
    "covoiturage_possible",
    "navette_souhaitee",
    "logement",
    "consomme_alcool",
    "restriction_alimentaire",
    "restriction_alimentaire_autre",
    "chanson_1",
    "chanson_2",
    "chanson_3",
]
PHASES = ["mairie", "reception", "after"]
OUI_NON = ['oui', "non"]

PHASE_LABELS = {
    name: ("Soirée" if name == "after" else name.capitalize()) for name in PHASES
    }
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

DROIT_IMAGE_LABELS = {
    "oui": "Promis, zéro story ni post sur Facebook, TikTok, Snap ou WhatsApp !",
}

LOGEMENT_BUCKET_LABELS = {
    "trouve": "Logement trouvé",
    "besoin_aide": "Besoin d'aide",
    "pas_concerne": "Pas concerné",
}
_BOOL_COLUMNS = {"checked_in_mairie", "checked_in_reception", "checked_in_after", "questionnaire_rempli"}
