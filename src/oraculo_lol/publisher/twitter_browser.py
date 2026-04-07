from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger("oraculo_lol.publisher.twitter_browser")

SESSION_DIR = Path(__file__).resolve().parents[3] / "data" / "browser_session"


class TwitterBrowserError(RuntimeError):
    pass


def post_tweet_browser(text: str, *, reply_to_id: str | None = None) -> str | None:
    """
    Posta um tweet usando undetected-chromedriver com sessão salva.
    Retorna o tweet_id (str) se postou, None se falhou.

    Se reply_to_id for fornecido, navega até o tweet e responde.
    Pré-requisito: rodar `python -m scripts.setup_twitter_session` uma vez.
    """
    try:
        import undetected_chromedriver as uc  # noqa: PLC0415
    except ImportError:
        logger.error("undetected-chromedriver não instalado")
        return None

    if not SESSION_DIR.exists():
        logger.warning(
            "sessão do X não encontrada em %s — "
            "rode: python -m scripts.setup_twitter_session",
            SESSION_DIR,
        )
        return None

    try:
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={SESSION_DIR}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")

        driver = uc.Chrome(options=options, headless=False, version_main=146)

        try:
            from selenium.webdriver.common.by import By  # noqa: PLC0415
            from selenium.webdriver.support import expected_conditions as EC  # noqa: PLC0415
            from selenium.webdriver.support.ui import WebDriverWait  # noqa: PLC0415
            from selenium.webdriver.common.keys import Keys  # noqa: PLC0415
            from selenium.webdriver.common.action_chains import ActionChains  # noqa: PLC0415
            import pyperclip  # noqa: PLC0415

            wait = WebDriverWait(driver, 15)

            if reply_to_id:
                # Navega até o tweet original para fazer reply
                driver.get(f"https://x.com/i/web/status/{reply_to_id}")
                time.sleep(4)

                current_url = driver.current_url
                if "login" in current_url or "i/flow" in current_url:
                    logger.warning("sessão do X expirou")
                    driver.quit()
                    return None

                # Clica no botão de reply do tweet
                reply_btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, '[data-testid="reply"]')
                    )
                )
                reply_btn.click()
                time.sleep(2)

                # A caixa de reply aparece no modal
                compose = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]')
                    )
                )
            else:
                # Post normal — vai para home
                driver.get("https://x.com/home")
                time.sleep(3)

                current_url = driver.current_url
                if "login" in current_url or "i/flow" in current_url:
                    logger.warning("sessão do X expirou")
                    driver.quit()
                    return None

                compose = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]')
                    )
                )

            # Escreve o texto via clipboard
            compose.click()
            time.sleep(1)
            ActionChains(driver).key_down(Keys.COMMAND).send_keys("a").key_up(Keys.COMMAND).perform()
            time.sleep(0.3)
            compose.send_keys(Keys.DELETE)
            time.sleep(0.3)
            pyperclip.copy(text)
            time.sleep(0.5)
            compose.click()
            time.sleep(0.5)
            ActionChains(driver).key_down(Keys.COMMAND).send_keys("v").key_up(Keys.COMMAND).perform()
            time.sleep(2)

            # Posta
            post_btn = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-testid="tweetButtonInline"]')
                )
            )
            driver.execute_script("arguments[0].click();", post_btn)
            time.sleep(4)

            # Tenta capturar o tweet_id da URL atual após postar
            tweet_id = None
            try:
                current = driver.current_url
                # URL após postar: https://x.com/user/status/TWEET_ID
                if "/status/" in current:
                    tweet_id = current.split("/status/")[-1].split("?")[0].strip()
            except Exception:  # noqa: BLE001
                pass

            action = "reply" if reply_to_id else "tweet"
            logger.info("%s postado via browser (%d chars) tweet_id=%s", action, len(text), tweet_id)
            driver.quit()
            return tweet_id or "ok"

        except Exception as exc:  # noqa: BLE001
            import traceback
            logger.warning("falha ao postar via browser: %r", exc)
            logger.warning("traceback: %s", traceback.format_exc())
            driver.quit()
            return None

    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao iniciar browser: %r", exc)
        return None