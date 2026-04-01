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

    stats: dict[str, Any] = Field(default_factory=dict)
    riot_enrichment: RiotEnrichment = Field(default_factory=RiotEnrichment)

    source_payloads: dict[str, Any] = Field(default_factory=dict)

