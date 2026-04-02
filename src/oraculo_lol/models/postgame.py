from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GameResult(BaseModel):
    """Resultado de um game individual dentro de um match."""
    game_id: int
    position: int                    # Jogo 1, 2, 3...
    winner_id: int | None = None
    winner_name: str | None = None
    length_seconds: int | None = None

    @property
    def length_minutes(self) -> str:
        if self.length_seconds is None:
            return "?"
        return f"{self.length_seconds // 60}min"


class MatchPostGame(BaseModel):
    """Contexto completo do pós-jogo de um match."""
    version: Literal["v1"] = "v1"
    created_at: datetime

    pandascore_match_id: int
    team_a_id: int
    team_a_name: str | None = None
    team_b_id: int
    team_b_name: str | None = None

    # Placar final da série
    score_a: int = 0
    score_b: int = 0

    # Games individuais finalizados
    games: list[GameResult] = Field(default_factory=list)

    # Previsão original (se existir)
    predicted_winner: str | None = None
    confidence: str | None = None
    prediction_correct: bool | None = None  # None = sem previsão

    # Análise gerada pelo GPT
    game_summary: str | None = None        # resumo por game
    series_summary: str | None = None      # resumo final da série