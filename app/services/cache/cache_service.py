import hashlib
import json
import re
import time
from typing import Any, Optional, Dict
import logfire

from app.config import settings

try:
    import redis
    _REDIS_INSTALLED = True
except ImportError:
    _REDIS_INSTALLED = False


def normalize_query_text(query: str) -> str:
    """
    Standardize raw query string for robust cache key generation:
    - Lowercase
    - Strip leading/trailing whitespace
    - Normalize internal whitespace sequences
    - Strip trailing punctuation (?, !, .)
    """
    if not query:
        return ""
    q = query.lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[?!.,;:]+$", "", q).strip()
    return q


class InMemoryCache:
    """
    Thread-safe in-memory cache with TTL expiration.
    Used when Redis is unavailable or in development mode.
    """
    def __init__(self, max_items: int = 1000):
        self._store: Dict[str, tuple[Any, float]] = {}
        self._max_items = max_items

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        val, expiry = self._store[key]
        if time.time() > expiry:
            del self._store[key]
            return None
        return val

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        if len(self._store) >= self._max_items:
            # Purge expired or oldest items
            now = time.time()
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]
            if len(self._store) >= self._max_items:
                oldest = next(iter(self._store))
                del self._store[oldest]
        self._store[key] = (value, time.time() + ttl_seconds)

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def clear(self) -> None:
        self._store.clear()


class CacheService:
    """
    Enterprise Multi-Layer Caching Service for RAG pipelines.
    Supports Redis cluster/standalone with automatic in-memory fallback.
    """
    def __init__(self):
        self.enabled = settings.CACHE_ENABLED
        self._redis_client: Optional[Any] = None
        self._memory_cache = InMemoryCache()
        self._is_redis_connected = False

        if self.enabled and _REDIS_INSTALLED and settings.REDIS_URL:
            try:
                self._redis_client = redis.from_url(
                    settings.REDIS_URL,
                    socket_timeout=settings.CACHE_TIMEOUT_SECONDS,
                    socket_connect_timeout=0.3,
                    decode_responses=True
                )
                # Quick health ping
                self._redis_client.ping()
                self._is_redis_connected = True
                logfire.info(f"⚡ Redis Cache Connected ({settings.REDIS_URL})")
            except Exception as e:
                logfire.warning(f"⚠️ Redis unavailable ({e}) — operating in in-memory cache mode.")
                self._redis_client = None
                self._is_redis_connected = False


    @property
    def is_connected(self) -> bool:
        return self._is_redis_connected

    # --- Cache Key Generators ---

    @staticmethod
    def is_cacheable(query_type: Optional[str] = None, intent: Optional[str] = None, is_mutation: bool = False) -> bool:
        """
        Explicit caching policy enforcement:
        - Shift Handover state and mutations are STRICTLY NON-CACHEABLE.
        - Approvals, rejections, returns, LOTO acknowledgements, audits are NEVER cached.
        - Only read-only static technical QA queries are cacheable.
        """
        if is_mutation:
            return False
        
        non_cacheable_intents = ["shift", "shift_handover", "multi_agent", "high_risk", "safety_interlock"]
        if intent and any(n in str(intent).lower() for n in non_cacheable_intents):
            return False
            
        non_cacheable_query_types = [
            "get_handover", "list_handovers", "create_handover", "transition_success",
            "transition_failed", "multi_agent_composite", "safety_interlock",
            "shift_database", "concurrency_conflict"
        ]
        if query_type and any(n in str(query_type).lower() for n in non_cacheable_query_types):
            return False

        return True

    @staticmethod
    def make_response_key(query: str, session_scope: Optional[str] = None) -> str:
        """
        Layer A: Query -> Grounded Response Cache Key
        """
        norm_q = normalize_query_text(query)
        base = f"resp:{settings.KNOWLEDGE_BASE_VERSION}:{settings.PROMPT_VERSION}:{norm_q}"
        if session_scope:
            base += f":{session_scope}"
        key_hash = hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]
        return f"rag:response:{key_hash}"

    @staticmethod
    def make_retrieval_key(query: str, top_k: int = 5) -> str:
        """
        Layer B: Query -> Retrieval Candidates Pool Key
        """
        norm_q = normalize_query_text(query)
        base = f"ret:{settings.KNOWLEDGE_BASE_VERSION}:{settings.RETRIEVAL_VERSION}:{top_k}:{norm_q}"
        key_hash = hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]
        return f"rag:retrieval:{key_hash}"

    @staticmethod
    def make_embedding_key(text: str, model_name: str = "gemini-embedding-2-preview") -> str:
        """
        Layer C: Text -> Vector Embedding Key
        """
        norm_text = text.strip()
        base = f"emb:{model_name}:{norm_text}"
        key_hash = hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]
        return f"rag:embedding:{key_hash}"

    # --- Core Cache Operations ---

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None

        # 1. Try Redis
        if self._redis_client is not None and self._is_redis_connected:
            try:
                raw = self._redis_client.get(key)
                if raw is not None:
                    return json.loads(raw)
            except Exception as e:
                logfire.warning(f"Redis get failed ({e}) — trying memory cache.")

        # 2. Fallback to memory cache
        return self._memory_cache.get(key)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        if not self.enabled:
            return False

        ttl = ttl_seconds or settings.CACHE_TTL_SECONDS
        json_val = json.dumps(value)

        # 1. Store in memory cache
        self._memory_cache.set(key, value, ttl_seconds=ttl)

        # 2. Store in Redis
        if self._redis_client is not None and self._is_redis_connected:
            try:
                self._redis_client.setex(key, ttl, json_val)
                return True
            except Exception as e:
                logfire.warning(f"Redis set failed ({e}) — saved to in-memory store.")

        return True

    def delete(self, key: str) -> bool:
        if not self.enabled:
            return False
        mem_ok = self._memory_cache.delete(key)
        if self._redis_client is not None and self._is_redis_connected:
            try:
                self._redis_client.delete(key)
            except Exception:
                pass
        return mem_ok

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def flush_version(self, version: Optional[str] = None) -> None:
        """
        Invalidate cache when knowledge base version is bumped.
        """
        self._memory_cache.clear()
        if self._redis_client is not None and self._is_redis_connected:
            try:
                keys = self._redis_client.keys("rag:*")
                if keys:
                    self._redis_client.delete(*keys)
                logfire.info(f"🧹 Flushed RAG Redis cache ({len(keys)} keys).")
            except Exception as e:
                logfire.warning(f"Redis flush failed: {e}")


# Global Cache Singleton
cache_service = CacheService()
