from __future__ import annotations

from ..oraculo.prediction import Prediction

TWITTER_LIMIT = 280
THREADS_LIMIT = 500

# Emojis por nível de confiança
_CONFIDENCE_EMOJI = {
    "alta": "🔥",
    "média": "⚡",
    "baixa": "🤔",
}

def _prob_bar(prob: float | None) -> str:
    """Barra de probabilidade com caracteres compatíveis em todos os dispositivos."""
    if prob is None:
        return ""
    filled = round(prob * 10)
    return "●" * filled + "○" * (10 - filled)


def _header(prediction: Prediction) -> str:
    """Linha de abertura com os times e o favorito."""
    teams = prediction.teams
    if len(teams) == 2:
        a, b = teams[0].name, teams[1].name
        return f"⚔️ {a} vs {b}"
    return "⚔️ Prévia de Partida"


def _winner_line(prediction: Prediction) -> str:
    emoji = _CONFIDENCE_EMOJI.get(prediction.confidence or "", "🎯")
    conf = (prediction.confidence or "?").upper()
    winner = prediction.winner if hasattr(prediction, "winner") else prediction.predicted_winner
    return f"{emoji} Favorito: {winner} | Confiança: {conf}"


def _probs_block(prediction: Prediction) -> str:
    lines = []
    for t in prediction.teams:
        prob = t.win_probability
        pct = f"{prob * 100:.0f}%" if prob is not None else "?"
        bar = _prob_bar(prob)
        lines.append(f"{t.name}: {pct} {bar}")
    return "\n".join(lines)


def _hashtags() -> str:
    return "#CBLOL #LoL #Circuitão #OráculoDoLoL"


def format_for_twitter(prediction: Prediction) -> str:
    """
    Monta o post para o X respeitando 280 caracteres.
    Prioridade: header + favorito + probabilidades + hashtags.
    O reasoning é incluído só se couber.
    """
    header = _header(prediction)
    winner = _winner_line(prediction)
    probs = _probs_block(prediction)
    tags = _hashtags()

    # Versão completa com reasoning
    reasoning = prediction.reasoning or ""
    full = f"{header}\n{winner}\n\n{probs}\n\n{reasoning}\n\n{tags}"
    if len(full) <= TWITTER_LIMIT:
        return full

    # Sem reasoning
    short = f"{header}\n{winner}\n\n{probs}\n\n{tags}"
    if len(short) <= TWITTER_LIMIT:
        return short

    # Sem probabilidades (último recurso)
    minimal = f"{header}\n{winner}\n\n{tags}"
    return minimal[:TWITTER_LIMIT]


def format_for_threads(prediction: Prediction) -> str:
    """
    Monta o post para o Threads respeitando 500 caracteres.
    Threads tem mais espaço — inclui reasoning quando possível.
    """
    header = _header(prediction)
    winner = _winner_line(prediction)
    probs = _probs_block(prediction)
    reasoning = prediction.reasoning or ""
    tags = _hashtags()

    full = f"{header}\n{winner}\n\n{probs}\n\n{reasoning}\n\n{tags}"
    if len(full) <= THREADS_LIMIT:
        return full

    # Trunca o reasoning se não couber
    base = f"{header}\n{winner}\n\n{probs}\n\n"
    suffix = f"\n\n{tags}"
    available = THREADS_LIMIT - len(base) - len(suffix)
    if available > 20 and reasoning:
        truncated = reasoning[:available - 3] + "..."
        return f"{base}{truncated}{suffix}"

    return f"{base}{suffix}"[:THREADS_LIMIT]