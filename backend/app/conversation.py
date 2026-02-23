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
import json
from app.config import MAX_HISTORY_MESSAGES, CONVERSATIONS_PATH
import logging

logger = logging.getLogger(__name__)

# In-memory cache + persistent store
_conversations: dict[str, dict] = {}

MAX_HISTORY_TURNS = MAX_HISTORY_MESSAGES // 2


def _save_to_disk():
    """Save the current conversation state to disk."""
    try:
        CONVERSATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONVERSATIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(_conversations, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to save conversations: %s", e)


def _load_from_disk():
    """Load conversation state from disk on startup."""
    global _conversations
    if CONVERSATIONS_PATH.exists():
        try:
            with open(CONVERSATIONS_PATH, "r", encoding="utf-8") as f:
                _conversations = json.load(f)
            logger.info("Loaded %d conversations from disk", len(_conversations))
        except Exception as e:
            logger.error("Failed to load conversations: %s", e)
            _conversations = {}


# Load on module import
_load_from_disk()


def get_or_create_id(conversation_id: str | None, session_id: str | None = None) -> str:
    """Return the provided ID or generate a new one."""
    if conversation_id and conversation_id in _conversations:
        return conversation_id

    new_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    if new_id not in _conversations:
        _conversations[new_id] = {
            "title": "New conversation",
            "messages": [],
            "session_id": session_id,
        }
        _save_to_disk()
        logger.info("Created new conversation: %s (session: %s)", new_id, session_id)
    return new_id


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    sources: list | None = None,
    metadata: dict | None = None,
    session_id: str | None = None,
) -> None:
    """Append a message to the conversation history."""
    if conversation_id not in _conversations:
        _conversations[conversation_id] = {
            "title": "New conversation", 
            "messages": [],
            "session_id": session_id,
        }

    msg = {"role": role, "content": content}
    if sources is not None:
        msg["sources"] = sources
    if metadata is not None:
        msg["metadata"] = metadata

    conv = _conversations[conversation_id]
    conv["messages"].append(msg)
    
    # Ensure session_id is set if it was missing
    if session_id and not conv.get("session_id"):
        conv["session_id"] = session_id

    # Set title from first user message
    if role == "user" and conv["title"] == "New conversation":
        conv["title"] = content[:50] + ("…" if len(content) > 50 else "")

    # Trim to keep last N messages (preserve pairs)
    max_msgs = MAX_HISTORY_TURNS * 2
    if len(conv["messages"]) > max_msgs:
        conv["messages"] = conv["messages"][-max_msgs:]

    _save_to_disk()


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


def list_conversations(session_id: str | None = None) -> list[dict]:
    """Return all conversations, optionally filtered by session_id."""
    result = []
    for conv_id, conv in _conversations.items():
        # If session_id is provided, only show matches. 
        # If session_id is None, show all (backward compatibility/admin view)
        if session_id and conv.get("session_id") != session_id:
            continue
            
        if conv["messages"]:  # Only list non-empty conversations
            result.append({
                "id": conv_id,
                "title": conv["title"],
                "message_count": len(conv["messages"]),
            })
    return list(reversed(result))  # newest first


def clear_conversation(conversation_id: str) -> None:
    """Remove a conversation from memory and disk."""
    _conversations.pop(conversation_id, None)
    _save_to_disk()
