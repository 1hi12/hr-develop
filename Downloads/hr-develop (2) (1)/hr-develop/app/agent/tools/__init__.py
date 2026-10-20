# app/agent/tools/cv_extractor/__init__.py
# ✅ Imports relatifs — fonctionnent uniquement si les fichiers existent dans ce dossier

try:
    from .extractor import extract_cv
except ImportError:
    extract_cv = None

try:
    from .parser import parse_file
except ImportError:
    parse_file = None

try:
    from .llm_extractor import extract_skills_gemini, extract_info_gemini
except ImportError:
    extract_skills_gemini = None
    extract_info_gemini = None

try:
    from .chunker import chunk_text
except ImportError:
    chunk_text = None

try:
    from .embedder import embed_chunks, embed_single_query
except ImportError:
    embed_chunks = None
    embed_single_query = None

__all__ = [
    "extract_cv",
    "parse_file",
    "extract_skills_gemini",
    "extract_info_gemini",
    "chunk_text",
    "embed_chunks",
    "embed_single_query",
]
