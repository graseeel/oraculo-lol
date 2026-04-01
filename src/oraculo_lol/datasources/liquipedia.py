from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.datasources.liquipedia")

# Wiki do LoL na Liquipedia
WIKI = "leagueoflegends"

# Slugs dos torneios BR para filtrar nas queries
CBLOL_TOURNAMENT_SLUG = "CBLOL"
BR_TOURNAMENT_SLUGS = ["CBLOL", "CBLOL Academy"]


class LiquipediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiquipediaClient:
    api_key: str
    base_url: str = "https://api.liquipedia.net/api/v3"
    timeout_s: float = 20.0
    max_retries: int = 4
    # Rate limit gentil: Liquipedia pede 1 req/s no plano free
    rate_limit_s: float = 1.2

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Apikey {self.api_key}",
            "Accept": "application/json",
        }

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        params = dict(params or {})
        params.setdefault("wiki", WIKI)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s, headers=self._headers()) as client:
                    resp = client.get(url, params=params)
                # Respeita rate limit e erros transientes
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "liquipedia transient status=%s; retry_in=%ss url=%s",
                        resp.status_code, wait, url,
                    )
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    raise LiquipediaError(
                        f"liquipedia error status={resp.status_code} url={url} body={resp.text[:500]}"
                    )
                # Pausa gentil entre requests (rate limit free tier)
                time.sleep(self.rate_limit_s)
                return resp.json()
            except LiquipediaError:
                raise
            except Exception as exc:
                last_exc = exc
                wait = min(2 ** attempt, 30)
                logger.warning("liquipedia request failed; retry_in=%ss url=%s err=%r", wait, url, exc)
                time.sleep(wait)

        raise LiquipediaError(f"liquipedia failed after retries url={url} err={last_exc!r}")

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int = 50,
        max_pages: int = 10,
    ) -> list[Any]:
        """
        Paginação via offset/limit (padrão Liquipedia API v3).
        """
        out: list[Any] = []
        params = dict(params or {})
        params["limit"] = limit

        for page in range(max_pages):
            params["offset"] = page * limit
            resp = self.get(path, params=params)
            chunk = resp.get("result", []) if isinstance(resp, dict) else []
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < limit:
                break
        return out


def from_env() -> LiquipediaClient:
    s = load_settings()
    if not s.liquipedia_api_key:
        raise LiquipediaError("LIQUIPEDIA_API_KEY não configurada")
    return LiquipediaClient(api_key=s.liquipedia_api_key)


def upcoming_br_matches(*, max_pages: int = 5) -> list[dict[str, Any]]:
    """
    Próximas partidas BR (CBLOL + CBLOL Academy) via Liquipedia.
    Retorna lista de matches no formato da API v3.
    """
    client = from_env()
    conditions = " OR ".join(
        f'[[tournament_liquipediatier::premier]] AND [[tournament_name::{slug}::*]]'
        for slug in BR_TOURNAMENT_SLUGS
    )
    return client.paginate(
        "/match",
        params={
            "conditions": conditions,
            "order": "date_start ASC",
        },
        max_pages=max_pages,
    )


def team_by_name(*, team_name: str) -> dict[str, Any] | None:
    """
    Busca time pelo nome na Liquipedia (ex.: 'LOUD', 'paiN Gaming').
    """
    client = from_env()
    results = client.paginate(
        "/team",
        params={"conditions": f"[[name::{team_name}]]"},
        limit=1,
        max_pages=1,
    )
    return results[0] if results else None


def players_by_team(*, team_name: str) -> list[dict[str, Any]]:
    """
    Lista jogadores ativos de um time (ex.: 'LOUD').
    """
    client = from_env()
    return client.paginate(
        "/player",
        params={
            "conditions": f"[[team::{team_name}]] AND [[status::Active]]",
        },
        max_pages=2,
    )


def tournament_by_name(*, name: str) -> dict[str, Any] | None:
    """
    Busca torneio pelo nome (ex.: 'CBLOL 2025 Split 1').
    """
    client = from_env()
    results = client.paginate(
        "/tournament",
        params={"conditions": f"[[name::{name}::*]]"},
        limit=5,
        max_pages=1,
    )
    return results[0] if results else None