from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TeamRef(BaseModel):
    id: int
    name: str | None = None
    slug: str | None = None


class PlayerRef(BaseModel):
    id: int
    name: str | None = None
    slug: str | None = None
    role: str | None = None


class LeagueRef(BaseModel):
    id: int
    name: str | None = None
    slug: str | None = None


class TournamentRef(BaseModel):
    id: int
    name: str | None = None
    slug: str | None = None


class SerieRef(BaseModel):
    id: int
    full_name: str | None = None
    season: str | None = None
    year: int | None = None
    slug: str | None = None


class OfficialRosterSnapshot(BaseModel):
    source: Literal["pandascore"] = "pandascore"
    team: TeamRef
    players: list[PlayerRef] = Field(default_factory=list)
    fetched_at: datetime
    raw: dict[str, Any] | None = None


class RiotEnrichment(BaseModel):
    status: Literal["disabled", "missing_mapping", "ok", "partial", "error"] = "disabled"
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Liquipedia enrichment
# ---------------------------------------------------------------------------

class LiquipediaPlayerDraft(BaseModel):
    name: str
    champion: str | None = None
    role: str | None = None


class LiquipediaTeamDraft(BaseModel):
    name: str
    picks: list[str] = Field(default_factory=list)
    bans: list[str] = Field(default_factory=list)
    players: list[LiquipediaPlayerDraft] = Field(default_factory=list)


class RecentDraft(BaseModel):
    """Draft de uma partida recente — usado como histórico de picks para jogos futuros."""
    date: str | None = None
    opponent: str | None = None
    teams: list[LiquipediaTeamDraft] = Field(default_factory=list)


class LiquipediaEnrichment(BaseModel):
    """
    Enriquecimento via Liquipedia — picks, bans e composições.

    status='ok'          → draft do jogo específico disponível (partida passada)
    status='recent_only' → jogo futuro sem draft; recent_drafts tem histórico de picks
    status='not_found'   → partida não encontrada na Liquipedia
    status='disabled'    → chave não configurada
    status='error'       → falha na API
    """
    status: Literal["disabled", "not_found", "ok", "recent_only", "error"] = "disabled"
    teams: list[LiquipediaTeamDraft] = Field(default_factory=list)
    recent_drafts: dict[str, list[RecentDraft]] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Histórico de partidas
# ---------------------------------------------------------------------------

class MatchResult(BaseModel):
    match_id: int
    date: datetime | None = None
    opponent_name: str | None = None
    opponent_id: int | None = None
    won: bool | None = None
    score_for: int | None = None
    score_against: int | None = None
    tournament_name: str | None = None
    league_name: str | None = None


class TeamHistory(BaseModel):
    team_id: int
    team_name: str | None = None
    matches: list[MatchResult] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len([m for m in self.matches if m.won is not None])

    @property
    def wins(self) -> int:
        return len([m for m in self.matches if m.won is True])

    @property
    def losses(self) -> int:
        return len([m for m in self.matches if m.won is False])

    @property
    def winrate(self) -> float | None:
        if self.total == 0:
            return None
        return self.wins / self.total


class HeadToHead(BaseModel):
    team_a_id: int
    team_a_name: str | None = None
    team_b_id: int
    team_b_name: str | None = None
    matches: list[MatchResult] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len([m for m in self.matches if m.won is not None])

    @property
    def team_a_wins(self) -> int:
        return len([m for m in self.matches if m.won is True])

    @property
    def team_b_wins(self) -> int:
        return len([m for m in self.matches if m.won is False])


# ---------------------------------------------------------------------------
# Contexto completo da partida
# ---------------------------------------------------------------------------

class MatchContext(BaseModel):
    version: Literal["v1"] = "v1"
    created_at: datetime

    pandascore_match_id: int

    begin_at: datetime | None = None
    number_of_games: int | None = None

    league: LeagueRef | None = None
    serie: SerieRef | None = None
    tournament: TournamentRef | None = None

    teams: list[TeamRef] = Field(default_factory=list)
    official_rosters: list[OfficialRosterSnapshot] = Field(default_factory=list)

    team_histories: list[TeamHistory] = Field(default_factory=list)
    head_to_head: HeadToHead | None = None

    liquipedia_enrichment: LiquipediaEnrichment = Field(
        default_factory=LiquipediaEnrichment
    )

    stats: dict[str, Any] = Field(default_factory=dict)
    riot_enrichment: RiotEnrichment = Field(default_factory=RiotEnrichment)
    source_payloads: dict[str, Any] = Field(default_factory=dict)