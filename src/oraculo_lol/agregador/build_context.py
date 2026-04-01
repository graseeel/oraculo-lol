from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..datasources.pandascore import PandascoreClient, lol_match_by_id, from_env as pandascore_from_env
from ..models.context import (
    LeagueRef,
    MatchContext,
    OfficialRosterSnapshot,
    SerieRef,
    TeamRef,
    TournamentRef,
)
from ..paths import ensure_dir
from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.agregador.build_context")


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        # Pandascore costuma vir em ISO-8601 com Z
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:  # noqa: BLE001
        return None


def _team_ref(obj: dict[str, Any]) -> TeamRef:
    return TeamRef(id=int(obj["id"]), name=obj.get("name"), slug=obj.get("slug"))


def _league_ref(obj: dict[str, Any]) -> LeagueRef:
    return LeagueRef(id=int(obj["id"]), name=obj.get("name"), slug=obj.get("slug"))


def _tournament_ref(obj: dict[str, Any]) -> TournamentRef:
    return TournamentRef(id=int(obj["id"]), name=obj.get("name"), slug=obj.get("slug"))


def _serie_ref(obj: dict[str, Any]) -> SerieRef:
    return SerieRef(
        id=int(obj["id"]),
        full_name=obj.get("full_name") or obj.get("name"),
        season=obj.get("season"),
        year=obj.get("year"),
        slug=obj.get("slug"),
    )


def _fetch_team_players(client: PandascoreClient, team_id: int) -> list[dict[str, Any]]:
    """
    Algumas instâncias não expõem /lol/teams/{id}/players (404).
    Fallback: listar players filtrando por team_id.
    """
    try:
        data = client.paginate("/lol/players", params={"filter[team_id]": str(team_id)}, max_pages=3)
        if isinstance(data, list):
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao buscar players do time=%s err=%r", team_id, exc)
    return []


def build_match_context(*, pandascore_match_id: int, include_payloads: bool = True) -> MatchContext:
    client = pandascore_from_env()

    # Usa helper com fallback (alguns planos bloqueiam /matches/{id})
    match = lol_match_by_id(match_id=pandascore_match_id)

    teams: list[TeamRef] = []
    official_rosters: list[OfficialRosterSnapshot] = []

    # opponents: [{"opponent": {team...}}, ...]
    opponents = match.get("opponents") or []
    if isinstance(opponents, list):
        for item in opponents:
            if not isinstance(item, dict):
                continue
            opp = item.get("opponent")
            if not isinstance(opp, dict) or "id" not in opp:
                continue
            t = _team_ref(opp)
            teams.append(t)

    fetched_at = datetime.now(timezone.utc)
    for t in teams:
        raw_players = _fetch_team_players(client, t.id)
        players = []
        for p in raw_players:
            if not isinstance(p, dict) or "id" not in p:
                continue
            players.append(
                {
                    "id": int(p["id"]),
                    "name": p.get("name"),
                    "slug": p.get("slug"),
                    # "role": p.get("role")  # só se existir e for confiável
                }
            )
        official_rosters.append(
            OfficialRosterSnapshot(
                team=t,
                players=players,  # pydantic converte p/ PlayerRef
                fetched_at=fetched_at,
                raw={"team_players": raw_players} if include_payloads else None,
            )
        )

    ctx = MatchContext(
        created_at=fetched_at,
        pandascore_match_id=int(match["id"]),
        begin_at=_parse_dt(match.get("begin_at")),
        number_of_games=match.get("number_of_games"),
        league=_league_ref(match["league"]) if isinstance(match.get("league"), dict) else None,
        serie=_serie_ref(match["serie"]) if isinstance(match.get("serie"), dict) else None,
        tournament=_tournament_ref(match["tournament"])
        if isinstance(match.get("tournament"), dict)
        else None,
        teams=teams,
        official_rosters=official_rosters,
        stats={},
        source_payloads={"pandascore.match": match} if include_payloads else {},
    )
    return ctx


def save_context_json(ctx: MatchContext) -> Path:
    s = load_settings()
    base = ensure_dir(s.abs_data_dir() / "context")
    path = base / f"pandascore_match_{ctx.pandascore_match_id}.json"
    path.write_text(json.dumps(ctx.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path

