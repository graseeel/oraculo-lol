from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oraculo_lol.agregador.build_context import build_match_context, save_context_json
from oraculo_lol.datasources.pandascore import upcoming_br_lol_matches, lol_match_by_id
from oraculo_lol.oraculo.postgame_runner import build_postgame, run_postgame_analysis
from oraculo_lol.oraculo.prediction import save_prediction_json
from oraculo_lol.oraculo.runner import run_prediction
from oraculo_lol.publisher.formatter import (
    format_for_threads,
    format_for_twitter_long,
    format_postgame_game,
    format_postgame_series,
)
from oraculo_lol.publisher.telegram import send_alert_safe
from oraculo_lol.publisher.threads import post_thread_safe
from oraculo_lol.publisher.twitter import post_tweet_safe
from oraculo_lol.runtime import init_runtime
from oraculo_lol.settings import load_settings
from oraculo_lol.threads_monitor import check_threads_token

logger = logging.getLogger("scripts.scheduler")

PRE_MATCH_OFFSET_S = 60 * 60
CYCLE_INTERVAL_S = 60 * 60 * 6
POLL_INTERVAL_S = 60 * 5


def _state_path() -> Path:
    s = load_settings()
    return s.abs_data_dir() / "postgame_state.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"posted_games": {}, "posted_series": []}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


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
    now = datetime.now(timezone.utc)
    post_at = begin_at.astimezone(timezone.utc).timestamp() - PRE_MATCH_OFFSET_S
    return max(0.0, post_at - now.timestamp())


def _post_both(twitter_text: str, threads_text: str, match_name: str) -> tuple[bool, bool]:
    tw_ok = post_tweet_safe(twitter_text)
    th_ok = post_thread_safe(threads_text)
    if not tw_ok:
        send_alert_safe(
            f"⚠️ <b>Falha ao postar no X</b>\n\nPartida: {match_name}\n"
            "Possível causa: sessão do Chrome expirada.\n\n"
            "Execute: <code>python -m scripts.setup_twitter_session</code>"
        )
    if not th_ok:
        send_alert_safe(f"⚠️ <b>Falha ao postar no Threads</b>\n\nPartida: {match_name}")
    return tw_ok, th_ok


def _process_pregame(match: dict[str, Any]) -> None:
    match_id = match.get("id")
    name = match.get("name") or str(match_id)
    try:
        logger.info("pré-jogo match_id=%s name=%s", match_id, name)
        ctx = build_match_context(pandascore_match_id=int(match_id), include_payloads=False)
        save_context_json(ctx)
        prediction = run_prediction(match_id=int(match_id))
        save_prediction_json(prediction)

        tw = format_for_twitter_long(prediction)
        th = format_for_threads(prediction)
        tw_ok, th_ok = _post_both(tw, th, name)

        if tw_ok and th_ok:
            send_alert_safe(
                f"✅ <b>Pré-jogo postado</b>\n\nPartida: {name}\n"
                f"Favorito: {prediction.predicted_winner} ({prediction.confidence})"
            )
        logger.info("pré-jogo match_id=%s — X:%s Threads:%s",
                    match_id, "✓" if tw_ok else "✗", "✓" if th_ok else "✗")

    except Exception as exc:  # noqa: BLE001
        logger.error("falha no pré-jogo match_id=%s err=%r", match_id, exc)
        send_alert_safe(
            f"🚨 <b>Erro no pré-jogo</b>\n\nPartida: {name}\n"
            f"Erro: <code>{str(exc)[:200]}</code>"
        )


