from __future__ import annotations

import logging
import time

from oraculo_lol.runtime import init_runtime

logger = logging.getLogger("scripts.scheduler")


def main() -> int:
    init_runtime()
    logger.info("scheduler inicializado (placeholder).")
    logger.info("loop simples: checar a cada 3600s (por enquanto).")
    while True:
        logger.info("tick")
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())

