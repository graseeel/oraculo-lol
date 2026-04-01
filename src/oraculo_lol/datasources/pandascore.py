from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.datasources.pandascore")

BR_DEFAULT_LEAGUE_IDS = [302, 5377]  # CBLOL, Circuito Desafiante (Circuitão)


class PandascoreError(RuntimeError):
    pass


def _csv(values: Iterable[int | str]) -> str:
    return ",".join(str(v) for v in values)


@dataclass(frozen=True)
class PandascoreClient:
    api_key: str
    base_url: str = "https://api.pandascore.co"
    timeout_s: float = 20.0
    max_retries: int = 4

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        params = params or {}

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s, headers=self._headers()) as client:
                    resp = client.get(url, params=params)

                # Rate limit / transient errors
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2**attempt, 30)
                    logger.warning(
                        "pandascore transient status=%s; retry_in=%ss url=%s",
                        resp.status_code,
                        wait,
                        url,
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code >= 400:
                    raise PandascoreError(
                        f"pandascore error status={resp.status_code} url={url} body={resp.text[:500]}"
                    )

                return resp.json()
            except PandascoreError:
                # Erros permanentes (ex.: 404 route not found, 401 invalid token) não devem dar retry.
                raise
            except Exception as exc:  # noqa: BLE001 - boundary: network/unknown errors can retry
                last_exc = exc
                wait = min(2**attempt, 30)
                logger.warning("pandascore request failed; retry_in=%ss url=%s err=%r", wait, url, exc)
                time.sleep(wait)

        raise PandascoreError(f"pandascore failed after retries url={url} err={last_exc!r}")

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> list[Any]:
        """
        Paginação padrão da Pandascore via page[number] / page[size].
        """
        out: list[Any] = []
        params = dict(params or {})
        params.setdefault("page[size]", per_page)

        for page_number in range(1, max_pages + 1):
            params["page[number]"] = page_number
            chunk = self.get(path, params=params)
            if not chunk:
                break
            if not isinstance(chunk, list):
                raise PandascoreError(f"expected list payload from {path}, got {type(chunk)}")
            out.extend(chunk)
            if len(chunk) < per_page:
                break
        return out


def from_env() -> PandascoreClient:
    s = load_settings()
    if not s.pandascore_api_key:
        raise PandascoreError("PANDASCORE_API_KEY não configurada")
    return PandascoreClient(api_key=s.pandascore_api_key)


def search_lol_leagues(*, name_query: str, max_pages: int = 3) -> list[dict[str, Any]]:
    """
    Busca ligas de LoL por nome (ex.: 'CBLOL', 'Circuitão').
    Útil para descobrir IDs oficiais para filtros.
    """
    client = from_env()
    # A Pandascore costuma suportar search[name]=...
    return client.paginate(
        "/lol/leagues",
        params={"search[name]": name_query},
        max_pages=max_pages,
    )


def upcoming_lol_matches(
    *,
    league_ids: list[int] | None = None,
    tournament_ids: list[int] | None = None,
    series_ids: list[int] | None = None,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """
    Próximas partidas de LoL.

    Filtros aceitos são enviados no padrão filter[<field>]=...
    (a API aceita CSV em muitos casos; mantemos flexível).
    """
    client = from_env()
    params: dict[str, Any] = {}

    if league_ids:
        params["filter[league_id]"] = _csv(league_ids)
    if tournament_ids:
        params["filter[tournament_id]"] = _csv(tournament_ids)
    if series_ids:
        params["filter[serie_id]"] = _csv(series_ids)

    return client.paginate("/lol/matches/upcoming", params=params, max_pages=max_pages)


def upcoming_br_lol_matches(*, max_pages: int = 5) -> list[dict[str, Any]]:
    """
    Atalho: próximas partidas do escopo BR inicial (CBLOL + Circuitão).
    """
    return upcoming_lol_matches(league_ids=BR_DEFAULT_LEAGUE_IDS, max_pages=max_pages)


def lol_match_by_id(*, match_id: int) -> dict[str, Any]:
    client = from_env()
    try:
        data = client.get(f"/lol/matches/{match_id}")
        if not isinstance(data, dict):
            raise PandascoreError(f"expected dict payload, got {type(data)}")
        return data
    except PandascoreError as exc:
        # Alguns tokens/planos permitem listar matches mas bloqueiam /matches/{id}.
        # Fallback: buscar via listagem com filter[id]=...
        msg = str(exc)
        if "status=403" not in msg:
            raise
        items = client.paginate("/lol/matches", params={"filter[id]": str(match_id)}, max_pages=1)
        if items and isinstance(items[0], dict):
            return items[0]
        raise


def lol_team_players(*, team_id: int) -> list[dict[str, Any]]:
    client = from_env()
    # A rota /lol/teams/{id}/players não existe em alguns ambientes (retorna 404).
    # Estratégia alternativa: listar players filtrando por team_id.
    data = client.paginate("/lol/players", params={"filter[team_id]": str(team_id)}, max_pages=3)
    if not isinstance(data, list):
        raise PandascoreError(f"expected list payload, got {type(data)}")
    return [x for x in data if isinstance(x, dict)]

