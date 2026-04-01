from __future__ import annotations

from ..models.context import MatchContext, TeamHistory

SYSTEM_PROMPT = """\
Você é o Oráculo do LoL — o maior hype man do cenário brasileiro de League of Legends.
Você conhece o CBLOL e o Circuitão de cor e fala com energia de quem está narrando ao vivo.

Sua missão é analisar os dados de uma partida e gerar uma previsão fundamentada.

Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem texto fora do JSON.
O formato esperado é:

{
  "predicted_winner": "<nome exato do time favorito>",
  "confidence": "<alta|média|baixa>",
  "teams": [
    {"name": "<time A>", "win_probability": <0.0 a 1.0>},
    {"name": "<time B>", "win_probability": <0.0 a 1.0>}
  ],
  "reasoning": "<análise curta e direta>"
}

Regras para o reasoning:
- Escreva em português brasileiro corrido, sem bullet points
- Máximo de 180 caracteres — seja direto e objetivo
- Use dados reais fornecidos para embasar a análise
- Termos em inglês permitidos apenas quando forem jargão consolidado do cenário: "stomp", "diff", "carry", "feed"
- Nunca use "miracle run", "missão impossível" ou expressões genéricas de hype
- Se a diferença for grande, pode dizer que será um stomp. Se for equilibrado, diga que é um jogo difícil de prever
- Se não houver dados suficientes, seja honesto e explique brevemente
- win_probability dos dois times deve somar 1.0
- Responda em português brasileiro
"""


def _fmt_winrate(history: TeamHistory) -> str:
    if history.total == 0:
        return "sem dados"
    wr = history.winrate
    pct = f"{wr * 100:.0f}%" if wr is not None else "?"
    return f"{history.wins}V {history.losses}D ({pct} de vitórias)"


def build_prompt(ctx: MatchContext) -> str:
    lines: list[str] = []

    # --- Cabeçalho ---
    lines.append("## Dados da Partida\n")
    if ctx.league:
        lines.append(f"Liga: {ctx.league.name or ctx.league.slug or ctx.league.id}")
    if ctx.serie:
        lines.append(f"Temporada: {ctx.serie.full_name or ctx.serie.season or ctx.serie.id}")
    if ctx.tournament:
        lines.append(f"Torneio: {ctx.tournament.name or ctx.tournament.id}")
    if ctx.begin_at:
        lines.append(f"Data/hora: {ctx.begin_at.strftime('%d/%m/%Y %H:%M UTC')}")
    if ctx.number_of_games:
        lines.append(f"Formato: MD{ctx.number_of_games}")
    lines.append("")

    team_names = [t.name or str(t.id) for t in ctx.teams]
    if team_names:
        lines.append(f"Times: {' vs '.join(team_names)}\n")

    # --- Rosters ---
    if ctx.official_rosters:
        lines.append("## Rosters Oficiais\n")
        for roster in ctx.official_rosters:
            team_label = roster.team.name or str(roster.team.id)
            lines.append(f"**{team_label}**")
            if roster.players:
                lines.append(", ".join(p.name or str(p.id) for p in roster.players))
            else:
                lines.append("_(roster não disponível)_")
            lines.append("")

    # --- Histórico individual ---
    if ctx.team_histories:
        lines.append("## Forma Recente (últimas partidas)\n")
        for history in ctx.team_histories:
            label = history.team_name or str(history.team_id)
            lines.append(f"**{label}**: {_fmt_winrate(history)}")
            for r in history.matches[:5]:
                date_str = r.date.strftime("%d/%m") if r.date else "?"
                result_str = "V" if r.won else ("D" if r.won is False else "?")
                opp = r.opponent_name or "?"
                score = ""
                if r.score_for is not None and r.score_against is not None:
                    score = f" ({r.score_for}-{r.score_against})"
                tournament = f" [{r.tournament_name}]" if r.tournament_name else ""
                lines.append(f"  {date_str} {result_str} vs {opp}{score}{tournament}")
            lines.append("")

    # --- Head-to-Head ---
    if ctx.head_to_head and ctx.head_to_head.total > 0:
        h2h = ctx.head_to_head
        a = h2h.team_a_name or str(h2h.team_a_id)
        b = h2h.team_b_name or str(h2h.team_b_id)
        lines.append("## Confronto Direto (H2H)\n")
        lines.append(f"{a}: {h2h.team_a_wins} vitórias")
        lines.append(f"{b}: {h2h.team_b_wins} vitórias")
        lines.append(f"Total de confrontos: {h2h.total}\n")
        lines.append("Últimos confrontos:")
        for r in h2h.matches[:5]:
            date_str = r.date.strftime("%d/%m/%Y") if r.date else "?"
            winner = a if r.won else (b if r.won is False else "?")
            score = ""
            if r.score_for is not None and r.score_against is not None:
                score = f" {r.score_for}-{r.score_against}"
            tournament = f" [{r.tournament_name}]" if r.tournament_name else ""
            lines.append(f"  {date_str} — Vencedor: {winner}{score}{tournament}")
        lines.append("")
    elif ctx.head_to_head and ctx.head_to_head.total == 0:
        a = ctx.head_to_head.team_a_name or str(ctx.head_to_head.team_a_id)
        b = ctx.head_to_head.team_b_name or str(ctx.head_to_head.team_b_id)
        lines.append(f"## Confronto Direto (H2H)\n\n{a} e {b} nunca se enfrentaram nos dados disponíveis.\n")

    # --- Stats extras ---
    if ctx.stats:
        lines.append("## Estatísticas Adicionais\n")
        for key, value in ctx.stats.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    lines.append("Com base nesses dados, gere a previsão no formato JSON especificado.")
    return "\n".join(lines)


def system_prompt() -> str:
    return SYSTEM_PROMPT