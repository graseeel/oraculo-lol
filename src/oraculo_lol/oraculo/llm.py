from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from ..settings import load_settings

logger = logging.getLogger("oraculo_lol.oraculo.llm")

DEFAULT_MODEL = "gpt-4o"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAIClient:
    api_key: str
    model: str = DEFAULT_MODEL
    timeout_s: float = 60.0
    max_retries: int = 3
    temperature: float = 0.3

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        """
        Envia uma conversa (system + user) e retorna o texto da resposta.
        Aplica retry com backoff em erros transientes (429, 5xx).
        """
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s, headers=self._headers()) as client:
                    resp = client.post(OPENAI_CHAT_URL, json=payload)

                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "openai transient status=%s retry_in=%ss", resp.status_code, wait
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code >= 400:
                    raise LLMError(
                        f"openai error status={resp.status_code} body={resp.text[:500]}"
                    )

                data = resp.json()
                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    raise LLMError(f"openai retornou resposta sem 'choices': {data}")

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise LLMError("openai retornou 'content' vazio")

                logger.info(
                    "openai ok model=%s tokens_used=%s",
                    self.model,
                    data.get("usage", {}).get("total_tokens", "?"),
                )
                return content

            except LLMError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = min(2 ** attempt, 30)
                logger.warning("openai request failed retry_in=%ss err=%r", wait, exc)
                time.sleep(wait)

        raise LLMError(f"openai failed after retries err={last_exc!r}")


def from_env() -> OpenAIClient:
    s = load_settings()
    if not s.llm_api_key:
        raise LLMError("LLM_API_KEY não configurada")
    model = s.llm_model or DEFAULT_MODEL
    return OpenAIClient(api_key=s.llm_api_key, model=model)