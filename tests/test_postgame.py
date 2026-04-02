"""
Testes unitários de models/postgame.py, oraculo/postgame_runner.py
e publisher/formatter.py (funções de pós-jogo).

Rodar com:
    pytest tests/test_postgame.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from oraculo_lol.models.postgame import GameResult, MatchPostGame
from oraculo_lol.oraculo.postgame_runner import build_postgame
from oraculo_lol.publisher.formatter import (
    TWITTER_LIMIT,
    format_postgame_game,
    format_postgame_series,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_postgame(
    *,
    team_a_name: str = "RED Canids",
    team_b_name: str = "Fluxo W7M",
    score_a: int = 2,
    score_b: int = 0,
    games: list[GameResult] | None = None,
    predicted_winner: str | None = "RED Canids",
    confidence: str | None = "média",
    prediction_correct: bool | None = True,
    game_summary: str | None = "Red Canids domina e fecha rápido.",
    series_summary: str | None = "Serie dominada. Oráculo acertou mais uma.",
) -> MatchPostGame:
    if games is None:
        games = [
            GameResult(game_id=1, position=1, winner_id=161,
                       winner_name="RED Canids", length_seconds=2764),
            GameResult(game_id=2, position=2, winner_id=161,
                       winner_name="RED Canids", length_seconds=1790),
        ]
    return MatchPostGame(
        created_at=datetime.now(timezone.utc),
        pandascore_match_id=1407081,
        team_a_id=161,
        team_a_name=team_a_name,
        team_b_id=136357,
        team_b_name=team_b_name,
        score_a=score_a,
        score_b=score_b,
        games=games,
        predicted_winner=predicted_winner,
        confidence=confidence,
        prediction_correct=prediction_correct,
        game_summary=game_summary,
        series_summary=series_summary,
    )


def _make_match_payload(
    *,
    match_id: int = 1407081,
    team_a_id: int = 161,
    team_a_name: str = "RED Canids",
    team_b_id: int = 136357,
    team_b_name: str = "Fluxo W7M",
    score_a: int = 2,
    score_b: int = 0,
    status: str = "finished",
) -> dict[str, Any]:
    return {
        "id": match_id,
        "status": status,
        "name": f"{team_a_name} vs {team_b_name}",
        "opponents": [
            {"opponent": {"id": team_a_id, "name": team_a_name}},
            {"opponent": {"id": team_b_id, "name": team_b_name}},
        ],
        "results": [
            {"team_id": team_a_id, "score": score_a},
            {"team_id": team_b_id, "score": score_b},
        ],
        "games": [],
    }


def _make_game_payload(
    *,
    game_id: int,
    position: int,
    winner_id: int,
    length: int | None = 2764,
    finished: bool = True,
) -> dict[str, Any]:
    return {
        "id": game_id,
        "position": position,
        "finished": finished,
        "length": length,
        "winner": {"id": winner_id, "type": "Team"},
    }


# ---------------------------------------------------------------------------
# GameResult
# ---------------------------------------------------------------------------

class TestGameResult:
    def test_length_minutes_com_valor(self):
        g = GameResult(game_id=1, position=1, winner_id=161,
                       winner_name="RED Canids", length_seconds=2764)
        assert g.length_minutes == "46min"

    def test_length_minutes_sem_valor(self):
        g = GameResult(game_id=1, position=1, winner_id=161,
                       winner_name="RED Canids", length_seconds=None)
        assert g.length_minutes == "?"

    def test_length_minutes_jogo_curto(self):
        g = GameResult(game_id=2, position=2, winner_id=161,
                       winner_name="RED Canids", length_seconds=1790)
        assert g.length_minutes == "29min"


# ---------------------------------------------------------------------------
# build_postgame
# ---------------------------------------------------------------------------

class TestBuildPostgame:
    def test_times_extraidos_corretamente(self):
        match = _make_match_payload()
        games = [_make_game_payload(game_id=1, position=1, winner_id=161)]
        pg = build_postgame(match, games)
        assert pg.team_a_name == "RED Canids"
        assert pg.team_b_name == "Fluxo W7M"

    def test_placar_extraido_corretamente(self):
        match = _make_match_payload(score_a=2, score_b=1)
        pg = build_postgame(match, [])
        assert pg.score_a == 2
        assert pg.score_b == 1

    def test_winner_name_resolvido(self):
        match = _make_match_payload()
        games = [_make_game_payload(game_id=1, position=1, winner_id=161)]
        pg = build_postgame(match, games)
        assert pg.games[0].winner_name == "RED Canids"

    def test_winner_name_time_b(self):
        match = _make_match_payload()
        games = [_make_game_payload(game_id=1, position=1, winner_id=136357)]
        pg = build_postgame(match, games)
        assert pg.games[0].winner_name == "Fluxo W7M"

    def test_length_preservado(self):
        match = _make_match_payload()
        games = [_make_game_payload(game_id=1, position=1, winner_id=161, length=2764)]
        pg = build_postgame(match, games)
        assert pg.games[0].length_seconds == 2764

    def test_length_none_nao_quebra(self):
        match = _make_match_payload()
        games = [_make_game_payload(game_id=1, position=1, winner_id=161, length=None)]
        pg = build_postgame(match, games)
        assert pg.games[0].length_seconds is None
        assert pg.games[0].length_minutes == "?"

    def test_sem_games_nao_quebra(self):
        match = _make_match_payload()
        pg = build_postgame(match, [])
        assert pg.games == []

    def test_sem_opponents_nao_quebra(self):
        match = _make_match_payload()
        match["opponents"] = []
        pg = build_postgame(match, [])
        assert pg.team_a_id == 0
        assert pg.team_b_id == 0

    def test_prediction_none_quando_sem_cache(self):
        """Sem arquivo de previsão em cache, prediction_correct deve ser None."""
        match = _make_match_payload(match_id=999999999)  # ID que não existe em cache
        pg = build_postgame(match, [])
        assert pg.predicted_winner is None
        assert pg.prediction_correct is None


# ---------------------------------------------------------------------------
# format_postgame_game
# ---------------------------------------------------------------------------

class TestFormatPostgameGame:
    def test_nunca_passa_280_chars(self):
        pg = _make_postgame(
            team_a_name="Vivo Keyd Stars Academy",
            team_b_name="Ei Nerd Esports",
            game_summary="A" * 300,
        )
        result = format_postgame_game(pg)
        assert len(result) <= TWITTER_LIMIT, f"passou de 280: {len(result)} chars"

    def test_nomes_abreviados(self):
        pg = _make_postgame(
            team_a_name="RED Canids",
            team_b_name="Fluxo W7M",
        )
        result = format_postgame_game(pg)
        assert "Red Canids" in result
        assert "Fluxo" in result
        assert "Fluxo W7M" not in result

    def test_vencedor_abreviado(self):
        pg = _make_postgame(
            games=[GameResult(game_id=1, position=1, winner_id=161,
                              winner_name="Vivo Keyd Stars Academy",
                              length_seconds=2764)],
        )
        result = format_postgame_game(pg)
        assert "Vivo Keyd" in result
        assert "Vivo Keyd Stars Academy" not in result

    def test_duracao_presente(self):
        pg = _make_postgame()
        result = format_postgame_game(pg)
        assert "46min" in result or "29min" in result

    def test_duracao_ausente_nao_quebra(self):
        pg = _make_postgame(
            games=[GameResult(game_id=1, position=1, winner_id=161,
                              winner_name="RED Canids", length_seconds=None)],
        )
        result = format_postgame_game(pg)
        assert "?" in result
        assert len(result) <= TWITTER_LIMIT

    def test_placar_presente(self):
        pg = _make_postgame(score_a=1, score_b=0)
        result = format_postgame_game(pg)
        assert "1x0" in result

    def test_games_vazio_retorna_string_vazia(self):
        pg = _make_postgame(games=[])
        result = format_postgame_game(pg)
        assert result == ""

    def test_summary_incluido_quando_cabe(self):
        summary = "Domínio total no mid."
        pg = _make_postgame(game_summary=summary)
        result = format_postgame_game(pg)
        assert summary in result

    def test_summary_longo_truncado(self):
        pg = _make_postgame(game_summary="X" * 300)
        result = format_postgame_game(pg)
        assert len(result) <= TWITTER_LIMIT

    def test_hashtags_presentes(self):
        pg = _make_postgame()
        result = format_postgame_game(pg)
        assert "#CBLOL" in result


# ---------------------------------------------------------------------------
# format_postgame_series
# ---------------------------------------------------------------------------

class TestFormatPostgameSeries:
    def test_nunca_passa_280_chars(self):
        pg = _make_postgame(
            team_a_name="Vivo Keyd Stars Academy",
            team_b_name="Ei Nerd Esports",
            series_summary="B" * 300,
        )
        result = format_postgame_series(pg)
        assert len(result) <= TWITTER_LIMIT, f"passou de 280: {len(result)} chars"

    def test_previsao_correta_mostra_check(self):
        pg = _make_postgame(prediction_correct=True)
        result = format_postgame_series(pg)
        assert "✅" in result

    def test_previsao_errada_mostra_x(self):
        pg = _make_postgame(prediction_correct=False,
                            predicted_winner="Fluxo W7M")
        result = format_postgame_series(pg)
        assert "❌" in result

    def test_sem_previsao_sem_linha_de_acerto(self):
        pg = _make_postgame(predicted_winner=None, prediction_correct=None)
        result = format_postgame_series(pg)
        assert "✅" not in result
        assert "❌" not in result

    def test_vencedor_no_header(self):
        pg = _make_postgame(score_a=2, score_b=0)
        result = format_postgame_series(pg)
        assert "Red Canids" in result
        assert "vence" in result

    def test_placar_presente(self):
        pg = _make_postgame(score_a=2, score_b=1)
        result = format_postgame_series(pg)
        assert "2x1" in result

    def test_nomes_abreviados(self):
        pg = _make_postgame(
            team_a_name="Vivo Keyd Stars Academy",
            team_b_name="KaBuM! Ilha das Lendas",
            score_a=2,
            score_b=0,
            predicted_winner="Vivo Keyd Stars Academy",
            prediction_correct=True,
        )
        result = format_postgame_series(pg)
        assert "Vivo Keyd" in result
        assert "KaBuM!" in result
        assert "Vivo Keyd Stars Academy" not in result
        assert "KaBuM! Ilha das Lendas" not in result

    def test_summary_incluido_quando_cabe(self):
        summary = "Série controlada do início ao fim."
        pg = _make_postgame(series_summary=summary)
        result = format_postgame_series(pg)
        assert summary in result

    def test_summary_longo_truncado(self):
        pg = _make_postgame(series_summary="Y" * 300)
        result = format_postgame_series(pg)
        assert len(result) <= TWITTER_LIMIT

    def test_hashtags_presentes(self):
        pg = _make_postgame()
        result = format_postgame_series(pg)
        assert "#CBLOL" in result

    def test_score_empatado_nao_quebra(self):
        """Edge case de forfeit ou dados incompletos."""
        pg = _make_postgame(score_a=0, score_b=0)
        result = format_postgame_series(pg)
        assert len(result) <= TWITTER_LIMIT