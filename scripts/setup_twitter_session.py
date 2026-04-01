"""
Setup de sessão do X (Twitter) — rode UMA VEZ para salvar o login.

Uso:
    python -m scripts.setup_twitter_session

O Chrome vai abrir visível sem detecção de bot.
Faça login normalmente com @OraculoLoL_BR.
O script detecta o login automaticamente e fecha.

Se a sessão expirar, rode novamente.
"""
from __future__ import annotations

import time
from pathlib import Path

SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "browser_session"

LOGIN_TIMEOUT_S = 300  # 5 minutos
CHECK_INTERVAL_S = 3


def _is_logged_in(driver: object) -> bool:  # type: ignore[type-arg]
    try:
        url = driver.current_url  # type: ignore[union-attr]
        return (
            isinstance(url, str)
            and "x.com" in url
            and "login" not in url
            and "i/flow" not in url
            and "signup" not in url
        )
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("ERRO: undetected-chromedriver não instalado.")
        print("Rode: pip install undetected-chromedriver")
        return 1

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Sessão será salva em: {SESSION_DIR}")
    print()
    print("=" * 60)
    print("O Chrome vai abrir direto no login do X.")
    print("Faça login com a conta @OraculoLoL_BR.")
    print("O script detecta o login e fecha automaticamente.")
    print("=" * 60)
    print()

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={SESSION_DIR}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    driver = uc.Chrome(options=options, headless=False, version_main=146)

    try:
        driver.get("https://x.com/login")

        print("Aguardando login", end="", flush=True)

        elapsed = 0
        logged_in = False
        while elapsed < LOGIN_TIMEOUT_S:
            time.sleep(CHECK_INTERVAL_S)
            elapsed += CHECK_INTERVAL_S
            print(".", end="", flush=True)

            if _is_logged_in(driver):
                logged_in = True
                break

        print()

        if not logged_in:
            print("TIMEOUT: login não detectado em 5 minutos. Tente novamente.")
            driver.quit()
            return 1

        time.sleep(3)
        print("✓ Login detectado! Sessão salva com sucesso.")
        print("O bot vai usar essa sessão automaticamente.")

    finally:
        driver.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())