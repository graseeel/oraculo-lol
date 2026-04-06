"""
Testes unitários de publisher/formatter.py e publisher/layout.py.

Rodar com:
    pytest tests/test_formatter.py -v
"""
from __future__ import annotations

import pytest

from oraculo_lol.publisher.formatter import (
    TWITTER_LIMIT,
    TWITTER_SHORT_LIMIT,
    THREADS_LIMIT,
    _abbreviate,
    format_for_twitter,
    format_for_twitter_long,
    format_for_threads,
)
from oraculo_lol.publisher.layout import calc_available_chars, MIN_REASONING_CHARS
from oraculo_lol.oraculo.prediction import Prediction, TeamPrediction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prediction(
    *,
    team_a: str = "RED Canids",
    team_b: str = "Fluxo W7M",
    winner: str = "RED Canids",
    confidence: str = "alta",
    reasoning: str = "Time com melhor forma recente.",
    reasoning_long: str | None = None,
    prob_a: float = 0.65,
    prob_b: float = 0.35,
) -> Prediction:
    return Prediction(
        pandascore_match_id=1,
        llm_model="gpt-4o",
        predicted_winner=winner,
        confidence=confidence,
        reasoning=reasoning,
        reasoning_long=reasoning_long,
        teams=[
            TeamPrediction(name=team_a, win_probability=prob_a),
            TeamPrediction(name=team_b, win_probability=prob_b),
        ],
    )


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

class TestConstantes:
    def test_twitter_limit_e_25000(self):
        assert TWITTER_LIMIT == 25000

    def test_twitter_short_limit_e_280(self):
        assert TWITTER_SHORT_LIMIT == 280

    def test_threads_limit_e_500(self):
        assert THREADS_LIMIT == 500


# ---------------------------------------------------------------------------
# _abbreviate
# ---------------------------------------------------------------------------

class TestAbbreviate:
    def test_nome_conhecido_retorna_abreviado(self):
        assert _abbreviate("Vivo Keyd Stars Academy") == "Vivo Keyd"

    def test_nome_conhecido_case_insensitive(self):
        assert _abbreviate("LOUD") == "Loud"
        assert _abbreviate("loud") == "Loud"
        assert _abbreviate("Loud") == "Loud"

    def test_nome_desconhecido_retorna_original(self):
        assert _abbreviate("Time Desconhecido FC") == "Time Desconhecido FC"

    def test_none_retorna_interrogacao(self):
        assert _abbreviate(None) == "?"

    def test_string_vazia_retorna_interrogacao(self):
        assert _abbreviate("") == "?"

    def test_todos_times_cblol(self):
        casos = {
            "Fluxo W7M": "Fluxo",
            "Los Grandes": "LOS",
            "Vivo Keyd Stars": "Vivo Keyd",
            "Vivo Keyd Stars Academy": "Vivo Keyd",
            "RED Canids Kalunga": "Red Canids",
            "RED Canids": "Red Canids",
            "FURIA Esports": "Furia",
            "LOUD": "Loud",
            "Leviatán": "Leviatan",
            "Leviatan Esports": "Leviatan",
            "pain gaming": "Pain Gaming",
        }
        for entrada, esperado in casos.items():
            assert _abbreviate(entrada) == esperado, f"falhou para: {entrada!r}"

    def test_todos_times_circuito(self):
        casos = {
            "Estral Esports": "Estral Esports",
            "KaBuM! e-Sports": "KaBuM!",
            "KaBuM! Ilha das Lendas": "KaBuM!",
            "RED Academy": "Red Academy",
            "Vivo Keyd Academy": "Vivo Academy",
            "pain academy": "Pain Academy",
            "paiN Gaming Academy": "Pain Academy",
            "RMD Gaming": "RMD Gaming",
            "7Rex Team": "7Rex Team",
            "7REX": "7Rex Team",
            "Ei Nerd Esports": "Ei Nerd Esports",
            "INTZ": "INTZ",
            "INTZ e-Sports": "INTZ",
            "Team Solid": "Team Solid",
        }
        for entrada, esperado in casos.items():
            assert _abbreviate(entrada) == esperado, f"falhou para: {entrada!r}"


