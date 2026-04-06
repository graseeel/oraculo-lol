from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.datasources.liquipedia")

WIKI = "leagueoflegends"

# Mapeamento Pandascore → Liquipedia (case-sensitive na Liquipedia)
# Validado consultando a API com [[opponent::NOME]]
_PANDASCORE_TO_LIQUIPEDIA: dict[str, str] = {
    # CBLOL
    "fluxo w7m": "Fluxo W7M",
    "los grandes": "LOS",
    "vivo keyd stars": "Keyd Stars",
    "vivo keyd stars academy": "Keyd Stars Academy",
    "red canids kalunga": "RED Canids",
    "red canids": "RED Canids",
    "furia esports": "FURIA",
    "loud": "LOUD",
    "leviatan esports": "Leviatán",   # com acento — validado na API
    "leviatán": "Leviatán",
    "pain gaming": "paiN Gaming",
    # Circuito Desafiante
    "estral esports": "Estral Esports",
    "kabum! e-sports": "KaBuM! IDL",
    "kabum! esports": "KaBuM! IDL",
    "kabum! ilha das lendas": "KaBuM! IDL",
    "kabum!": "KaBuM! IDL",
    "red academy": "RED Academy",
    "vivo keyd academy": "Keyd Stars Academy",
    "pain gaming academy": "PaiN Gaming Academy",
    "pain academy": "PaiN Gaming Academy",
    "rmd gaming": "RMD Gaming",
    "7rex": "7REX",
    "7rex team": "7REX",
    "ei nerd esports": "Ei Nerd Esports",
    "intz e-sports": "INTZ",
    "intz": "INTZ",
    "team solid": "Team Solid (Brazilian team)",  # nome completo na Liquipedia
}


class LiquipediaError(RuntimeError):
    pass


def _to_liquipedia_name(pandascore_name: str) -> str:
    """Converte nome do Pandascore para o nome exato usado na Liquipedia."""
    return _PANDASCORE_TO_LIQUIPEDIA.get(pandascore_name.lower(), pandascore_name)


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
                logger.warning(
                    "liquipedia request failed; retry_in=%ss url=%s err=%r", wait, url, exc
                )
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


