"""
Conversation Memory — In-memory multi-turn conversation store.

Design: Sliding window of last MAX_HISTORY_TURNS turns (user+assistant pairs).
Each message stores role, content, and optionally sources/metadata for frontend replay.

Token cost tradeoff:
  - Without memory: ~1,500 input tokens/query
  - With 5-turn window: ~2,500–3,500 input tokens/query (+67–133%)
  - Bounded and predictable — no extra LLM calls like summarization would require
  - Fits within 8K context window of llama-3.1-8b-instant
"""

import uuid
from app.config import MAX_HISTORY_MESSAGES
import logging

logger = logging.getLogger(__name__)

# In-memory store: conversation_id → { title, messages[] }
_conversations: dict[str, dict] = {}

MAX_HISTORY_TURNS = MAX_HISTORY_MESSAGES // 2  # 5 turns = 10 messages


def get_or_create_id(conversation_id: str | None) -> str:
    """Return the provided ID or generate a new one."""
    if conversation_id and conversation_id in _conversations:
        return conversation_id
    new_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    if new_id not in _conversations:
        _conversations[new_id] = {"title": "New conversation", "messages": []}
        logger.info("Created new conversation: %s", new_id)
    return new_id


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    sources: list | None = None,
    metadata: dict | None = None,
) -> None:
    """Append a message to the conversation history."""
    if conversation_id not in _conversations:
        _conversations[conversation_id] = {"title": "New conversation", "messages": []}

    msg = {"role": role, "content": content}
    if sources is not None:
        msg["sources"] = sources
    if metadata is not None:
        msg["metadata"] = metadata

    conv = _conversations[conversation_id]
    conv["messages"].append(msg)

    # Set title from first user message
    if role == "user" and conv["title"] == "New conversation":
        conv["title"] = content[:50] + ("…" if len(content) > 50 else "")

    # Trim to keep last N messages (preserve pairs)
    max_msgs = MAX_HISTORY_TURNS * 2
    if len(conv["messages"]) > max_msgs:
        conv["messages"] = conv["messages"][-max_msgs:]


def get_messages_for_llm(conversation_id: str) -> list[dict]:
    """
    Return conversation history as a list of {role, content} dicts
    suitable for the LLM messages array. Only includes the last K turns.
    """
    conv = _conversations.get(conversation_id)
    if not conv or not conv["messages"]:
        return []

    # Return only role + content (strip sources/metadata)
    return [
        {"role": m["role"], "content": m["content"]}
        for m in conv["messages"]
    ]


def get_all_messages(conversation_id: str) -> list[dict]:
    """Return all messages for a conversation (includes sources/metadata for frontend)."""
    conv = _conversations.get(conversation_id)
    if not conv:
        return []
    return conv["messages"]


def list_conversations() -> list[dict]:
    """Return all conversations with IDs and titles, newest first."""
    result = []
    for conv_id, conv in _conversations.items():
        if conv["messages"]:  # Only list non-empty conversations
            result.append({
                "id": conv_id,
                "title": conv["title"],
                "message_count": len(conv["messages"]),
            })
    return list(reversed(result))  # newest first


def get_history(conversation_id: str) -> str:
    """Legacy: formatted string (kept for compatibility, no longer used in prompt)."""
    messages = get_messages_for_llm(conversation_id)
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
