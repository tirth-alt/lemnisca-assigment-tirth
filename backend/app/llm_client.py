"""
LLM Client — Thin wrapper around the Groq Python SDK.
No LangChain, no abstractions — just pure API calls.

Supports multi-turn conversation via the messages[] array:
  system prompt → conversation history → current user message
"""

from groq import Groq
from app.config import GROQ_API_KEY
import logging

logger = logging.getLogger(__name__)

_client: Groq | None = None


def _get_client() -> Groq:
    """Lazy-initialise the Groq client."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def generate(
    model: str,
    system_prompt: str,
    user_message: str,
    conversation_history: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> dict:
    """
    Call the Groq chat-completion API with multi-turn support.

    Args:
        model: Model ID to use
        system_prompt: System prompt (includes RAG context)
        user_message: Current user question
        conversation_history: Previous turns as [{role, content}, ...]

    Returns:
    {
        "answer": str,
        "input_tokens": int,
        "output_tokens": int,
    }
    """
    client = _get_client()

    # Build messages array: system → history → current user message
    messages = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        usage = response.usage

        return {
            "answer": choice.message.content or "",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        }

    except Exception as e:
        logger.error("Groq API error: %s", e)
        raise