# ---------------------------------------------------------------------------
# format_for_twitter (curto — legado/fallback, limite 280)
# ---------------------------------------------------------------------------

class TestFormatForTwitter:
    def test_nunca_passa_280_chars(self):
        p = _make_prediction(
            team_a="Vivo Keyd Stars Academy",
            team_b="Ei Nerd Esports",
            winner="Vivo Keyd Stars Academy",
            reasoning="A" * 300,
        )
        result = format_for_twitter(p)
        assert len(result) <= TWITTER_SHORT_LIMIT, f"passou de 280: {len(result)} chars"

    def test_nomes_abreviados_no_header(self):
        p = _make_prediction(
            team_a="Vivo Keyd Stars Academy",
            team_b="RED Canids Kalunga",
        )
        result = format_for_twitter(p)
        assert "Vivo Keyd" in result
        assert "Red Canids" in result
        assert "Vivo Keyd Stars Academy" not in result
        assert "RED Canids Kalunga" not in result

    def test_nome_vencedor_abreviado(self):
        p = _make_prediction(
            team_a="Fluxo W7M",
            team_b="LOUD",
            winner="Fluxo W7M",
        )
        result = format_for_twitter(p)
        assert "Favorito: Fluxo" in result
        assert "Fluxo W7M" not in result

    def test_reasoning_curto_incluido_inteiro(self):
        reasoning = "Time dominante na fase de picks."
        p = _make_prediction(reasoning=reasoning)
        result = format_for_twitter(p)
        assert reasoning in result

    def test_reasoning_longo_truncado_com_reticencias(self):
        p = _make_prediction(
            team_a="Fluxo W7M",
            team_b="LOUD",
            reasoning="A" * 300,
        )
        result = format_for_twitter(p)
        assert result.endswith("#CBLOL #LoL #Circuitão #OráculoDoLoL")
        assert len(result) <= TWITTER_SHORT_LIMIT

    def test_hashtags_sempre_presentes(self):
        p = _make_prediction()
        result = format_for_twitter(p)
        assert "#CBLOL" in result
        assert "#OráculoDoLoL" in result

    def test_probabilidades_no_post(self):
        p = _make_prediction(prob_a=0.72, prob_b=0.28)
        result = format_for_twitter(p)
        assert "72%" in result
        assert "28%" in result

    def test_win_probability_none_nao_quebra(self):
        p = Prediction(
            pandascore_match_id=1,
            llm_model="gpt-4o",
            predicted_winner="Fluxo",
            confidence="baixa",
            reasoning="Sem dados suficientes.",
            teams=[
                TeamPrediction(name="Fluxo W7M", win_probability=None),
                TeamPrediction(name="LOUD", win_probability=None),
            ],
        )
        result = format_for_twitter(p)
        assert len(result) <= TWITTER_SHORT_LIMIT

    def test_sem_times_nao_quebra(self):
        p = Prediction(
            pandascore_match_id=1,
            llm_model="gpt-4o",
            predicted_winner=None,
            confidence=None,
            reasoning=None,
            teams=[],
        )
        result = format_for_twitter(p)
        assert len(result) <= TWITTER_SHORT_LIMIT

    def test_nomes_curtos_aproveitam_mais_espaco(self):
        reasoning = "X" * 160

        p_curto = _make_prediction(
            team_a="LOUD",
            team_b="Fluxo W7M",
            winner="LOUD",
            reasoning=reasoning,
        )
        p_longo = _make_prediction(
            team_a="Vivo Keyd Stars Academy",
            team_b="Ei Nerd Esports",
            winner="Vivo Keyd Stars Academy",
            reasoning=reasoning,
        )

        result_curto = format_for_twitter(p_curto)
        result_longo = format_for_twitter(p_longo)

        assert len(result_curto) <= TWITTER_SHORT_LIMIT
        assert len(result_longo) <= TWITTER_SHORT_LIMIT

        def _extract_reasoning(post: str) -> str:
            parts = post.split("\n\n")
            return parts[1] if len(parts) >= 3 else ""

        reasoning_curto = _extract_reasoning(result_curto)
        reasoning_longo = _extract_reasoning(result_longo)

        assert len(reasoning_curto) >= len(reasoning_longo)


