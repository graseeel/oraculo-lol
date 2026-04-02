from __future__ import annotations

from .formatter import TWITTER_LIMIT, _abbreviate, _hashtags

# Chars mínimos para valer a pena incluir reasoning no prompt.
# Abaixo disso o GPT geraria algo tão curto que ficaria pior do que nada.
MIN_REASONING_CHARS = 40


def calc_available_chars(
    team_a_name: str | None,
    team_b_name: str | None,
    predicted_winner: str | None,
    confidence: str | None,
    win_prob_a: float | None = None,
    win_prob_b: float | None = None,
) -> int:
    """
    Calcula quantos chars sobram para o reasoning após montar
    header + winner_line + hashtags, usando os nomes abreviados.

    Retorna 0 se o espaço for menor que MIN_REASONING_CHARS.
    Fonte da verdade: TWITTER_LIMIT (280).
    """
    a = _abbreviate(team_a_name)
    b = _abbreviate(team_b_name)
    winner = _abbreviate(predicted_winner)
    conf = (confidence or "?").upper()

    # Replica a estrutura de _header
    header = f"⚔️ {a} vs {b}" if (team_a_name and team_b_name) else "⚔️ Prévia de Partida"

    # Replica a estrutura de _winner_line
    emoji = "🎯"  # pior caso (emoji maior não existe aqui, todos têm o mesmo len)
    pa = f"{win_prob_a * 100:.0f}%" if win_prob_a is not None else "?"
    pb = f"{win_prob_b * 100:.0f}%" if win_prob_b is not None else "?"
    probs = f"{a} ({pa}) vs {b} ({pb})"
    winner_line = f"{emoji} Favorito: {winner} | {conf}\n{probs}"

    tags = _hashtags()

    # Estrutura completa do post: base + reasoning + suffix
    base = f"{header}\n{winner_line}\n\n"
    suffix = f"\n\n{tags}"
    available = TWITTER_LIMIT - len(base) - len(suffix)

    return max(available, 0) if available >= MIN_REASONING_CHARS else 0