def find_match_by_teams(
    *,
    team_a_name: str,
    team_b_name: str,
    match_date: datetime,
    tolerance_hours: int = 48,
) -> dict[str, Any] | None:
    """
    Busca uma partida na Liquipedia pelos nomes dos times e data aproximada.
    Usa o mapeamento Pandascore→Liquipedia validado via API.
    Fail-safe: retorna None se não encontrar ou falhar.
    """
    try:
        client = from_env()

        liq_name_a = _to_liquipedia_name(team_a_name)
        liq_name_b = _to_liquipedia_name(team_b_name)

        results = client.paginate(
            "/match",
            params={
                "conditions": f"[[opponent::{liq_name_a}]]",
                "order": "date DESC",
            },
            limit=50,
            max_pages=2,
        )

        if not results:
            logger.debug("liquipedia: nenhum match para opponent=%s", liq_name_a)
            return None

        tolerance_s = tolerance_hours * 3600
        best: dict[str, Any] | None = None
        best_delta: float = float("inf")

        for m in results:
            opp_names = [
                o.get("name", "") for o in (m.get("match2opponents") or [])
                if isinstance(o, dict)
            ]
            if liq_name_b not in opp_names:
                continue

            date_str = m.get("date")
            if not date_str:
                continue

            try:
                match_dt = datetime.fromisoformat(str(date_str).replace(" ", "T"))
                if match_dt.tzinfo is None:
                    match_dt = match_dt.replace(tzinfo=timezone.utc)
                delta = abs((match_dt - match_date.astimezone(timezone.utc)).total_seconds())

                if delta <= tolerance_s and delta < best_delta:
                    best_delta = delta
                    best = m
            except Exception:  # noqa: BLE001
                pass

        if best:
            logger.info(
                "liquipedia: match encontrado para %s vs %s (delta=%.0fs)",
                liq_name_a, liq_name_b, best_delta,
            )
        else:
            logger.debug(
                "liquipedia: match não encontrado para %s vs %s dentro de %dh",
                liq_name_a, liq_name_b, tolerance_hours,
            )

        return best

    except LiquipediaError as exc:
        logger.warning("liquipedia: falha ao buscar match err=%r", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("liquipedia: erro inesperado err=%r", exc)
        return None


def extract_picks_bans(match: dict[str, Any]) -> dict[str, Any]:
    """
    Extrai picks, bans e stats de jogadores de um match da Liquipedia.
    Usa match2games[0].extradata.vetophase para o draft em ordem.
    Usa match2games[0].participants para jogador + campeão + role + KDA.

    Retorna:
    {
      "teams": [
        {
          "name": "RED Canids",
          "picks": ["Ambessa", "Pantheon", ...],
          "bans":  ["Jarvan IV", "Vi", ...],
          "players": [
            {"name": "Zynts", "champion": "Ambessa", "role": "top",
             "kills": 2, "deaths": 2, "assists": 7}
          ]
        },
        ...
      ]
    }
    Fail-safe: retorna dict vazio se não houver dados.
    """
    try:
        opponents = match.get("match2opponents") or []
        games = match.get("match2games") or []

        if not opponents or not games:
            return {}

        game = games[0]
        extradata = game.get("extradata") or {}
        participants = game.get("participants") or {}

        team_names = [o.get("name", f"Time {i+1}") for i, o in enumerate(opponents)]
        teams: list[dict[str, Any]] = [
            {"name": name, "picks": [], "bans": [], "players": []}
            for name in team_names
        ]

        # Draft em ordem via vetophase
        vetophase = extradata.get("vetophase") or {}
        if isinstance(vetophase, dict):
            for _, entry in sorted(vetophase.items(), key=lambda x: int(x[0])):
                if not isinstance(entry, dict):
                    continue
                team_idx = int(entry.get("team", 1)) - 1
                action_type = entry.get("type", "")
                champion = entry.get("character", "")

                if not champion or team_idx >= len(teams):
                    continue

                if action_type == "ban":
                    teams[team_idx]["bans"].append(champion)
                elif action_type == "pick":
                    teams[team_idx]["picks"].append(champion)

        # Jogadores com campeão, role e KDA
        for key, p in participants.items():
            if not isinstance(p, dict) or not p:
                continue
            try:
                parts = str(key).split("_")
                if len(parts) != 2:
                    continue
                team_idx = int(parts[0]) - 1
                if team_idx >= len(teams):
                    continue
                teams[team_idx]["players"].append({
                    "name": p.get("displayName") or p.get("player", ""),
                    "champion": p.get("character", ""),
                    "role": p.get("role", ""),
                    "kills": p.get("kills"),
                    "deaths": p.get("deaths"),
                    "assists": p.get("assists"),
                })
            except (ValueError, TypeError):
                continue

        return {"teams": teams}

    except Exception as exc:  # noqa: BLE001
        logger.warning("liquipedia: falha ao extrair picks/bans err=%r", exc)
        return {}


def fetch_recent_drafts(
    *,
    team_a_name: str,
    team_b_name: str,
    last_n: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """
    Busca os últimos N drafts de cada time separadamente.
    Útil para análise de picks preferidos em jogos futuros sem draft disponível.
    Retorna: {"team_a": [...], "team_b": [...]}
    Fail-safe: retorna listas vazias em caso de erro.
    """
    result: dict[str, list[dict[str, Any]]] = {"team_a": [], "team_b": []}

    try:
        client = from_env()

        for key, name in [("team_a", team_a_name), ("team_b", team_b_name)]:
            liq_name = _to_liquipedia_name(name)
            try:
                matches = client.paginate(
                    "/match",
                    params={
                        "conditions": f"[[opponent::{liq_name}]] AND [[finished::1]]",
                        "order": "date DESC",
                    },
                    limit=last_n,
                    max_pages=1,
                )
                for m in matches[:last_n]:
                    draft = extract_picks_bans(m)
                    if draft and any(t.get("picks") for t in draft.get("teams", [])):
                        opponent_name = next(
                            (o.get("name") for o in (m.get("match2opponents") or [])
                             if o.get("name") != liq_name),
                            "?"
                        )
                        result[key].append({
                            "date": m.get("date"),
                            "opponent": opponent_name,
                            "winner": m.get("winner"),
                            "draft": draft,
                        })
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "liquipedia: falha ao buscar drafts de %s err=%r", liq_name, exc
                )

    except Exception as exc:  # noqa: BLE001
        logger.warning("liquipedia: erro em fetch_recent_drafts err=%r", exc)

    return result