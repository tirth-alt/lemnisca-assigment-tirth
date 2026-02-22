"""
Conversation Memory — In-memory multi-turn conversation store.
"""

import uuid
from app.config import MAX_HISTORY_MESSAGES
import logging

logger = logging.getLogger(__name__)

# In-memory store: conversation_id → list of { role, content }
_conversations: dict[str, list[dict]] = {}


def get_or_create_id(conversation_id: str | None) -> str:
    """Return the provided ID or generate a new one."""
    if conversation_id:
        return conversation_id
    new_id = f"conv_{uuid.uuid4().hex[:12]}"
    logger.info("Created new conversation: %s", new_id)
    return new_id


def add_message(conversation_id: str, role: str, content: str) -> None:
    """Append a message to the conversation history."""
    if conversation_id not in _conversations:
        _conversations[conversation_id] = []
    _conversations[conversation_id].append({"role": role, "content": content})
    # Trim to keep last N messages
    if len(_conversations[conversation_id]) > MAX_HISTORY_MESSAGES:
        _conversations[conversation_id] = _conversations[conversation_id][-MAX_HISTORY_MESSAGES:]


def get_history(conversation_id: str) -> str:
    """
    Return the conversation history formatted as a string for the LLM system prompt.
    """
    messages = _conversations.get(conversation_id, [])
    if not messages:
        return ""

    parts = []
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        parts.append(f"{role_label}: {msg['content']}")

    return "\n".join(parts)


def clear_conversation(conversation_id: str) -> None:
    """Remove a conversation from memory."""
    _conversations.pop(conversation_id, None)
