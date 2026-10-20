"""
PHASE 1 — Chargement du document
PHASE 2 — Extraction du texte brut (Raw Text)
Supporte : PDF, DOCX, Images (OCR), TXT
"""

import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {
    "pdf": "pdf",
    "docx": "docx",
    "doc": "docx",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "webp": "image",
    "tiff": "image",
    "txt": "text",
}


def parse_file(file_bytes: bytes, filename: str) -> str:
    """
    Phase 1 + 2 combinées :
    Charge le fichier et retourne le texte brut extrait.

    Args:
        file_bytes : contenu binaire du fichier
        filename   : nom du fichier (pour détecter le type)

    Returns:
        raw_text : texte brut nettoyé
    """
    suffix = Path(filename).suffix.lower().lstrip(".")
    file_type = ALLOWED_TYPES.get(suffix)

    if not file_type:
        raise ValueError(f"Format non supporté : .{suffix}. Acceptés : {list(ALLOWED_TYPES.keys())}")

    if len(file_bytes) < 100:
        raise ValueError("Fichier vide ou corrompu")

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > 20:
        raise ValueError(f"Fichier trop volumineux : {size_mb:.1f} MB (max 20 MB)")

    logger.info(f"[Parser] Chargement : {filename} | type={file_type} | {size_mb:.2f} MB")

    extractors = {
        "pdf":   _extract_pdf,
        "docx":  _extract_docx,
        "image": _extract_image,
        "text":  _extract_plain_text,
    }

    raw_text = extractors[file_type](file_bytes)
    raw_text = _clean_text(raw_text)

    if len(raw_text.strip()) < 50:
        logger.warning(f"[Parser] Texte très court : {len(raw_text)} chars pour {filename}")

    logger.info(f"[Parser] Texte extrait : {len(raw_text)} caractères")
    return raw_text


# ──────────────────────────────────────────────────────────
# Extracteurs par type
# ──────────────────────────────────────────────────────────

def _extract_pdf(file_bytes: bytes) -> str:
    """
    PDF → texte.
    Tentative 1 : pdfplumber (meilleur pour les colonnes et tableaux)
    Tentative 2 : pymupdf   (meilleur pour les PDF complexes / scannés)
    """
    # Tentative pdfplumber
    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if text and text.strip():
                    pages_text.append(f"[Page {i + 1}]\n{text}")
        result = "\n\n".join(pages_text)
        if result.strip():
            logger.info(f"[Parser] pdfplumber OK — {len(result)} chars")
            return result
    except Exception as e:
        logger.warning(f"[Parser] pdfplumber échoué : {e}")

    # Fallback pymupdf
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_text = []
        for i, page in enumerate(doc):
            text = page.get_text("text")
            if text.strip():
                pages_text.append(f"[Page {i + 1}]\n{text}")
        result = "\n\n".join(pages_text)
        logger.info(f"[Parser] pymupdf OK — {len(result)} chars")
        return result
    except Exception as e:
        logger.error(f"[Parser] pymupdf échoué : {e}")
        raise RuntimeError(f"Impossible d'extraire le texte du PDF : {e}")


def _extract_docx(file_bytes: bytes) -> str:
    """DOCX → texte avec python-docx (paragraphes + tableaux)."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        parts = []

        # Paragraphes
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                parts.append(text)

        # Tableaux
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    parts.append(row_text)

        result = "\n".join(parts)
        logger.info(f"[Parser] DOCX OK — {len(result)} chars")
        return result
    except Exception as e:
        logger.error(f"[Parser] Erreur DOCX : {e}")
        raise RuntimeError(f"Impossible d'extraire le texte DOCX : {e}")


def _extract_image(file_bytes: bytes) -> str:
    """Image → texte via OCR pytesseract avec prétraitement."""
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageEnhance

        image = Image.open(io.BytesIO(file_bytes))
        image = image.convert("L")                      # Niveaux de gris
        image = image.filter(ImageFilter.SHARPEN)       # Netteté
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)                   # Contraste

        text = pytesseract.image_to_string(
            image,
            lang="fra+eng",
            config="--psm 6 --oem 3",
        )
        logger.info(f"[Parser] OCR OK — {len(text)} chars")
        return text
    except Exception as e:
        logger.error(f"[Parser] Erreur OCR : {e}")
        raise RuntimeError(f"Impossible d'extraire le texte de l'image : {e}")


def _extract_plain_text(file_bytes: bytes) -> str:
    """Fichier texte brut avec détection d'encodage."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")


# ──────────────────────────────────────────────────────────
# Nettoyage
# ──────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Nettoie le texte extrait."""
    text = re.sub(r"[^\x20-\x7E\xA0-\xFF\n\t]", " ", text)
    text = text.replace("\t", " ")
    text = re.sub(r" {3,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