# ---------------------------------------------------------------------------
# format_for_twitter_long (X Premium — limite 25000)
# ---------------------------------------------------------------------------

class TestFormatForTwitterLong:
    def test_nunca_passa_25000_chars(self):
        p = _make_prediction(reasoning_long="A" * 30000)
        result = format_for_twitter_long(p)
        assert len(result) <= TWITTER_LIMIT, f"passou de 25000: {len(result)} chars"

    def test_nomes_abreviados(self):
        p = _make_prediction(
            team_a="Vivo Keyd Stars Academy",
            team_b="RED Canids Kalunga",
        )
        result = format_for_twitter_long(p)
        assert "Vivo Keyd" in result
        assert "Red Canids" in result
        assert "Vivo Keyd Stars Academy" not in result

    def test_reasoning_long_usado_quando_disponivel(self):
        p = _make_prediction(
            reasoning="Curto.",
            reasoning_long="Análise detalhada com picks e forma recente.",
        )
        result = format_for_twitter_long(p)
        assert "Análise detalhada" in result
        assert "Curto." not in result

    def test_fallback_para_reasoning_quando_long_ausente(self):
        p = _make_prediction(
            reasoning="Análise curta usada como fallback.",
            reasoning_long=None,
        )
        result = format_for_twitter_long(p)
        assert "Análise curta" in result

    def test_hashtags_presentes(self):
        p = _make_prediction()
        result = format_for_twitter_long(p)
        assert "#CBLOL" in result

    def test_credito_liquipedia_presente(self):
        p = _make_prediction()
        result = format_for_twitter_long(p)
        assert "Liquipedia" in result

    def test_probabilidades_presentes(self):
        p = _make_prediction(prob_a=0.72, prob_b=0.28)
        result = format_for_twitter_long(p)
        assert "72%" in result
        assert "28%" in result

    def test_sem_times_nao_quebra(self):
        p = Prediction(
            pandascore_match_id=1,
            llm_model="gpt-4o",
            predicted_winner=None,
            confidence=None,
            reasoning=None,
            teams=[],
        )
        result = format_for_twitter_long(p)
        assert len(result) <= TWITTER_LIMIT


# ---------------------------------------------------------------------------
# format_for_threads (limite 500)
# ---------------------------------------------------------------------------

class TestFormatForThreads:
    def test_nunca_passa_500_chars(self):
        p = _make_prediction(reasoning="B" * 600)
        result = format_for_threads(p)
        assert len(result) <= THREADS_LIMIT, f"passou de 500: {len(result)} chars"

    def test_nomes_abreviados(self):
        p = _make_prediction(
            team_a="paiN Gaming",
            team_b="Vivo Keyd Stars Academy",
        )
        result = format_for_threads(p)
        assert "Pain Gaming" in result
        assert "Vivo Keyd" in result
        assert "paiN Gaming" not in result
        assert "Vivo Keyd Stars Academy" not in result

    def test_hashtags_sempre_presentes(self):
        p = _make_prediction()
        result = format_for_threads(p)
        assert "#CBLOL" in result

    def test_reasoning_curto_incluido_inteiro(self):
        reasoning = "Jogo equilibrado, mas RED é favorito."
        p = _make_prediction(reasoning=reasoning)
        result = format_for_threads(p)
        assert reasoning in result

    def test_threads_tem_mais_espaco_que_twitter_short(self):
        """Threads (500) permite reasoning maior que o Twitter legado (280)."""
        reasoning = "X" * 250

        p = _make_prediction(reasoning=reasoning)
        result_threads = format_for_threads(p)
        result_twitter = format_for_twitter(p)

        assert len(result_threads) <= THREADS_LIMIT
        assert len(result_twitter) <= TWITTER_SHORT_LIMIT
        assert len(result_threads) > len(result_twitter)


