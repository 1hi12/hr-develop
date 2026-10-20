"""
job_matching.py
===============
Unified AI matching engine for CV ↔ Job posting scoring.

Components
----------
  MultiModelAIEngine    — LiteLLM Orange proxy only (openai/gpt-4o), no other provider
  EmbeddingService      — SHA-256 hash → in-memory LRU cache → Milvus check → generate
  AIScorer              — LLM-based scoring: domain detection + 4-dimension evaluation
  MatchingScore         — structured score (domain/skills/seniority/potential)
  CVJobMatcher          — orchestrates all of the above
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import ssl
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

warnings.filterwarnings("ignore")
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[attr-defined]

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Seniority ordering
# ─────────────────────────────────────────────────────────────────────────────

_SENIORITY_RANK: dict[str, int] = {
    "intern":    0,
    "junior":    1,
    "mid":       2,
    "senior":    3,
    "expert":    4,   # expert = lead level
    "lead":      4,
    "principal": 5,
    "executive": 5,
    "unknown":   2,  # treat unknown as mid
}

# Hard score cap per gap: skills cannot compensate for a large seniority gap
_GAP_SCORE_CAP: dict[int, float] = {
    -3: 45.0,   # intern vs senior: max 45/100
    -4: 25.0,   # intern vs expert/lead: max 25/100
    -5: 10.0,   # intern vs principal: max 10/100
}

# Hard score cap per skill coverage — only applies in formula fallback path.
# Primary scoring uses AIScorer (LLM) which handles semantics natively.
_COVERAGE_SCORE_CAP: list[tuple[float, float]] = [
    (0.00, 15.0),   # 0%   skills matched → max 15/100
    (0.10, 25.0),   # ≤10% skills matched → max 25/100
    (0.25, 40.0),   # ≤25% skills matched → max 40/100
    (0.40, 55.0),   # ≤40% skills matched → max 55/100
    (0.60, 72.0),   # ≤60% skills matched → max 72/100
    (0.80, 88.0),   # ≤80% skills matched → max 88/100
]

def _seniority_multiplier(gap: int) -> float:
    if gap >= 0:
        return 1.00
    if gap == -1:
        return 0.70   # 1 level below → noticeable penalty
    if gap == -2:
        return 0.40   # 2 levels below → strong penalty
    if gap == -3:
        return 0.10   # 3 levels below → very strong penalty
    return 0.00       # 4+ levels below → eliminated by seniority


# ─────────────────────────────────────────────────────────────────────────────
# MatchingScore dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MatchingScore:
    skill_score:          float   # cosine similarity × 100  (0-100)
    seniority_multiplier: float   # 0.00 – 1.00
    final_score:          float   # 0-100 composite
    seniority_gap:        int     # candidate_rank - job_rank
    skill_coverage:       float   # matched_skills / required_skills  (0-1)
    cross_encoder_score:  float   # -1 if not computed, else 0-1

    def to_dict(self) -> dict:
        return {
            "skill_score":          round(self.skill_score, 1),
            "seniority_multiplier": round(self.seniority_multiplier, 2),
            "final_score":          round(self.final_score, 1),
            "seniority_gap":        self.seniority_gap,
            "skill_coverage":       round(self.skill_coverage, 2),
            "cross_encoder_score":  round(self.cross_encoder_score, 3),
        }


_ScoreTuple = tuple  # (MatchingScore, justif, matched, missing, strengths, weaknesses, recommendation)


def _score_tuple_to_cache_dict(result: _ScoreTuple) -> dict:
    ms, justif, matched, missing, strengths, weaknesses, recommendation = result
    return {
        "score": ms.to_dict(),
        "justification": justif,
        "matched_skills": matched,
        "missing_skills": missing,
        "key_strengths": strengths,
        "key_weaknesses": weaknesses,
        "recommendation": recommendation,
    }


def _cache_dict_to_score_tuple(d: dict) -> _ScoreTuple:
    s = d["score"]
    ms = MatchingScore(
        skill_score          =s["skill_score"],
        seniority_multiplier =s["seniority_multiplier"],
        final_score          =s["final_score"],
        seniority_gap        =s["seniority_gap"],
        skill_coverage       =s["skill_coverage"],
        cross_encoder_score  =s["cross_encoder_score"],
    )
    return (
        ms, d["justification"], d["matched_skills"], d["missing_skills"],
        d["key_strengths"], d["key_weaknesses"], d["recommendation"],
    )


def compute_match_score(
    cosine_sim:           float,
    candidate_seniority:  str,
    job_seniority:        Optional[str],
    skill_coverage:       float = -1.0,  # -1.0 = no required_skills → skip coverage cap
    cross_encoder_score:  float = -1.0,  # -1 means not computed
) -> MatchingScore:
    """
    Composite score.

    skill_coverage meaning:
      -1.0  → job has no required_skills → coverage component skipped, no cap
       0.0  → required skills exist but candidate matches none → cap at 15
       0–1  → normal fractional coverage

    Formulas:
      Without cross-encoder, with coverage:    cosine×0.35 + coverage×0.45 + seniority×0.20
      Without cross-encoder, no required skills: cosine×0.70 + seniority×0.30
      With cross-encoder, with coverage:    cross×0.45 + cosine×0.25 + coverage×0.20 + seniority×0.10
      With cross-encoder, no required skills: cross×0.50 + cosine×0.30 + seniority×0.20

    Coverage caps and seniority gap caps only apply when required skills exist.
    """
    has_required = skill_coverage >= 0.0

    skill_score    = min(100.0, max(0.0, cosine_sim * 100))
    coverage_score = min(100.0, skill_coverage * 100) if has_required else 0.0

    c_rank = _SENIORITY_RANK.get((candidate_seniority or "unknown").lower(), 2)
    j_rank = _SENIORITY_RANK.get((job_seniority or "unknown").lower(), 2)
    gap    = c_rank - j_rank
    mult   = _seniority_multiplier(gap)

    if cross_encoder_score >= 0.0:
        if has_required:
            final = (
                cross_encoder_score * 100 * 0.45
                + skill_score            * 0.25
                + coverage_score         * 0.20
                + mult * 100             * 0.10
            )
        else:
            final = (
                cross_encoder_score * 100 * 0.50
                + skill_score            * 0.30
                + mult * 100             * 0.20
            )
    else:
        if has_required:
            final = (
                skill_score      * 0.35
                + coverage_score * 0.45
                + mult * 100     * 0.20
            )
        else:
            # No required skills: score purely on semantic similarity + seniority
            final = (
                skill_score  * 0.70
                + mult * 100 * 0.30
            )

    final = min(100.0, max(0.0, final))

    # Apply seniority gap hard cap
    cap = _GAP_SCORE_CAP.get(gap) or (_GAP_SCORE_CAP.get(-5) if gap <= -5 else None)
    if cap is not None:
        final = min(final, cap)

    # Apply skill coverage hard cap — only when required skills were specified
    if has_required:
        for threshold, coverage_cap in _COVERAGE_SCORE_CAP:
            if skill_coverage <= threshold:
                final = min(final, coverage_cap)
                break

    return MatchingScore(
        skill_score         =skill_score,
        seniority_multiplier=mult,
        final_score         =final,
        seniority_gap       =gap,
        skill_coverage      =skill_coverage,
        cross_encoder_score =cross_encoder_score,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AIScorer  — LLM-based scoring (domain detection + 4-dimension evaluation)
# ─────────────────────────────────────────────────────────────────────────────

import json, re, time as _time

# ── Batch scorer prompt (1 LLM call for all candidates) ──────────────────────
_BATCH_SCORER_PROMPT = """\
Tu es un expert RH. Évalue la correspondance entre ces {n} candidats et ce poste en UNE SEULE réponse.
{lang_instruction}

POSTE : {job_title} | Niveau : {job_seniority} | Domaine : {job_domain_hint}
Compétences requises : {required_skills}
Description : {job_description}

CANDIDATS :
{candidates_block}

RÈGLES (applique à chaque candidat) :
• DOMAINE (0-100) : même domaine → 85-100 | adjacent → 40-65 | différent → 0-25
• COMPÉTENCES (0-100) : % compétences requises matchées. Abréviations comprises :
  TS=TypeScript JS=JavaScript ML=Machine Learning TF=TensorFlow K8s=Kubernetes
  React.js=React Postgres=PostgreSQL NLP=NLP PY=Python DL=Deep Learning etc.
  Sois INCLUSIF : synonymes et variantes comptent.
• SÉNIORITÉ (0-100) : même/sur-qualifié → 90-100 | -1 niveau → 60-75 | -2 → 30-45 | -3+ → 0-20
• POTENTIEL (0-100) : capacité d'évolution rapide vers le poste
score_final = domaine×0.35 + compétences×0.35 + séniorité×0.20 + potentiel×0.10

