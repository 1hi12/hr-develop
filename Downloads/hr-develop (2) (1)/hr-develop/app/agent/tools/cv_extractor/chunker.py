import re
import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration du chunking
# ---------------------------------------------------------------------------

SEMANTIC_CHUNK_SIZE  = 450      # Augmenté pour donner plus de contexte au LLM
SIMILARITY_THRESHOLD = 0.78 # Un peu plus souple pour éviter de trop découpe
FALLBACK_CHUNK_SIZE  = 600
FALLBACK_CHUNK_OVERLAP = 100

SECTION_PATTERNS = [
    r"(?i)^(expériences?\s*(professionnelles?)?|professional\s*experience|work\s*experience)",
    r"(?i)^(formation|éducation|education|études|diplômes?|academic)",
    r"(?i)^(compétences?|skills?|technical\s*skills?|hard\s*skills?|soft\s*skills?)",
    r"(?i)^(langues?|languages?)",
    r"(?i)^(projets?|projects?|réalisations?)",
    r"(?i)^(certifications?|certificats?)",
    r"(?i)^(centres?\s*d.intérêts?|loisirs?|hobbies?|interests?)",
    r"(?i)^(résumé|profil|objectif|about\s*me|summary|profile)",
    r"(?i)^(contact|coordonnées|informations?\s*personnelles?)",
    r"(?i)^(publications?|références?|awards?|prix)",
]

@dataclass
class LoadedDocument:
    filename: str
    raw_text: str

@dataclass
class Chunk:
    chunk_id: str
    text: str
    section: str
    chunk_index: int
    char_start: int
    char_end: int
    source_filename: str
    metadata: dict = field(default_factory=dict)

# ---------------------------------------------------------------------------
# Embeddings - Réutilise le modèle de embedder.py pour éviter la duplication
# ---------------------------------------------------------------------------

def _get_embeddings(texts: list[str]) -> list[list[float]]:
    """Récupère les embeddings via le modèle partagé de embedder.py (proxy Orange)."""
    from app.agent.tools.cv_extractor.embedder import _get_model
    import asyncio

    model = _get_model()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(model.embed_texts(texts))
    finally:
        loop.close()

# ---------------------------------------------------------------------------
# Logique de Découpage
# ---------------------------------------------------------------------------

def chunk_document(doc: LoadedDocument) -> list[Chunk]:
    if not doc.raw_text:
        return []

    sections = _split_by_sections(doc.raw_text)
    chunks: list[Chunk] = []
    global_index = 0
    char_cursor = 0

    for section_name, section_text in sections:
        if not section_text.strip(): continue
        
        try:
            # Tentative sémantique
            sub_texts = _semantic_split(section_text)
        except Exception as exc:
            logger.warning(f"[Semantic] Fallback sur '{section_name}': {exc}")
            sub_texts = _split_by_size(section_text, FALLBACK_CHUNK_SIZE, FALLBACK_CHUNK_OVERLAP)

        for sub_text in sub_texts:
            stripped = sub_text.strip()
            if len(stripped) < 20: # Trop court pour être utile
                char_cursor += len(sub_text)
                continue

            chunks.append(Chunk(
                chunk_id=f"{doc.filename}_{global_index}",
                text=stripped,
                section=section_name,
                chunk_index=global_index,
                char_start=char_cursor,
                char_end=char_cursor + len(sub_text),
                source_filename=doc.filename
            ))
            global_index += 1
            char_cursor += len(sub_text)

    return chunks

def _semantic_split(text: str) -> list[str]:
    sentences = _split_into_sentences(text)
    if len(sentences) <= 1:
        return sentences

    embeddings = _get_embeddings(sentences)
    
    # Calcul des similarités cosinus
    chunks = []
    current_chunk_sentences = [sentences[0]]
    current_size = len(sentences[0])

    for i in range(len(embeddings) - 1):
        sim = _cosine_similarity(embeddings[i], embeddings[i+1])
        next_sent = sentences[i+1]
        
        # Break si trop différent OU si le chunk devient trop gros
        if sim < SIMILARITY_THRESHOLD or (current_size + len(next_sent)) > SEMANTIC_CHUNK_SIZE:
            chunks.append(" ".join(current_chunk_sentences))
            current_chunk_sentences = [next_sent]
            current_size = len(next_sent)
        else:
            current_chunk_sentences.append(next_sent)
            current_size += len(next_sent) + 1

    if current_chunk_sentences:
        chunks.append(" ".join(current_chunk_sentences))
    
    return chunks

def _cosine_similarity(v1, v2):
    dot = sum(a*b for a,b in zip(v1, v2))
    n1 = math.sqrt(sum(a*a for a in v1))
    n2 = math.sqrt(sum(b*b for b in v2))
    return dot / (n1 * n2) if n1 * n2 > 0 else 0

def _split_into_sentences(text: str) -> list[str]:
    # Découpage intelligent : points, retours à la ligne ou listes à puces
    pattern = r"(?<=[.!?])\s+|\n{1,}"
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if len(p.strip()) > 4]

def _split_by_sections(text: str) -> list[tuple[str, str]]:
    lines = text.split("\n")
    sections = []
    current_sec = "header"
    current_content = []

    for line in lines:
        clean = line.strip()
        is_title = False
        for pat in SECTION_PATTERNS:
            if re.match(pat, clean) and len(clean) < 50:
                if current_content:
                    sections.append((current_sec, "\n".join(current_content)))
                current_sec = re.sub(r"\W+", "_", clean.lower())
                current_content = []
                is_title = True
                break
        if not is_title:
            current_content.append(line)
            
    if current_content:
        sections.append((current_sec, "\n".join(current_content)))
    return sections

def _split_by_size(text: str, size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks
