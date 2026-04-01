from __future__ import annotations

from ..models.context import MatchContext

SYSTEM_PROMPT = """\
Você é um analista especializado em esports de League of Legends, \
com foco no cenário brasileiro (CBLOL e Circuitão).

Sua tarefa é analisar os dados de uma partida e gerar uma previsão fundamentada.

Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem texto fora do JSON.
O formato esperado é:

{
  "predicted_winner": "<nome exato do time favorito>",
  "confidence": "<alta|média|baixa>",
  "teams": [
    {"name": "<time A>", "win_probability": <0.0 a 1.0>},
    {"name": "<time B>", "win_probability": <0.0 a 1.0>}
  ],
  "reasoning": "<parágrafo único explicando o raciocínio>"
}

Regras:
- win_probability dos dois times deve somar 1.0
- Se não houver dados suficientes para uma previsão confiável, use confidence "baixa" e explique no reasoning
- Nunca invente estatísticas que não estão nos dados fornecidos
- Responda em português brasileiro
"""


def build_prompt(ctx: MatchContext) -> str:
    """
    Constrói a mensagem do usuário (user turn) a partir do MatchContext.
    O system prompt é fixo e retornado separadamente por `system_prompt()`.
    """
    lines: list[str] = []

    # --- Cabeçalho da partida ---
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

    # --- Times ---
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
                player_names = [p.name or str(p.id) for p in roster.players]
                lines.append(", ".join(player_names))
            else:
                lines.append("_(roster não disponível)_")
            lines.append("")

    # --- Stats (se existirem) ---
    if ctx.stats:
        lines.append("## Estatísticas Adicionais\n")
        for key, value in ctx.stats.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    # --- Instrução final ---
    lines.append("Com base nesses dados, gere a previsão no formato JSON especificado.")

    return "\n".join(lines)


def system_prompt() -> str:
    return SYSTEM_PROMPT