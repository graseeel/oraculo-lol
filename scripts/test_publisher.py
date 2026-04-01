"""
Script de teste de posting — roda uma vez e verifica X e Threads.
Uso: python -m scripts.test_publisher
"""
from __future__ import annotations

import json

from oraculo_lol.oraculo.prediction import Prediction, TeamPrediction
from oraculo_lol.publisher.formatter import format_for_threads, format_for_twitter
from oraculo_lol.publisher.threads import post_thread_safe
from oraculo_lol.publisher.twitter import post_tweet_safe
from oraculo_lol.runtime import init_runtime


def main() -> int:
    init_runtime()

    # Previsão fake para teste
    prediction = Prediction(
        pandascore_match_id=0,
        llm_model="gpt-4o",
        predicted_winner="LOUD",
        confidence="alta",
        teams=[
            TeamPrediction(name="LOUD", win_probability=0.75),
            TeamPrediction(name="paiN Gaming", win_probability=0.25),
        ],
        reasoning=(
            "LOUD tá dominando o split! 75% de win rate recente, "
            "Bull e Envy jogando no limite máximo. "
            "paiN vai precisar de um miracle run pra segurar essa pressão. "
            "É missão quase impossível hoje! 🔥"
        ),
        raw_response="",
        parse_error=False,
    )

    twitter_text = format_for_twitter(prediction)
    threads_text = format_for_threads(prediction)

    print("=" * 60)
    print(f"TWITTER ({len(twitter_text)} chars):")
    print(twitter_text)
    print("=" * 60)
    print(f"THREADS ({len(threads_text)} chars):")
    print(threads_text)
    print("=" * 60)

    tw_ok = post_tweet_safe(twitter_text)
    th_ok = post_thread_safe(threads_text)

    result = {
        "twitter": "✓ postado" if tw_ok else "✗ falhou",
        "threads": "✓ postado" if th_ok else "✗ falhou",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (tw_ok and th_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())