from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..datasources.liquipedia import (
    LiquipediaError,
    extract_picks_bans,
    find_match_by_teams,
    from_env as liquipedia_from_env,
)
from ..datasources.pandascore import (
    PandascoreClient,
    from_env as pandascore_from_env,
    lol_head_to_head,
    lol_match_by_id,
    lol_team_past_matches,
)
from ..models.context import (
    HeadToHead,
    LeagueRef,
    LiquipediaEnrichment,
    LiquipediaPlayerDraft,
    LiquipediaTeamDraft,
    MatchContext,
    MatchResult,
    OfficialRosterSnapshot,
    SerieRef,
    TeamHistory,
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
    try:
        data = client.paginate("/lol/players", params={"filter[team_id]": str(team_id)}, max_pages=3)
        if isinstance(data, list):
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao buscar players do time=%s err=%r", team_id, exc)
    return []


def _winner_id(match: dict[str, Any]) -> int | None:
    winner = match.get("winner")
    if isinstance(winner, dict) and "id" in winner:
        return int(winner["id"])
    return None


def _scores_for_team(match: dict[str, Any], team_id: int) -> tuple[int | None, int | None]:
    results = match.get("results")
    if not isinstance(results, list) or len(results) < 2:
        return None, None
    score_map: dict[int, int] = {}
    for r in results:
        if isinstance(r, dict) and isinstance(r.get("team"), dict) and "score" in r:
            tid = r["team"].get("id")
            if tid is not None:
                score_map[int(tid)] = int(r["score"])
    if not score_map:
        return None, None
    score_for = score_map.get(team_id)
    others = [s for tid, s in score_map.items() if tid != team_id]
    score_against = others[0] if others else None
    return score_for, score_against


def _opponent_of(match: dict[str, Any], team_id: int) -> tuple[int | None, str | None]:
    for opp in (match.get("opponents") or []):
        if not isinstance(opp, dict):
            continue
        o = opp.get("opponent")
        if not isinstance(o, dict) or "id" not in o:
            continue
        oid = int(o["id"])
        if oid != team_id:
            return oid, o.get("name")
    return None, None


def _match_to_result(match: dict[str, Any], team_id: int) -> MatchResult:
    winner_id = _winner_id(match)
    won: bool | None = None
    if winner_id is not None:
        won = (winner_id == team_id)
    score_for, score_against = _scores_for_team(match, team_id)
    opp_id, opp_name = _opponent_of(match, team_id)
    tournament_name: str | None = None
    league_name: str | None = None
    if isinstance(match.get("tournament"), dict):
        tournament_name = match["tournament"].get("name")
    if isinstance(match.get("league"), dict):
        league_name = match["league"].get("name")
    return MatchResult(
        match_id=int(match["id"]),
        date=_parse_dt(match.get("begin_at")),
        opponent_id=opp_id,
        opponent_name=opp_name,
        won=won,
        score_for=score_for,
        score_against=score_against,
        tournament_name=tournament_name,
        league_name=league_name,
    )


def _build_team_history(team: TeamRef, last_n: int = 10) -> TeamHistory:
    try:
        raw_matches = lol_team_past_matches(team_id=team.id, last_n=last_n)
        results = [_match_to_result(m, team.id) for m in raw_matches]
        logger.info("histórico time=%s (%s): %d partidas", team.id, team.name, len(results))
        return TeamHistory(team_id=team.id, team_name=team.name, matches=results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha no histórico time=%s err=%r", team.id, exc)
        return TeamHistory(team_id=team.id, team_name=team.name, matches=[])


def _build_head_to_head(team_a: TeamRef, team_b: TeamRef, last_n: int = 10) -> HeadToHead:
    try:
        raw_matches = lol_head_to_head(team_a_id=team_a.id, team_b_id=team_b.id, last_n=last_n)
        results = [_match_to_result(m, team_a.id) for m in raw_matches]
        logger.info("H2H %s vs %s: %d confrontos", team_a.name, team_b.name, len(results))
        return HeadToHead(
            team_a_id=team_a.id, team_a_name=team_a.name,
            team_b_id=team_b.id, team_b_name=team_b.name,
            matches=results,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha no H2H err=%r", exc)
        return HeadToHead(
            team_a_id=team_a.id, team_a_name=team_a.name,
            team_b_id=team_b.id, team_b_name=team_b.name,
            matches=[],
        )


def _build_liquipedia_enrichment(
    teams: list[TeamRef],
    begin_at: datetime | None,
    *,
    include_raw: bool = False,
) -> LiquipediaEnrichment:
    """
    Tenta enriquecer o contexto com picks/bans da Liquipedia.
    Fail-safe: retorna LiquipediaEnrichment(status="disabled") se a chave não estiver configurada,
    ou status="not_found"/"error" em outros casos de falha.
    """
    from ..settings import load_settings
    s = load_settings()
    if not s.liquipedia_api_key:
        logger.debug("LIQUIPEDIA_API_KEY não configurada — enriquecimento ignorado")
        return LiquipediaEnrichment(status="disabled")

    if len(teams) != 2 or begin_at is None:
        return LiquipediaEnrichment(status="disabled")

    try:
        match = find_match_by_teams(
            team_a_name=teams[0].name or "",
            team_b_name=teams[1].name or "",
            match_date=begin_at,
        )

        if match is None:
            logger.info(
                "liquipedia: partida não encontrada para %s vs %s",
                teams[0].name, teams[1].name,
            )
            return LiquipediaEnrichment(status="not_found")

        raw_draft = extract_picks_bans(match)
        if not raw_draft or not raw_draft.get("teams"):
            return LiquipediaEnrichment(
                status="not_found",
                raw=raw_draft if include_raw else None,
            )

        team_drafts = []
        for t in raw_draft["teams"]:
            players = [
                LiquipediaPlayerDraft(
                    name=p.get("name", ""),
                    champion=p.get("champion") or None,
                    role=p.get("role") or None,
                )
                for p in (t.get("players") or [])
            ]
            team_drafts.append(LiquipediaTeamDraft(
                name=t.get("name", ""),
                picks=t.get("picks", []),
                bans=t.get("bans", []),
                players=players,
            ))

        logger.info(
            "liquipedia: enriquecimento OK para %s vs %s",
            teams[0].name, teams[1].name,
        )
        return LiquipediaEnrichment(
            status="ok",
            teams=team_drafts,
            raw=raw_draft if include_raw else None,
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("liquipedia: falha no enriquecimento err=%r", exc)
        return LiquipediaEnrichment(status="error")


def build_match_context(*, pandascore_match_id: int, include_payloads: bool = True) -> MatchContext:
    client = pandascore_from_env()
    match = lol_match_by_id(match_id=pandascore_match_id)

    teams: list[TeamRef] = []
    official_rosters: list[OfficialRosterSnapshot] = []

    opponents = match.get("opponents") or []
    if isinstance(opponents, list):
        for item in opponents:
            if not isinstance(item, dict):
                continue
            opp = item.get("opponent")
            if not isinstance(opp, dict) or "id" not in opp:
                continue
            teams.append(_team_ref(opp))

    fetched_at = datetime.now(timezone.utc)

    # Rosters
    for t in teams:
        raw_players = _fetch_team_players(client, t.id)
        players = [
            {"id": int(p["id"]), "name": p.get("name"), "slug": p.get("slug")}
            for p in raw_players
            if isinstance(p, dict) and "id" in p
        ]
        official_rosters.append(
            OfficialRosterSnapshot(
                team=t,
                players=players,
                fetched_at=fetched_at,
                raw={"team_players": raw_players} if include_payloads else None,
            )
        )

    # Histórico individual
    team_histories: list[TeamHistory] = []
    for i, t in enumerate(teams):
        if i > 0:
            time.sleep(2)
        team_histories.append(_build_team_history(t))

    # Head-to-Head
    head_to_head: HeadToHead | None = None
    if len(teams) == 2:
        time.sleep(2)
        head_to_head = _build_head_to_head(teams[0], teams[1])

    # Enriquecimento Liquipedia (fail-safe)
    begin_at = _parse_dt(match.get("begin_at"))
    liquipedia_enrichment = _build_liquipedia_enrichment(
        teams,
        begin_at,
        include_raw=include_payloads,
    )

    return MatchContext(
        created_at=fetched_at,
        pandascore_match_id=int(match["id"]),
        begin_at=begin_at,
        number_of_games=match.get("number_of_games"),
        league=_league_ref(match["league"]) if isinstance(match.get("league"), dict) else None,
        serie=_serie_ref(match["serie"]) if isinstance(match.get("serie"), dict) else None,
        tournament=_tournament_ref(match["tournament"])
        if isinstance(match.get("tournament"), dict)
        else None,
        teams=teams,
        official_rosters=official_rosters,
        team_histories=team_histories,
        head_to_head=head_to_head,
        liquipedia_enrichment=liquipedia_enrichment,
        stats={},
        source_payloads={"pandascore.match": match} if include_payloads else {},
    )


def save_context_json(ctx: MatchContext) -> Path:
    s = load_settings()
    base = ensure_dir(s.abs_data_dir() / "context")
    path = base / f"pandascore_match_{ctx.pandascore_match_id}.json"
    path.write_text(
        json.dumps(ctx.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path