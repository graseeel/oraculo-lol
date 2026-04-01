from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..datasources.pandascore import BR_DEFAULT_LEAGUE_IDS, PandascoreClient, from_env as pandascore_from_env
from ..models.rosters import RostersSnapshot, TeamRoster
from ..paths import ensure_dir
from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.agregador.rosters")


def _extract_team_from_match_opp(opp: dict[str, Any]) -> dict[str, Any] | None:
    # expected { "opponent": {team...} }
    if not isinstance(opp, dict):
        return None
    o = opp.get("opponent")
    if not isinstance(o, dict) or "id" not in o:
        return None
    return o


def _fetch_team_players(client: PandascoreClient, team_id: int) -> list[dict[str, Any]]:
    try:
        # fallback robusto: players filtrados por team_id
        data = client.paginate("/lol/players", params={"filter[team_id]": str(team_id)}, max_pages=3)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao buscar players do time=%s err=%r", team_id, exc)
    return []


def sync_rosters_from_upcoming(*, league_ids: list[int] | None = None, max_pages: int = 5) -> RostersSnapshot:
    """
    Estratégia prática (MVP): usa upcoming matches para descobrir quais times estão no circuito agora,
    e puxa /teams/{id}/players para cada um.
    """
    client = pandascore_from_env()
    league_ids = league_ids or BR_DEFAULT_LEAGUE_IDS

    params = {"filter[league_id]": ",".join(str(x) for x in league_ids)}
    matches = client.paginate("/lol/matches/upcoming", params=params, max_pages=max_pages)

    teams_by_id: dict[int, dict[str, Any]] = {}
    for m in matches:
        if not isinstance(m, dict):
            continue
        opponents = m.get("opponents") or []
        if not isinstance(opponents, list):
            continue
        for opp in opponents:
            t = _extract_team_from_match_opp(opp)
            if not t:
                continue
            tid = int(t["id"])
            teams_by_id.setdefault(tid, t)

    fetched_at = datetime.now(timezone.utc)
    team_rosters: list[TeamRoster] = []
    for tid, t in sorted(teams_by_id.items(), key=lambda kv: kv[0]):
        raw_players = _fetch_team_players(client, tid)
        players = []
        for p in raw_players:
            if "id" not in p:
                continue
            players.append(
                {
                    "pandascore_player_id": int(p["id"]),
                    "name": p.get("name"),
                    "slug": p.get("slug"),
                }
            )

        team_rosters.append(
            TeamRoster(
                pandascore_team_id=tid,
                name=t.get("name"),
                slug=t.get("slug"),
                players=players,
            )
        )

    return RostersSnapshot(
        fetched_at=fetched_at,
        scope={"league_ids": league_ids, "discovered_from": "pandascore_upcoming_matches"},
        teams=team_rosters,
    )


def save_rosters_snapshot(snapshot: RostersSnapshot) -> Path:
    s = load_settings()
    base = ensure_dir(s.abs_data_dir() / "rosters")
    path = base / "pandascore_rosters_br_latest.json"
    path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path

