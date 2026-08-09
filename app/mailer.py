"""Envoi d'email minimal (smtplib, stdlib). Si SMTP n'est pas configuré dans
.env (SMTP_HOST/SMTP_USER/SMTP_PASSWORD), le message est simplement affiché
dans la console — pratique en dev, sans dépendance externe à installer."""
import smtplib
from email.message import EmailMessage

from app import config


def send_email(to: str, subject: str, body: str) -> None:
    if not (config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD):
        print(f"[email non envoyé — SMTP non configuré]\nÀ : {to}\nSujet : {subject}\n\n{body}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
