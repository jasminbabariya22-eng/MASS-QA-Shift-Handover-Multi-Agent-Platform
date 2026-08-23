import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    # --- GEMINI EMBEDDINGS ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # --- VECTOR DB (QDRANT) ---
    QDRANT_URL = os.getenv("QDRANT_CLUSTER_ENDPOINT")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION = "enterprise_rag"

    # --- REASONING ENGINE (GROQ) ---
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = "llama-3.3-70b-versatile"
    GROQ_FALLBACK_API_KEY = os.getenv("GROQ_FALLBACK_API_KEY")

    # --- LLM GATEWAY (PORTKEY) ---
    PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
    GROQ_SLUG =  "rag"     # primary: @rag/llama-3.3-70b-versatile
    GROQ_SLUG_2 = "brag"  # fallback: @brag/llama-3.1-8b-instant

    
    # --- OBSERVABILITY ---
    LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "true")
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "rag_scale_test")
    LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    # --- MULTIMODAL INGESTION ---
    DOCUMENT_PARSER = os.getenv("DOCUMENT_PARSER", "docling")
    VISION_ENABLED = os.getenv("VISION_ENABLED", "true").lower() == "true"
    VISION_MODEL = os.getenv("VISION_MODEL", "gemini-3.6-flash")
    VISION_DEVICE = os.getenv("VISION_DEVICE", "auto")

    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "600"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))

    MULTIMODAL_QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "mass_qa_multimodal")

    ENABLE_TABLE_PROCESSING = os.getenv("ENABLE_TABLE_PROCESSING", "true").lower() == "true"
    ENABLE_IMAGE_PROCESSING = os.getenv("ENABLE_IMAGE_PROCESSING", "true").lower() == "true"
    ENABLE_CHART_PROCESSING = os.getenv("ENABLE_CHART_PROCESSING", "true").lower() == "true"
    ENABLE_DIAGRAM_PROCESSING = os.getenv("ENABLE_DIAGRAM_PROCESSING", "true").lower() == "true"

    ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "./data/artifacts")
    MANIFEST_DIR = os.getenv("MANIFEST_DIR", "./data/manifests")

    # --- HYBRID RETRIEVAL V2 ---
    HYBRID_DENSE_WEIGHT = float(os.getenv("HYBRID_DENSE_WEIGHT", "1.0"))
    HYBRID_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", "1.0"))
    HYBRID_RRF_K = int(os.getenv("HYBRID_RRF_K", "60"))
    RETRIEVAL_CANDIDATE_K = int(os.getenv("RETRIEVAL_CANDIDATE_K", "20"))
    BM25_INDEX_DIR = os.getenv("BM25_INDEX_DIR", "data/retrieval/bm25")

    # --- CACHING & REDIS (PHASE 3) ---
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))
    RETRIEVAL_CACHE_TTL_SECONDS = int(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "600"))
    EMBEDDING_CACHE_TTL_SECONDS = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", "3600"))

    # --- VERSIONING ---
    KNOWLEDGE_BASE_VERSION = os.getenv("KNOWLEDGE_BASE_VERSION", "v1")
    RETRIEVAL_VERSION = os.getenv("RETRIEVAL_VERSION", "v2")
    PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v2")

    # --- SECURITY & AUTHENTICATION (PHASE 3) ---
    AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
    JWT_SECRET = os.getenv("JWT_SECRET", "mass-qa-production-secret-key-2026")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))

    # --- POSTGRESQL DATABASE ---
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "Mass")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "Alethe@123")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:Alethe%40123@localhost:5433/Mass")

    # --- CONNECTION POOLING ---
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "30.0"))
    DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # --- STEP 9: API MESH / GATEWAY & TIMEOUTS ---
    API_REQUEST_TIMEOUT_SECONDS = float(os.getenv("API_REQUEST_TIMEOUT_SECONDS", "30.0"))
    AGENT_EXECUTION_TIMEOUT_SECONDS = float(os.getenv("AGENT_EXECUTION_TIMEOUT_SECONDS", "25.0"))
    STREAMING_TIMEOUT_SECONDS = float(os.getenv("STREAMING_TIMEOUT_SECONDS", "60.0"))
    CACHE_TIMEOUT_SECONDS = float(os.getenv("CACHE_TIMEOUT_SECONDS", "0.5"))

    # --- RATE LIMITING ---
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "120"))
    RATE_LIMIT_STREAM_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_STREAM_REQUESTS_PER_MINUTE", "60"))
    RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE", "30"))

    # --- SECURITY HEADERS & PAYLOAD LIMITS ---
    ENABLE_SECURITY_HEADERS = os.getenv("ENABLE_SECURITY_HEADERS", "true").lower() == "true"
    MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576")) # 1 MB
    CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")



# Apply LangChain environment variables for automatic tracing
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGSMITH_TRACING", "true")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "rag_scale_test")
os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

settings = Settings()


