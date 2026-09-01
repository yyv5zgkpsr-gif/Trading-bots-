"""Shared agent base class and optional LLM access.

Any agent that wants qualitative reasoning (news summarization, fundamental
narrative, bull/bear debate) can call ``self.ask_llm(...)``. If no
ANTHROPIC_API_KEY is configured (or the anthropic package isn't installed),
``ask_llm`` returns ``None`` and callers fall back to rule-based heuristics —
the whole pipeline works with or without an LLM configured.
"""

import os
from typing import Optional

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised only when dependency missing
    anthropic = None

DEFAULT_MODEL = "claude-3-5-sonnet-latest"


class LLMMixin:
    _client = None

    @classmethod
    def _get_client(cls):
        if anthropic is None:
            return None
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        if LLMMixin._client is None:
            LLMMixin._client = anthropic.Anthropic(api_key=api_key)
        return LLMMixin._client

    def ask_llm(self, system: str, user: str, max_tokens: int = 600) -> Optional[str]:
        client = self._get_client()
        if client is None:
            return None
        model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception:
            return None
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        return text or None


class Agent(LLMMixin):
    name = "agent"

    def run(self, *args, **kwargs):
        raise NotImplementedError
