from __future__ import annotations

import logging
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.datasources.liquipedia")

WIKI = "leagueoflegends"
BR_TOURNAMENT_SLUGS = ["CBLOL", "CBLOL Academy"]


class LiquipediaError(RuntimeError):
    pass


def _normalize(s: str) -> str:
    """Remove acentos e converte para lowercase para comparação."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


@dataclass(frozen=True)
class LiquipediaClient:
    api_key: str
    base_url: str = "https://api.liquipedia.net/api/v3"
    timeout_s: float = 20.0
    max_retries: int = 4
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
    client = from_env()
    conditions = " OR ".join(
        f'[[tournament_liquipediatier::premier]] AND [[tournament_name::{slug}::*]]'
        for slug in BR_TOURNAMENT_SLUGS
    )
    return client.paginate(
        "/match",
        params={"conditions": conditions, "order": "date_start ASC"},
        max_pages=max_pages,
    )


def team_by_name(*, team_name: str) -> dict[str, Any] | None:
    client = from_env()
    results = client.paginate(
        "/team",
        params={"conditions": f"[[name::{team_name}]]"},
        limit=1,
        max_pages=1,
    )
    return results[0] if results else None


def players_by_team(*, team_name: str) -> list[dict[str, Any]]:
    client = from_env()
    return client.paginate(
        "/player",
        params={"conditions": f"[[team::{team_name}]] AND [[status::Active]]"},
        max_pages=2,
    )


def tournament_by_name(*, name: str) -> dict[str, Any] | None:
    client = from_env()
    results = client.paginate(
        "/tournament",
        params={"conditions": f"[[name::{name}::*]]"},
        limit=5,
        max_pages=1,
    )
    return results[0] if results else None


def find_match_by_teams(
    *,
    team_a_name: str,
    team_b_name: str,
    match_date: datetime,
    tolerance_hours: int = 24,
) -> dict[str, Any] | None:
    """
    Busca uma partida na Liquipedia pelos nomes dos times e data aproximada.
    Usa matching case-insensitive com normalização de acentos.
    Retorna o match mais próximo em data dentro da janela de tolerância.
    Fail-safe: retorna None se não encontrar ou se falhar.
    """
    try:
        client = from_env()

        # Janela de busca: ±tolerance_hours ao redor da data do match
        date_from = (match_date - timedelta(hours=tolerance_hours)).strftime("%Y-%m-%d %H:%M:%S")
        date_to = (match_date + timedelta(hours=tolerance_hours)).strftime("%Y-%m-%d %H:%M:%S")

        conditions = f"[[date_start::>{date_from}]] AND [[date_start::<{date_to}]]"

        results = client.paginate(
            "/match",
            params={
                "conditions": conditions,
                "order": "date_start ASC",
            },
            limit=50,
            max_pages=2,
        )

        if not results:
            logger.debug("liquipedia: nenhuma partida encontrada na janela de %dh", tolerance_hours)
            return None

        a_norm = _normalize(team_a_name)
        b_norm = _normalize(team_b_name)

        best: dict[str, Any] | None = None
        best_delta: float = float("inf")

        for m in results:
            opponents = m.get("match2opponents") or []
            opp_names = [_normalize(o.get("name", "")) for o in opponents if isinstance(o, dict)]

            # Verifica se ambos os times estão no match
            a_found = any(a_norm in n or n in a_norm for n in opp_names)
            b_found = any(b_norm in n or n in b_norm for n in opp_names)

            if not (a_found and b_found):
                continue

            # Calcula delta de tempo
            date_str = m.get("date") or m.get("date_start")
            if date_str:
                try:
                    match_dt = datetime.fromisoformat(str(date_str).replace(" ", "T"))
                    if match_dt.tzinfo is None:
                        match_dt = match_dt.replace(tzinfo=timezone.utc)
                    delta = abs((match_dt - match_date.astimezone(timezone.utc)).total_seconds())
                    if delta < best_delta:
                        best_delta = delta
                        best = m
                except Exception:  # noqa: BLE001
                    pass

        if best:
            logger.info(
                "liquipedia: match encontrado para %s vs %s (delta=%.0fs)",
                team_a_name, team_b_name, best_delta,
            )
        else:
            logger.debug("liquipedia: match não encontrado para %s vs %s", team_a_name, team_b_name)

        return best

    except LiquipediaError as exc:
        logger.warning("liquipedia: falha ao buscar match err=%r", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("liquipedia: erro inesperado err=%r", exc)
        return None


def extract_picks_bans(match: dict[str, Any]) -> dict[str, Any]:
    """
    Extrai picks e bans de um match da Liquipedia.
    Retorna dict com estrutura:
    {
      "teams": [
        {
          "name": "RED Canids",
          "picks": ["Azir", "Orianna", ...],
          "bans": ["Zed", "LeBlanc", ...],
          "players": [{"name": "Grevthar", "champion": "Azir", "role": "mid"}, ...]
        },
        ...
      ]
    }
    Fail-safe: retorna dict vazio se não houver dados.
    """
    try:
        opponents = match.get("match2opponents") or []
        teams = []

        for opp in opponents:
            if not isinstance(opp, dict):
                continue

            team_name = opp.get("name", "?")
            players_data = opp.get("match2players") or []
            picks: list[str] = []
            bans: list[str] = []
            players: list[dict[str, str]] = []

            for p in players_data:
                if not isinstance(p, dict):
                    continue
                champion = p.get("champion") or p.get("char", "")
                player_name = p.get("displayname") or p.get("name", "")
                role = p.get("role", "")

                if champion:
                    picks.append(champion)
                if player_name:
                    players.append({
                        "name": player_name,
                        "champion": champion,
                        "role": role,
                    })

            # Bans ficam no nível do match, não do opponent
            # Tentamos extrair do campo extradata se disponível
            extradata = opp.get("extradata") or {}
            if isinstance(extradata, dict):
                for k, v in extradata.items():
                    if "ban" in k.lower() and v:
                        bans.append(str(v))

            teams.append({
                "name": team_name,
                "picks": picks,
                "bans": bans,
                "players": players,
            })

        return {"teams": teams} if teams else {}

    except Exception as exc:  # noqa: BLE001
        logger.warning("liquipedia: falha ao extrair picks/bans err=%r", exc)
        return {}