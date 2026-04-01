from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RosterPlayer(BaseModel):
    pandascore_player_id: int
    name: str | None = None
    slug: str | None = None

    # Enriquecimento manual futuro (opcional)
    riot_game_name: str | None = None
    riot_tag_line: str | None = None
    riot_puuid: str | None = None
    riot_last_verified_at: datetime | None = None


class TeamRoster(BaseModel):
    pandascore_team_id: int
    name: str | None = None
    slug: str | None = None
    players: list[RosterPlayer] = Field(default_factory=list)


class RostersSnapshot(BaseModel):
    version: Literal["v1"] = "v1"
    source: Literal["pandascore"] = "pandascore"
    fetched_at: datetime
    scope: dict[str, Any] = Field(default_factory=dict)  # ex: league_ids
    teams: list[TeamRoster] = Field(default_factory=list)

