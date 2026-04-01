from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..paths import ensure_dir
from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.oraculo.prediction")


class TeamPrediction(BaseModel):
    name: str
    win_probability: float | None = None  # 0.0–1.0, se o modelo fornecer


class Prediction(BaseModel):
    version: Literal["v1"] = "v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    pandascore_match_id: int
    llm_model: str
    llm_provider: Literal["openai"] = "openai"

    # Resultado principal
    predicted_winner: str | None = None          # nome do time favorito
    confidence: str | None = None                # "alta" / "média" / "baixa"
    teams: list[TeamPrediction] = Field(default_factory=list)
    reasoning: str | None = None                 # raciocínio livre do modelo

    # Saída bruta (sempre preservada para auditoria)
    raw_response: str = ""
    parse_error: bool = False                    # True se não conseguiu parsear o JSON da LLM


def save_prediction_json(prediction: Prediction) -> Path:
    s = load_settings()
    base = ensure_dir(s.abs_data_dir() / "predictions")
    path = base / f"pandascore_match_{prediction.pandascore_match_id}.json"
    path.write_text(
        json.dumps(prediction.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("previsão salva em %s", path)
    return path