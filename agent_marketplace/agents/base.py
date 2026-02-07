"""Base agent with shared LLM call logic via OpenAI SDK."""

from __future__ import annotations

from openai import OpenAI

from agent_marketplace.config import OPENAI_API_KEY, OPENAI_MODEL

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


class BaseAgent:
    """Shared agent logic — wraps a single OpenAI chat completion call."""

    def __init__(self, persona: str) -> None:
        self.persona = persona

    def think(self, prompt: str, max_tokens: int = 1024) -> str:
        client = _get_client()
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": self.persona},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
