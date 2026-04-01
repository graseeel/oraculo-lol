from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.publisher.threads")

THREADS_BASE = "https://graph.threads.net/v1.0"


class ThreadsError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThreadsClient:
    user_id: str
    access_token: str
    timeout_s: float = 15.0

    def _post(self, path: str, **kwargs) -> dict:  # type: ignore[type-arg]
        url = f"{THREADS_BASE}/{path}"
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, **kwargs)

            if resp.status_code == 429:
                raise ThreadsError("Threads rate limit atingido (429)")

            if resp.status_code >= 400:
                raise ThreadsError(
                    f"Threads error status={resp.status_code} body={resp.text[:300]}"
                )

            return resp.json()
        except ThreadsError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ThreadsError(f"falha na chamada Threads: {exc!r}") from exc

    def post_thread(self, text: str) -> str:
        """
        Publica um post no Threads em dois passos:
        1. Cria o container (mídia)
        2. Publica o container
        Retorna o thread_id publicado.
        """
        # Passo 1: criar container
        container_data = self._post(
            f"{self.user_id}/threads",
            params={
                "media_type": "TEXT",
                "text": text,
                "access_token": self.access_token,
            },
        )
        container_id = container_data.get("id")
        if not container_id:
            raise ThreadsError(f"container_id não retornado: {container_data}")

        # Passo 2: publicar
        publish_data = self._post(
            f"{self.user_id}/threads_publish",
            params={
                "creation_id": container_id,
                "access_token": self.access_token,
            },
        )
        thread_id = publish_data.get("id", "?")
        logger.info("thread postado id=%s chars=%d", thread_id, len(text))
        return str(thread_id)


def from_env() -> ThreadsClient:
    s = load_settings()
    if not s.threads_user_id:
        raise ThreadsError("THREADS_USER_ID não configurado")
    if not s.threads_access_token:
        raise ThreadsError("THREADS_ACCESS_TOKEN não configurado")
    return ThreadsClient(user_id=s.threads_user_id, access_token=s.threads_access_token)


def post_thread_safe(text: str) -> bool:
    """
    Wrapper fail-safe: posta e retorna True se OK, False se falhou.
    Nunca levanta exceção — ideal para uso no scheduler.
    """
    try:
        client = from_env()
        client.post_thread(text)
        return True
    except ThreadsError as exc:
        logger.warning("falha ao postar no Threads: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("erro inesperado ao postar no Threads: %r", exc)
        return False