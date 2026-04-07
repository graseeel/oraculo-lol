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
    format_daily_summary,
    format_for_threads,
    format_for_twitter_long,
    format_postgame_game,
    format_postgame_series,
    format_split_opener,
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
DAILY_SUMMARY_DELAY_S = 60 * 60  # 1h após o último jogo


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
    return {"posted_games": {}, "posted_series": [], "daily_summaries": []}


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


def _update_prediction_result(
    match_id: int,
    postgame: Any,
    match: dict[str, Any],
) -> None:
    """Atualiza o arquivo de previsão com o resultado real após o jogo terminar."""
    try:
        from oraculo_lol.settings import load_settings
        s = load_settings()
        pred_path = s.abs_data_dir() / "predictions" / f"pandascore_match_{match_id}.json"
        if not pred_path.exists():
            return

        pred_data = json.loads(pred_path.read_text(encoding="utf-8"))

        # Vencedor real da série
        actual_winner = None
        if postgame.score_a > postgame.score_b:
            actual_winner = postgame.team_a_name
        elif postgame.score_b > postgame.score_a:
            actual_winner = postgame.team_b_name

        # Liga
        league_name = None
        if isinstance(match.get("league"), dict):
            league_name = match["league"].get("name")

        pred_data["actual_winner"] = actual_winner
        pred_data["prediction_correct"] = postgame.prediction_correct
        pred_data["league_name"] = league_name

        pred_path.write_text(
            json.dumps(pred_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "resultado salvo na previsão match_id=%s correto=%s",
            match_id, postgame.prediction_correct,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao salvar resultado na previsão match_id=%s err=%r", match_id, exc)


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

            # Salva resultado na previsão para métricas de performance
            _update_prediction_result(
                match_id=int(match_id),
                postgame=postgame,
                match=match,
            )

            posted_series.append(match_id)
            _save_state(state)
            logger.info("resultado final match=%s postado", name)

        except Exception as exc:  # noqa: BLE001
            logger.error("falha no resultado final match=%s err=%r", name, exc)


def _try_postgame_from_liquipedia(match_id: int, state: dict[str, Any]) -> None:
    """
    Fallback: busca resultado da partida na Liquipedia quando a Pandascore falha.
    Só age se a série ainda não foi postada.
    """
    posted_series: list[str] = state.setdefault("posted_series", [])
    if str(match_id) in posted_series:
        return

    # Precisa do contexto para saber os nomes dos times e begin_at
    try:
        from oraculo_lol.settings import load_settings
        from oraculo_lol.datasources.liquipedia import get_match_result
        from oraculo_lol.models.postgame import MatchPostGame, GameResult
        from oraculo_lol.oraculo.postgame_runner import run_postgame_analysis
        import json as _json
        from datetime import timezone

        s = load_settings()
        ctx_path = s.abs_data_dir() / "context" / f"pandascore_match_{match_id}.json"
        if not ctx_path.exists():
            logger.warning("fallback Liquipedia: contexto não encontrado match_id=%s", match_id)
            return

        ctx = _json.loads(ctx_path.read_text(encoding="utf-8"))
        teams = ctx.get("teams", [])
        if len(teams) < 2:
            return

        team_a_name = teams[0].get("name", "")
        team_b_name = teams[1].get("name", "")
        begin_at_str = ctx.get("begin_at")
        begin_at = _parse_dt(begin_at_str) or datetime.now(timezone.utc)

        result = get_match_result(
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            match_date=begin_at,
            delta_hours=8,
        )

        if not result:
            logger.info("fallback Liquipedia: resultado não encontrado match_id=%s", match_id)
            return

        winner_name = result.get("winner_name")
        score_a = result.get("score_a", 0)
        score_b = result.get("score_b", 0)

        # Monta postgame mínimo
        pred_data = None
        pred_path = s.abs_data_dir() / "predictions" / f"pandascore_match_{match_id}.json"
        if pred_path.exists():
            pred_data = _json.loads(pred_path.read_text(encoding="utf-8"))

        predicted_winner = pred_data.get("predicted_winner") if pred_data else None
        confidence = pred_data.get("confidence") if pred_data else None
        prediction_correct = None
        if predicted_winner and winner_name:
            from oraculo_lol.publisher.formatter import _abbreviate
            prediction_correct = (
                _abbreviate(predicted_winner).lower() == _abbreviate(winner_name).lower()
            )

        postgame = MatchPostGame(
            created_at=datetime.now(timezone.utc),
            pandascore_match_id=match_id,
            team_a_id=teams[0].get("id", 0),
            team_a_name=team_a_name,
            team_b_id=teams[1].get("id", 0),
            team_b_name=team_b_name,
            score_a=score_a,
            score_b=score_b,
            games=[GameResult(game_id=1, position=1, winner_name=winner_name)],
            predicted_winner=predicted_winner,
            confidence=confidence,
            prediction_correct=prediction_correct,
        )
        postgame.series_summary = run_postgame_analysis(postgame, mode="series")

        tw = format_postgame_series(postgame)
        th = format_postgame_series(postgame)
        name = f"{team_a_name} vs {team_b_name}"
        _post_both(tw, th, name)

        # Salva resultado na previsão
        _update_prediction_result(
            match_id=match_id,
            postgame=postgame,
            match={"league": {"name": result.get("tournament", "")}},
        )

        posted_series.append(str(match_id))
        _save_state(state)
        logger.info(
            "fallback Liquipedia: pós-jogo postado match_id=%s vencedor=%s",
            match_id, winner_name,
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("fallback Liquipedia: falha match_id=%s err=%r", match_id, exc)


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
                logger.error("falha ao monitorar match_id=%s via Pandascore err=%r — tentando Liquipedia", match_id, exc)
                # Fallback: tenta buscar resultado na Liquipedia
                try:
                    _try_postgame_from_liquipedia(match_id, state)
                except Exception as exc2:  # noqa: BLE001
                    logger.error("fallback Liquipedia também falhou match_id=%s err=%r", match_id, exc2)
                remaining.append(match_id)
        active_match_ids = remaining

    logger.info("todos os matches monitorados finalizados")


def _check_and_post_split_opener(
    scheduled: list[tuple[datetime, dict[str, Any]]],
    state: dict[str, Any],
) -> None:
    """
    Detecta se há partidas de um split novo (serie_id nunca visto).
    Se sim, gera e posta o post de abertura antes dos jogos.
    """
    posted_splits: list[str] = state.setdefault("posted_splits", [])

    # Coleta todos os serie_ids das partidas do ciclo
    new_splits: dict[str, dict[str, Any]] = {}
    for _, match in scheduled:
        serie = match.get("serie") or {}
        serie_id = str(serie.get("id", ""))
        if not serie_id or serie_id in posted_splits:
            continue
        if serie_id not in new_splits:
            new_splits[serie_id] = {
                "serie_id": serie_id,
                "serie_name": serie.get("full_name") or serie.get("season") or "?",
                "league_name": (match.get("league") or {}).get("name", "?"),
                "matches": [],
            }
        new_splits[serie_id]["matches"].append(match)

    for serie_id, split_data in new_splits.items():
        try:
            logger.info(
                "novo split detectado: %s %s (serie_id=%s)",
                split_data["league_name"], split_data["serie_name"], serie_id,
            )
            # Extrai times únicos das partidas
            teams: dict[int, str] = {}
            for m in split_data["matches"]:
                for opp in (m.get("opponents") or []):
                    o = opp.get("opponent") or {}
                    if o.get("id") and o.get("name"):
                        teams[int(o["id"])] = o["name"]

            # Monta dados para o post
            opener_data = {
                "league_name": split_data["league_name"],
                "serie_name": split_data["serie_name"],
                "teams": list(teams.values()),
                "matches": split_data["matches"],
            }

            # Gera análise de favoritos via GPT
            from oraculo_lol.oraculo.postgame_runner import build_split_opener_analysis
            favorites = build_split_opener_analysis(opener_data)
            opener_data["favorites"] = favorites

            tw = format_split_opener(opener_data)
            th = format_split_opener(opener_data)
            _post_both(tw, th, f"abertura {split_data['league_name']}")

            posted_splits.append(serie_id)
            _save_state(state)
            logger.info("abertura de split postada: %s %s", split_data["league_name"], split_data["serie_name"])

        except Exception as exc:  # noqa: BLE001
            logger.error("falha na abertura do split serie_id=%s err=%r", serie_id, exc)


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

    # Detecta abertura de novo split
    _check_and_post_split_opener(scheduled, state)

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

    # Agenda resumo diário 1h após último jogo
    if active_match_ids:
        _schedule_daily_summary(active_match_ids, state)


def _build_daily_summary(match_ids: list[int]) -> dict[str, Any] | None:
    """
    Coleta resultados do dia e monta o resumo.
    Retorna None se não houver dados suficientes.
    """
    s = load_settings()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    results = []
    for mid in match_ids:
        pred_path = s.abs_data_dir() / "predictions" / f"pandascore_match_{mid}.json"
        if not pred_path.exists():
            continue
        try:
            pred = json.loads(pred_path.read_text(encoding="utf-8"))
            if pred.get("prediction_correct") is None:
                continue
            results.append({
                "match_id": mid,
                "predicted_winner": pred.get("predicted_winner"),
                "actual_winner": pred.get("actual_winner"),
                "prediction_correct": pred.get("prediction_correct"),
                "confidence": pred.get("confidence"),
                "league_name": pred.get("league_name"),
            })
        except Exception:  # noqa: BLE001
            pass

    if not results:
        return None

    total = len(results)
    acertos = sum(1 for r in results if r.get("prediction_correct"))
    erros = total - acertos

    return {
        "date": today,
        "total": total,
        "acertos": acertos,
        "erros": erros,
        "results": results,
    }


def _schedule_daily_summary(match_ids: list[int], state: dict[str, Any]) -> None:
    """
    Aguarda 1h após o fim dos jogos e posta o resumo do dia.
    Só posta se ainda não tiver postado hoje.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_summaries: list[str] = state.setdefault("daily_summaries", [])

    if today in daily_summaries:
        logger.info("resumo diário já postado hoje (%s)", today)
        return

    logger.info("aguardando %dmin para postar resumo diário", DAILY_SUMMARY_DELAY_S // 60)
    time.sleep(DAILY_SUMMARY_DELAY_S)

    summary_data = _build_daily_summary(match_ids)
    if not summary_data:
        logger.info("resumo diário: sem resultados para postar")
        return

    tw = format_daily_summary(summary_data)
    th = format_daily_summary(summary_data)

    if tw:
        _post_both(tw, th, "resumo diário")
        daily_summaries.append(today)
        _save_state(state)
        logger.info(
            "resumo diário postado: %d acertos / %d jogos",
            summary_data["acertos"], summary_data["total"],
        )


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