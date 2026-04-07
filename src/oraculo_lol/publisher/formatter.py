from __future__ import annotations

from datetime import datetime, timezone

from ..models.postgame import MatchPostGame
from ..oraculo.prediction import Prediction

# X com Premium Basic — posts longos
TWITTER_LIMIT = 25000

# Threads — limite real da plataforma
THREADS_LIMIT = 500

# Limite legado mantido para compatibilidade e fallback
TWITTER_SHORT_LIMIT = 280

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
    "red canids kalunga": "Red Canids",
    "red canids": "Red Canids",
    "furia esports": "Furia",
    "loud": "Loud",
    "leviatan": "Leviatan",
    "leviatan esports": "Leviatan",
    "leviatán": "Leviatan",
    "pain gaming": "Pain Gaming",
    # Circuito Desafiante
    "estral esports": "Estral Esports",
    "kabum! e-sports": "KaBuM!",
    "kabum! esports": "KaBuM!",
    "kabum! ilha das lendas": "KaBuM!",
    "kabum!": "KaBuM!",
    "red academy": "Red Academy",
    "vivo keyd academy": "Vivo Academy",
    "vivo keyd stars academy": "Vivo Keyd",
    "pain academy": "Pain Academy",
    "pain gaming academy": "Pain Academy",
    "rmd gaming": "RMD Gaming",
    "7rex team": "7Rex Team",
    "7rex": "7Rex Team",
    "ei nerd esports": "Ei Nerd Esports",
    "intz": "INTZ",
    "intz e-sports": "INTZ",
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
    """Post curto — compatibilidade e fallback. Limite: 280 chars."""
    header = _header(prediction)
    winner = _winner_line(prediction)
    tags = _hashtags()
    reasoning = prediction.reasoning or ""

    base = f"{header}\n{winner}\n\n"
    suffix = f"\n\n{tags}"
    available = TWITTER_SHORT_LIMIT - len(base) - len(suffix)

    if available > 20 and reasoning:
        if len(reasoning) <= available:
            truncated = reasoning
        else:
            truncated = reasoning[:available - 3].rsplit(" ", 1)[0] + "..."
        return f"{base}{truncated}{suffix}"

    short = f"{header}\n{winner}\n\n{tags}"
    return short[:TWITTER_SHORT_LIMIT]


def format_for_twitter_long(prediction: Prediction) -> str:
    """
    Post longo para o X com Premium Basic — estilo gancho.

    Estrutura:
    ⚔️ TIME A vs TIME B — [data se disponível]

    [reasoning_long em 3 partes: afirmação forte / dado surpresa / conclusão]

    🔥 Previsão: VENCEDOR | CONFIANÇA
    TIME A X% × Y% TIME B

    #CBLOL #Circuitão #OráculoDoLoL
    Dados: Pandascore & Liquipedia
    """
    a_name = _abbreviate(prediction.teams[0].name) if len(prediction.teams) >= 1 else "?"
    b_name = _abbreviate(prediction.teams[1].name) if len(prediction.teams) >= 2 else "?"

    winner = _abbreviate(prediction.predicted_winner)
    conf_emoji = _CONFIDENCE_EMOJI.get(prediction.confidence or "", "🎯")
    conf = (prediction.confidence or "?").upper()

    pa = pb = None
    if len(prediction.teams) == 2:
        pa = prediction.teams[0].win_probability
        pb = prediction.teams[1].win_probability

    pa_str = f"{pa * 100:.0f}%" if pa is not None else "?"
    pb_str = f"{pb * 100:.0f}%" if pb is not None else "?"

    raw_reasoning = prediction.reasoning_long or prediction.reasoning or ""
    # Converte marcador [P] em parágrafos
    reasoning = raw_reasoning.replace("[P]", "\n\n")
    tags = _hashtags()

    lines = [
        f"⚔️ {a_name} vs {b_name}",
        "",
        reasoning,
        "",
        f"{conf_emoji} Previsão: {winner} | {conf}",
        f"{a_name} {pa_str} × {pb_str} {b_name}",
        "",
        tags,
        "Dados: Pandascore & Liquipedia",
    ]

    result = "\n".join(lines)
    return result[:TWITTER_LIMIT]


def format_for_threads(prediction: Prediction) -> str:
    """Post para o Threads — limite real de 500 chars."""
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


# ---------------------------------------------------------------------------
# Pós-jogo
# ---------------------------------------------------------------------------

def format_postgame_game(postgame: MatchPostGame) -> str:
    if not postgame.games:
        return ""

    game = postgame.games[-1]
    a = _abbreviate(postgame.team_a_name)
    b = _abbreviate(postgame.team_b_name)
    winner = _abbreviate(game.winner_name)
    dur = game.length_minutes

    header = f"🎮 Jogo {game.position} — {winner} vence em {dur}"
    score = f"Série: {a} {postgame.score_a}x{postgame.score_b} {b}"
    tags = _hashtags()

    base = f"{header}\n{score}\n"
    suffix = f"\n{tags}"
    available = TWITTER_SHORT_LIMIT - len(base) - len(suffix)

    summary = postgame.game_summary or ""
    if summary and available > 20:
        if len(summary) > available:
            summary = summary[:available - 3].rsplit(" ", 1)[0] + "..."
        return f"{base}{summary}{suffix}"

    return f"{base}{suffix}"[:TWITTER_SHORT_LIMIT]


