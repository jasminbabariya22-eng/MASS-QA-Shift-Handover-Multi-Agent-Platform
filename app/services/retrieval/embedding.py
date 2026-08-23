import time
import logfire
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.config import settings

BATCH_SIZE = 25
_VECTOR_DIM = 3072  # Guaranteed 3072-dim vector space for Qdrant collection

_active_model = None
_model_type: str | None = None  # "gemini" or "fallback"


# ── Model initialisation ───────────────────────────────────────────────────────

def _probe_gemini():
    """Try one embed call to verify Gemini is reachable. Returns model or None."""
    try:
        model = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-2-preview",
            google_api_key=settings.GEMINI_API_KEY,
        )
        model.embed_query("probe")
        logfire.info("Gemini embeddings ready (gemini-embedding-2-preview, 3072-dim).")
        return model
    except Exception as e:
        logfire.warning(f"Gemini probe failed: {e}. Will use sentence-transformers fallback with 3072-dim padding.")
        return None


def _load_fallback():
    from sentence_transformers import SentenceTransformer
    logfire.info("Loading sentence-transformers fallback (all-mpnet-base-v2, 768-dim -> 3072-dim padded).")
    return SentenceTransformer("all-mpnet-base-v2")


def _init():
    """Initialise embedding model once per process. Called lazily on first use."""
    global _active_model, _model_type
    if _active_model is not None:
        return

    gemini = _probe_gemini()
    if gemini:
        _active_model = gemini
        _model_type = "gemini"
    else:
        _active_model = _load_fallback()
        _model_type = "fallback"


def _pad_vector(vec: list[float], target_dim: int = _VECTOR_DIM) -> list[float]:
    """Pads a vector with zeros to reach target dimension for Qdrant collection compatibility."""
    if len(vec) >= target_dim:
        return vec[:target_dim]
    return vec + [0.0] * (target_dim - len(vec))


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_embedding_dim() -> int:
    """Return the vector dimension for the active model."""
    return _VECTOR_DIM


# ── Batch embedding with retry ─────────────────────────────────────────────────

def _embed_batch(batch: list[str]) -> list[list[float]]:
    global _active_model, _model_type
    if _model_type == "gemini":
        for attempt in range(3):
            try:
                vecs = _active_model.embed_documents(batch)
                return [_pad_vector(v) for v in vecs]
            except Exception as e:
                err = str(e).lower()
                is_quota = any(x in err for x in ("429", "resource_exhausted", "quota"))
                if is_quota:
                    logfire.warning(f"Gemini embedding quota exhausted: {e}. Switching to sentence-transformers fallback.")
                    _active_model = _load_fallback()
                    _model_type = "fallback"
                    raw_vecs = _active_model.encode(batch, show_progress_bar=False).tolist()
                    return [_pad_vector(v) for v in raw_vecs]
                else:
                    logfire.error(f"Gemini embedding failed: {e}")
                    raise
        logfire.warning("Switching to sentence-transformers fallback after retries.")
        _active_model = _load_fallback()
        _model_type = "fallback"
        raw_vecs = _active_model.encode(batch, show_progress_bar=False).tolist()
        return [_pad_vector(v) for v in raw_vecs]
    else:
        raw_vecs = _active_model.encode(batch, show_progress_bar=False).tolist()
        return [_pad_vector(v) for v in raw_vecs]


# ── Public API ─────────────────────────────────────────────────────────────────

def embed_query(query: str) -> list[float]:
    _init()
    if _model_type == "gemini":
        try:
            return _pad_vector(_active_model.embed_query(query))
        except Exception:
            pass
    return _pad_vector(_active_model.encode([query])[0].tolist())


def embed_texts(texts: list[str]) -> list[list[float]]:
    _init()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        with logfire.span("Embed batch", model=_model_type, start=i, size=len(batch)):
            all_embeddings.extend(_embed_batch(batch))
    return all_embeddings

