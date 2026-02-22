"""
LLM Client — Thin wrapper around the Groq Python SDK.
No LangChain, no abstractions — just pure API calls.

Supports multi-turn conversation via the messages[] array:
  system prompt → conversation history → current user message

Supports both batch and streaming modes.
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


def _build_messages(system_prompt, user_message, conversation_history=None):
    """Build the messages array for the API call."""
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    return messages


def generate(
    model: str,
    system_prompt: str,
    user_message: str,
    conversation_history: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> dict:
    """
    Call the Groq chat-completion API (non-streaming).

    Returns:
    {
        "answer": str,
        "input_tokens": int,
        "output_tokens": int,
    }
    """
    client = _get_client()
    messages = _build_messages(system_prompt, user_message, conversation_history)

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


def generate_stream(
    model: str,
    system_prompt: str,
    user_message: str,
    conversation_history: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
):
    """
    Stream tokens from the Groq chat-completion API.

    Yields dicts:
      {"type": "token", "content": "..."} — for each token
      {"type": "done", "input_tokens": int, "output_tokens": int} — final

    NOTE: Structured output parsing (evaluator, token counts) is impossible
    mid-stream because:
    1. The evaluator needs the full answer to compute grounding similarity
    2. Token usage is only available in the final stream chunk
    3. A complete JSON response can't be built until all tokens are collected
    """
    client = _get_client()
    messages = _build_messages(system_prompt, user_message, conversation_history)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        input_tokens = 0
        output_tokens = 0

        for chunk in stream:
            # Extract token content from the delta
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield {"type": "token", "content": delta.content}

            # Groq provides usage in the final chunk via x_groq
            if hasattr(chunk, 'x_groq') and chunk.x_groq and hasattr(chunk.x_groq, 'usage'):
                usage = chunk.x_groq.usage
                input_tokens = usage.prompt_tokens if usage else 0
                output_tokens = usage.completion_tokens if usage else 0

        yield {
            "type": "done",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    except Exception as e:
        logger.error("Groq streaming error: %s", e)
        yield {"type": "error", "content": str(e)}