def format_postgame_series(postgame: MatchPostGame) -> str:
    """
    Resultado final da série — usa espaço do X Premium (até 600 chars).
    Tom neutro no acerto/erro, análise do GPT expandida.
    """
    a = _abbreviate(postgame.team_a_name)
    b = _abbreviate(postgame.team_b_name)
    winner = _abbreviate(
        postgame.team_a_name if postgame.score_a > postgame.score_b else postgame.team_b_name
    )

    header = f"🏆 {winner} vence! {a} {postgame.score_a}×{postgame.score_b} {b}"

    prediction_line = ""
    if postgame.predicted_winner is not None:
        predicted = _abbreviate(postgame.predicted_winner)
        if postgame.prediction_correct:
            prediction_line = f"✅ Oráculo acertou — favorito {predicted} confirmado"
        else:
            prediction_line = f"❌ Oráculo errou — havia previsto {predicted}"

    summary = postgame.series_summary or ""
    tags = _hashtags()

    # Monta com espaço expandido do X Premium
    parts = [header]
    if prediction_line:
        parts.append(prediction_line)
    if summary:
        parts.append("")
        parts.append(summary)
    parts.append("")
    parts.append(tags)

    result = "\n".join(parts)
    return result[:TWITTER_LIMIT]


def format_daily_summary(summary: dict) -> str:
    """
    Resumo do dia de jogos — posta 1h após o último jogo.
    Formato compacto, cabe no Threads e no X.
    """
    total = summary.get("total", 0)
    acertos = summary.get("acertos", 0)
    erros = summary.get("erros", 0)
    acuracia = acertos / total * 100 if total > 0 else 0

    # Emoji de acurácia
    if acuracia >= 70:
        acc_emoji = "🔥"
    elif acuracia >= 50:
        acc_emoji = "⚡"
    else:
        acc_emoji = "🤔"

    # Linha de resultados individuais
    results = summary.get("results", [])
    result_lines = []
    for r in results:
        actual = _abbreviate(r.get("actual_winner"))
        predicted = _abbreviate(r.get("predicted_winner"))
        icon = "✅" if r.get("prediction_correct") else "❌"
        result_lines.append(f"{icon} {actual} (previsto: {predicted})")

    results_text = "\n".join(result_lines)
    tags = _hashtags()

    # Sequência atual
    streak_text = ""
    if acertos == total and total > 1:
        streak_text = f"\n🎯 {total} acertos seguidos hoje!"
    elif erros == total and total > 1:
        streak_text = f"\nDia difícil — {total} erros. Voltamos amanhã."

    lines = [
        f"📊 Resumo do dia — {total} {'jogo' if total == 1 else 'jogos'}",
        "",
        f"{acc_emoji} {acertos} acertos · {erros} erros · {acuracia:.0f}% de acurácia",
        "",
        results_text,
    ]

    if streak_text:
        lines.append(streak_text)

    lines += ["", tags]

    result = "\n".join(lines)
    return result[:THREADS_LIMIT]


def format_split_opener(opener_data: dict) -> str:
    """
    Post de abertura de split — posta no primeiro dia de jogos.
    Apresenta os times e os favoritos do Oráculo.
    """
    league = opener_data.get("league_name", "?")
    serie = opener_data.get("serie_name", "?")
    teams = opener_data.get("teams", [])
    favorites = opener_data.get("favorites", [])
    tags = _hashtags()

    # Times abreviados
    teams_abbr = [_abbreviate(t) for t in teams]
    teams_line = ", ".join(teams_abbr)

    lines = [
        f"⚔️ {league} {serie} — começa hoje!",
        "",
        f"Times: {teams_line}",
        "",
    ]

    if favorites:
        lines.append("🔮 Favoritos do Oráculo:")
        for f in favorites[:3]:
            pos = f.get("position", "?")
            team = _abbreviate(f.get("team", "?"))
            reason = f.get("reason", "")
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "•")
            lines.append(f"{medal} {team} — {reason}")
        lines.append("")

    lines += [
        "Que o split comece! 🎮",
        "",
        tags,
    ]

    result = "\n".join(lines)
    return result[:TWITTER_LIMIT]


def format_weekly_ranking(ranking_data: dict) -> str:
    """
    Post de ranking semanal — top 5 times em melhor forma.
    """
    ranking = ranking_data.get("ranking", [])
    headline = ranking_data.get("headline", "Times em melhor forma esta semana")
    tags = _hashtags()

    medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4️⃣", 5: "5️⃣"}

    lines = [
        "📈 Ranking da Semana — Cenário BR",
        "",
        f"💬 {headline}",
        "",
    ]

    for r in ranking[:5]:
        pos = r.get("position", "?")
        team = _abbreviate(r.get("team", "?"))
        reason = r.get("reason", "")
        medal = medals.get(pos, "•")
        lines.append(f"{medal} {team} — {reason}")

    lines += ["", tags]

    result = "\n".join(lines)
    return result[:TWITTER_LIMIT]


def format_streak(streak: int, teams: list[str]) -> str:
    """
    Celebra sequência de acertos consecutivos (a partir de 5).
    """
    tags = _hashtags()

    # Emoji baseado no tamanho da streak
    if streak >= 10:
        emoji = "🔥🔥🔥"
        hype = "O Oráculo está IMPARÁVEL."
    elif streak >= 7:
        emoji = "🔥🔥"
        hype = "O Oráculo está em chamas."
    else:
        emoji = "🔥"
        hype = "O Oráculo está afiado."

    # Lista dos times acertados (últimos 5 no máximo)
    shown = [_abbreviate(t) for t in teams[:5]]
    teams_line = " ✅ · ".join(shown) + " ✅"
    if len(teams) > 5:
        teams_line += f" (+{len(teams)-5})"

    lines = [
        f"{emoji} {streak} acertos seguidos!",
        "",
        teams_line,
        "",
        hype + " Será que a sequência continua?",
        "",
        tags,
    ]

    result = "\n".join(lines)
    return result[:THREADS_LIMIT]