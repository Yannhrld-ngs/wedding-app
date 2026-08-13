"""Envoi d'email via l'API Brevo (HTTPS, port 443) plutôt que SMTP — certains
hébergeurs bloquent les ports SMTP sortants (25/465/587), l'API HTTPS n'a pas
ce problème. Si BREVO_API_KEY n'est pas configuré dans .env, le message est
simplement affiché dans la console — pratique en dev."""
import logging

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from app import config

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    if not config.BREVO_API_KEY:
        logger.warning(f"[email non envoyé — BREVO_API_KEY non configurée] À : {to} — Sujet : {subject}\n{body}")
        return

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = config.BREVO_API_KEY
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        sender={"email": config.SMTP_FROM},
        to=[{"email": to}],
        subject=subject,
        text_content=body,
    )

    try:
        api_instance.send_transac_email(send_smtp_email)
    except ApiException as e:
        logger.error(f"[échec envoi email via l'API Brevo] À : {to}\n{e}")
