import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import logfire

from app.services.cache import cache_service


class ChatMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


class SessionState(BaseModel):
    session_id: str
    user_id: str = "anonymous"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    messages: List[ChatMessage] = Field(default_factory=list)


class ConversationManager:
    """
    Manages multi-turn chatbot conversations with bounded context windows.
    Provides session persistence with memory fallback.
    """
    def __init__(self, max_history_turns: int = 4):
        self.max_history_turns = max_history_turns
        self._in_memory_sessions: Dict[str, SessionState] = {}

    def get_or_create_session(self, session_id: Optional[str] = None, user_id: str = "anonymous") -> SessionState:
        """
        Retrieve existing session or instantiate a new one.
        """
        sid = session_id or str(uuid.uuid4())

        # 1. Check in-memory
        if sid in self._in_memory_sessions:
            return self._in_memory_sessions[sid]

        # 2. Check Cache / Redis
        cache_key = f"session:{sid}"
        cached = cache_service.get(cache_key)
        if cached:
            try:
                session = SessionState.model_validate(cached)
                self._in_memory_sessions[sid] = session
                return session
            except Exception as e:
                logfire.warning(f"Error parsing cached session ({e}).")

        # 3. Create new
        new_session = SessionState(session_id=sid, user_id=user_id)
        self._in_memory_sessions[sid] = new_session
        self._save_session(new_session)
        return new_session

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        user_id: str = "anonymous"
    ) -> ChatMessage:
        """
        Append user or assistant message to conversation history.
        """
        session = self.get_or_create_session(session_id, user_id=user_id)
        msg = ChatMessage(
            session_id=session.session_id,
            role=role,
            content=content,
            citations=citations or [],
            created_at=time.time()
        )
        session.messages.append(msg)
        session.updated_at = time.time()
        self._save_session(session)
        return msg

    def get_bounded_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        Extract bounded recent conversation turns for LLM context conditioning.
        Formats as [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}].
        """
        session = self.get_or_create_session(session_id)
        # Take the last N message turns
        recent_messages = session.messages[-(self.max_history_turns * 2):]
        return [{"role": m.role, "content": m.content} for m in recent_messages]

    def clear_session(self, session_id: str) -> bool:
        """
        Wipe a session's conversation history.
        """
        if session_id in self._in_memory_sessions:
            del self._in_memory_sessions[session_id]
        cache_key = f"session:{session_id}"
        cache_service.delete(cache_key)
        return True

    def _save_session(self, session: SessionState) -> None:
        """
        Persist session state to cache with 24-hour TTL.
        """
        cache_key = f"session:{session.session_id}"
        cache_service.set(cache_key, session.model_dump(), ttl_seconds=86400)


# Global Session Manager Singleton
conversation_manager = ConversationManager(max_history_turns=4)
