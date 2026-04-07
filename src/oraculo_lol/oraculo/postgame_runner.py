from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models.postgame import GameResult, MatchPostGame
from ..oraculo.llm import from_env as llm_from_env
from ..publisher.formatter import _abbreviate
from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.oraculo.postgame_runner")

POSTGAME_SYSTEM = """\
Você é o Oráculo do LoL — analista do cenário BR com energia de narrador ao vivo.
Você recebe dados de uma partida finalizada e gera análises curtas e diretas.
Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem texto fora do JSON.
Use português brasileiro, jargões do cenário são bem-vindos.
"""


def _load_prediction(match_id: int) -> dict[str, Any] | None:
    s = load_settings()
    path = s.abs_data_dir() / "predictions" / f"pandascore_match_{match_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _fmt_games(games: list[GameResult], team_a: str, team_b: str) -> str:
    lines = []
    for g in games:
        winner = g.winner_name or "?"
        dur = g.length_minutes
        lines.append(f"Jogo {g.position}: {winner} vence em {dur}")
    return "\n".join(lines)


def _build_game_prompt(postgame: MatchPostGame, game: GameResult) -> str:
    a = _abbreviate(postgame.team_a_name)
    b = _abbreviate(postgame.team_b_name)
    winner = _abbreviate(game.winner_name)
    score_a = postgame.score_a
    score_b = postgame.score_b

    return f"""Dados do Jogo {game.position}:
Times: {a} vs {b}
Vencedor: {winner} em {game.length_minutes}
Placar atual da série: {a} {score_a}x{score_b} {b}

Gere um JSON com:
{{
  "summary": "<análise em até 120 caracteres — direto, sem enrolação>"
}}"""


def _build_series_prompt(postgame: MatchPostGame) -> str:
    a = _abbreviate(postgame.team_a_name)
    b = _abbreviate(postgame.team_b_name)
    winner_name = _abbreviate(
        postgame.team_a_name if postgame.score_a > postgame.score_b else postgame.team_b_name
    )

    games_txt = _fmt_games(postgame.games, a, b)
    prediction_txt = ""
    if postgame.predicted_winner:
        correct = "✅ CORRETO" if postgame.prediction_correct else "❌ ERRADO"
        prediction_txt = f"\nPrevisão do Oráculo: {_abbreviate(postgame.predicted_winner)} ({postgame.confidence}) — {correct}"

    return f"""Série finalizada:
Times: {a} vs {b}
Resultado: {winner_name} vence {postgame.score_a}x{postgame.score_b}
{games_txt}{prediction_txt}

Gere um JSON com:
{{
  "summary": "<análise da série em até 200 caracteres>"
}}

Regras para o summary:
- Tom neutro e analítico — sem dramatismo
- Se acertou: celebre brevemente e explique o que foi decisivo
- Se errou: reconheça a surpresa sem drama — ex: "X surpreendeu ao dominar Y com..."
- NUNCA escreva "Previsão do Oráculo foi ERRADA" — use "surpreendeu", "contrariou as expectativas"
- Cite o tempo de jogo e o fator decisivo
- Português brasileiro corrido, sem bullet points"""


def run_postgame_analysis(postgame: MatchPostGame, *, mode: str) -> str:
    """
    Gera análise de pós-jogo via GPT.
    mode: "game" (análise de um game) ou "series" (análise final da série)
    Retorna o texto do summary gerado.
    Fail-safe: retorna string vazia em caso de erro.
    """
    try:
        client = llm_from_env()
        if mode == "game":
            game = postgame.games[-1]  # último game adicionado
            prompt = _build_game_prompt(postgame, game)
        else:
            prompt = _build_series_prompt(postgame)

        raw = client.chat(system=POSTGAME_SYSTEM, user=prompt, max_tokens=200)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(l for l in lines if not l.startswith("```")).strip()

        data = json.loads(cleaned)
        return data.get("summary", "")

    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao gerar análise pós-jogo mode=%s err=%r", mode, exc)
        return ""


def build_postgame(
    match: dict[str, Any],
    finished_games: list[dict[str, Any]],
) -> MatchPostGame:
    """
    Constrói o MatchPostGame a partir do payload do Pandascore.
    Carrega a previsão do cache se existir.
    """
    match_id = int(match["id"])
    opponents = match.get("opponents") or []

    team_a_id = team_b_id = 0
    team_a_name = team_b_name = None

    if len(opponents) >= 2:
        a = opponents[0].get("opponent") or {}
        b = opponents[1].get("opponent") or {}
        team_a_id = int(a.get("id", 0))
        team_b_id = int(b.get("id", 0))
        team_a_name = a.get("name")
        team_b_name = b.get("name")

    # Placar da série
    results = match.get("results") or []
    score_map: dict[int, int] = {}
    for r in results:
        if isinstance(r, dict):
            score_map[int(r.get("team_id", 0))] = int(r.get("score", 0))
    score_a = score_map.get(team_a_id, 0)
    score_b = score_map.get(team_b_id, 0)

    # Games finalizados
    games: list[GameResult] = []
    for g in finished_games:
        winner = g.get("winner") or {}
        winner_id = winner.get("id")
        winner_name: str | None = None
        if winner_id == team_a_id:
            winner_name = team_a_name
        elif winner_id == team_b_id:
            winner_name = team_b_name

        games.append(GameResult(
            game_id=int(g["id"]),
            position=int(g.get("position", 0)),
            winner_id=int(winner_id) if winner_id else None,
            winner_name=winner_name,
            length_seconds=g.get("length"),
        ))

    # Previsão do cache
    prediction = _load_prediction(match_id)
    predicted_winner: str | None = None
    confidence: str | None = None
    prediction_correct: bool | None = None

    if prediction:
        predicted_winner = prediction.get("predicted_winner")
        confidence = prediction.get("confidence")
        if predicted_winner:
            series_winner_name = team_a_name if score_a > score_b else team_b_name
            if series_winner_name:
                prediction_correct = (
                    predicted_winner.lower() == series_winner_name.lower()
                    or _abbreviate(predicted_winner).lower() == _abbreviate(series_winner_name).lower()
                )

    return MatchPostGame(
        created_at=datetime.now(timezone.utc),
        pandascore_match_id=match_id,
        team_a_id=team_a_id,
        team_a_name=team_a_name,
        team_b_id=team_b_id,
        team_b_name=team_b_name,
        score_a=score_a,
        score_b=score_b,
        games=games,
        predicted_winner=predicted_winner,
        confidence=confidence,
        prediction_correct=prediction_correct,
    )


