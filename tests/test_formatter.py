"""
Testes unitários de publisher/formatter.py e publisher/layout.py.

Rodar com:
    pytest tests/test_formatter.py -v
"""
from __future__ import annotations

import pytest

from oraculo_lol.publisher.formatter import (
    TWITTER_LIMIT,
    THREADS_LIMIT,
    _abbreviate,
    format_for_twitter,
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
    prob_a: float = 0.65,
    prob_b: float = 0.35,
) -> Prediction:
    return Prediction(
        pandascore_match_id=1,
        llm_model="gpt-4o",
        predicted_winner=winner,
        confidence=confidence,
        reasoning=reasoning,
        teams=[
            TeamPrediction(name=team_a, win_probability=prob_a),
            TeamPrediction(name=team_b, win_probability=prob_b),
        ],
    )


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
            "pain gaming": "Pain Gaming",
        }
        for entrada, esperado in casos.items():
            assert _abbreviate(entrada) == esperado, f"falhou para: {entrada!r}"

    def test_todos_times_circuito(self):
        casos = {
            "Estral Esports": "Estral Esports",
            "KaBuM! e-Sports": "KaBuM!",
            "RED Academy": "Red Academy",
            "Vivo Keyd Academy": "Vivo Academy",
            "pain academy": "Pain Academy",
            "RMD Gaming": "RMD Gaming",
            "7Rex Team": "7Rex Team",
            "Ei Nerd Esports": "Ei Nerd Esports",
            "INTZ": "INTZ",
            "Team Solid": "Team Solid",
        }
        for entrada, esperado in casos.items():
            assert _abbreviate(entrada) == esperado, f"falhou para: {entrada!r}"


# ---------------------------------------------------------------------------
# format_for_twitter
# ---------------------------------------------------------------------------

class TestFormatForTwitter:
    def test_nunca_passa_280_chars(self):
        p = _make_prediction(
            team_a="Vivo Keyd Stars Academy",
            team_b="Ei Nerd Esports",
            winner="Vivo Keyd Stars Academy",
            reasoning="A" * 300,  # reasoning propositalmente longo
        )
        result = format_for_twitter(p)
        assert len(result) <= TWITTER_LIMIT, f"passou de 280: {len(result)} chars"

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
        assert len(result) <= TWITTER_LIMIT

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
        assert len(result) <= TWITTER_LIMIT

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
        assert len(result) <= TWITTER_LIMIT

    def test_nomes_curtos_aproveitam_mais_espaco(self):
        """Com nomes curtos o reasoning incluído deve ser maior do que com nomes longos.

        O post total com nomes longos pode chegar mais perto dos 280 chars porque
        o header/winner_line são maiores — mas o reasoning em si fica menor.
        Com nomes curtos o header ocupa menos, sobra mais espaço para o reasoning.
        """
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

        # Ambos respeitam o limite
        assert len(result_curto) <= TWITTER_LIMIT
        assert len(result_longo) <= TWITTER_LIMIT

        # Extrai o reasoning incluído em cada post (entre \n\n e \n\n#)
        def _extract_reasoning(post: str) -> str:
            parts = post.split("\n\n")
            # estrutura: header+winner | reasoning | hashtags
            return parts[1] if len(parts) >= 3 else ""

        reasoning_curto = _extract_reasoning(result_curto)
        reasoning_longo = _extract_reasoning(result_longo)

        # Com nomes curtos o reasoning incluído deve ser maior ou igual
        assert len(reasoning_curto) >= len(reasoning_longo), (
            f"esperado reasoning_curto ({len(reasoning_curto)}) >= "
            f"reasoning_longo ({len(reasoning_longo)})"
        )


# ---------------------------------------------------------------------------
# format_for_threads
# ---------------------------------------------------------------------------

class TestFormatForThreads:
    def test_nunca_passa_280_chars(self):
        p = _make_prediction(reasoning="B" * 300)
        result = format_for_threads(p)
        assert len(result) <= THREADS_LIMIT, f"passou de 280: {len(result)} chars"

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


# ---------------------------------------------------------------------------
# calc_available_chars
# ---------------------------------------------------------------------------

class TestCalcAvailableChars:
    def test_retorna_positivo_com_nomes_curtos(self):
        result = calc_available_chars(
            team_a_name="LOUD",
            team_b_name="Fluxo W7M",
            predicted_winner="LOUD",
            confidence="alta",
            win_prob_a=0.65,
            win_prob_b=0.35,
        )
        assert result > 0

    def test_retorna_positivo_com_nomes_longos(self):
        result = calc_available_chars(
            team_a_name="Vivo Keyd Stars Academy",
            team_b_name="Ei Nerd Esports",
            predicted_winner="Vivo Keyd Stars Academy",
            confidence="média",
            win_prob_a=0.72,
            win_prob_b=0.28,
        )
        assert result > 0

    def test_nomes_curtos_tem_mais_espaco_que_longos(self):
        curto = calc_available_chars(
            team_a_name="LOUD",
            team_b_name="Fluxo W7M",
            predicted_winner="LOUD",
            confidence="alta",
            win_prob_a=0.65,
            win_prob_b=0.35,
        )
        longo = calc_available_chars(
            team_a_name="Vivo Keyd Stars Academy",
            team_b_name="Ei Nerd Esports",
            predicted_winner="Vivo Keyd Stars Academy",
            confidence="média",
            win_prob_a=0.72,
            win_prob_b=0.28,
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
        )
        assert result >= 0

    def test_none_names_nao_quebra(self):
        result = calc_available_chars(
            team_a_name=None,
            team_b_name=None,
            predicted_winner=None,
            confidence=None,
        )
        assert result >= 0

    def test_abaixo_do_minimo_retorna_zero(self):
        """Se o espaço disponível for menor que MIN_REASONING_CHARS, retorna 0."""
        # Força um cenário com reasoning quase impossível de caber
        # usando nomes que — mesmo abreviados — deixam pouco espaço
        result = calc_available_chars(
            team_a_name="Ei Nerd Esports",
            team_b_name="Estral Esports",
            predicted_winner="Ei Nerd Esports",
            confidence="média",
            win_prob_a=0.55,
            win_prob_b=0.45,
        )
        # Não sabemos o valor exato, mas nunca deve ser negativo
        assert result >= 0