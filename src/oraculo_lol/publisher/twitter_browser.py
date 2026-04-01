from __future__ import annotations

import logging
import time
from pathlib import Path

from ..paths import project_root
from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.publisher.twitter_browser")

# Sessão salva em disco — evita login a cada post
SESSION_DIR = project_root() / "data" / "browser_session"


class TwitterBrowserError(RuntimeError):
    pass


def _session_path() -> Path:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR


def post_tweet_browser(text: str) -> bool:
    """
    Posta um tweet via Playwright (browser automation).
    Usa sessão persistente para não fazer login toda vez.
    Retorna True se postou, False se falhou.

    AVISO: automação via browser viola os ToS do X.
    Use apenas enquanto não tiver plano pago da API.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        logger.error("playwright não instalado — rode: pip install playwright && playwright install chromium")
        return False

    s = load_settings()
    if not s.twitter_username or not s.twitter_password:
        logger.warning("TWITTER_USERNAME ou TWITTER_PASSWORD não configurados")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(_session_path()),
                headless=True,
                args=["--no-sandbox"],
            )

            page = browser.new_page()

            # Verifica se já está logado
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)

            if "login" in page.url or "i/flow" in page.url:
                logger.info("sessão expirada — fazendo login no X")
                _do_login(page, s.twitter_username, s.twitter_password)

            # Navega para home e posta
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)

            # Caixa de texto do tweet
            compose = page.locator('[data-testid="tweetTextarea_0"]').first
            compose.click()
            time.sleep(0.5)
            compose.fill(text)
            time.sleep(0.5)

            # Botão de postar
            post_btn = page.locator('[data-testid="tweetButtonInline"]').first
            post_btn.click()
            time.sleep(3)

            logger.info("tweet postado via browser (%d chars)", len(text))
            browser.close()
            return True

    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao postar via browser: %r", exc)
        return False


def _do_login(page: object, username: str, password: str) -> None:
    """Executa o fluxo de login do X."""
    from playwright.sync_api import Page  # noqa: PLC0415
    page: Page  # type: ignore[no-redef]

    page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)

    # Campo de usuário/email
    user_input = page.locator('input[autocomplete="username"]').first
    user_input.fill(username)
    time.sleep(0.5)
    page.keyboard.press("Enter")
    time.sleep(2)

    # Às vezes o X pede verificação adicional (handle/phone)
    verify = page.locator('input[data-testid="ocfEnterTextTextInput"]')
    if verify.count() > 0:
        logger.info("X pediu verificação adicional — usando username")
        verify.first.fill(username)
        page.keyboard.press("Enter")
        time.sleep(2)

    # Senha
    pass_input = page.locator('input[name="password"]').first
    pass_input.fill(password)
    time.sleep(0.5)
    page.keyboard.press("Enter")
    time.sleep(4)

    if "login" in page.url or "i/flow" in page.url:
        raise TwitterBrowserError("login falhou — verifique usuário/senha ou 2FA")

    logger.info("login no X realizado com sucesso")