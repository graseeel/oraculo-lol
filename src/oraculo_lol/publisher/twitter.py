from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.publisher.twitter")

TWEET_URL = "https://api.twitter.com/2/tweets"


class TwitterError(RuntimeError):
    pass


def _percent_encode(value: str) -> str:
    return quote(str(value), safe="")


def _build_oauth_header(
    *,
    method: str,
    url: str,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
) -> str:
    """
    Gera o header Authorization OAuth 1.0a para a X API v2.
    Implementação manual — sem dependência de libs externas.
    """
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }

    # Signature base string
    param_string = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted(oauth_params.items())
    )
    base_string = "&".join([
        method.upper(),
        _percent_encode(url),
        _percent_encode(param_string),
    ])

    # Signing key
    signing_key = f"{_percent_encode(api_secret)}&{_percent_encode(access_token_secret)}"

    # HMAC-SHA1
    signature = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    import base64
    oauth_params["oauth_signature"] = base64.b64encode(signature).decode("utf-8")

    # Montar header
    header_parts = ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


@dataclass(frozen=True)
class TwitterClient:
    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str
    timeout_s: float = 15.0

    def post_tweet(self, text: str) -> str:
        """
        Posta um tweet e retorna o tweet_id.
        Fail-fast em erros permanentes (4xx). Não retenta para evitar duplicatas.
        """
        auth_header = _build_oauth_header(
            method="POST",
            url=TWEET_URL,
            api_key=self.api_key,
            api_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
        )

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(TWEET_URL, json={"text": text}, headers=headers)

            if resp.status_code == 429:
                raise TwitterError("X rate limit atingido (429) — não retentando para evitar ban")

            if resp.status_code >= 400:
                raise TwitterError(
                    f"X error status={resp.status_code} body={resp.text[:300]}"
                )

            data = resp.json()
            tweet_id = data.get("data", {}).get("id", "?")
            logger.info("tweet postado id=%s chars=%d", tweet_id, len(text))
            return tweet_id

        except TwitterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TwitterError(f"falha ao postar tweet: {exc!r}") from exc


def from_env() -> TwitterClient:
    s = load_settings()
    missing = [
        k for k, v in {
            "TWITTER_API_KEY": s.twitter_api_key,
            "TWITTER_API_SECRET": s.twitter_api_secret,
            "TWITTER_ACCESS_TOKEN": s.twitter_access_token,
            "TWITTER_ACCESS_TOKEN_SECRET": s.twitter_access_token_secret,
        }.items() if not v
    ]
    if missing:
        raise TwitterError(f"credenciais X não configuradas: {missing}")
    return TwitterClient(
        api_key=s.twitter_api_key,
        api_secret=s.twitter_api_secret,
        access_token=s.twitter_access_token,
        access_token_secret=s.twitter_access_token_secret,
    )


def post_tweet_safe(text: str) -> bool:
    """
    Wrapper fail-safe: posta e retorna True se OK, False se falhou.
    Nunca levanta exceção — ideal para uso no scheduler.
    """
    try:
        client = from_env()
        client.post_tweet(text)
        return True
    except TwitterError as exc:
        logger.warning("falha ao postar no X: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("erro inesperado ao postar no X: %r", exc)
        return False