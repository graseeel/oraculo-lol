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

                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2**attempt, 30)
                    logger.warning(
                        "pandascore transient status=%s; retry_in=%ss url=%s",
                        resp.status_code, wait, url,
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code >= 400:
                    raise PandascoreError(
                        f"pandascore error status={resp.status_code} url={url} body={resp.text[:500]}"
                    )

                return resp.json()
            except PandascoreError:
                raise
            except Exception as exc:  # noqa: BLE001
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
    client = from_env()
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
    return upcoming_lol_matches(league_ids=BR_DEFAULT_LEAGUE_IDS, max_pages=max_pages)


def lol_match_by_id(*, match_id: int) -> dict[str, Any]:
    client = from_env()
    try:
        data = client.get(f"/lol/matches/{match_id}")
        if not isinstance(data, dict):
            raise PandascoreError(f"expected dict payload, got {type(data)}")
        return data
    except PandascoreError as exc:
        msg = str(exc)
        if "status=403" not in msg:
            raise
        items = client.paginate("/lol/matches", params={"filter[id]": str(match_id)}, max_pages=1)
        if items and isinstance(items[0], dict):
            return items[0]
        raise


def lol_team_players(*, team_id: int) -> list[dict[str, Any]]:
    client = from_env()
    data = client.paginate("/lol/players", params={"filter[team_id]": str(team_id)}, max_pages=3)
    if not isinstance(data, list):
        raise PandascoreError(f"expected list payload, got {type(data)}")
    return [x for x in data if isinstance(x, dict)]


def lol_team_past_matches(
    *,
    team_id: int,
    last_n: int = 10,
) -> list[dict[str, Any]]:
    """
    Retorna as últimas `last_n` partidas finalizadas de um time,
    ordenadas da mais recente para a mais antiga.
    Fail-safe: erros de API retornam lista vazia.
    """
    client = from_env()
    try:
        matches = client.paginate(
            "/lol/matches",
            params={
                "filter[opponent_id]": str(team_id),
                "filter[status]": "finished",
                "sort": "-begin_at",
                "page[size]": last_n,
            },
            per_page=last_n,
            max_pages=1,
        )
    except PandascoreError as exc:
        logger.warning("falha ao buscar histórico do time=%s err=%r", team_id, exc)
        return []

    # Deduplicar por id e garantir status finished
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if mid is None or mid in seen:
            continue
        if m.get("status") != "finished":
            continue
        seen.add(mid)
        result.append(m)

    return result[:last_n]


def lol_head_to_head(
    *,
    team_a_id: int,
    team_b_id: int,
    last_n: int = 10,
) -> list[dict[str, Any]]:
    """
    Retorna as últimas `last_n` partidas finalizadas entre dois times.
    Busca por partidas onde ambos os times são opponents.
    Fail-safe: erros de API retornam lista vazia.
    """
    client = from_env()
    try:
        matches = client.paginate(
            "/lol/matches",
            params={
                "filter[opponent_id]": f"{team_a_id},{team_b_id}",
                "filter[status]": "finished",
                "sort": "-begin_at",
                "page[size]": last_n * 2,  # margem para filtrar após receber
            },
            per_page=last_n * 2,
            max_pages=1,
        )
    except PandascoreError as exc:
        logger.warning(
            "falha ao buscar H2H team_a=%s team_b=%s err=%r", team_a_id, team_b_id, exc
        )
        return []

    seen: set[int] = set()
    result: list[dict[str, Any]] = []

    for m in matches:
        if not isinstance(m, dict):
            continue
        if m.get("status") != "finished":
            continue
        mid = m.get("id")
        if mid is None or mid in seen:
            continue

        # Confirmar que os DOIS times estão nos opponents desse match
        opponents = m.get("opponents") or []
        opp_ids: set[int] = set()
        for opp in opponents:
            if isinstance(opp, dict):
                o = opp.get("opponent") or {}
                if isinstance(o, dict) and "id" in o:
                    opp_ids.add(int(o["id"]))

        if team_a_id not in opp_ids or team_b_id not in opp_ids:
            continue

        seen.add(mid)
        result.append(m)

    return result[:last_n]