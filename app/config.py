import os
import yaml
from dotenv import load_dotenv

load_dotenv()
# If environment variable not exist, default values are provided below.

# --- Sécurité ---
SECRET_KEY = os.getenv("SECRET_KEY", default=None)  # Clé secrète pour Flask (session, CSRF, etc.)
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", default="wedding_organizer_session")

# --- Stockage  ---
GUESTS_CSV_PATH = os.getenv("GUESTS_CSV_PATH", default="scripts/invites_exemple.csv")
GUESTS_LOG_PATH = os.getenv("GUESTS_LOG_PATH", default="data/invites_log.yaml")
ORGANIZERS_PATH = os.getenv("ORGANIZERS_PATH", default="data/organizers.yaml")
QR_OUTPUT_DIR = os.getenv("QR_OUTPUT_DIR", default="app/static/qrcodes")

# --- Infos du mariage --- 
# save personal information in a yaml file that must be included in .gitignore 
# to avoid sharing personal information publicly
with open("data/config.yaml", "r") as f:
    default_config = yaml.safe_load(f) 

WEDDING_NAME1 = os.getenv("WEDDING_NAME1", default=default_config["inputs"]["WEDDING_NAME1"])
WEDDING_NAME2 = os.getenv("WEDDING_NAME2", default=default_config["inputs"]["WEDDING_NAME2"])
WEDDING_DATE = os.getenv("WEDDING_DATE", default=default_config["inputs"]["WEDDING_DATE"])
VENUE_NAME = os.getenv("VENUE_NAME", default=default_config["inputs"]["VENUE_NAME"])
VENUE_CIVIL = os.getenv("VENUE_CIVIL", default=default_config["inputs"]["VENUE_CIVIL"])
VENUE_RECEPTION = os.getenv("VENUE_RECEPTION", default=default_config["inputs"]["VENUE_RECEPTION"])

VENUE_ACCESS_INFO = [
    {"mode": "Voiture", "detail": "Parking sur place, à compléter"},
    {"mode": "Train", "detail": "Gare de Dax, puis taxi/covoiturage, à compléter"},
    {"mode": "Covoiturage", "detail": "Un groupe sera organisé, à compléter"},
]
VENUE_SCHEDULE = [
    {"heure": "15h00", "moment": "Cérémonie"},
    {"heure": "17h00", "moment": "Cocktail"},
    {"heure": "20h00", "moment": "Dîner"},
    {"heure": "22h00", "moment": "Soirée dansante"},
]

# Photo de couverture affichée sur la carte d'invitation (chemin servi via /static)
COVER_IMAGE_URL = os.getenv("COVER_IMAGE_URL", default="/static/Images/couverture-invitation.png")

# URL de base utilisée pour générer les liens dans les QR codes
BASE_URL = os.getenv("BASE_URL", default="http://localhost:8000")
