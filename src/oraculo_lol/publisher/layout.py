from __future__ import annotations

from .formatter import THREADS_LIMIT, TWITTER_LIMIT, TWITTER_SHORT_LIMIT, _abbreviate, _hashtags

# Chars mínimos para valer a pena incluir reasoning
MIN_REASONING_CHARS = 40


def calc_available_chars(
    team_a_name: str | None,
    team_b_name: str | None,
    predicted_winner: str | None,
    confidence: str | None,
    win_prob_a: float | None = None,
    win_prob_b: float | None = None,
    *,
    platform: str = "threads",
) -> int:
    """
    Calcula quantos chars sobram para o reasoning após montar o post fixo.

    platform:
        "twitter_short" → TWITTER_SHORT_LIMIT (280) — legado/fallback
        "threads"       → THREADS_LIMIT (500)
        "twitter_long"  → não usa esse cálculo (25000 chars, sem restrição prática)

    Retorna 0 se o espaço for menor que MIN_REASONING_CHARS.
    """
    if platform == "twitter_long":
        # Com 25000 chars o reasoning pode ser longo — retorna um valor generoso
        return 1500

    limit = THREADS_LIMIT if platform == "threads" else TWITTER_SHORT_LIMIT

    a = _abbreviate(team_a_name)
    b = _abbreviate(team_b_name)
    winner = _abbreviate(predicted_winner)
    conf = (confidence or "?").upper()

    header = f"⚔️ {a} vs {b}" if (team_a_name and team_b_name) else "⚔️ Prévia de Partida"

    emoji = "🎯"
    pa = f"{win_prob_a * 100:.0f}%" if win_prob_a is not None else "?"
    pb = f"{win_prob_b * 100:.0f}%" if win_prob_b is not None else "?"
    probs = f"{a} ({pa}) vs {b} ({pb})"
    winner_line = f"{emoji} Favorito: {winner} | {conf}\n{probs}"

    tags = _hashtags()
    base = f"{header}\n{winner_line}\n\n"
    suffix = f"\n\n{tags}"
    available = limit - len(base) - len(suffix)

    return max(available, 0) if available >= MIN_REASONING_CHARS else 0