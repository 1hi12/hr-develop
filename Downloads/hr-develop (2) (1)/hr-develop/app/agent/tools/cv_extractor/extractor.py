"""
ORCHESTRATEUR PHASES 1 → 5
Point d'entrée : fichier → CVExtracted complet avec chunks et embeddings
"""

import asyncio
import logging
from app.agent.tools.cv_extractor.parser import parse_file
from app.agent.tools.cv_extractor.chunker import chunk_document, LoadedDocument
from app.agent.tools.cv_extractor.llm_extractor import extract_info_gemini
from app.agent.tools.cv_extractor.embedder import embed_texts
from app.schemas.cv import (
    CVExtracted, Skill, Experience, Education,
    SeniorityLevel, ExtractedSkills, Chunk, EmbeddedChunk,
)

logger = logging.getLogger(__name__)


async def extract_cv(file_bytes: bytes, filename: str) -> CVExtracted:
    """
    Pipeline d'extraction complet (Phases 1 → 5) :
      1. Parse fichier → texte brut
      2. 3 appels LLM parallèles (gemini) → infos + skills + séniorité
      3. Chunking du texte brut
      4. Embedding de chaque chunk

    Returns:
        CVExtracted : objet Pydantic complet
    """
    logger.info(f"[Extractor] Début extraction : {filename}")

    # ── Phase 1 + 2 : Parsing ──────────────────────────────
    raw_text = parse_file(file_bytes=file_bytes, filename=filename)

    # ── Phase 3 : Extraction LLM (3 appels parallèles) ─────
    general, skills_raw, seniority_raw = await extract_info_gemini(raw_text)

    # ── Phase 4 : Chunking ────────────────────────────────
    doc = LoadedDocument(filename=filename, raw_text=raw_text)
    chunks = chunk_document(doc)
    chunks_dicts = [
        {
            "chunk_id": c.chunk_id,
            "text": c.text,
            "section": c.section,
            "chunk_index": c.chunk_index,
            "source_filename": c.source_filename,
            "metadata": c.metadata,
        }
        for c in chunks
    ]

    # ── Phase 5 : Embedding des chunks ───────────────────
    embedded_dicts = await _embed_chunks(chunks_dicts)

    # ── Assemblage CVExtracted ────────────────────────────
    cv = _assemble(
        general=general,
        skills_raw=skills_raw,
        seniority_raw=seniority_raw,
        raw_text=raw_text,
        chunks=chunks,
        embedded_chunks=embedded_dicts,
    )

    logger.info(
        f"[Extractor] Extraction terminée : {filename} "
        f"| skills={len(cv.skills)} "
        f"| chunks={len(cv.chunks)} "
        f"| seniority={cv.seniority_level}"
    )
    return cv


async def _embed_chunks(chunks_dicts: list[dict]) -> list[dict]:
    """
    Embed chaque chunk avec ses métadonnées.
    Retourne une liste de dictionnaires avec les embeddings ajoutés.
    """
    texts = [c["text"] for c in chunks_dicts]
    embeddings = await embed_texts(texts)
    
    result = []
    for chunk, embedding in zip(chunks_dicts, embeddings):
        chunk["embedding"] = embedding
        result.append(chunk)
    return result


# ──────────────────────────────────────────────────────────
# Assemblage
# ──────────────────────────────────────────────────────────

def _assemble(
    general: dict,
    skills_raw: dict,
    seniority_raw: dict,
    raw_text: str,
    chunks: list,
    embedded_chunks: list[dict],
) -> CVExtracted:

    # Skills Pydantic
    skills = []
    for s in skills_raw.get("skills", []):
        try:
            skills.append(Skill(**s))
        except Exception:
            pass

    # Experiences
    experiences = []
    for exp in seniority_raw.get("experiences", []):
        try:
            experiences.append(Experience(**exp))
        except Exception:
            pass

    # Education
    education = []
    for edu in seniority_raw.get("education", []):
        try:
            education.append(Education(**edu))
        except Exception:
            pass

    # Séniorité
    try:
        seniority = SeniorityLevel(seniority_raw.get("seniority_level", "unknown"))
    except ValueError:
        seniority = SeniorityLevel.UNKNOWN

    # ExtractedSkills
    extracted_skills = ExtractedSkills(
        technical   = skills_raw.get("technical", []),
        frameworks  = skills_raw.get("frameworks", []),
        databases   = skills_raw.get("databases", []),
        devops      = skills_raw.get("devops", []),
        soft_skills = skills_raw.get("soft_skills", []),
        languages   = skills_raw.get("languages", []),
        all_skills  = skills_raw.get("all_skills", []),
    )

    # Chunks Pydantic - utiliser les dataclass directement
    cv_chunks = [Chunk(
        chunk_id=c.chunk_id,
        text=c.text,
        section=c.section,
        chunk_index=c.chunk_index,
        source_filename=c.source_filename,
    ) for c in chunks]

    # EmbeddedChunks Pydantic
    embedded_cv_chunks = [
        EmbeddedChunk(
            chunk_id=e["chunk_id"],
            text=e["text"],
            section=e["section"],
            chunk_index=e["chunk_index"],
            source_filename=e["source_filename"],
            embedding=e["embedding"],
            metadata=e.get("metadata", {}),
        )
        for e in embedded_chunks
    ]

    # Confidence score
    filled = sum([
        bool(general.get("full_name")),
        bool(general.get("email")),
        bool(extracted_skills.all_skills),
        bool(experiences),
    ])
    confidence = round(filled / 4.0, 2)

    return CVExtracted(
        full_name  = general.get("full_name"),
        email      = general.get("email"),
        phone      = general.get("phone"),
        location   = general.get("location"),
        linkedin   = general.get("linkedin"),
        github     = general.get("github"),
        summary    = general.get("summary"),
        languages  = general.get("languages", []),
        skills     = skills,
        experiences= experiences,
        education  = education,
        seniority_level         = seniority,
        total_years_experience  = seniority_raw.get("total_years_experience"),
        raw_text                = raw_text,
        chunks                  = cv_chunks,
        embedded_chunks         = embedded_cv_chunks,
        extracted_skills        = extracted_skills,
        extraction_confidence   = confidence,
    )


def _build_all_skills(skills_raw: dict) -> list[str]:
    return list(dict.fromkeys(
        skills_raw.get("technical", []) +
        skills_raw.get("frameworks", []) +
        skills_raw.get("databases", []) +
        skills_raw.get("devops", [])
    ))
