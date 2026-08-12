import os
import yaml
from dotenv import load_dotenv

# If environment variable not exist, default values are provided below.
load_dotenv()

import urllib.parse
from sqlalchemy import create_engine, text

# --- Sécurité ---
SECRET_KEY = os.getenv("SECRET_KEY", default="secret")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", default="wedding_organizer_session")

# --- Connection à la base de donnée (PostgreSQL — ex. Neon) ---
SQL_DATABASE = os.getenv("SQL_DATABASE", default=None)
SQL_USERNAME = os.getenv("SQL_USERNAME", default=None)
SQL_PASSWORD = os.getenv("SQL_PASSWORD", default=None)
SQL_SERVER = os.getenv("SQL_SERVER", default=None)
SQL_DB = False

if SQL_USERNAME and SQL_PASSWORD and SQL_DATABASE and SQL_SERVER:
    conn_str = (
        f"postgresql+psycopg2://{SQL_USERNAME}:{urllib.parse.quote_plus(SQL_PASSWORD)}"
        f"@{SQL_SERVER}/{SQL_DATABASE}?sslmode=require&channel_binding=require"
    )
    try:
        engine = create_engine(conn_str, echo=False)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';"))
            all_tables = [row[0] for row in result]
            required_tables = ["guests"]
            missing_tables = [table for table in required_tables if table not in all_tables]
            if missing_tables:
                raise FileNotFoundError(f"Les tables suivantes sont manquantes dans la base de données {SQL_DATABASE}: {', '.join(missing_tables)}")

    except Exception as e:
        print(f"Erreur lors de la connexion à la base de données {SQL_DATABASE} :", e)
    SQL_DB = True


# --- Infos du mariage --- 
# save personal information in a yaml file that must be included in .gitignore 
# to avoid sharing personal information publicly
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


# --- Local files  ---
GUESTS_PATH = "inputs/invites_list.csv"
QR_OUTPUT_DIR = "app/static/qrcodes"
GUESTS_LOG_PATH = "data/invites_log.yaml" 
ORGANIZERS_PATH = "data/organizers.yaml"

# Images
COVER_IMAGE_URL = os.getenv("COVER_IMAGE_URL", default="/static/Images/couverture-invitation.png")
WEDDING_COLORS_URL= os.getenv("WEDDING_COLORS_URL", default="/static/Images/couleur-mariage.png")
HOME_IMAGE_URL = os.getenv("HOME_IMAGE_URL", default="/static/Images/home.png")

# URL de base utilisée pour générer les liens dans les QR codes
BASE_URL = os.getenv("BASE_URL", default="http://localhost:8000")

# List des personnes autorisées à se connecter à l'interface organisateur (login, mot de passe)
ORGANIZER_ROLES = ["testeur"]

# --- Envoi d'email (création / réinitialisation de mot de passe organisateur) ---
BREVO_API_KEY = os.getenv("BREVO_API_KEY", default=None)
SMTP_FROM = os.getenv("SMTP_FROM", default=f"no-reply@mariage-{WEDDING_NAME1}-et-{WEDDING_NAME2}.org")
