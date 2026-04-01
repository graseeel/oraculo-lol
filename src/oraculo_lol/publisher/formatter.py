from __future__ import annotations

from ..oraculo.prediction import Prediction

TWITTER_LIMIT = 280
THREADS_LIMIT = 280  # Padronizado com o X para consistência entre plataformas

_CONFIDENCE_EMOJI = {
    "alta": "🔥",
    "média": "⚡",
    "baixa": "🤔",
}


def _header(prediction: Prediction) -> str:
    teams = prediction.teams
    if len(teams) == 2:
        a, b = teams[0].name, teams[1].name
        return f"⚔️ {a} vs {b}"
    return "⚔️ Prévia de Partida"


def _winner_line(prediction: Prediction) -> str:
    """Linha com favorito e probabilidades inline — sem bolinhas."""
    emoji = _CONFIDENCE_EMOJI.get(prediction.confidence or "", "🎯")
    conf = (prediction.confidence or "?").upper()
    winner = prediction.predicted_winner or "?"

    # Probabilidades inline: LOUD (75%) vs paiN (25%)
    if len(prediction.teams) == 2:
        a, b = prediction.teams[0], prediction.teams[1]
        pa = f"{a.win_probability * 100:.0f}%" if a.win_probability is not None else "?"
        pb = f"{b.win_probability * 100:.0f}%" if b.win_probability is not None else "?"
        probs = f"{a.name} ({pa}) vs {b.name} ({pb})"
        return f"{emoji} Favorito: {winner} | {conf}\n{probs}"

    return f"{emoji} Favorito: {winner} | Confiança: {conf}"


def _hashtags() -> str:
    return "#CBLOL #LoL #Circuitão #OráculoDoLoL"


def format_for_twitter(prediction: Prediction) -> str:
    """
    Monta o post para o X respeitando 280 caracteres.
    Trunca o reasoning deterministicamente — não depende do GPT respeitar o limite.
    """
    header = _header(prediction)
    winner = _winner_line(prediction)
    tags = _hashtags()
    reasoning = prediction.reasoning or ""

    # Calcula espaço disponível para o reasoning
    base = f"{header}\n{winner}\n\n"
    suffix = f"\n\n{tags}"
    available = TWITTER_LIMIT - len(base) - len(suffix)

    if available > 20 and reasoning:
        if len(reasoning) <= available:
            truncated = reasoning
        else:
            # Trunca na última palavra inteira antes do limite
            truncated = reasoning[:available - 3].rsplit(" ", 1)[0] + "..."
        return f"{base}{truncated}{suffix}"

    # Sem reasoning se não couber
    short = f"{header}\n{winner}\n\n{tags}"
    return short[:TWITTER_LIMIT]


def format_for_threads(prediction: Prediction) -> str:
    """
    Monta o post para o Threads respeitando 500 caracteres.
    Threads tem mais espaço — reasoning completo quando possível.
    """
    header = _header(prediction)
    winner = _winner_line(prediction)
    reasoning = prediction.reasoning or ""
    tags = _hashtags()

    full = f"{header}\n{winner}\n\n{reasoning}\n\n{tags}"
    if len(full) <= THREADS_LIMIT:
        return full

    # Trunca reasoning
    base = f"{header}\n{winner}\n\n"
    suffix = f"\n\n{tags}"
    available = THREADS_LIMIT - len(base) - len(suffix)
    if available > 20 and reasoning:
        truncated = reasoning[:available - 3] + "..."
        return f"{base}{truncated}{suffix}"

    return f"{base}{suffix}"[:THREADS_LIMIT]