def build_split_opener_analysis(opener_data: dict[str, Any]) -> str:
    """
    Gera análise de favoritos para abertura de split via GPT.
    Usa os dados das partidas do primeiro dia como contexto.
    """
    league = opener_data.get("league_name", "?")
    serie = opener_data.get("serie_name", "?")
    teams = opener_data.get("teams", [])
    teams_list = ", ".join(teams) if teams else "?"

    prompt = f"""Abertura do {league} — {serie}

Times participantes: {teams_list}

Com base no que você sabe sobre esses times e o cenário BR de LoL,
gere um JSON com os 3 favoritos para vencer o split:

{{
  "favorites": [
    {{"position": 1, "team": "<time>", "reason": "<motivo em até 60 chars>"}},
    {{"position": 2, "team": "<time>", "reason": "<motivo em até 60 chars>"}},
    {{"position": 3, "team": "<time>", "reason": "<motivo em até 60 chars>"}}
  ]
}}

Use nomes abreviados: Furia, Loud, Fluxo, Red Canids, LOS, Vivo Keyd, Pain Gaming, Leviatan.
Responda EXCLUSIVAMENTE em JSON válido, sem markdown."""

    try:
        client = from_env()
        raw = client.chat(
            system=POSTGAME_SYSTEM,
            user=prompt,
            max_tokens=300,
        )
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(cleaned)
        return data.get("favorites", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao gerar favoritos do split err=%r", exc)
        return []


def build_weekly_ranking_analysis(
    *,
    teams: list[str],
    winrates: dict[str, dict],
    bot_accuracy: dict[str, dict],
    week_key: str,
) -> dict[str, Any]:
    """
    Gera ranking semanal dos times via GPT.
    Combina winrate recente e acurácia histórica do bot.
    """
    # Monta contexto de dados para o GPT
    data_lines = []
    for team in teams:
        wr = winrates.get(team)
        acc = bot_accuracy.get(team)
        parts = [f"- {_abbreviate(team)}:"]
        if wr and wr.get("total", 0) > 0:
            parts.append(f"forma recente {wr['wins']}V {wr['losses']}D ({wr['winrate']*100:.0f}%)")
        if acc and acc.get("total", 0) > 0:
            parts.append(f"Oráculo: {acc['correct']}/{acc['total']} previsões certas")
        data_lines.append(" ".join(parts))

    data_text = "\n".join(data_lines) if data_lines else "Sem dados disponíveis."

    prompt = f"""Ranking semanal do cenário BR — {week_key}

Dados dos times:
{data_text}

Gere um JSON com o ranking dos 5 times em melhor momento:
{{
  "ranking": [
    {{"position": 1, "team": "<nome abreviado>", "reason": "<motivo em até 70 chars>"}},
    {{"position": 2, "team": "<nome abreviado>", "reason": "<motivo em até 70 chars>"}},
    {{"position": 3, "team": "<nome abreviado>", "reason": "<motivo em até 70 chars>"}},
    {{"position": 4, "team": "<nome abreviado>", "reason": "<motivo em até 70 chars>"}},
    {{"position": 5, "team": "<nome abreviado>", "reason": "<motivo em até 70 chars>"}}
  ],
  "headline": "<frase de destaque da semana em até 80 chars>"
}}

Use nomes abreviados: Furia, Loud, Fluxo, Red Canids, LOS, Vivo Keyd, Pain Gaming, Leviatan.
Responda EXCLUSIVAMENTE em JSON válido, sem markdown."""

    try:
        client = from_env()
        raw = client.chat(system=POSTGAME_SYSTEM, user=prompt, max_tokens=400)
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao gerar ranking semanal err=%r", exc)
        # Fallback: ranking básico por winrate sem GPT
        sorted_teams = sorted(
            [(t, winrates.get(t, {}).get("winrate", 0)) for t in teams],
            key=lambda x: x[1], reverse=True,
        )
        return {
            "ranking": [
                {"position": i+1, "team": _abbreviate(t), "reason": f"{wr*100:.0f}% de aproveitamento"}
                for i, (t, wr) in enumerate(sorted_teams[:5])
            ],
            "headline": "Times em melhor forma esta semana",
        }