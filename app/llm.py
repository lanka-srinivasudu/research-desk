"""OpenRouter LLM client with retry/backoff for rate limits."""

import os
import time
from typing import Optional

import httpx


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
MAX_RETRIES = 5
BASE_BACKOFF = 2.0


class LLMClient:
    """Client for calling OpenRouter API with retry logic."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = OPENROUTER_BASE_URL,
        model: str = DEFAULT_MODEL,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")
        self.base_url = base_url
        self.model = model
        self._client = httpx.Client(timeout=60.0)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://research-desk.local",
            "X-Title": "Research Desk",
        }

    def chat(self, messages: list[dict], temperature: float = 0.3) -> str:
        """
        Send a chat completion request with retry on 429/402.
        Returns the assistant's message content.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        for attempt in range(MAX_RETRIES):
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]

            if response.status_code in (429, 402):
                # Rate limited or insufficient credits - back off and retry
                wait_time = BASE_BACKOFF * (2**attempt)
                time.sleep(wait_time)
                continue

            # Other errors - raise immediately
            response.raise_for_status()

        # All retries exhausted
        raise RuntimeError(f"LLM request failed after {MAX_RETRIES} retries (rate limited)")

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_client() -> LLMClient:
    """Factory function to create an LLMClient."""
    return LLMClient()