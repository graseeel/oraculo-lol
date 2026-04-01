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
    role: str | None = None  # só preencher se a fonte trouxer algo confiável


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
    """
    Roster "oficial" para a análise: origem Pandascore por IDs.
    Não depende de texto do jogador como chave.
    """

    source: Literal["pandascore"] = "pandascore"
    team: TeamRef
    players: list[PlayerRef] = Field(default_factory=list)
    fetched_at: datetime
    raw: dict[str, Any] | None = None  # opcional p/ auditoria/debug


class RiotEnrichment(BaseModel):
    """
    Enriquecimento opcional via Riot. Fail-safe: se não houver mapping confiável, fica ausente/empty.
    """

    status: Literal["disabled", "missing_mapping", "ok", "partial", "error"] = "disabled"
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Histórico de partidas
# ---------------------------------------------------------------------------

class MatchResult(BaseModel):
    """
    Resultado de uma partida passada, da perspectiva de um time.
    won=True → vitória, won=False → derrota, won=None → indefinido.
    """

    match_id: int
    date: datetime | None = None
    opponent_name: str | None = None
    opponent_id: int | None = None
    won: bool | None = None
    score_for: int | None = None       # games vencidos pelo time
    score_against: int | None = None   # games vencidos pelo adversário
    tournament_name: str | None = None
    league_name: str | None = None


class TeamHistory(BaseModel):
    """Histórico recente de um time: forma + lista de resultados."""

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
    """
    Histórico de confrontos diretos entre dois times.
    Os resultados em matches são da perspectiva do team_a.
    """

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

    # Campos de histórico — default vazio para não quebrar JSONs antigos
    team_histories: list[TeamHistory] = Field(default_factory=list)
    head_to_head: HeadToHead | None = None

    stats: dict[str, Any] = Field(default_factory=dict)
    riot_enrichment: RiotEnrichment = Field(default_factory=RiotEnrichment)

    source_payloads: dict[str, Any] = Field(default_factory=dict)