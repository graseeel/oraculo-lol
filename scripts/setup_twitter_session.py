"""
Setup de sessão do X (Twitter) — rode UMA VEZ para salvar o login.

Uso:
    python -m scripts.setup_twitter_session

O Firefox vai abrir direto na página de login do X.
Faça login normalmente. O script detecta e fecha automaticamente.

Se a sessão expirar, rode novamente.
"""
from __future__ import annotations

import time
from pathlib import Path

FIREFOX_EXECUTABLE = "/Applications/Firefox.app/Contents/MacOS/firefox"
SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "browser_session"

LOGIN_TIMEOUT_S = 300  # 5 minutos
CHECK_INTERVAL_S = 3


def _is_logged_in(page: object) -> bool:  # type: ignore[type-arg]
    try:
        url = page.evaluate("window.location.href")  # type: ignore[union-attr]
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
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERRO: playwright não instalado.")
        print("Rode: pip install playwright && playwright install firefox")
        return 1

    if not Path(FIREFOX_EXECUTABLE).exists():
        print(f"ERRO: Firefox não encontrado em {FIREFOX_EXECUTABLE}")
        return 1

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Sessão será salva em: {SESSION_DIR}")
    print()
    print("=" * 60)
    print("O Firefox vai abrir direto no login do X.")
    print("Faça login com a conta @OraculoLoL_BR.")
    print("O script detecta o login e fecha automaticamente.")
    print("=" * 60)
    print()

    with sync_playwright() as p:
        browser = p.firefox.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            executable_path=FIREFOX_EXECUTABLE,
            # Pula tela de boas-vindas e onboarding do Firefox
            firefox_user_prefs={
                "browser.startup.homepage_override.mstone": "ignore",
                "startup.homepage_welcome_url": "",
                "startup.homepage_welcome_url.additional": "",
                "browser.startup.firstrunSkipsHomepage": True,
                "trailhead.firstrun.branches": "",
                "browser.aboutwelcome.enabled": False,
                "datareporting.policy.dataSubmissionPolicyBypassNotification": True,
            },
        )

        page = browser.new_page()
        page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=30_000)

        print("Aguardando login", end="", flush=True)

        elapsed = 0
        logged_in = False
        while elapsed < LOGIN_TIMEOUT_S:
            time.sleep(CHECK_INTERVAL_S)
            elapsed += CHECK_INTERVAL_S
            print(".", end="", flush=True)

            if _is_logged_in(page):
                logged_in = True
                break

        print()

        if not logged_in:
            print("TIMEOUT: login não detectado em 5 minutos. Tente novamente.")
            browser.close()
            return 1

        time.sleep(3)
        print("✓ Login detectado! Sessão salva com sucesso.")
        print("O bot vai usar essa sessão automaticamente.")
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())