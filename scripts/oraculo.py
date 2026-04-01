from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from oraculo_lol.oraculo.prediction import save_prediction_json
from oraculo_lol.oraculo.runner import run_prediction
from oraculo_lol.runtime import init_runtime

logger = logging.getLogger("scripts.oraculo")


def main() -> int:
    init_runtime()

    parser = argparse.ArgumentParser(description="Oráculo do LoL — gera previsão de partida via LLM")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--match-id",
        type=int,
        help="ID do match na Pandascore. Tenta carregar contexto em cache; gera se não existir.",
    )
    group.add_argument(
        "--context-file",
        type=Path,
        help="Path para um JSON de contexto já gerado pelo agregador.",
    )
    args = parser.parse_args()

    try:
        prediction = run_prediction(
            match_id=args.match_id,
            context_file=args.context_file,
        )
    except (ValueError, FileNotFoundError) as exc:
        logger.error("erro de entrada: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("falha ao gerar previsão: %r", exc)
        return 1

    # Salva em data/predictions/
    path = save_prediction_json(prediction)

    # Imprime no stdout
    print(json.dumps(prediction.model_dump(mode="json"), ensure_ascii=False, indent=2))

    logger.info("previsão salva em %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())