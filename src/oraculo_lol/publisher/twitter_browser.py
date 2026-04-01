from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger("oraculo_lol.publisher.twitter_browser")

SESSION_DIR = Path(__file__).resolve().parents[3] / "data" / "browser_session"


class TwitterBrowserError(RuntimeError):
    pass


def post_tweet_browser(text: str) -> bool:
    """
    Posta um tweet usando undetected-chromedriver com sessão salva.
    Retorna True se postou, False se falhou.

    Pré-requisito: rodar `python -m scripts.setup_twitter_session` uma vez.
    """
    try:
        import undetected_chromedriver as uc  # noqa: PLC0415
    except ImportError:
        logger.error("undetected-chromedriver não instalado — rode: pip install undetected-chromedriver")
        return False

    if not SESSION_DIR.exists():
        logger.warning(
            "sessão do X não encontrada em %s — "
            "rode: python -m scripts.setup_twitter_session",
            SESSION_DIR,
        )
        return False

    try:
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={SESSION_DIR}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")

        driver = uc.Chrome(options=options, headless=False, version_main=146)

        try:
            # Verifica se a sessão ainda é válida
            driver.get("https://x.com/home")
            time.sleep(3)

            current_url = driver.current_url
            if "login" in current_url or "i/flow" in current_url:
                logger.warning(
                    "sessão do X expirou — rode: python -m scripts.setup_twitter_session"
                )
                driver.quit()
                return False

            # Caixa de composição do tweet
            from selenium.webdriver.common.by import By  # noqa: PLC0415
            from selenium.webdriver.support import expected_conditions as EC  # noqa: PLC0415
            from selenium.webdriver.support.ui import WebDriverWait  # noqa: PLC0415

            wait = WebDriverWait(driver, 15)
            compose = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]'))
            )
            # Clica na caixa e garante foco
            compose.click()
            time.sleep(1)
            # Limpa qualquer texto residual
            from selenium.webdriver.common.keys import Keys  # noqa: PLC0415
            from selenium.webdriver.common.action_chains import ActionChains  # noqa: PLC0415
            ActionChains(driver).key_down(Keys.COMMAND).send_keys("a").key_up(Keys.COMMAND).perform()
            time.sleep(0.3)
            compose.send_keys(Keys.DELETE)
            time.sleep(0.3)
            # Copia e cola via clipboard (suporta emojis)
            import pyperclip  # noqa: PLC0415
            pyperclip.copy(text)
            time.sleep(0.5)
            compose.click()
            time.sleep(0.5)
            ActionChains(driver).key_down(Keys.COMMAND).send_keys("v").key_up(Keys.COMMAND).perform()
            time.sleep(2)

            # Botão de postar — usa JS click para bypassar elementos sobrepostos
            post_btn = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetButtonInline"]'))
            )
            driver.execute_script("arguments[0].click();", post_btn)
            time.sleep(3)

            logger.info("tweet postado via undetected-chromedriver (%d chars)", len(text))
            driver.quit()
            return True

        except Exception as exc:  # noqa: BLE001
            import traceback
            logger.warning("falha ao postar via browser: %r", exc)
            logger.warning("traceback: %s", traceback.format_exc())
            driver.quit()
            return False

    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao iniciar browser: %r", exc)
        return False