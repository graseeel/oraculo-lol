from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from urllib.parse import quote

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.datasources.riot")


class RiotError(RuntimeError):
    pass


# Platform routing (LoL shard)
PLATFORM_HOSTS: dict[str, str] = {
    "br1": "https://br1.api.riotgames.com",
    # outros comuns (deixando pronto pro futuro):
    "na1": "https://na1.api.riotgames.com",
    "euw1": "https://euw1.api.riotgames.com",
    "eun1": "https://eun1.api.riotgames.com",
    "la1": "https://la1.api.riotgames.com",
    "la2": "https://la2.api.riotgames.com",
}

# Regional routing (match-v5/account-v1)
REGIONAL_HOSTS: dict[str, str] = {
    "americas": "https://americas.api.riotgames.com",
    "europe": "https://europe.api.riotgames.com",
    "asia": "https://asia.api.riotgames.com",
}


def _backoff_seconds(attempt: int) -> int:
    return min(2**attempt, 30)


@dataclass(frozen=True)
class RiotClient:
    api_key: str
    timeout_s: float = 20.0
    max_retries: int = 4

    def _headers(self) -> dict[str, str]:
        return {"X-Riot-Token": self.api_key}

    def get(self, base_url: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        url = base_url.rstrip("/") + "/" + path.lstrip("/")
        params = params or {}

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s, headers=self._headers()) as client:
                    resp = client.get(url, params=params)

                # 429 (rate limit) e 5xx (transientes)
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = _backoff_seconds(attempt)
                    logger.warning(
                        "riot transient status=%s retry_in=%ss url=%s",
                        resp.status_code,
                        wait,
                        url,
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code >= 400:
                    raise RiotError(f"riot error status={resp.status_code} url={url} body={resp.text[:500]}")

                return resp.json()
            except Exception as exc:  # noqa: BLE001 - boundary: we rethrow RiotError
                last_exc = exc
                wait = _backoff_seconds(attempt)
                logger.warning("riot request failed retry_in=%ss url=%s err=%r", wait, url, exc)
                time.sleep(wait)

        raise RiotError(f"riot failed after retries url={url} err={last_exc!r}")


def from_env() -> RiotClient:
    s = load_settings()
    if not s.riot_api_key:
        raise RiotError("RIOT_API_KEY não configurada")
    return RiotClient(api_key=s.riot_api_key)


def lol_platform_status(*, platform: str = "br1") -> dict[str, Any]:
    """
    Status do shard de LoL (ex.: br1). Endpoint: lol/status/v4/platform-data
    """
    p = platform.lower()
    host = PLATFORM_HOSTS.get(p)
    if not host:
        raise RiotError(f"platform inválida: {platform!r}")
    client = from_env()
    data = client.get(host, "/lol/status/v4/platform-data")
    if not isinstance(data, dict):
        raise RiotError(f"status payload inesperado: {type(data)}")
    return data


def lol_summoner_by_name(*, summoner_name: str, platform: str = "br1") -> dict[str, Any]:
    """
    Busca Summoner por nome (plataforma). Endpoint: lol/summoner/v4/summoners/by-name/{summonerName}
    Retorna, entre outros: id (encryptedSummonerId), accountId (legado), puuid.
    """
    p = platform.lower()
    host = PLATFORM_HOSTS.get(p)
    if not host:
        raise RiotError(f"platform inválida: {platform!r}")
    client = from_env()
    # summoner_name é o "Summoner Name" legado (não é Riot ID com #tag).
    path = f"/lol/summoner/v4/summoners/by-name/{quote(summoner_name, safe='')}"
    data = client.get(host, path)
    if not isinstance(data, dict):
        raise RiotError(f"summoner payload inesperado: {type(data)}")
    return data


def lol_summoner_by_puuid(*, puuid: str, platform: str = "br1") -> dict[str, Any]:
    """
    Busca Summoner por PUUID (plataforma). Endpoint: lol/summoner/v4/summoners/by-puuid/{puuid}
    Útil quando você obtém o PUUID via account-v1 (Riot ID).
    """
    p = platform.lower()
    host = PLATFORM_HOSTS.get(p)
    if not host:
        raise RiotError(f"platform inválida: {platform!r}")
    client = from_env()
    data = client.get(host, f"/lol/summoner/v4/summoners/by-puuid/{puuid}")
    if not isinstance(data, dict):
        raise RiotError(f"summoner payload inesperado: {type(data)}")
    return data


def account_by_riot_id(*, game_name: str, tag_line: str, regional: str = "americas") -> dict[str, Any]:
    """
    Busca conta (account-v1) por Riot ID (gameName + tagLine).
    Endpoint: /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}
    Retorna: puuid, gameName, tagLine.
    """
    r = regional.lower()
    host = REGIONAL_HOSTS.get(r)
    if not host:
        raise RiotError(f"regional inválida: {regional!r}")
    client = from_env()
    gn = quote(game_name, safe="")
    tl = quote(tag_line, safe="")
    data = client.get(host, f"/riot/account/v1/accounts/by-riot-id/{gn}/{tl}")
    if not isinstance(data, dict):
        raise RiotError(f"account payload inesperado: {type(data)}")
    return data


def match_ids_by_puuid(
    *,
    puuid: str,
    regional: str = "americas",
    start: int = 0,
    count: int = 20,
) -> list[str]:
    """
    Lista IDs de partidas (match-v5) a partir do PUUID.
    Endpoint: /lol/match/v5/matches/by-puuid/{puuid}/ids
    """
    r = regional.lower()
    host = REGIONAL_HOSTS.get(r)
    if not host:
        raise RiotError(f"regional inválida: {regional!r}")
    client = from_env()
    data = client.get(
        host,
        f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
        params={"start": start, "count": count},
    )
    if not isinstance(data, list):
        raise RiotError(f"match ids payload inesperado: {type(data)}")
    return [str(x) for x in data]


def match_by_id(*, match_id: str, regional: str = "americas") -> dict[str, Any]:
    """
    Baixa detalhes de uma partida (match-v5). Endpoint: /lol/match/v5/matches/{matchId}
    """
    r = regional.lower()
    host = REGIONAL_HOSTS.get(r)
    if not host:
        raise RiotError(f"regional inválida: {regional!r}")
    client = from_env()
    data = client.get(host, f"/lol/match/v5/matches/{match_id}")
    if not isinstance(data, dict):
        raise RiotError(f"match payload inesperado: {type(data)}")
    return data

