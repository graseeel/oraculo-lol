from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    # `src/oraculo_lol/paths.py` -> root é 3 níveis acima
    return Path(__file__).resolve().parents[2]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

