from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException, status

from app.config import SECRET_KEY, SESSION_COOKIE_NAME

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY)

SESSION_MAX_AGE = 60 * 60 * 12  # 12h, largement suffisant pour le jour J
RESET_TOKEN_MAX_AGE = 60 * 60  # 1h de validité pour un lien de création/réinitialisation de mot de passe


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_session_token(login: str) -> str:
    return serializer.dumps({"login": login})


def read_session_token(token: str) -> str | None:
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("login")
    except (BadSignature, SignatureExpired):
        return None


def create_password_reset_token(email: str) -> str:
    return serializer.dumps({"email": email, "purpose": "password_reset"})


def read_password_reset_token(token: str) -> str | None:
    """Retourne l'email si le token est valide et non expiré, sinon None."""
    try:
        data = serializer.loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if data.get("purpose") != "password_reset":
        return None
    return data.get("email")


def get_current_organizer_login(request: Request) -> str:
    """Dependency FastAPI : lève 401 si pas connecté, sinon retourne le login."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    login = read_session_token(token) if token else None
    if not login:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/organisateur/login"})
    return login
