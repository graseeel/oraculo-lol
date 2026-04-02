"""
Gera e instala o .plist do launchd para rodar o scheduler automaticamente.

Uso:
    python -m scripts.setup_launchd

O scheduler vai:
- Iniciar automaticamente quando o Mac ligar
- Reiniciar automaticamente se crashar
- Salvar logs em data/scheduler.log e data/scheduler_error.log
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PLIST_LABEL = "com.oraculo.lol.scheduler"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_DIR = PROJECT_ROOT / "data"


def _detect_python() -> Path:
    """Detecta o Python do venv atual."""
    venv = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv.exists():
        return venv
    # Fallback para o Python em uso agora
    return Path(sys.executable)


def _build_plist(python_path: Path) -> str:
    log_out = LOG_DIR / "scheduler.log"
    log_err = LOG_DIR / "scheduler_error.log"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>scripts.scheduler</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>{log_out}</string>

    <key>StandardErrorPath</key>
    <string>{log_err}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{python_path.parent}:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
"""


def _is_loaded() -> bool:
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main() -> int:
    python_path = _detect_python()

    print(f"Python detectado : {python_path}")
    print(f"Projeto          : {PROJECT_ROOT}")
    print(f"Plist            : {PLIST_PATH}")
    print(f"Log stdout       : {LOG_DIR}/scheduler.log")
    print(f"Log stderr       : {LOG_DIR}/scheduler_error.log")
    print()

    # Garante que o diretório de logs existe
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Para o scheduler se já estiver rodando
    if _is_loaded():
        print("⏹  Scheduler já está rodando — parando para recarregar...")
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], check=False)

    # Escreve o plist
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_build_plist(python_path), encoding="utf-8")
    print(f"✓ Arquivo .plist criado em {PLIST_PATH}")

    # Carrega no launchd
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"✗ Falha ao carregar no launchd: {result.stderr}")
        return 1

    print("✓ Scheduler carregado no launchd com sucesso!")
    print()
    print("Comandos úteis:")
    print(f"  Ver status   : launchctl list {PLIST_LABEL}")
    print(f"  Parar        : launchctl unload {PLIST_PATH}")
    print(f"  Reiniciar    : launchctl unload {PLIST_PATH} && launchctl load {PLIST_PATH}")
    print(f"  Ver logs     : tail -f {LOG_DIR}/scheduler.log")
    print(f"  Ver erros    : tail -f {LOG_DIR}/scheduler_error.log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())