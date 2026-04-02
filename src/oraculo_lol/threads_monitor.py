from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .publisher.telegram import send_alert_safe
from .settings import load_settings

logger = logging.getLogger("oraculo_lol.threads_monitor")

# Token Threads expira em 60 dias após criação
TOKEN_LIFETIME_DAYS = 60

# Alerta começa N dias antes de expirar
ALERT_BEFORE_DAYS = 5


def check_threads_token() -> None:
    """
    Verifica se o token Threads está próximo de expirar.
    Alerta via Telegram se faltar <= ALERT_BEFORE_DAYS dias.
    Deve ser chamado uma vez por ciclo do scheduler.
    """
    s = load_settings()

    if not s.threads_token_created_at:
        logger.debug("THREADS_TOKEN_CREATED_AT não configurado — monitor ignorado")
        return

    try:
        created_at = datetime.fromisoformat(s.threads_token_created_at).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        logger.warning(
            "THREADS_TOKEN_CREATED_AT com formato inválido: %r — use YYYY-MM-DD",
            s.threads_token_created_at,
        )
        return

    expires_at = created_at + timedelta(days=TOKEN_LIFETIME_DAYS)
    now = datetime.now(timezone.utc)
    days_left = (expires_at - now).days

    if days_left < 0:
        msg = (
            "🚨 <b>Token Threads EXPIRADO</b>\n\n"
            f"O token expirou há {abs(days_left)} dia(s).\n"
            "O bot não consegue mais postar no Threads.\n\n"
            "Acesse o Meta for Developers e gere um novo token.\n"
            "Atualize THREADS_ACCESS_TOKEN e THREADS_TOKEN_CREATED_AT no .env."
        )
        logger.error("token Threads expirado há %d dias", abs(days_left))
        send_alert_safe(msg)
        return

    if days_left <= ALERT_BEFORE_DAYS:
        msg = (
            f"⚠️ <b>Token Threads expira em {days_left} dia(s)</b>\n\n"
            f"Data de expiração: {expires_at.strftime('%d/%m/%Y')}\n\n"
            "Acesse o Meta for Developers e renove o token antes que expire.\n"
            "Atualize THREADS_ACCESS_TOKEN e THREADS_TOKEN_CREATED_AT no .env."
        )
        logger.warning("token Threads expira em %d dias", days_left)
        send_alert_safe(msg)
        return

    logger.debug("token Threads ok — expira em %d dias (%s)", days_left, expires_at.strftime("%d/%m/%Y"))