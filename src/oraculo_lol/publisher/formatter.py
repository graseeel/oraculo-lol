from __future__ import annotations

from ..oraculo.prediction import Prediction

TWITTER_LIMIT = 280
THREADS_LIMIT = 280

_CONFIDENCE_EMOJI = {
    "alta": "🔥",
    "média": "⚡",
    "baixa": "🤔",
}

_TEAM_NAMES: dict[str, str] = {
    # CBLOL
    "fluxo w7m": "Fluxo",
    "los grandes": "LOS",
    "vivo keyd stars": "Vivo Keyd",
    "vivo keyd stars academy": "Vivo Keyd",
    "red canids kalunga": "Red Canids",
    "red canids": "Red Canids",
    "furia esports": "Furia",
    "loud": "Loud",
    "leviatan": "Leviatan",
    "leviatán": "Leviatan",
    "pain gaming": "Pain Gaming",
    # Circuito Desafiante
    "estral esports": "Estral Esports",
    "kabum! e-sports": "KaBuM!",
    "kabum! esports": "KaBuM!",
    "kabum!": "KaBuM!",
    "red academy": "Red Academy",
    "vivo keyd academy": "Vivo Academy",
    "pain academy": "Pain Academy",
    "rmd gaming": "RMD Gaming",
    "7rex team": "7Rex Team",
    "ei nerd esports": "Ei Nerd Esports",
    "intz": "INTZ",
    "team solid": "Team Solid",
}


def _abbreviate(name: str | None) -> str:
    if not name:
        return "?"
    return _TEAM_NAMES.get(name.lower(), name)


def _header(prediction: Prediction) -> str:
    teams = prediction.teams
    if len(teams) == 2:
        a = _abbreviate(teams[0].name)
        b = _abbreviate(teams[1].name)
        return f"⚔️ {a} vs {b}"
    return "⚔️ Prévia de Partida"


def _winner_line(prediction: Prediction) -> str:
    emoji = _CONFIDENCE_EMOJI.get(prediction.confidence or "", "🎯")
    conf = (prediction.confidence or "?").upper()
    winner = _abbreviate(prediction.predicted_winner)

    if len(prediction.teams) == 2:
        a, b = prediction.teams[0], prediction.teams[1]
        pa = f"{a.win_probability * 100:.0f}%" if a.win_probability is not None else "?"
        pb = f"{b.win_probability * 100:.0f}%" if b.win_probability is not None else "?"
        a_name = _abbreviate(a.name)
        b_name = _abbreviate(b.name)
        probs = f"{a_name} ({pa}) vs {b_name} ({pb})"
        return f"{emoji} Favorito: {winner} | {conf}\n{probs}"

    return f"{emoji} Favorito: {winner} | Confiança: {conf}"


def _hashtags() -> str:
    return "#CBLOL #LoL #Circuitão #OráculoDoLoL"


def format_for_twitter(prediction: Prediction) -> str:
    header = _header(prediction)
    winner = _winner_line(prediction)
    tags = _hashtags()
    reasoning = prediction.reasoning or ""

    base = f"{header}\n{winner}\n\n"
    suffix = f"\n\n{tags}"
    available = TWITTER_LIMIT - len(base) - len(suffix)

    if available > 20 and reasoning:
        if len(reasoning) <= available:
            truncated = reasoning
        else:
            truncated = reasoning[:available - 3].rsplit(" ", 1)[0] + "..."
        return f"{base}{truncated}{suffix}"

    short = f"{header}\n{winner}\n\n{tags}"
    return short[:TWITTER_LIMIT]


def format_for_threads(prediction: Prediction) -> str:
    header = _header(prediction)
    winner = _winner_line(prediction)
    reasoning = prediction.reasoning or ""
    tags = _hashtags()

    full = f"{header}\n{winner}\n\n{reasoning}\n\n{tags}"
    if len(full) <= THREADS_LIMIT:
        return full

    base = f"{header}\n{winner}\n\n"
    suffix = f"\n\n{tags}"
    available = THREADS_LIMIT - len(base) - len(suffix)
    if available > 20 and reasoning:
        truncated = reasoning[:available - 3] + "..."
        return f"{base}{truncated}{suffix}"

    return f"{base}{suffix}"[:THREADS_LIMIT]