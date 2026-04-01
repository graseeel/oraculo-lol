"""
Teste real do Oráculo — busca o próximo jogo BR e posta nas redes.

Uso:
    python -m scripts.test_real

Fluxo:
    1. Busca próximas partidas BR (Pandascore)
    2. Seleciona a mais próxima com begin_at definido
    3. Gera contexto completo (rosters + histórico)
    4. Chama o GPT para previsão real
    5. Posta no X e Threads
"""
from __future__ import annotations

import json
import logging
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

logger = logging.getLogger("scripts.test_real")


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:  # noqa: BLE001
        return None


def _pick_next_match(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Retorna a próxima partida futura com begin_at definido."""
    now = datetime.now(timezone.utc)
    future = []
    for m in matches:
        begin_at = _parse_dt(m.get("begin_at"))
        if begin_at and begin_at > now:
            future.append((begin_at, m))
    if not future:
        return None
    future.sort(key=lambda x: x[0])
    return future[0][1]


def main() -> int:
    init_runtime()

    print("=" * 60)
    print("Oráculo do LoL — Teste Real")
    print("=" * 60)
    print()

    # 1. Buscar próximas partidas
    print("🔍 Buscando próximas partidas BR...")
    try:
        matches = upcoming_br_lol_matches(max_pages=2)
    except Exception as exc:  # noqa: BLE001
        logger.error("falha ao buscar partidas: %r", exc)
        return 1

    if not matches:
        print("❌ Nenhuma partida encontrada.")
        return 1

    print(f"   {len(matches)} partidas encontradas.")

    # 2. Selecionar a mais próxima
    match = _pick_next_match(matches)
    if not match:
        print("❌ Nenhuma partida futura com data definida.")
        return 1

    match_id = match.get("id")
    name = match.get("name") or str(match_id)
    begin_at = _parse_dt(match.get("begin_at"))
    begin_str = begin_at.strftime("%d/%m/%Y %H:%M UTC") if begin_at else "?"

    print(f"   ✓ Próximo jogo: {name}")
    print(f"   📅 Data: {begin_str}")
    print(f"   🔑 Match ID: {match_id}")
    print()

    # 3. Gerar contexto
    print("📊 Gerando contexto (rosters + histórico)...")
    try:
        ctx = build_match_context(pandascore_match_id=int(match_id), include_payloads=False)
        save_context_json(ctx)
        teams = " vs ".join(t.name or str(t.id) for t in ctx.teams)
        print(f"   ✓ Times: {teams}")
    except Exception as exc:  # noqa: BLE001
        logger.error("falha ao gerar contexto: %r", exc)
        return 1

    print()

    # 4. Gerar previsão com GPT
    print("🤖 Chamando o GPT-4o para previsão...")
    try:
        prediction = run_prediction(match_id=int(match_id))
        save_prediction_json(prediction)
        print(f"   ✓ Vencedor previsto: {prediction.predicted_winner}")
        print(f"   ✓ Confiança: {prediction.confidence}")
        print(f"   ✓ Reasoning: {prediction.reasoning}")
    except Exception as exc:  # noqa: BLE001
        logger.error("falha ao gerar previsão: %r", exc)
        return 1

    print()

    # 5. Formatar e mostrar
    twitter_text = format_for_twitter(prediction)
    threads_text = format_for_threads(prediction)

    print("=" * 60)
    print(f"TWITTER ({len(twitter_text)} chars):")
    print(twitter_text)
    print("=" * 60)
    print(f"THREADS ({len(threads_text)} chars):")
    print(threads_text)
    print("=" * 60)
    print()

    # 6. Postar
    print("📤 Postando nas redes...")
    tw_ok = post_tweet_safe(twitter_text)
    th_ok = post_thread_safe(threads_text)

    result = {
        "match": name,
        "match_id": match_id,
        "predicted_winner": prediction.predicted_winner,
        "confidence": prediction.confidence,
        "twitter": "✓ postado" if tw_ok else "✗ falhou",
        "threads": "✓ postado" if th_ok else "✗ falhou",
    }

    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (tw_ok and th_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())