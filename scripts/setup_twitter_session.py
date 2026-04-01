"""
Setup de sessão do X (Twitter) — rode UMA VEZ para salvar o login.

Uso:
    python -m scripts.setup_twitter_session

O Chromium vai abrir visível. Faça login normalmente (usuário, senha, 2FA se tiver).
Após logar, pressione ENTER no terminal para salvar a sessão e fechar o browser.
Nas próximas execuções o bot usa essa sessão sem precisar de login.

Se a sessão expirar (o X pede login de novo), rode esse script novamente.
"""
from __future__ import annotations

from pathlib import Path

SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "browser_session"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERRO: playwright não instalado.")
        print("Rode: pip install playwright && playwright install chromium")
        return 1

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Sessão será salva em: {SESSION_DIR}")
    print()
    print("=" * 60)
    print("O Chromium vai abrir. Faça login no X normalmente.")
    print("Após logar e ver o feed, volte aqui e pressione ENTER.")
    print("=" * 60)
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,  # visível para login manual
            args=["--no-sandbox"],
        )

        page = browser.new_page()
        page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=30_000)

        input("Após fazer login no X, pressione ENTER aqui para salvar a sessão...")

        # Verifica se está logado
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=15_000)
        if "login" in page.url or "i/flow" in page.url:
            print("AVISO: parece que o login não foi concluído. Tente novamente.")
            browser.close()
            return 1

        print("✓ Sessão salva com sucesso!")
        print("O bot vai usar essa sessão automaticamente nas próximas execuções.")
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())