def _process_postgame(match: dict[str, Any], state: dict[str, Any]) -> None:
    match_id = str(match.get("id"))
    name = match.get("name") or match_id
    games = match.get("games") or []

    posted_games: dict[str, list[int]] = state.setdefault("posted_games", {})
    posted_series: list[str] = state.setdefault("posted_series", [])
    already_posted = set(posted_games.get(match_id, []))

    # Post por game individual
    for g in sorted(games, key=lambda x: x.get("position", 0)):
        game_id = g.get("id")
        if not g.get("finished") or game_id in already_posted:
            continue
        try:
            finished = [x for x in games if x.get("finished") and x.get("id") in already_posted | {game_id}]
            postgame = build_postgame(match, finished)
            postgame.game_summary = run_postgame_analysis(postgame, mode="game")

            tw = format_postgame_game(postgame)
            th = format_postgame_game(postgame)
            _post_both(tw, th, name)

            already_posted.add(game_id)
            posted_games[match_id] = list(already_posted)
            _save_state(state)
            logger.info("pós-jogo game_id=%s match=%s postado", game_id, name)

        except Exception as exc:  # noqa: BLE001
            logger.error("falha no pós-jogo game_id=%s err=%r", game_id, exc)

    # Post de resultado final
    if match.get("status") == "finished" and match_id not in posted_series:
        try:
            finished_games = [g for g in games if g.get("finished")]
            postgame = build_postgame(match, finished_games)
            postgame.series_summary = run_postgame_analysis(postgame, mode="series")

            tw = format_postgame_series(postgame)
            th = format_postgame_series(postgame)
            _post_both(tw, th, name)

            posted_series.append(match_id)
            _save_state(state)
            logger.info("resultado final match=%s postado", name)

        except Exception as exc:  # noqa: BLE001
            logger.error("falha no resultado final match=%s err=%r", name, exc)


def _monitor_active_matches(active_match_ids: list[int], state: dict[str, Any]) -> None:
    if not active_match_ids:
        return

    logger.info("monitorando %d partidas em andamento", len(active_match_ids))

    while active_match_ids:
        time.sleep(POLL_INTERVAL_S)
        remaining = []
        for match_id in active_match_ids:
            try:
                match = lol_match_by_id(match_id=match_id)
                _process_postgame(match, state)
                if match.get("status") != "finished":
                    remaining.append(match_id)
                else:
                    logger.info("match_id=%s finalizado", match_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("falha ao monitorar match_id=%s err=%r", match_id, exc)
                remaining.append(match_id)
        active_match_ids = remaining

    logger.info("todos os matches monitorados finalizados")


def _run_cycle() -> None:
    logger.info("iniciando ciclo de busca de partidas BR")
    check_threads_token()

    try:
        matches = upcoming_br_lol_matches(max_pages=2)
    except Exception as exc:  # noqa: BLE001
        logger.error("falha ao buscar partidas: %r", exc)
        send_alert_safe(
            f"🚨 <b>Falha ao buscar partidas</b>\n\n"
            f"Erro: <code>{str(exc)[:200]}</code>\n"
            "Tentará novamente no próximo ciclo."
        )
        return

    logger.info("%d partidas encontradas", len(matches))

    scheduled = []
    for m in matches:
        begin_at = _parse_dt(m.get("begin_at"))
        if begin_at is None:
            continue
        scheduled.append((begin_at, m))

    scheduled.sort(key=lambda x: x[0])

    state = _load_state()
    active_match_ids: list[int] = []

    for begin_at, match in scheduled:
        wait_s = _seconds_until_post(begin_at)

        if wait_s > CYCLE_INTERVAL_S:
            logger.info(
                "match_id=%s em %s — fora da janela, pulando",
                match.get("id"), begin_at.strftime("%d/%m %H:%M UTC"),
            )
            continue

        if wait_s > 0:
            logger.info(
                "match_id=%s — aguardando %.0f min (1h antes de %s)",
                match.get("id"), wait_s / 60, begin_at.strftime("%H:%M UTC"),
            )
            time.sleep(wait_s)

        _process_pregame(match)
        active_match_ids.append(int(match["id"]))

    _monitor_active_matches(active_match_ids, state)


def main() -> int:
    init_runtime()
    logger.info("Oráculo do LoL — scheduler iniciado")
    logger.info(
        "configuração: posta %dmin antes | ciclo a cada %dh | poll a cada %dmin",
        PRE_MATCH_OFFSET_S // 60,
        CYCLE_INTERVAL_S // 3600,
        POLL_INTERVAL_S // 60,
    )

    send_alert_safe(
        "🟢 <b>Oráculo do LoL iniciado</b>\n\n"
        f"Posta {PRE_MATCH_OFFSET_S // 60}min antes de cada partida.\n"
        f"Ciclo de busca a cada {CYCLE_INTERVAL_S // 3600}h.\n"
        f"Polling durante partidas a cada {POLL_INTERVAL_S // 60}min."
    )

    while True:
        _run_cycle()
        logger.info("ciclo concluído — próximo em %dh", CYCLE_INTERVAL_S // 3600)
        time.sleep(CYCLE_INTERVAL_S)


if __name__ == "__main__":
    raise SystemExit(main())