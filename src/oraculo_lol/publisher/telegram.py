from __future__ import annotations

import logging

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.publisher.telegram")

TELEGRAM_API = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


def _send(token: str, chat_id: str, text: str, timeout_s: float = 10.0) -> bool:
    """
    Envia mensagem via Telegram Bot API.
    Retorna True se enviou, False se falhou.
    Nunca levanta exceção — fail-safe por design.
    """
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        if resp.status_code >= 400:
            logger.warning("telegram error status=%s body=%s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao enviar alerta telegram: %r", exc)
        return False


def send_alert(text: str) -> bool:
    """
    Envia alerta para o chat configurado em TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.
    Fail-safe: retorna False silenciosamente se não configurado ou se falhar.
    """
    s = load_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        logger.debug("telegram não configurado — alerta ignorado")
        return False
    return _send(token=s.telegram_bot_token, chat_id=s.telegram_chat_id, text=text)


def send_alert_safe(text: str) -> None:
    """Wrapper sem retorno — ideal para uso no scheduler onde o resultado não importa."""
    send_alert(text)