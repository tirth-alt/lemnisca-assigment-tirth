import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", BASE_DIR.parent))
DOCS_DIR = PROJECT_ROOT / "clearpath_docs"
INDEX_DIR = BASE_DIR / "data"
FAISS_INDEX_PATH = INDEX_DIR / "faiss_index.bin"
CHUNKS_PATH = INDEX_DIR / "chunks.json"
CONVERSATIONS_PATH = INDEX_DIR / "conversations.json"

# ── Groq ───────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SIMPLE_MODEL = "llama-3.1-8b-instant"
COMPLEX_MODEL = "llama-3.3-70b-versatile"

# ── Embedding ──────────────────────────────────────────────────────────
EMBEDDING_MODEL = "multi-qa-MiniLM-L6-cos-v1"
EMBEDDING_DIM = 384

# ── Chunking ──────────────────────────────────────────────────────────
MAX_CHUNK_SIZE = 512          # approx characters
OVERLAP_SENTENCES = 3         # boundary sentences carried to next chunk

# ── Retrieval ─────────────────────────────────────────────────────────
TOP_K = 5

# ── Router ────────────────────────────────────────────────────────────
COMPLEXITY_THRESHOLD = 3      # additive score >= this → complex
MULTI_DOC_THRESHOLD = 3       # distinct docs in retrieval → upgrade

# ── Evaluator ─────────────────────────────────────────────────────────
GROUNDING_THRESHOLD = 0.35    # cosine sim below this → low_grounding flag

# ── Conversation ──────────────────────────────────────────────────────
MAX_HISTORY_MESSAGES = 10
