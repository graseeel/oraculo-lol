from __future__ import annotations

from ..models.context import LiquipediaEnrichment, MatchContext, RecentDraft, TeamHistory

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
- O número máximo de caracteres será informado na mensagem do usuário — respeite exatamente
- Se houver draft do jogo específico, priorize análise da draft sobre forma recente
- Se houver apenas histórico de picks, use para identificar padrões de composição
- Termos em inglês permitidos quando forem jargão consolidado: "stomp", "diff", "carry", "feed"
- Nunca use "miracle run", "missão impossível" ou expressões genéricas de hype
- Se a diferença for grande, pode dizer que será um stomp. Se equilibrado, diga que é difícil prever
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


def _fmt_draft_specific(enrichment: LiquipediaEnrichment) -> str | None:
    """Formata seção de picks/bans do jogo específico (status='ok')."""
    if enrichment.status != "ok" or not enrichment.teams:
        return None

    lines: list[str] = ["## Draft do Jogo (Picks e Bans)\n"]
    for team in enrichment.teams:
        lines.append(f"**{team.name}**")
        if team.bans:
            lines.append(f"Bans: {', '.join(team.bans)}")
        if team.players:
            for p in team.players:
                role = f" ({p.role})" if p.role else ""
                champion = f" → {p.champion}" if p.champion else ""
                lines.append(f"  {p.name}{role}{champion}")
        elif team.picks:
            lines.append(f"Picks: {', '.join(team.picks)}")
        lines.append("")

    return "\n".join(lines)


def _fmt_recent_draft(draft: RecentDraft, team_name: str) -> str:
    """Formata um draft recente de um time específico."""
    team_data = next(
        (t for t in draft.teams if t.name == team_name),
        draft.teams[0] if draft.teams else None,
    )
    if not team_data or not team_data.picks:
        return ""

    date_str = draft.date[:10] if draft.date else "?"
    opp = draft.opponent or "?"
    picks = ", ".join(team_data.picks)
    bans = ", ".join(team_data.bans[:3]) if team_data.bans else "—"
    return f"  vs {opp} ({date_str}): Picks: {picks} | Bans: {bans}"


def _fmt_draft_recent(enrichment: LiquipediaEnrichment, ctx: MatchContext) -> str | None:
    """Formata seção de histórico de picks por time (status='recent_only')."""
    if enrichment.status != "recent_only" or not enrichment.recent_drafts:
        return None

    lines: list[str] = ["## Picks Recentes (últimas partidas)\n"]

    team_names = [t.name or "" for t in ctx.teams]
    keys = ["team_a", "team_b"]

    for i, (key, team_name) in enumerate(zip(keys, team_names)):
        drafts = enrichment.recent_drafts.get(key, [])
        if not drafts:
            lines.append(f"**{team_name}**: sem dados de picks recentes\n")
            continue

        lines.append(f"**{team_name}**")
        for draft in drafts:
            line = _fmt_recent_draft(draft, team_name)
            if line:
                lines.append(line)
        lines.append("")

    return "\n".join(lines)


def build_prompt(ctx: MatchContext, max_reasoning_chars: int) -> str:
    lines: list[str] = []

    # --- Instrução de limite de reasoning ---
    if max_reasoning_chars > 0:
        lines.append(
            f"⚠️ LIMITE DO REASONING: exatamente até {max_reasoning_chars} caracteres. "
            "Não ultrapasse. Não precisa preencher tudo, mas use bem o espaço.\n"
        )
    else:
        lines.append(
            "⚠️ LIMITE DO REASONING: espaço insuficiente nesta postagem. "
            'Defina reasoning como "" (string vazia).\n'
        )

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

    # --- Draft do jogo específico (partida passada com picks) ---
    draft_section = _fmt_draft_specific(ctx.liquipedia_enrichment)
    if draft_section:
        lines.append(draft_section)

    # --- Histórico de picks (partida futura) ---
    recent_section = _fmt_draft_recent(ctx.liquipedia_enrichment, ctx)
    if recent_section:
        lines.append(recent_section)

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
        lines.append(
            f"## Confronto Direto (H2H)\n\n"
            f"{a} e {b} nunca se enfrentaram nos dados disponíveis.\n"
        )

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