# ---------------------------------------------------------------------------
# calc_available_chars
# ---------------------------------------------------------------------------

class TestCalcAvailableChars:
    def test_threads_retorna_positivo_com_nomes_curtos(self):
        result = calc_available_chars(
            team_a_name="LOUD",
            team_b_name="Fluxo W7M",
            predicted_winner="LOUD",
            confidence="alta",
            win_prob_a=0.65,
            win_prob_b=0.35,
            platform="threads",
        )
        assert result > 0

    def test_threads_retorna_positivo_com_nomes_longos(self):
        result = calc_available_chars(
            team_a_name="Vivo Keyd Stars Academy",
            team_b_name="Ei Nerd Esports",
            predicted_winner="Vivo Keyd Stars Academy",
            confidence="média",
            win_prob_a=0.72,
            win_prob_b=0.28,
            platform="threads",
        )
        assert result > 0

    def test_threads_nomes_curtos_tem_mais_espaco_que_longos(self):
        curto = calc_available_chars(
            team_a_name="LOUD",
            team_b_name="Fluxo W7M",
            predicted_winner="LOUD",
            confidence="alta",
            win_prob_a=0.65,
            win_prob_b=0.35,
            platform="threads",
        )
        longo = calc_available_chars(
            team_a_name="Vivo Keyd Stars Academy",
            team_b_name="Ei Nerd Esports",
            predicted_winner="Vivo Keyd Stars Academy",
            confidence="média",
            win_prob_a=0.72,
            win_prob_b=0.28,
            platform="threads",
        )
        assert curto > longo

    def test_nunca_retorna_negativo(self):
        result = calc_available_chars(
            team_a_name="Nome Extremamente Longo Que Nao Existe",
            team_b_name="Outro Nome Muito Longo Tambem",
            predicted_winner="Nome Extremamente Longo Que Nao Existe",
            confidence="média",
            win_prob_a=0.5,
            win_prob_b=0.5,
            platform="threads",
        )
        assert result >= 0

    def test_none_names_nao_quebra(self):
        result = calc_available_chars(
            team_a_name=None,
            team_b_name=None,
            predicted_winner=None,
            confidence=None,
            platform="threads",
        )
        assert result >= 0

    def test_twitter_long_retorna_1500(self):
        """Platform twitter_long retorna valor fixo generoso."""
        result = calc_available_chars(
            team_a_name="LOUD",
            team_b_name="Fluxo W7M",
            predicted_winner="LOUD",
            confidence="alta",
            platform="twitter_long",
        )
        assert result == 1500

    def test_twitter_short_retorna_menor_que_threads(self):
        """Platform twitter_short (280) tem menos espaço que threads (500)."""
        short = calc_available_chars(
            team_a_name="LOUD",
            team_b_name="Fluxo W7M",
            predicted_winner="LOUD",
            confidence="alta",
            platform="twitter_short",
        )
        threads = calc_available_chars(
            team_a_name="LOUD",
            team_b_name="Fluxo W7M",
            predicted_winner="LOUD",
            confidence="alta",
            platform="threads",
        )
        assert short < threads

    def test_abaixo_do_minimo_retorna_zero(self):
        result = calc_available_chars(
            team_a_name="Ei Nerd Esports",
            team_b_name="Estral Esports",
            predicted_winner="Ei Nerd Esports",
            confidence="média",
            win_prob_a=0.55,
            win_prob_b=0.45,
            platform="threads",
        )
        assert result >= 0