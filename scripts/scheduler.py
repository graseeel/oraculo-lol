from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from oraculo_lol.agregador.build_context import build_match_context, save_context_json
from oraculo_lol.datasources.pandascore import upcoming_br_lol_matches
from oraculo_lol.oraculo.prediction import save_prediction_json
from oraculo_lol.oraculo.runner import run_prediction
from oraculo_lol.publisher.formatter import format_for_threads, format_for_twitter
from oraculo_lol.publisher.threads import post_thread_safe
from oraculo_lol.publisher.twitter import post_tweet_safe
from oraculo_lol.runtime import init_runtime

logger = logging.getLogger("scripts.scheduler")

# Quanto antes do begin_at o oráculo deve postar (em segundos)
PRE_MATCH_OFFSET_S = 60 * 60  # 1 hora

# Intervalo entre ciclos de busca de partidas
CYCLE_INTERVAL_S = 60 * 60 * 6  # 6 horas


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:  # noqa: BLE001
        return None


def _seconds_until_post(begin_at: datetime) -> float:
    """
    Calcula quantos segundos faltam para postar (1h antes do begin_at).
    Retorna 0 se o momento já passou (posta imediatamente).
    """
    now = datetime.now(timezone.utc)
    target = begin_at.astimezone(timezone.utc)
    post_at = target.timestamp() - PRE_MATCH_OFFSET_S
    return max(0.0, post_at - now.timestamp())


def _process_match(match: dict[str, Any]) -> None:
    """
    Processa uma partida: gera contexto, previsão e posta nas redes.
    Fail-safe: erros são logados mas não travam o scheduler.
    """
    match_id = match.get("id")
    name = match.get("name") or str(match_id)

    try:
        logger.info("processando match_id=%s name=%s", match_id, name)

        # Contexto (sempre regera — sem cache)
        ctx = build_match_context(pandascore_match_id=int(match_id), include_payloads=False)
        save_context_json(ctx)

        # Previsão
        prediction = run_prediction(match_id=int(match_id))
        save_prediction_json(prediction)

        # Formatar e postar
        twitter_text = format_for_twitter(prediction)
        threads_text = format_for_threads(prediction)

        tw_ok = post_tweet_safe(twitter_text)
        th_ok = post_thread_safe(threads_text)

        logger.info(
            "match_id=%s postado — X:%s Threads:%s",
            match_id,
            "✓" if tw_ok else "✗",
            "✓" if th_ok else "✗",
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("falha ao processar match_id=%s err=%r", match_id, exc)


def _run_cycle() -> None:
    """
    Um ciclo completo: busca partidas → agenda e processa.
    """
    logger.info("iniciando ciclo de busca de partidas BR")

    try:
        matches = upcoming_br_lol_matches(max_pages=2)
    except Exception as exc:  # noqa: BLE001
        logger.error("falha ao buscar partidas: %r", exc)
        return

    logger.info("%d partidas encontradas", len(matches))

    # Ordena por begin_at para processar na ordem cronológica
    scheduled = []
    for m in matches:
        begin_at = _parse_dt(m.get("begin_at"))
        if begin_at is None:
            logger.warning("match_id=%s sem begin_at — pulando", m.get("id"))
            continue
        scheduled.append((begin_at, m))

    scheduled.sort(key=lambda x: x[0])

    for begin_at, match in scheduled:
        wait_s = _seconds_until_post(begin_at)

        if wait_s > CYCLE_INTERVAL_S:
            logger.info(
                "match_id=%s em %s — fora da janela deste ciclo, pulando",
                match.get("id"),
                begin_at.strftime("%d/%m %H:%M UTC"),
            )
            continue

        if wait_s > 0:
            logger.info(
                "match_id=%s — aguardando %.0f minutos para postar (1h antes de %s)",
                match.get("id"),
                wait_s / 60,
                begin_at.strftime("%H:%M UTC"),
            )
            time.sleep(wait_s)

        _process_match(match)


def main() -> int:
    init_runtime()
    logger.info("Oráculo do LoL — scheduler iniciado")
    logger.info(
        "configuração: posta %dmin antes | ciclo a cada %dh",
        PRE_MATCH_OFFSET_S // 60,
        CYCLE_INTERVAL_S // 3600,
    )

    while True:
        _run_cycle()
        logger.info("ciclo concluído — próximo em %dh", CYCLE_INTERVAL_S // 3600)
        time.sleep(CYCLE_INTERVAL_S)


if __name__ == "__main__":
    raise SystemExit(main())