Pour chaque candidat, fournis aussi :
• profile_summary : paragraphe analytique de 5 à 7 phrases décrivant le profil du candidat pour
  CE poste précis — expérience, séniorité, compétences clés, et une analyse de ses points forts
  ET de ses points faibles par rapport au poste. IMPORTANT : mets en **gras** (markdown **texte**)
  directement dans ce paragraphe le ou les points forts les plus déterminants et le ou les points
  faibles les plus déterminants, pour qu'ils ressortent visuellement à la lecture.
• key_strengths : liste de 2 à 3 points forts courts (quelques mots chacun).
• key_weaknesses : liste de 1 à 2 points faibles courts (quelques mots chacun).
• recommendation : 2 à 3 phrases de recommandation concrète pour le recruteur sur CE candidat
  pour CE poste précis (à considérer sérieusement / à former / peu adapté, etc., avec la raison).

Réponds UNIQUEMENT avec ce JSON array (un objet par candidat dans l'ordre, aucun texte autour) :
[{{"idx":0,"score_domaine":85,"score_competences":70,"score_seniorite":90,"score_potentiel":75,"score_final":80,"domaine_cv":"Frontend Dev","domaine_compatible":true,"competences_matchees":["React","TypeScript"],"competences_manquantes":["GraphQL"],"justification":"2 phrases: points forts et lacunes critiques.","profile_summary":"Jean est un développeur avec une **solide expertise en React et TypeScript**, directement applicable au poste. Son expérience de 4 ans couvre plusieurs projets frontend complexes. Toutefois, il **n'a aucune expérience avec GraphQL**, une technologie clé requise ici, ce qui représente un frein important. Sa capacité d'apprentissage rapide observée par le passé pourrait compenser ce manque avec un accompagnement adapté.","key_strengths":["strength1","strength2"],"key_weaknesses":["weakness1"],"recommendation":"2-3 phrases de recommandation..."}},...]

RAPPEL : dans profile_summary, encadre bien de ** ** (exactement comme dans l'exemple ci-dessus)
le(s) point(s) fort(s) et le(s) point(s) faible(s) les plus déterminants — ne l'oublie pas."""

_AI_SCORER_PROMPT = """\
Tu es un expert RH senior et spécialiste en IA. Évalue la correspondance entre ce candidat et ce poste.
{lang_instruction}

━━━━━━━━━━━━━━━━━━━━ POSTE ━━━━━━━━━━━━━━━━━━━━
Titre          : {job_title}
Domaine métier : {job_domain_hint}
Niveau requis  : {job_seniority}
Description    : {job_description}
Compétences requises : {required_skills}

━━━━━━━━━━━━━━━━━━━━ CANDIDAT ━━━━━━━━━━━━━━━━━
Nom            : {candidate_name}
Niveau actuel  : {candidate_seniority}
Années d'exp   : {years_exp}
Compétences    : {candidate_skills}
Résumé profil  : {cv_summary}

━━━━━━━━━━━━━━━━━━━━ INSTRUCTIONS ━━━━━━━━━━━━━
Évalue sur 4 dimensions INDÉPENDANTES (sois strict et réaliste) :

1. DOMAINE (0-100) : Le domaine métier du candidat correspond-il au poste ?
   - Même domaine exact           → 85-100
   - Domaine adjacent/transférable → 40-65
   - Domaine complètement différent → 0-25

2. COMPÉTENCES (0-100) : Combien de compétences requises le candidat possède-t-il ?
   - Base : (compétences_matchées / compétences_requises) × 100
   - Bonus si compétences similaires/équivalentes détectées
   - 0 compétence matchée → max 10

3. SÉNIORITÉ (0-100) : Le niveau d'expérience correspond-il ?
   - Même niveau ou sur-qualifié    → 90-100
   - 1 niveau en dessous            → 60-75
   - 2 niveaux en dessous           → 30-45
   - 3+ niveaux en dessous          → 0-20
   - Tient compte des années d'exp réelles

4. POTENTIEL (0-100) : Peut-il évoluer rapidement vers le poste ?
   - Compétences complémentaires, trajectoire cohérente → 60-90
   - Reconversion difficile, domaine éloigné           → 0-30

CALCUL FINAL :
score_final = domaine×0.35 + competences×0.35 + seniorite×0.20 + potentiel×0.10
(arrondi à l'entier)

COMPÉTENCES : identifie les matchs EXACTS, SÉMANTIQUES et par ABRÉVIATION. Exemples :
- "TS" = "TypeScript", "JS" = "JavaScript", "PY" = "Python"
- "ML" = "Machine Learning", "DL" = "Deep Learning", "NLP" = "Natural Language Processing"
- "TF" = "TensorFlow", "K8s" = "Kubernetes", "GCP" = "Google Cloud"
- "React.js" = "React", "Node.js" = "Node", "Vue.js" = "Vue"
- "CSS/SCSS" = "CSS" = "SCSS" = "Sass", "REST" = "REST API" = "RESTful"
- "Postgres" = "PostgreSQL", "Mongo" = "MongoDB", "Redis" = "Redis"
Sois INCLUSIF dans les matchs : une compétence similaire ou équivalente compte comme match.

Fournis aussi :
- profile_summary : paragraphe analytique de 5 à 7 phrases sur ce candidat pour CE poste
  (expérience, séniorité, compétences clés, points forts ET points faibles). Mets en **gras**
  (markdown **texte**) le ou les points forts et le ou les points faibles les plus déterminants,
  directement dans le paragraphe.
- key_strengths : 2 à 3 points forts courts.
- key_weaknesses : 1 à 2 points faibles courts.
- recommendation : 2 à 3 phrases de recommandation concrète pour le recruteur.

Réponds UNIQUEMENT avec ce JSON (aucun texte avant ou après) :
{{
  "score_domaine": <0-100>,
  "score_competences": <0-100>,
  "score_seniorite": <0-100>,
  "score_potentiel": <0-100>,
  "score_final": <0-100>,
  "domaine_cv": "<domaine détecté du CV en 3 mots max>",
  "domaine_poste": "<domaine détecté du poste en 3 mots max>",
  "domaine_compatible": <true|false>,
  "competences_matchees": ["skill1", "skill2"],
  "competences_manquantes": ["skill3", "skill4"],
  "verdict": "<recommandé|entretien_possible|à_former|refusé>",
  "justification": "<3 phrases: compétences présentes, lacunes critiques, recommandation finale>",
  "profile_summary": "<paragraphe de 5 à 7 phrases, avec le(s) point(s) fort(s) et faible(s) les plus déterminants encadrés de **ainsi** (ex: 'il maîtrise **Python** mais **manque d'expérience en tests**')>",
  "key_strengths": ["strength1", "strength2"],
  "key_weaknesses": ["weakness1"],
  "recommendation": "<2-3 phrases de recommandation>"
}}"""


def _lang_instruction(lang: str) -> str:
    if lang == "en":
        return "Answer ALL text fields (justification, profile_summary, key_strengths, key_weaknesses, recommendation) in English."
    return "Réponds à TOUS les champs texte (justification, profile_summary, key_strengths, key_weaknesses, recommendation) en français."


def _scaled_scoring_max_tokens(n: int) -> int:
    """
    Scale the output token budget with chunk size: each candidate needs a
    5-7 sentence profile_summary plus strengths/weaknesses/recommendation —
    far more text per item than CV extraction — so a flat 2000 was only
    ever enough for ~3-4 candidates before truncating mid-JSON.
    """
    return min(8192, n * 500 + 500)


async def _merge_async_iterables(iterables: list):
    """
    Fan-in: consume several async generators concurrently, yielding each
    item as soon as any of them produces one — instead of exhausting them
    one at a time. Used to stream results from parallel chunk-scoring calls
    in arrival order rather than chunk order.
    """
    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    async def _pump(gen):
        # A generator that raises must still signal completion — otherwise
        # `remaining` never reaches 0 and the merge hangs forever waiting for
        # a sentinel that will never arrive.
        try:
            async for item in gen:
                await queue.put(item)
        except Exception as exc:
            logger.warning("[Merge] Source generator failed: %s", exc)
        finally:
            await queue.put(SENTINEL)

    tasks = [asyncio.create_task(_pump(it)) for it in iterables]
    remaining = len(tasks)
    try:
        while remaining > 0:
            item = await queue.get()
            if item is SENTINEL:
                remaining -= 1
            else:
                yield item
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class AIScorer:
    """
    LLM-based CV ↔ Job scorer.
    Pipeline:
      1. Send structured prompt to LLM (LiteLLM Orange proxy only)
      2. Parse JSON response with 4-dimension scores
      3. Compute weighted final score
      4. Fallback to compute_match_score() if LLM fails
    """

    def __init__(self, ai_engine: "MultiModelAIEngine") -> None:
        self._engine = ai_engine

    async def score(
        self,
        job_title:            str,
        job_description:      str,
        required_skills:      list[str],
        job_seniority:        Optional[str],
        candidate_name:       str,
        candidate_skills:     list[str],
        candidate_seniority:  str,
        years_exp:            Optional[float],
        cv_summary:           str,
        # fallback values
        cosine_sim:           float = 0.0,
        skill_coverage:       float = 0.0,
        cross_encoder_score:  float = -1.0,
        lang:                 str = "fr",
    ) -> tuple[MatchingScore, str, list[str], list[str], list[str], list[str], str]:
        """
        Returns (MatchingScore, justification, matched_skills, missing_skills,
        key_strengths, key_weaknesses, recommendation).
        Falls back to compute_match_score() if LLM fails or returns invalid JSON.
        """
        prompt = _AI_SCORER_PROMPT.format(
            lang_instruction   = _lang_instruction(lang),
            job_title          = job_title,
            job_domain_hint    = self._infer_domain(job_title, required_skills),
            job_seniority      = job_seniority or "non spécifié",
            job_description    = (job_description or "")[:600],
            required_skills    = ", ".join(required_skills) if required_skills else "non spécifié",
            candidate_name     = candidate_name,
            candidate_seniority= candidate_seniority or "inconnu",
            years_exp          = f"{years_exp:.1f}" if years_exp else "0",
            candidate_skills   = ", ".join(candidate_skills[:20]) if candidate_skills else "non spécifié",
            cv_summary         = (cv_summary or "non disponible")[:400],
        )

        try:
            raw, model = await self._engine.generate(prompt)
            data = self._parse_json(raw)
            if data:
                logger.info(
                    "[AIScorer] %s scored via %s → final=%s domaine=%s/%s compat=%s",
                    candidate_name[:20], model,
                    data.get("score_final"),
                    data.get("domaine_cv"), data.get("domaine_poste"),
                    data.get("domaine_compatible"),
                )
                return self._build_score(data, candidate_seniority, job_seniority, skill_coverage)
        except Exception as exc:
            logger.warning("[AIScorer] LLM scoring failed for %s: %s — using fallback", candidate_name[:20], exc)

        # Fallback to formula-based score
        ms = compute_match_score(cosine_sim, candidate_seniority, job_seniority, skill_coverage, cross_encoder_score)
        matched = [s for s in required_skills if s.lower() in [x.lower() for x in candidate_skills]]
        missing = [s for s in required_skills if s.lower() not in [x.lower() for x in candidate_skills]]
        fallback_text = "Automated analysis (fallback)." if lang == "en" else "Analyse automatique (fallback)."
        return ms, fallback_text, matched, missing, [], [], ""

    def _infer_domain(self, job_title: str, skills: list[str]) -> str:
        """Quick heuristic domain hint for the prompt."""
        title_lower = job_title.lower()
        if any(k in title_lower for k in ["data", "scientist", "ml", "machine learning", "ia", "ai"]):
            return "Data Science / IA / Machine Learning"
        if any(k in title_lower for k in ["security", "sécurité", "cybersec", "pentest"]):
            return "Cybersécurité / Cloud Security"
        if any(k in title_lower for k in ["devops", "sre", "infrastructure", "cloud"]):
            return "DevOps / Infrastructure Cloud"
        if any(k in title_lower for k in ["frontend", "react", "vue", "angular", "ui"]):
            return "Développement Frontend"
        if any(k in title_lower for k in ["backend", "api", "python", "java", "node"]):
            return "Développement Backend"
        if any(k in title_lower for k in ["fullstack", "full stack", "full-stack"]):
            return "Développement Fullstack"
        return "Informatique / Technologie"

    def _parse_json(self, raw: str) -> Optional[dict]:
        """Extract and parse JSON from LLM response."""
        try:
            # Try direct parse first
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            pass
        # Extract JSON block from markdown or surrounding text
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("[AIScorer] Could not parse JSON from LLM response: %s", raw[:200])
        return None

    def _build_score(
        self,
        data:                 dict,
        candidate_seniority:  str,
        job_seniority:        Optional[str],
        skill_coverage_hint:  float,
    ) -> tuple[MatchingScore, str, list[str], list[str], list[str], list[str], str]:
        """Convert LLM JSON response to MatchingScore."""
        s_domain  = float(data.get("score_domaine",     0))
        s_skills  = float(data.get("score_competences", 0))
        s_seniority = float(data.get("score_seniorite", 0))
        s_potential = float(data.get("score_potentiel", 0))

        # Weighted final (matches prompt formula)
        final = (
            s_domain    * 0.35
            + s_skills  * 0.35
            + s_seniority * 0.20
            + s_potential * 0.10
        )
        # Trust LLM final if provided and reasonable, else use computed
        llm_final = float(data.get("score_final", -1))
        if 0 <= llm_final <= 100:
            # Average LLM final with computed to avoid hallucination drift
            final = (final + llm_final) / 2

        final = round(min(100.0, max(0.0, final)), 1)

        # Seniority gap for display
        c_rank = _SENIORITY_RANK.get((candidate_seniority or "unknown").lower(), 2)
        j_rank = _SENIORITY_RANK.get((job_seniority or "unknown").lower(), 2)
        gap    = c_rank - j_rank
        mult   = s_seniority / 100.0

        matched = data.get("competences_matchees", [])
        missing = data.get("competences_manquantes", [])
        # profile_summary is the new, longer analysis paragraph — falls back to the
        # older short "justification" field if the LLM omitted profile_summary.
        justif      = data.get("profile_summary") or data.get("justification", "")
        strengths   = data.get("key_strengths", []) or []
        weaknesses  = data.get("key_weaknesses", []) or []
        recommendation = data.get("recommendation", "") or ""

        # Use skill coverage from LLM-detected matches
        ai_coverage = len(matched) / max(len(matched) + len(missing), 1)

        ms = MatchingScore(
            skill_score          = s_skills,
            seniority_multiplier = mult,
            final_score          = final,
            seniority_gap        = gap,
            skill_coverage       = ai_coverage,
            cross_encoder_score  = -1.0,
        )
        return ms, justif, matched, missing, strengths, weaknesses, recommendation

    async def batch_score(
        self,
        job_title:       str,
        job_description: str,
        required_skills: list[str],
        job_seniority:   Optional[str],
        candidates:      list[dict],
        lang:            str = "fr",
    ) -> list[tuple[MatchingScore, str, list[str], list[str], list[str], list[str], str]]:
        """
        Score all candidates in ONE LLM call instead of N calls.
        candidates: list of dicts with keys:
          candidate_id, name, seniority, years_exp, skills, cv_summary,
          cosine_sim, skill_coverage, cross_encoder_score
        Returns list of (MatchingScore, justification, matched, missing,
        key_strengths, key_weaknesses, recommendation).
        Falls back to individual scoring per candidate if batch fails.
        """
        if not candidates:
            return []

        BATCH_SIZE = 15  # max candidates per LLM call to stay within context

        # Chunks are independent LLM calls — score them concurrently instead
        # of one after another (same fix as the individual-candidate fallback
        # above): for a large candidate pool this was N sequential calls
        # compounding their latency; llm_gate still bounds real concurrency
        # against the Orange proxy.
        chunks = [
            candidates[i: i + BATCH_SIZE]
            for i in range(0, len(candidates), BATCH_SIZE)
        ]
        chunk_results_list = await asyncio.gather(*(
            self._score_chunk(job_title, job_description, required_skills, job_seniority, chunk, lang)
            for chunk in chunks
        ))

        all_results: list[tuple[MatchingScore, str, list[str], list[str], list[str], list[str], str]] = []
        for chunk_results in chunk_results_list:
            all_results.extend(chunk_results)

        return all_results

    async def _score_chunk(
        self,
        job_title:       str,
        job_description: str,
        required_skills: list[str],
        job_seniority:   Optional[str],
        candidates:      list[dict],
        lang:            str = "fr",
    ) -> list[tuple[MatchingScore, str, list[str], list[str], list[str], list[str], str]]:
        """Score one chunk of candidates in a single LLM call."""
        lines = []
        for i, c in enumerate(candidates):
            skills_str = ", ".join((c.get("skills") or [])[:15]) or "non spécifié"
            summary = (c.get("cv_summary") or "").strip()[:200]
            titles = (c.get("experience_titles") or "").strip()
            lines.append(
                f"[{i}] {c.get('name','?')} | {c.get('seniority','?')} | "
                f"{c.get('years_exp') or 0:.0f}y exp | Skills: {skills_str}"
                + (f" | Postes: {titles}" if titles else "")
                + (f" | Résumé: {summary}" if summary else "")
            )
        candidates_block = "\n".join(lines)

        prompt = _BATCH_SCORER_PROMPT.format(
            n               = len(candidates),
            lang_instruction= _lang_instruction(lang),
            job_title       = job_title,
            job_seniority   = job_seniority or "non spécifié",
            job_domain_hint = self._infer_domain(job_title, required_skills),
            required_skills = ", ".join(required_skills) if required_skills else "non spécifié",
            job_description = (job_description or "")[:400],
            candidates_block= candidates_block,
        )

        fallback_partial = "Automated analysis (partial fallback)." if lang == "en" else "Analyse automatique (fallback partiel)."

        try:
            # generate() defaulted to max_tokens=2000 regardless of chunk size —
            # fine for a single candidate but a hard cap for up to 15 candidates
            # each needing a 5-7 sentence profile_summary + strengths/weaknesses/
            # recommendation. The response was silently truncated mid-JSON for
            # larger chunks, which _parse_batch_json then failed to parse —
            # the real cause of "Batch scoring failed" cascading into the much
            # slower individual-fallback path, not just proxy timeouts.
            raw, model = await self._engine.generate(prompt, max_tokens=_scaled_scoring_max_tokens(len(candidates)))
            items = self._parse_batch_json(raw, len(candidates))
            if items:
                results = []
                for i, c in enumerate(candidates):
                    data = items[i] if i < len(items) else {}
                    if data:
                        ms, justif, matched, missing, strengths, weaknesses, recommendation = self._build_score(
                            data, c.get("seniority","unknown"), job_seniority,
                            c.get("skill_coverage", -1.0)
                        )
                    else:
                        ms = compute_match_score(
                            c.get("cosine_sim", 0.0), c.get("seniority","unknown"),
                            job_seniority, c.get("skill_coverage", -1.0),
                            c.get("cross_encoder_score", -1.0)
                        )
                        matched = [s for s in required_skills if s.lower() in {x.lower() for x in (c.get("skills") or [])}]
                        missing = [s for s in required_skills if s.lower() not in {x.lower() for x in (c.get("skills") or [])}]
                        justif = fallback_partial
                        strengths, weaknesses, recommendation = [], [], ""
                    results.append((ms, justif, matched, missing, strengths, weaknesses, recommendation))
                logger.info("[AIScorer] Batch of %d scored via %s", len(candidates), model)
                return results
        except Exception as exc:
            logger.warning("[AIScorer] Batch scoring failed: %s — falling back to individual", exc)

        # Full fallback: score each candidate individually, in parallel — a
        # sequential loop here made one slow/timed-out candidate delay every
        # other candidate behind it; llm_gate still bounds real concurrency
        # against the Orange proxy, so this doesn't add extra quota risk.
        return await asyncio.gather(*(
            self.score(
                job_title=job_title, job_description=job_description,
                required_skills=required_skills, job_seniority=job_seniority,
                candidate_name=c.get("name","?"),
                candidate_skills=c.get("skills") or [],
                candidate_seniority=c.get("seniority","unknown"),
                years_exp=c.get("years_exp"), cv_summary=c.get("cv_summary",""),
                cosine_sim=c.get("cosine_sim",0.0),
                skill_coverage=c.get("skill_coverage",-1.0),
                cross_encoder_score=c.get("cross_encoder_score",-1.0),
                lang=lang,
            )
            for c in candidates
        ))

    async def _score_chunk_stream(
        self,
        job_title:       str,
        job_description: str,
        required_skills: list[str],
        job_seniority:   Optional[str],
        candidates:      list[dict],
        lang:            str = "fr",
    ):
        """
        Same one-LLM-call-per-chunk protocol as _score_chunk, but streams the
        completion and yields (candidate_id, MatchingScore, justif, matched,
        missing, strengths, weaknesses, recommendation) as soon as each
        candidate's JSON object completes in the response — instead of
        waiting for the whole chunk. Each object carries its own "idx" so
        results don't need to arrive in input order.

        Falls back to the ordinary (non-streamed) formula score for any
        candidate whose object fails to parse — never raises.
        """
        from app.infrastructure.llm.multi_worker_extractor import _StreamingArrayParser

        lines = []
        for i, c in enumerate(candidates):
            skills_str = ", ".join((c.get("skills") or [])[:15]) or "non spécifié"
            summary = (c.get("cv_summary") or "").strip()[:200]
            titles = (c.get("experience_titles") or "").strip()
            lines.append(
                f"[{i}] {c.get('name','?')} | {c.get('seniority','?')} | "
                f"{c.get('years_exp') or 0:.0f}y exp | Skills: {skills_str}"
                + (f" | Postes: {titles}" if titles else "")
                + (f" | Résumé: {summary}" if summary else "")
            )
        candidates_block = "\n".join(lines)

        prompt = _BATCH_SCORER_PROMPT.format(
            n               = len(candidates),
            lang_instruction= _lang_instruction(lang),
            job_title       = job_title,
            job_seniority   = job_seniority or "non spécifié",
            job_domain_hint = self._infer_domain(job_title, required_skills),
            required_skills = ", ".join(required_skills) if required_skills else "non spécifié",
            job_description = (job_description or "")[:400],
            candidates_block= candidates_block,
        )

        parser = _StreamingArrayParser()
        seen_idx: set[int] = set()

        try:
            async for delta in self._engine.generate_stream(
                prompt, max_tokens=_scaled_scoring_max_tokens(len(candidates))
            ):
                for data in parser.feed(delta):
                    idx = data.get("idx")
                    c = candidates[idx] if isinstance(idx, int) and 0 <= idx < len(candidates) else None
                    if c is None:
                        continue
                    seen_idx.add(idx)
                    ms, justif, matched, missing, strengths, weaknesses, recommendation = self._build_score(
                        data, c.get("seniority", "unknown"), job_seniority,
                        c.get("skill_coverage", -1.0),
                    )
                    yield (c["candidate_id"], ms, justif, matched, missing, strengths, weaknesses, recommendation)
        except Exception as exc:
            logger.warning("[AIScorer] Streamed chunk scoring failed: %s", exc)

        # Any candidate whose object never arrived (stream failed early, or
        # the model skipped/malformed one) gets the formula-based fallback.
        for i, c in enumerate(candidates):
            if i in seen_idx:
                continue
            ms = compute_match_score(
                c.get("cosine_sim", 0.0), c.get("seniority", "unknown"),
                job_seniority, c.get("skill_coverage", -1.0),
                c.get("cross_encoder_score", -1.0),
            )
            matched = [s for s in required_skills if s.lower() in {x.lower() for x in (c.get("skills") or [])}]
            missing = [s for s in required_skills if s.lower() not in {x.lower() for x in (c.get("skills") or [])}]
            fallback_text = "Automated analysis (fallback)." if lang == "en" else "Analyse automatique (fallback)."
            yield (c["candidate_id"], ms, fallback_text, matched, missing, [], [], "")

    async def batch_score_stream(
        self,
        job_title:       str,
        job_description: str,
        required_skills: list[str],
        job_seniority:   Optional[str],
        candidates:      list[dict],
        lang:            str = "fr",
    ):
        """
        Streamed counterpart to batch_score(): yields (candidate_id,
        MatchingScore, justif, matched, missing, strengths, weaknesses,
        recommendation) as each candidate is scored, across all chunks
        running concurrently — instead of returning the full list only once
        every chunk has finished.
        """
        if not candidates:
            return

        BATCH_SIZE = 15
        chunks = [
            candidates[i: i + BATCH_SIZE]
            for i in range(0, len(candidates), BATCH_SIZE)
        ]
        streams = [
            self._score_chunk_stream(job_title, job_description, required_skills, job_seniority, chunk, lang)
            for chunk in chunks
        ]
        async for item in _merge_async_iterables(streams):
            yield item

    def _parse_batch_json(self, raw: str, expected: int) -> list[dict]:
        """Parse JSON array from batch LLM response."""
        try:
            data = json.loads(raw.strip())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        match = re.search(r'\[[\s\S]*\]', raw)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        logger.warning("[AIScorer] Could not parse batch JSON — expected %d items", expected)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# CrossEncoderReranker  (disabled — Orange LiteLLM proxy only, see class docstring)
# ─────────────────────────────────────────────────────────────────────────────

class CrossEncoderReranker:
    """
    Disabled — no local Hugging Face model is loaded. Scoring uses only the
    Orange LiteLLM proxy + vector similarity (see MultiModelAIEngine/AIScorer).
    `ready` always False so every call site takes its existing cosine fallback.
    """

    def __init__(self) -> None:
        self._model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def score_pairs(self, job_text: str, cv_texts: list[str]) -> list[float]:
        """Score (job, cv) pairs. Returns sigmoid-normalized scores in [0,1]."""
        if not self._ready or self._model is None or not cv_texts:
            return [-1.0] * len(cv_texts)
        import numpy as np
        pairs = [(job_text[:512], cv[:512]) for cv in cv_texts]
        raw   = self._model.predict(pairs, show_progress_bar=False)
        return [float(1.0 / (1.0 + np.exp(-s))) for s in raw]


# ─────────────────────────────────────────────────────────────────────────────
# MultiModelAIEngine  (Orange LiteLLM proxy only)
# ─────────────────────────────────────────────────────────────────────────────

class MultiModelAIEngine:
    """
    Uses LiteLLM Orange Proxy ONLY for all LLM calls.
    Model: openai/gpt-4o via Orange management.llmproxy.ai.orange
    """

    TIMEOUT_LITELLM: float = 30.0

    def __init__(self) -> None:
        self._litellm_client: Any = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize LiteLLM Orange client (OpenAI-compatible)"""
        if settings.litellm_api_key and settings.litellm_base_url:
            try:
                import httpx
                from openai import AsyncOpenAI
                self._litellm_client = AsyncOpenAI(
                    api_key=settings.litellm_api_key,
                    base_url=settings.litellm_base_url,
                    # The SDK's own retry-on-429 (default max_retries=2) waits
                    # for the proxy's Retry-After (often 60s) — but our own
                    # asyncio.wait_for(TIMEOUT_LITELLM=30s) below always cuts
                    # that off first, so every 429 wasted ~30s for a retry we
                    # could never actually receive. max_retries=0 lets a 429
                    # fail immediately and go straight to fallback scoring.
                    max_retries=0,
                    http_client=httpx.AsyncClient(
                        verify=False,
                        timeout=httpx.Timeout(connect=10.0, read=self.TIMEOUT_LITELLM, write=10.0, pool=5.0),
                    ),
                )
                logger.info("[AIEngine] LiteLLM Orange client initialised (%s)", settings.litellm_model)
            except Exception as e:
                logger.error("[AIEngine] LiteLLM init failed: %s", e)
                raise

    async def _call_litellm(self, prompt: str, max_tokens: int = 2000) -> str:
        """Call LiteLLM Orange API with concurrency control and cost tracking."""
        from app.infrastructure.llm.cost_guard import cost_guard
        from app.infrastructure.llm.llm_gate import llm_gate
        # Shared with MultiWorkerExtractor's CV-upload calls: a matching request
        # running at the same time as a bulk upload must queue behind the same
        # gate instead of racing it for the same small Orange token quota.
        async with llm_gate:
            resp = await asyncio.wait_for(
                self._litellm_client.chat.completions.create(
                    model=settings.litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.15,  # lower = more reproducible scores for the same candidate/job
                    max_tokens=max_tokens,
                ),
                timeout=self.TIMEOUT_LITELLM,
            )
            usage = getattr(resp, "usage", None)
            if usage:
                await cost_guard.check_and_record(
                    prompt_tokens=getattr(usage, "prompt_tokens", 0),
                    completion_tokens=getattr(usage, "completion_tokens", 0),
                )
            return (resp.choices[0].message.content or "").strip()

    async def generate(self, prompt: str, max_tokens: int = 2000) -> tuple[str, str]:
        """
        Returns (generated_text, model_name_used).
        Uses ONLY LiteLLM Orange - no fallback.
        """
        if not self._litellm_client:
            raise RuntimeError("[AIEngine] LiteLLM client not initialized")

        try:
            text = await self._call_litellm(prompt, max_tokens=max_tokens)
            if text:
                logger.debug("[AIEngine] LiteLLM succeeded (%d chars)", len(text))
                return text, settings.litellm_model
            else:
                raise RuntimeError("[AIEngine] LiteLLM returned empty response")
        except asyncio.TimeoutError:
            logger.error("[AIEngine] LiteLLM timed out (%.0fs)", self.TIMEOUT_LITELLM)
            raise RuntimeError(f"[AIEngine] LiteLLM timeout after {self.TIMEOUT_LITELLM}s")
        except Exception as exc:
            logger.error("[AIEngine] LiteLLM failed: %s", exc)
            raise RuntimeError(f"[AIEngine] LiteLLM error: {exc}")

    async def generate_stream(self, prompt: str, max_tokens: int = 2000):
        """
        Same call as generate(), but streams the completion and yields raw
        text deltas as they arrive — for callers that want to parse partial
        output (e.g. a streaming JSON array) instead of waiting for the
        whole response.
        """
        from app.infrastructure.llm.cost_guard import cost_guard
        from app.infrastructure.llm.llm_gate import llm_gate

        if not self._litellm_client:
            raise RuntimeError("[AIEngine] LiteLLM client not initialized")

        async with llm_gate:
            stream = await self._litellm_client.chat.completions.create(
                model=settings.litellm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.15,  # lower = more reproducible scores for the same candidate/job
                max_tokens=max_tokens,
                stream=True,
            )
            async for event in stream:
                if event.choices:
                    delta = event.choices[0].delta.content
                    if delta:
                        yield delta
                usage = getattr(event, "usage", None)
                if usage:
                    await cost_guard.check_and_record(
                        prompt_tokens=getattr(usage, "prompt_tokens", 0),
                        completion_tokens=getattr(usage, "completion_tokens", 0),
                    )


# ─────────────────────────────────────────────────────────────────────────────
# EmbeddingService  (SHA-256 hash → LRU cache → generate)
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def _cached_embedding(text_hash: str) -> Optional[list]:
    """In-memory LRU cache keyed by SHA-256 hash truncated to 32 chars."""
    return None  # cache miss returns None; real values stored by wrapper


class EmbeddingService:
    """
    Never generate embeddings twice for the same text content.

    Strategy:
      1. Compute SHA-256 hash of text
      2. Check in-memory LRU cache (256 entries) → return if hit
      3. For CV embeddings: check if candidate_id exists in Milvus → return stored chunks
      4. Generate new embedding → store in memory cache → return
    """

    # Module-level dict backing the LRU (since lru_cache can't store mutable values)
    _store: dict[str, list[float]] = {}

    def __init__(self) -> None:
        from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
        self._embedder = OpenAIEmbedder()
        logger.info("[EmbeddingService] Initialised with OpenAIEmbedder (Orange LiteLLM proxy)")

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:32]

    async def embed_query(self, text: str) -> list[float]:
        """
        Embed a job description query.
        Uses 'query: ' prefix (multilingual-e5-base requirement for precision).
        In-memory LRU cache — same JD never re-embedded within process lifetime.
        """
        h = self._hash(text)
        if h in self._store:
            logger.debug("[EmbeddingService] Cache hit for query (hash=%s)", h[:8])
            return self._store[h]

        logger.debug("[EmbeddingService] Cache miss — generating embedding (hash=%s)", h[:8])
        embedding = await self._embedder.embed_single(text, is_query=True)
        self._store[h] = embedding
        return embedding

    async def embed_cv_chunks(
        self,
        candidate_id: str,
        cv_text: str,
        chunks: list,
    ) -> list:
        """
        Embed CV chunks with deduplication.
        If the candidate already exists in Milvus (checked via candidate_id), skip generation.
        Returns list of EmbeddedChunk objects.
        """
        from app.infrastructure.vector_store.milvus_store import MilvusVectorStore

        try:
            store = MilvusVectorStore()
            if await store.candidate_exists(candidate_id):
                logger.info(
                    "[EmbeddingService] candidate %s already in Milvus — skip embedding",
                    candidate_id[:8],
                )
                return []  # caller must not re-insert
        except Exception as exc:
            logger.warning("[EmbeddingService] Milvus existence check failed: %s", exc)

        # Generate embeddings for all chunks
        texts = [c.text for c in chunks]
        vectors = await self._embedder.embed_texts(texts)

        from app.core.entities.candidate import EmbeddedChunk
        return [
            EmbeddedChunk(
                chunk_id=c.chunk_id,
                text=c.text,
                section=c.section,
                chunk_index=c.chunk_index,
                source_filename=c.source_filename,
                embedding=vectors[i],
            )
            for i, c in enumerate(chunks)
        ]


# ─────────────────────────────────────────────────────────────────────────────
# DescriptionGenerator  — French AI analysis (3-4 sentences)
# ─────────────────────────────────────────────────────────────────────────────

_DESCRIPTION_PROMPT = """\
Tu es un expert RH. Génère une analyse concise en français (3 à 4 phrases) pour ce candidat.

Candidat :
- Compétences : {skills}
- Niveau de séniorité : {seniority}
- Score de correspondance : {final_score:.0f}/100
- Gap de séniorité : {seniority_gap} niveau(x) ({gap_label})

Poste requis :
- Compétences requises : {required_skills}
- Niveau requis : {job_seniority}

Compétences correspondantes : {matched_skills}
Compétences manquantes : {missing_skills}

Rédige 3 à 4 phrases en français couvrant :
1. Les compétences qui correspondent
2. Les compétences manquantes importantes
3. L'impact du niveau de séniorité
4. La recommandation (recruter, former, refuser, junior à former)

Réponds uniquement avec les phrases, sans titre ni liste."""


class DescriptionGenerator:
    """Generates a French AI analysis for each candidate match."""

    def __init__(self, ai_engine: MultiModelAIEngine) -> None:
        self._engine = ai_engine

    async def generate(
        self,
        candidate_skills:    list[str],
        candidate_seniority: str,
        job_required_skills: list[str],
        job_seniority:       Optional[str],
        score:               MatchingScore,
        matched_skills:      list[str],
        missing_skills:      list[str],
    ) -> str:
        gap = score.seniority_gap
        gap_label = (
            "sur-qualifié" if gap > 0
            else "niveau parfait" if gap == 0
            else f"sous-qualifié de {abs(gap)} niveau(x)"
        )

        prompt = _DESCRIPTION_PROMPT.format(
            skills=", ".join(candidate_skills[:15]) or "non spécifié",
            seniority=candidate_seniority or "inconnu",
            final_score=score.final_score,
            seniority_gap=gap,
            gap_label=gap_label,
            required_skills=", ".join(job_required_skills[:10]) or "non spécifié",
            job_seniority=job_seniority or "non spécifié",
            matched_skills=", ".join(matched_skills[:8]) or "aucune",
            missing_skills=", ".join(missing_skills[:8]) or "aucune",
        )

        try:
            text, model = await self._engine.generate(prompt)
            logger.info("[DescriptionGenerator] Generated via %s (%d chars)", model, len(text))
            return text.strip()
        except RuntimeError as exc:
            logger.error("[DescriptionGenerator] All models failed: %s", exc)
            return _fallback_description(score, matched_skills, missing_skills, gap_label)


def _fallback_description(
    score: MatchingScore,
    matched: list[str],
    missing: list[str],
    gap_label: str,
) -> str:
    matched_str = ", ".join(matched[:5]) if matched else "aucune compétence requise"
    missing_str = ", ".join(missing[:5]) if missing else "aucune"
    return (
        f"Le candidat présente un score de correspondance de {score.final_score:.0f}/100. "
        f"Compétences correspondantes : {matched_str}. "
        f"Compétences manquantes : {missing_str}. "
        f"Niveau : {gap_label}. "
        f"{'Profil recommandé pour un entretien.' if score.final_score >= 60 else 'Profil à réévaluer ou à former.'}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CVJobMatcher  — main orchestrator
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CandidateResult:
    candidate_id:          str
    full_name:             str
    seniority:             str
    years_experience:      Optional[float]
    candidate_skills:      list[str]
    matched_skills:        list[str]
    missing_skills:        list[str]
    score:                 MatchingScore
    raw_cosine:            float
    ai_description:        Optional[str] = None
    status:                str = "pending"
    scoring_time_s:        float = 0.0
    email:                 Optional[str] = None
    key_strengths:         list[str] = field(default_factory=list)
    key_weaknesses:        list[str] = field(default_factory=list)
    recommendation:        str = ""


class CVJobMatcher:
    """
    End-to-end CV ↔ Job matching:
      1. Embed job description (cached)
      2. Search Milvus (cosine ANN)
      3. Fetch candidate metadata from PostgreSQL
      4. Cross-encoder reranking (local, FR+EN, CPU)
      5. Formula score: cosine×0.35 + skill_coverage×0.45 + seniority×0.20
         (or with cross-encoder: cross×0.45 + cosine×0.25 + coverage×0.20 + seniority×0.10)
         with hard caps (_COVERAGE_SCORE_CAP, _GAP_SCORE_CAP)
      6. Generate description (DescriptionGenerator)
      7. Return ranked CandidateResult list
    """

    def __init__(self) -> None:
        self._embed_svc     = EmbeddingService()
        self._ai_engine     = MultiModelAIEngine()
        self._ai_scorer     = AIScorer(self._ai_engine)
        self._cross_encoder = CrossEncoderReranker()

    async def _prepare_candidates(
        self,
        job_title:        str,
        job_description:  str,
        required_skills:  list[str],
        top_k:            int,
        job_posting_id:   Optional[str] = None,
    ) -> tuple[list[dict], str]:
        """
        Steps 1-5 shared by match() and match_stream(): embed the job query,
        search Milvus, fetch+dedup PostgreSQL candidates, cross-encoder
        pre-filter, and build the candidates_data list ready for scoring.
        Returns (candidates_data, query_text).
        """
        # ── 1. Embed job query (cached) ──────────────────────────────────────
        query_text = f"{job_title}\n{job_description}"
        if required_skills:
            query_text += "\nRequired: " + ", ".join(required_skills)

        query_embedding = await self._embed_svc.embed_query(query_text)

        # ── 2. Milvus search (best-effort; we always include all PG candidates) ──
        from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
        from app.infrastructure.database.session import AsyncSessionLocal
        from app.infrastructure.database.models import CandidateModel
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.infrastructure.circuit_breaker import milvus_breaker, CircuitBreakerOpen

        store: Optional[MilvusVectorStore] = None
        cosine_by_id: dict[str, float] = {}
        try:
            store = MilvusVectorStore()
            async with milvus_breaker:
                milvus_results = await store.search(
                    query_embedding=query_embedding,
                    top_k=top_k * 5,
                    min_score=0.0,  # no cut-off — we rely on final formula score
                )
            for r in milvus_results:
                if r.candidate_id not in cosine_by_id or r.score > cosine_by_id[r.candidate_id]:
                    cosine_by_id[r.candidate_id] = r.score
            logger.info("[CVJobMatcher] Milvus returned %d unique candidate ids", len(cosine_by_id))
        except CircuitBreakerOpen as cb_err:
            logger.warning("[CVJobMatcher] Milvus circuit OPEN for '%s': %s", job_title, cb_err)
        except Exception as milvus_err:
            logger.warning(
                "[CVJobMatcher] Milvus unavailable for '%s': %s — scoring by keywords only",
                job_title, milvus_err,
            )

        # ── 3. Fetch candidates from PostgreSQL, excluding only those rejected
        #      for THIS job posting — a rejection on job A must not remove a
        #      candidate from the matching pool of job B ──────────────────────
        from app.infrastructure.database.models import CandidateJobApplicationModel

        query = (
            select(CandidateModel)
            .options(
                selectinload(CandidateModel.extracted_skills),
                selectinload(CandidateModel.skills),
                selectinload(CandidateModel.experiences),
            )
        )
        if job_posting_id:
            rejected_for_this_job = select(CandidateJobApplicationModel.candidate_id).where(
                CandidateJobApplicationModel.job_posting_id == job_posting_id,
                CandidateJobApplicationModel.status == "rejected",
            )
            query = query.where(~CandidateModel.candidate_id.in_(rejected_for_this_job))
        else:
            # No job context available — fall back to the old global exclusion.
            query = query.where(CandidateModel.status != "rejected")

        async with AsyncSessionLocal() as session:
            rows = await session.execute(query.limit(1000))
            all_candidates = list(rows.scalars())

            # Per-posting status for THIS job only — a candidate hired/rejected
            # on job A must still show as "pending" when matched against job B.
            status_by_id: dict[str, str] = {}
            if job_posting_id:
                app_rows = await session.execute(
                    select(
                        CandidateJobApplicationModel.candidate_id,
                        CandidateJobApplicationModel.status,
                    ).where(CandidateJobApplicationModel.job_posting_id == job_posting_id)
                )
                status_by_id = {cid: status for cid, status in app_rows}

        logger.info("[CVJobMatcher] Loaded %d candidates from PostgreSQL", len(all_candidates))

        # ── 3b. DEDUPLICATE by full_name across ALL PG candidates ───────────
        # For candidates with a Milvus score use it; others get keyword-based cosine.
        req_lower = {s.lower().strip() for s in required_skills}

        def _keyword_cosine(c: CandidateModel) -> float:
            """Estimate cosine similarity via skill-keyword overlap when no Milvus embedding."""
            skill_set: set[str] = set()
            if c.extracted_skills:
                for s in (c.extracted_skills.all_skills or []):
                    if s:
                        skill_set.add(s.lower().strip())
            if c.skills:
                for row in c.skills:
                    if row.name:
                        skill_set.add(row.name.lower().strip())
            if not skill_set and isinstance(c.skills_json, dict):
                for s in (c.skills_json.get("all_skills") or c.skills_json.get("technical", [])):
                    if s:
                        skill_set.add(s.lower().strip())
            if not req_lower:
                return 0.4  # no required skills: neutral score
            matched = req_lower & skill_set
            return len(matched) / len(req_lower)

        seen_names: dict[str, tuple[str, float]] = {}  # name → (candidate_id, best_cosine)
        cosine_all: dict[str, float] = {}
        for c in all_candidates:
            name      = (c.full_name or "").strip().lower()
            dedup_key = name if name else c.candidate_id
            cosine    = cosine_by_id.get(c.candidate_id) or _keyword_cosine(c)
            cosine_all[c.candidate_id] = cosine
            if dedup_key not in seen_names or cosine > seen_names[dedup_key][1]:
                seen_names[dedup_key] = (c.candidate_id, cosine)

        kept_ids      = {cid for cid, _ in seen_names.values()}
        candidate_ids = [cid for cid in (list(cosine_by_id.keys()) + [c.candidate_id for c in all_candidates])
                         if cid in kept_ids]
        # preserve order: Milvus hits first, then PG-only candidates
        seen_order: dict[str, int] = {}
        ordered_ids: list[str] = []
        for cid in candidate_ids:
            if cid not in seen_order:
                seen_order[cid] = len(ordered_ids)
                ordered_ids.append(cid)
        candidate_ids = ordered_ids
        candidates_db = {c.candidate_id: c for c in all_candidates if c.candidate_id in kept_ids}
        cosine_by_id  = cosine_all  # replace with enriched map

        logger.info(
            "[CVJobMatcher] Merged pool: %d unique candidates (Milvus+PG)",
            len(candidate_ids)
        )

        # ── 4. Cross-encoder pre-filter (FREE local, keeps top 15×top_k) ────
        ce_scores_by_id: dict[str, float] = {}
        if self._cross_encoder.ready and candidate_ids and store is not None:
            chunks_data = await store.fetch_chunks_by_candidate_ids(candidate_ids)
            cv_texts_by_id: dict[str, list[str]] = {}
            for chunk in chunks_data:
                cid = chunk["candidate_id"]
                cv_texts_by_id.setdefault(cid, []).append(chunk["text"])

            ordered_ids   = list(candidate_ids)
            cv_full_texts = [
                " ".join(cv_texts_by_id.get(cid, [""]))[:2000]
                for cid in ordered_ids
            ]
            ce_scores = await asyncio.to_thread(
                self._cross_encoder.score_pairs, query_text, cv_full_texts
            )
            ce_scores_by_id = dict(zip(ordered_ids, ce_scores))

            # Pre-filter: keep only top (top_k × 1.5) candidates for LLM scoring
            pre_filter_k = max(top_k * 2, 15)
            sorted_by_ce = sorted(ce_scores_by_id.items(), key=lambda x: x[1], reverse=True)
            candidate_ids = [cid for cid, _ in sorted_by_ce[:pre_filter_k]]
            logger.info(
                "[CVJobMatcher] Cross-encoder pre-filter: %d → %d candidates for LLM",
                len(ce_scores_by_id), len(candidate_ids)
            )

        # ── 5. Collect candidate data for batch scoring ──────────────────────
        candidates_data: list[dict] = []
        for cid in candidate_ids:
            c_db = candidates_db.get(cid)
            if not c_db:
                continue

            skill_set: set[str] = set()
            if c_db.extracted_skills:
                for s in (c_db.extracted_skills.all_skills or []):
                    if s:
                        skill_set.add(s)
            if c_db.skills:
                for row in c_db.skills:
                    if row.name:
                        skill_set.add(row.name)
            if not skill_set and isinstance(c_db.skills_json, dict):
                for s in (c_db.skills_json.get("all_skills") or c_db.skills_json.get("technical", [])):
                    if s:
                        skill_set.add(s)
            skills = list(skill_set)

            skills_lower_set = {s.lower() for s in skills}
            hint_matched = [s for s in required_skills if s.lower() in skills_lower_set]
            skill_coverage_hint = len(hint_matched) / len(required_skills) if required_skills else -1.0

            # Job titles/companies were loaded from the DB but never actually
            # reached the LLM — scoring ran on a flat skill list + summary
            # only, with no signal like "Senior Backend Eng @ Acme" that
            # matters for domain/seniority judgment. Most recent 3, since
            # that's what a recruiter would weigh most anyway.
            experience_titles = "; ".join(
                f"{e.title or '?'} @ {e.company or '?'}"
                for e in (c_db.experiences or [])[:3]
                if e.title or e.company
            )

            candidates_data.append({
                "candidate_id":      cid,
                "name":              c_db.full_name or "Inconnu",
                "email":             c_db.email,
                "seniority":         c_db.seniority_level or "unknown",
                "years_exp":         c_db.total_years_experience,
                "skills":            skills,
                "cv_summary":        getattr(c_db, "summary", "") or "",
                "experience_titles": experience_titles,
                "cosine_sim":        cosine_by_id.get(cid, 0.0),
                "skill_coverage":    skill_coverage_hint,
                "cross_encoder_score": ce_scores_by_id.get(cid, -1.0),
                "status":            status_by_id.get(cid, "pending") if job_posting_id else (c_db.status or "pending"),
                "_c_db":             c_db,
            })

        return candidates_data, query_text

    async def _split_cached_pairs(
        self,
        job_title:        str,
        job_description:  str,
        required_skills:  list[str],
        job_seniority:    Optional[str],
        lang:             str,
        candidates_data:  list[dict],
    ) -> tuple[str, dict[str, str], dict[str, "_ScoreTuple"], list[dict]]:
        """
        Split candidates_data into already-cached scores and candidates that
        still need an LLM call, using the per-(candidate,job) pair cache —
        content-addressed, so a changed candidate or job just misses instead
        of serving a stale score. Returns (job_hash, hash_by_id, cached,
        to_score).
        """
        from app.services import matching_cache

        job_hash = matching_cache.job_content_hash(job_title, job_description, required_skills, job_seniority)
        hash_by_id: dict[str, str] = {
            c["candidate_id"]: matching_cache.candidate_content_hash(
                c["skills"], c["seniority"], c["years_exp"], c["cv_summary"],
                c.get("experience_titles", ""),
            )
            for c in candidates_data
        }
        pairs = [(cid, chash) for cid, chash in hash_by_id.items()]
        hits = await matching_cache.get_cached_pair_scores(job_hash, lang, pairs)

        cached: dict[str, _ScoreTuple] = {
            cid: _cache_dict_to_score_tuple(hit) for cid, hit in hits.items()
        }
        to_score = [c for c in candidates_data if c["candidate_id"] not in cached]
        return job_hash, hash_by_id, cached, to_score

    async def match(
        self,
        job_title:        str,
        job_description:  str,
        required_skills:  list[str],
        job_seniority:    Optional[str] = None,
        top_k:            int = 10,
        min_score:        float = 0.30,
        generate_ai_desc: bool = True,
        lang:             str = "fr",
        job_posting_id:   Optional[str] = None,
    ) -> list[CandidateResult]:
        candidates_data, _query_text = await self._prepare_candidates(
            job_title, job_description, required_skills, top_k, job_posting_id,
        )

        job_hash, hash_by_id, cached, to_score = await self._split_cached_pairs(
            job_title, job_description, required_skills, job_seniority, lang, candidates_data,
        )

        # ── 6. BATCH AI scoring — only candidates not already cached ────────
        from app.services import matching_cache

        t_scoring = _time.monotonic()
        new_scores: dict[str, _ScoreTuple] = {}
        if to_score:
            batch_scores = await self._ai_scorer.batch_score(
                job_title       =job_title,
                job_description =job_description,
                required_skills =required_skills,
                job_seniority   =job_seniority,
                candidates      =to_score,
                lang            =lang,
            )
            for cdata, result in zip(to_score, batch_scores):
                cid = cdata["candidate_id"]
                new_scores[cid] = result
                await matching_cache.set_cached_pair_score(
                    job_hash, lang, cid, hash_by_id[cid], _score_tuple_to_cache_dict(result),
                )
        scoring_elapsed = round(_time.monotonic() - t_scoring, 2)
        per_candidate_time = round(scoring_elapsed / max(len(to_score), 1), 3)
        logger.info(
            "[CVJobMatcher] Scored %d/%d candidates via LLM in %.2fs (%d reused from pair cache)",
            len(to_score), len(candidates_data), scoring_elapsed, len(cached),
        )

        # ── 7. Assemble results ──────────────────────────────────────────────
        all_scores = {**cached, **new_scores}
        output: list[CandidateResult] = []
        for cdata in candidates_data:
            cid = cdata["candidate_id"]
            result = all_scores.get(cid)
            if result is None:
                continue
            ms, justif, matched, missing, strengths, weaknesses, recommendation = result
            output.append(CandidateResult(
                candidate_id    =cid,
                full_name       =cdata["name"],
                email           =cdata.get("email"),
                seniority       =cdata["seniority"],
                years_experience=cdata["years_exp"],
                candidate_skills=cdata["skills"],
                matched_skills  =matched,
                missing_skills  =missing,
                score           =ms,
                ai_description  =justif,
                raw_cosine      =cdata["cosine_sim"],
                status          =cdata["status"],
                scoring_time_s  =per_candidate_time if cid in new_scores else 0.0,
                key_strengths   =strengths,
                key_weaknesses  =weaknesses,
                recommendation  =recommendation,
            ))

        # ── 8. Sort by final_score, take top_k ───────────────────────────────
        output.sort(key=lambda x: x.score.final_score, reverse=True)
        output = output[:top_k]

        logger.info(
            "[CVJobMatcher] '%s' → %d candidates scored in %.2fs (top=%.1f)",
            job_title, len(output), scoring_elapsed,
            output[0].score.final_score if output else 0,
        )
        return output

    async def match_stream(
        self,
        job_title:        str,
        job_description:  str,
        required_skills:  list[str],
        job_seniority:    Optional[str] = None,
        top_k:            int = 10,
        lang:             str = "fr",
        job_posting_id:   Optional[str] = None,
    ):
        """
        Streamed counterpart to match(): same steps 1-5 (embed, Milvus, PG
        fetch, cross-encoder pre-filter), but yields each CandidateResult as
        soon as it's scored instead of returning the full sorted list only
        once every candidate is done. Callers that need the final ranked
        top_k list should collect the yielded results and sort/trim
        themselves once the generator is exhausted (see the WS route).
        """
        candidates_data, _query_text = await self._prepare_candidates(
            job_title, job_description, required_skills, top_k, job_posting_id,
        )
        if not candidates_data:
            return

        from app.services import matching_cache

        job_hash, hash_by_id, cached, to_score = await self._split_cached_pairs(
            job_title, job_description, required_skills, job_seniority, lang, candidates_data,
        )

        by_id = {c["candidate_id"]: c for c in candidates_data}
        t_scoring = _time.monotonic()

        def _to_result(cdata: dict, result: "_ScoreTuple", scoring_time_s: float) -> CandidateResult:
            ms, justif, matched, missing, strengths, weaknesses, recommendation = result
            return CandidateResult(
                candidate_id    =cdata["candidate_id"],
                full_name       =cdata["name"],
                email           =cdata.get("email"),
                seniority       =cdata["seniority"],
                years_experience=cdata["years_exp"],
                candidate_skills=cdata["skills"],
                matched_skills  =matched,
                missing_skills  =missing,
                score           =ms,
                ai_description  =justif,
                raw_cosine      =cdata["cosine_sim"],
                status          =cdata["status"],
                scoring_time_s  =scoring_time_s,
                key_strengths   =strengths,
                key_weaknesses  =weaknesses,
                recommendation  =recommendation,
            )

        # Cached pairs need no LLM call — yield them immediately so the UI
        # shows them right away, before the (only) LLM call for the rest.
        for cid, result in cached.items():
            cdata = by_id.get(cid)
            if cdata is not None:
                yield _to_result(cdata, result, 0.0)

        if not to_score:
            return

        async for candidate_id, ms, justif, matched, missing, strengths, weaknesses, recommendation in (
            self._ai_scorer.batch_score_stream(
                job_title       =job_title,
                job_description =job_description,
                required_skills =required_skills,
                job_seniority   =job_seniority,
                candidates      =to_score,
                lang            =lang,
            )
        ):
            cdata = by_id.get(candidate_id)
            if cdata is None:
                continue
            result = (ms, justif, matched, missing, strengths, weaknesses, recommendation)
            await matching_cache.set_cached_pair_score(
                job_hash, lang, candidate_id, hash_by_id[candidate_id], _score_tuple_to_cache_dict(result),
            )
            yield _to_result(cdata, result, round(_time.monotonic() - t_scoring, 3))

    # ── PostgreSQL fallback — works without Milvus ───────────────────────────

    async def _pg_fallback(
        self,
        job_title:       str,
        required_skills: list[str],
        job_seniority:   Optional[str],
        top_k:           int,
    ) -> list[CandidateResult]:
        """
        Keyword/skill-based matching directly against PostgreSQL.
        Used when Milvus is unavailable or returns 0 results.
        Scores candidates by skill overlap + seniority, then ranks by final score.
        """
        from app.infrastructure.database.session import AsyncSessionLocal
        from app.infrastructure.database.models import CandidateModel, ExtractedSkillsModel
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        req_lower = [s.lower().strip() for s in required_skills]

        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(CandidateModel)
                .options(
                    selectinload(CandidateModel.extracted_skills),
                    selectinload(CandidateModel.skills),
                )
                .where(CandidateModel.status != "rejected")
                .limit(200)
            )
            candidates = list(rows.scalars())

        if not candidates:
            logger.info("[CVJobMatcher/PG] No candidates in DB")
            return []

        output: list[CandidateResult] = []
        for c in candidates:
            # Collect all skills for this candidate
            all_skills: list[str] = []
            if c.extracted_skills:
                es = c.extracted_skills
                for attr in ("technical", "frameworks", "databases", "devops", "soft_skills", "languages"):
                    val = getattr(es, attr, None)
                    if isinstance(val, list):
                        all_skills.extend(val)
                if isinstance(getattr(es, "all_skills", None), list):
                    all_skills.extend(es.all_skills)
            for sk in c.skills or []:
                if hasattr(sk, "name") and sk.name:
                    all_skills.append(sk.name)

            skills_lower = [s.lower().strip() for s in all_skills]

            matched  = [s for s in required_skills if s.lower().strip() in skills_lower]
            missing  = [s for s in required_skills if s.lower().strip() not in skills_lower]
            coverage = len(matched) / len(required_skills) if required_skills else 0.5

            ms = compute_match_score(
                cosine_sim=coverage,
                candidate_seniority=c.seniority_level or "unknown",
                job_seniority=job_seniority,
                skill_coverage=coverage,
            )

            years_exp = c.total_years_experience
            exp_str   = f"{int(years_exp)}Y Exp" if years_exp and years_exp >= 1 else "N/A"

            output.append(CandidateResult(
                candidate_id    =c.candidate_id,
                full_name       =c.full_name or "Candidat",
                email           =c.email,
                seniority       =c.seniority_level or "unknown",
                years_experience=years_exp,
                candidate_skills=list(set(all_skills))[:20],
                matched_skills  =matched,
                missing_skills  =missing,
                score           =ms,
                ai_description  =None,
                raw_cosine      =coverage,
                status          =c.status or "pending",
                scoring_time_s  =0.0,
            ))

        output.sort(key=lambda x: x.score.final_score, reverse=True)
        result = output[:top_k]
        logger.info(
            "[CVJobMatcher/PG] Fallback: %d candidates → top %d (best=%.1f)",
            len(output), len(result),
            result[0].score.final_score if result else 0,
        )
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor (avoids re-creating the matcher/clients every request)
# ─────────────────────────────────────────────────────────────────────────────

_matcher_instance: Optional[CVJobMatcher] = None


def get_cv_job_matcher() -> CVJobMatcher:
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = CVJobMatcher()
    return _matcher_instance


# ─────────────────────────────────────────────────────────────────────────────
# __main__ — full integration test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _run_test() -> None:
        print("\n" + "=" * 60)
        print("  CVJobMatcher — Integration Test")
        print("=" * 60)

        # ── Test 1: MatchingScore ────────────────────────────────────────────
        print("\n[1] MatchingScore unit tests")
        cases = [
            (0.85, "senior", "senior",  "perfect match"),
            (0.72, "junior", "senior",  "2-level gap → 0.70 multiplier"),
            (0.60, "mid",    "senior",  "1-level gap → 0.85 multiplier"),
            (0.90, "lead",   "junior",  "over-qualified → 1.00 multiplier"),
            (0.40, "intern", "senior",  "3-level gap → 0.50 multiplier"),
        ]
        for cosine, c_sen, j_sen, label in cases:
            ms = compute_match_score(cosine, c_sen, j_sen)
            print(
                f"  {label:<35} cosine={cosine:.2f} → "
                f"skill={ms.skill_score:.1f} mult={ms.seniority_multiplier:.2f} "
                f"final={ms.final_score:.1f} gap={ms.seniority_gap:+d}"
            )

        # ── Test 2: MultiModelAIEngine ────────────────────────────────────────
        print("\n[2] MultiModelAIEngine — generate test")
        engine = MultiModelAIEngine()
        try:
            text, model = await engine.generate(
                "Réponds uniquement: 'Moteur AI opérationnel.'"
            )
            print(f"  ✓ Model used: {model}")
            print(f"  Response: {text[:120]}")
        except RuntimeError as e:
            print(f"  ✗ All models failed: {e}")

        # ── Test 3: EmbeddingService cache ────────────────────────────────────
        print("\n[3] EmbeddingService — cache test")
        embed_svc = EmbeddingService()
        test_text = "Senior Data Scientist with Python, TensorFlow, NLP"
        emb1 = await embed_svc.embed_query(test_text)
        emb2 = await embed_svc.embed_query(test_text)
        assert emb1 is emb2, "Cache miss — same object expected!"
        print(f"  ✓ Cache hit confirmed (dim={len(emb1)}, same object)")

        # ── Test 4: Full CVJobMatcher ─────────────────────────────────────────
        print("\n[4] CVJobMatcher — end-to-end")
        matcher = CVJobMatcher()
        try:
            results = await matcher.match(
                job_title="Senior Data Scientist",
                job_description="Nous recherchons un Data Scientist pour concevoir des modèles ML.",
                required_skills=["Python", "TensorFlow", "NLP", "SQL"],
                job_seniority="senior",
                top_k=3,
                min_score=0.20,
                generate_ai_desc=True,
            )
            if not results:
                print("  ⚠  No candidates found (is Milvus populated?)")
            for i, r in enumerate(results, 1):
                print(f"\n  Candidate #{i}: {r.full_name} ({r.seniority})")
                print(f"    Skill score:  {r.score.skill_score:.1f}")
                print(f"    Seniority ×:  {r.score.seniority_multiplier:.2f}  (gap {r.score.seniority_gap:+d})")
                print(f"    Final score:  {r.score.final_score:.1f}/100")
                print(f"    Matched:      {r.matched_skills}")
                print(f"    Missing:      {r.missing_skills}")
                if r.ai_description:
                    print(f"    AI analysis:  {r.ai_description[:200]}…")
        except Exception as exc:
            print(f"  ✗ CVJobMatcher error: {exc}")
            import traceback; traceback.print_exc()

        print("\n" + "=" * 60)
        print("  Tests complete")
        print("=" * 60 + "\n")

    asyncio.run(_run_test())
