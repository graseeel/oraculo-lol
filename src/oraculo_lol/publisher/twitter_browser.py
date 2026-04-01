from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger("oraculo_lol.publisher.twitter_browser")

SESSION_DIR = Path(__file__).resolve().parents[4] / "data" / "browser_session"


class TwitterBrowserError(RuntimeError):
    pass


def post_tweet_browser(text: str) -> bool:
    """
    Posta um tweet usando a sessão salva pelo setup_twitter_session.py.
    Retorna True se postou, False se falhou.

    Pré-requisito: rodar `python -m scripts.setup_twitter_session` uma vez.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        logger.error("playwright não instalado — rode: pip install playwright && playwright install chromium")
        return False

    if not SESSION_DIR.exists():
        logger.warning(
            "sessão do X não encontrada em %s — "
            "rode: python -m scripts.setup_twitter_session",
            SESSION_DIR,
        )
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                headless=True,
                args=["--no-sandbox"],
            )

            page = browser.new_page()

            # Verifica se a sessão ainda é válida
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30_000)
            time.sleep(3)

            if "login" in page.url or "i/flow" in page.url:
                logger.warning(
                    "sessão do X expirou — rode: python -m scripts.setup_twitter_session"
                )
                browser.close()
                return False

            # Clicar na caixa de composição do tweet
            compose = page.locator('[data-testid="tweetTextarea_0"]').first
            compose.wait_for(state="visible", timeout=15_000)
            compose.click()
            time.sleep(0.5)
            compose.fill(text)
            time.sleep(0.5)

            # Botão de postar
            post_btn = page.locator('[data-testid="tweetButtonInline"]').first
            post_btn.wait_for(state="visible", timeout=10_000)
            post_btn.click()
            time.sleep(3)

            logger.info("tweet postado via browser (%d chars)", len(text))
            browser.close()
            return True

    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao postar via browser: %r", exc)
        return False