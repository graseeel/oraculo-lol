from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..agregador.build_context import build_match_context
from ..models.context import MatchContext
from ..paths import ensure_dir
from ..publisher.layout import calc_available_chars
from ..settings import load_settings
from .llm import LLMError, from_env as llm_from_env
from .prediction import Prediction, TeamPrediction, save_prediction_json
from .prompt import build_prompt, system_prompt

logger = logging.getLogger("oraculo_lol.oraculo.runner")


def _load_context_from_file(path: Path) -> MatchContext:
    if not path.exists():
        raise FileNotFoundError(f"arquivo de contexto não encontrado: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return MatchContext.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"falha ao parsear contexto em {path}: {exc}") from exc


def _default_context_path(match_id: int) -> Path:
    s = load_settings()
    return s.abs_data_dir() / "context" / f"pandascore_match_{match_id}.json"


def _parse_llm_response(raw: str, match_id: int, model: str) -> Prediction:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        data: dict[str, Any] = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("falha ao parsear JSON da LLM: %r — salvando como raw", exc)
        return Prediction(
            pandascore_match_id=match_id,
            llm_model=model,
            raw_response=raw,
            parse_error=True,
            reasoning=raw,
        )

    teams = [
        TeamPrediction(
            name=str(t.get("name", "")),
            win_probability=t.get("win_probability"),
        )
        for t in data.get("teams", [])
        if isinstance(t, dict)
    ]

    return Prediction(
        pandascore_match_id=match_id,
        llm_model=model,
        predicted_winner=data.get("predicted_winner"),
        confidence=data.get("confidence"),
        teams=teams,
        reasoning=data.get("reasoning"),
        raw_response=raw,
        parse_error=False,
    )


def _calc_reasoning_limit(ctx: MatchContext) -> int:
    """
    Calcula o limite de chars para o reasoning com base nos times do contexto.
    Usa os nomes como vêm do Pandascore — o _abbreviate interno cuida da abreviação.
    """
    if len(ctx.teams) == 2:
        a, b = ctx.teams[0], ctx.teams[1]
        return calc_available_chars(
            team_a_name=a.name,
            team_b_name=b.name,
            predicted_winner=a.name,  # pior caso: nome do time A como vencedor
            confidence="média",       # pior caso: "MÉDIA" tem 5 chars (mesmo que "ALTA")
            win_prob_a=0.72,
            win_prob_b=0.28,
        )
    return calc_available_chars(
        team_a_name=None,
        team_b_name=None,
        predicted_winner=None,
        confidence="média",
    )


def run_prediction(
    *,
    match_id: int | None = None,
    context_file: Path | None = None,
) -> Prediction:
    """
    Ponto de entrada principal do oráculo.

    Estratégia de carregamento do contexto:
    1. Se context_file fornecido → carrega direto
    2. Se match_id fornecido → tenta o path padrão; se não existir, gera na hora
    3. Nenhum dos dois → ValueError
    """
    if context_file is None and match_id is None:
        raise ValueError("forneça --match-id ou --context-file")

    # --- Carregar contexto ---
    ctx: MatchContext

    if context_file is not None:
        logger.info("carregando contexto de arquivo: %s", context_file)
        ctx = _load_context_from_file(context_file)
    else:
        default_path = _default_context_path(match_id)  # type: ignore[arg-type]
        if default_path.exists():
            logger.info("contexto encontrado em cache: %s", default_path)
            ctx = _load_context_from_file(default_path)
        else:
            logger.info(
                "contexto não encontrado em %s — gerando via Pandascore...", default_path
            )
            ctx = build_match_context(pandascore_match_id=match_id, include_payloads=False)  # type: ignore[arg-type]

    effective_match_id = ctx.pandascore_match_id

    # --- Calcular limite dinâmico de reasoning ---
    max_reasoning_chars = _calc_reasoning_limit(ctx)
    logger.info(
        "limite dinâmico de reasoning: %d chars para match_id=%s",
        max_reasoning_chars,
        effective_match_id,
    )

    # --- Chamar LLM ---
    client = llm_from_env()
    logger.info(
        "chamando LLM model=%s para match_id=%s", client.model, effective_match_id
    )

    user_msg = build_prompt(ctx, max_reasoning_chars)
    raw = client.chat(system=system_prompt(), user=user_msg)

    # --- Parsear resposta ---
    prediction = _parse_llm_response(raw, effective_match_id, client.model)

    if prediction.parse_error:
        logger.warning("LLM retornou resposta não-JSON para match_id=%s", effective_match_id)
    else:
        logger.info(
            "previsão: vencedor=%r confiança=%s reasoning_len=%d",
            prediction.predicted_winner,
            prediction.confidence,
            len(prediction.reasoning or ""),
        )

    return prediction