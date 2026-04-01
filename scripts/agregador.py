from __future__ import annotations

import argparse
import json
import logging

from oraculo_lol.runtime import init_runtime
from oraculo_lol.agregador.build_context import build_match_context, save_context_json
from oraculo_lol.agregador.rosters import save_rosters_snapshot, sync_rosters_from_upcoming
from oraculo_lol.datasources.pandascore import (
    upcoming_br_lol_matches,
    search_lol_leagues,
    upcoming_lol_matches,
)
from oraculo_lol.datasources.riot import (
    account_by_riot_id,
    lol_platform_status,
    lol_summoner_by_name,
    lol_summoner_by_puuid,
    match_by_id,
    match_ids_by_puuid,
)

logger = logging.getLogger("scripts.agregador")


def main() -> int:
    init_runtime()
    parser = argparse.ArgumentParser(description="Agregador (MVP) - utilitários de dados")
    sub = parser.add_subparsers(dest="cmd", required=True)

    leagues = sub.add_parser("pandascore-leagues", help="Buscar ligas por nome (LoL)")
    leagues.add_argument("--q", required=True, help="Query do nome (ex: CBLOL)")

    upcoming = sub.add_parser("pandascore-upcoming", help="Listar partidas próximas (LoL)")
    upcoming.add_argument(
        "--league-id",
        action="append",
        type=int,
        dest="league_ids",
        help="Pode repetir. Ex: --league-id 123 --league-id 456",
    )
    upcoming.add_argument("--max-pages", type=int, default=2)

    upcoming_br = sub.add_parser("pandascore-upcoming-br", help="Listar próximas partidas (BR: CBLOL+Circuitão)")
    upcoming_br.add_argument("--max-pages", type=int, default=2)

    riot_status = sub.add_parser("riot-status", help="Status do servidor LoL (Riot)")
    riot_status.add_argument("--platform", default="br1", help="Ex: br1, na1, euw1")

    riot_summoner = sub.add_parser("riot-summoner", help="Buscar Summoner por nome (Riot)")
    riot_summoner.add_argument("--platform", default="br1", help="Ex: br1")
    riot_summoner.add_argument("--name", required=True, help="Nome do Summoner (pode ter espaços)")

    riot_account = sub.add_parser("riot-account", help="Buscar conta por Riot ID (gameName + tagLine)")
    riot_account.add_argument("--regional", default="americas", help="Ex: americas, europe, asia")
    riot_account.add_argument("--game-name", required=True, help="Antes do # (ex: fade)")
    riot_account.add_argument("--tag-line", required=True, help="Depois do # (ex: void)")

    riot_match_ids = sub.add_parser("riot-match-ids", help="Listar IDs de partidas por PUUID (match-v5)")
    riot_match_ids.add_argument("--regional", default="americas")
    riot_match_ids.add_argument("--puuid", required=True)
    riot_match_ids.add_argument("--start", type=int, default=0)
    riot_match_ids.add_argument("--count", type=int, default=10)

    riot_match = sub.add_parser("riot-match", help="Baixar detalhes de uma partida por matchId (match-v5)")
    riot_match.add_argument("--regional", default="americas")
    riot_match.add_argument("--match-id", required=True)

    sync_rosters = sub.add_parser(
        "sync-rosters",
        help="Baixar snapshot de rosters (descoberto via próximas partidas Pandascore)",
    )
    sync_rosters.add_argument("--max-pages", type=int, default=5)
    sync_rosters.add_argument(
        "--league-id",
        action="append",
        type=int,
        dest="league_ids",
        help="Opcional. Pode repetir. Default: CBLOL+Circuitão",
    )

    build_ctx = sub.add_parser("build-context", help="Gerar JSON de contexto a partir de um match Pandascore")
    build_ctx.add_argument("--match-id", type=int, required=True, help="ID do match na Pandascore")
    build_ctx.add_argument("--no-payloads", action="store_true", help="Não embutir payloads crus no JSON")

    args = parser.parse_args()

    if args.cmd == "pandascore-leagues":
        data = search_lol_leagues(name_query=args.q)
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "pandascore-upcoming":
        data = upcoming_lol_matches(league_ids=args.league_ids, max_pages=args.max_pages)
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "pandascore-upcoming-br":
        data = upcoming_br_lol_matches(max_pages=args.max_pages)
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "riot-status":
        data = lol_platform_status(platform=args.platform)
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "riot-summoner":
        data = lol_summoner_by_name(summoner_name=args.name, platform=args.platform)
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "riot-account":
        data = account_by_riot_id(game_name=args.game_name, tag_line=args.tag_line, regional=args.regional)
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "riot-match-ids":
        data = match_ids_by_puuid(
            puuid=args.puuid,
            regional=args.regional,
            start=args.start,
            count=args.count,
        )
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "riot-match":
        data = match_by_id(match_id=args.match_id, regional=args.regional)
        print(json.dumps(data, ensure_ascii=False))
        return 0

    if args.cmd == "sync-rosters":
        snapshot = sync_rosters_from_upcoming(league_ids=args.league_ids, max_pages=args.max_pages)
        path = save_rosters_snapshot(snapshot)
        print(json.dumps({"saved_to": str(path), "teams": len(snapshot.teams)}, ensure_ascii=False))
        return 0

    if args.cmd == "build-context":
        ctx = build_match_context(pandascore_match_id=args.match_id, include_payloads=not args.no_payloads)
        path = save_context_json(ctx)
        print(json.dumps({"saved_to": str(path)}, ensure_ascii=False))
        return 0

    raise RuntimeError("cmd inválido")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

