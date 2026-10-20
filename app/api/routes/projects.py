"""
projects.py
===========
API endpoints pour l'AI Assistant de recommandation d'équipes projet
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import List, Dict, Any, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.entities.project import (
    Project,
    ProjectTask,
    TeamComposition
)
from app.services.project_team_recommender import recommend_team_for_project
from app.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["AI Assistant - Projects"])


# ═══════════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════════

class TaskInput(BaseModel):
    task_id: str = Field(..., description="ID unique de la tâche")
    title: str = Field(..., description="Titre de la tâche")
    description: str = Field(..., description="Description détaillée")
    required_skills: List[str] = Field(default_factory=list)
    seniority_level: str = Field(default="mid")
    estimated_workload_days: float = Field(...)
    priority: int = Field(default=1)
    dependencies: List[str] = Field(default_factory=list)


class ProjectAnalysisRequest(BaseModel):
    project_name: str = Field(...)
    project_description: str = Field(...)
    tasks: List[TaskInput] = Field(..., min_items=1)
    start_date: Optional[date] = None
    deadline: Optional[date] = None
    budget_max: Optional[float] = None
    team_size_max: Optional[int] = None
    constraints: Dict[str, Any] = Field(default_factory=dict)


class ProjectAnalysisResponse(BaseModel):
    success: bool
    project_id: str
    recommendations: TeamComposition
    message: str = ""


class TextAnalysisRequest(BaseModel):
    text: str = Field(..., description="Message libre de l'utilisateur")
    conversation_id: Optional[str] = Field(None, description="ID de la conversation courante (pour contexte)")


class TextAnalysisResponse(BaseModel):
    success: bool
    message: str
    response_type: str = "general"  # project | candidate_profile | specialty_search | job_offer | general
    recommendations: Optional[TeamComposition] = None
    extracted_project: Optional[Dict[str, Any]] = None
    job_offer_data: Optional[Dict[str, Any]] = None  # structured data for Word export


# ═══════════════════════════════════════════════════════════════════
# Intent detection patterns
# ═══════════════════════════════════════════════════════════════════

_CANDIDATE_PROFILE_PATTERNS = [
    r'résumé[ez]?\s+(?:du\s+candidat\s+|de\s+)?(.+)',
    r'résume[ez]?\s+(?:le\s+profil\s+de\s+)?(.+)',
    # "profil [adjective] de NAME" — adjective like "complet", "détaillé", etc.
    r'profil\s+\w+\s+de\s+(.+)',
    r'profil\s+(?:de\s+|du\s+candidat\s+)?(.+)',
    r'qui\s+est\s+([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)+)',
    r'parle[ez]?\s+moi\s+de\s+(.+)',
    r'cv\s+de\s+(.+)',
    # "donne-moi le profil [adjective] de NAME" — handles hyphen and optional adjective
    r'(?:donne[ez]?[-\s]moi\s+(?:le\s+)?(?:profil|résumé|cv|informations?)\s+(?:\w+\s+)?(?:de\s+|du\s+|d\'))(.+)',
    r'informations?\s+sur\s+(.+)',
    r'que\s+sais[- ]tu\s+(?:sur|de)\s+(.+)',
]

_SPECIALTY_SEARCH_PATTERNS = [
    # "candidats [les plus] orientés/spécialisés [en] SPECIALTY" — handles "quels sont les candidats les plus orientés frontend"
    r'candidats?\s+(?:les?\s+plus\s+)?(?:orientés?|spécialisés?|bons?|forts?|experts?)\s+(?:en\s+|dans?\s+(?:le\s+|la\s+|les?\s+)?|pour\s+)?(.+)',
    r'(?:candidats?|profils?|développeurs?|ingénieurs?|experts?)\s+(?:orientés?|spécialisés?|bons?|forts?|experts?|maitris(?:ant|e))\s+(?:en\s+|le\s+)?(.+)',
    r'qui\s+(?:maîtrise|connait|connait\s+bien|est\s+expert\s+en|est\s+spécialisé\s+en)\s+(.+)',
    r'(?:lequel|lesquels)\s+(?:des\s+candidats?\s+)?(?:est|sont)\s+(?:le\s+plus\s+)?(?:orienté|fort|bon|compétent)\s+(?:en\s+|pour\s+la?\s+)?(.+)',
    r'(?:meilleur|top|meilleures?)\s+candidats?\s+(?:en\s+|pour\s+|sur\s+)?(.+)',
    r'recherche[rz]?\s+(?:un|des)?\s+(?:expert|spécialiste|développeur|ingénieur)\s+(?:en\s+)?(.+)',
    r'candidats?\s+(?:qui\s+font\s+|versés?\s+en\s+|avec\s+expertise\s+en\s+)?(.+?)(?:\s+ou\s+.+)?$',
    r'qui\s+(?:peut|peuvent|sont\s+capables?\s+de|serait\s+idéal\s+pour)\s+(?:du\s+|de\s+la\s+|les?\s+)?(.+)',
    r'compétences?\s+(?:en\s+|autour\s+de\s+)?(.+)',
]

_JOB_OFFER_PATTERNS = [
    r'rédig[eé][rz]?\s+(?:une?\s+)?(?:offre|fiche|description|annonce|poste)\s+(?:d\'emploi\s+|de\s+travail\s+|de\s+poste\s+)?(?:pour\s+|un\s+|une?\s+)?(.+)',
    r'(?:crée[rz]?|génère[rz]?|écri[stz]?|prépare[rz]?)\s+(?:une?\s+)?(?:offre|annonce|fiche)\s+(?:d\'emploi\s+)?(?:pour\s+)?(.+)',
    r'offre\s+(?:d\'emploi|de\s+travail|de\s+poste)\s+(?:pour\s+(?:un|une)?\s+)?(.+)',
    r'fiche\s+de\s+poste\s+(?:pour\s+(?:un|une)?\s+)?(.+)',
    r'description\s+de\s+poste\s+(?:pour\s+(?:un|une)?\s+)?(.+)',
    r'annonce\s+(?:de\s+recrutement\s+)?(?:pour\s+)?(.+)',
    r'template\s+(?:d\'offre|offre)\s+(?:pour\s+)?(.+)',
]

_GENERAL_QUESTION_PATTERNS = [
    r'^comment\s+',
    r'^quel(?:le)?s?\s+sont\s+les\s+',
    r'^qu\'est[- ]ce\s+',
    r'^pouvez[- ]vous\s+',
    r'^peux[- ]tu\s+',
    r'^aide[rz]?\s*moi\s+à\s+',
    r'^explique[rz]?\s+',
    r'^donne[rz]?\s+moi\s+(?:des\s+)?conseils',
    r'^quelles?\s+sont\s+les\s+meilleures?\s+pratiques',
    r'^combien\s+',
]

# Patterns de questions de suivi conversationnelles (follow-up)
_FOLLOW_UP_PATTERNS = [
    r'^pourquoi\b',
    r'\bun\s+autre\s+candidat\b',
    r'\bd\'autres?\s+recommandations?\b',
    r'\bà\s+la\s+place\b',
    r'\ben\s+remplacement\b',
    r'\béla(?:bore|bore[rz]?)\b',
    r'\bdétaille[rz]?\b',
    r'\bcomment\s+(?:tu\s+as|as[- ]tu)\s+(?:classé|choisi|sélectionné|décidé|évalué)\b',
    r'\bpourquoi\s+(?:pas|plutôt|ce|lui|elle|cet|cette|lui)\b',
    r'\bqu\'en\s+(?:est[- ]il|penses?[- ]tu|dis[- ]tu)\b',
    r'\btu\s+(?:confirmes?|penses?|crois?|suggères?)\b',
    r'\bc\'est\s+(?:qui|lequel|laquelle)\b',
    r'\bcompar(?:e|er?)[rz]?\s',
    r'\bplus\s+(?:de\s+)?d[eé]tails?\b',
    r'\btu\s+peux\s+(?:me\s+)?(?:donner|préciser|expliquer|montrer)\b',
    r'\ble\s+(?:meilleur|premier|deuxième|troisième|top)\b',
    r'^et\s+(?:pour|si|avec|lui|elle|eux|elles)\b',
    r'\bqu\'(?:en|il|elle)\b.{0,30}\b(?:score|résultat|classement|rang)\b',
]


def _detect_intent(text: str) -> tuple[str, Optional[str]]:
    """
    Détecte l'intention de l'utilisateur.

    Returns:
        (intent, extracted_value) where intent is one of:
        candidate_profile | specialty_search | job_offer | general | project
    """
    text_stripped = text.strip()

    for pattern in _CANDIDATE_PROFILE_PATTERNS:
        m = re.search(pattern, text_stripped, re.IGNORECASE)
        if m:
            name = m.groups()[-1].strip()
            # Filtres de cohérence: un nom ne contient pas de mot-clé projet
            project_keywords = ['projet', 'développer', 'application', 'système', 'plateforme',
                                  'backend', 'frontend', 'api', 'base de données', 'budget']
            if len(name) < 60 and not any(kw in name.lower() for kw in project_keywords):
                name = re.sub(r'\b(le|la|du|de\s+la|des|un|une|candidat|candidate)\b', '',
                               name, flags=re.IGNORECASE).strip()
                if name:
                    return "candidate_profile", name

    for pattern in _JOB_OFFER_PATTERNS:
        m = re.search(pattern, text_stripped, re.IGNORECASE)
        if m:
            role = m.groups()[-1].strip()
            if role:
                return "job_offer", role

    for pattern in _SPECIALTY_SEARCH_PATTERNS:
        m = re.search(pattern, text_stripped, re.IGNORECASE)
        if m:
            specialty = m.groups()[-1].strip()
            # Remove trailing noise: "?", then "dans notre/la/votre base [de données]"
            specialty = specialty.rstrip('?').strip()
            specialty = re.sub(
                r'\s+(?:dans\s+(?:notre|votre|la)\s+base(?:\s+de\s+données?)?|en\s+ligne)\s*$',
                '', specialty, flags=re.IGNORECASE
            ).strip()
            project_keywords = ['projet', 'développer', 'système', 'plateforme', 'budget', 'deadline']
            if specialty and len(specialty) < 80 and not any(kw in specialty.lower() for kw in project_keywords):
                return "specialty_search", specialty

    for pattern in _GENERAL_QUESTION_PATTERNS:
        if re.search(pattern, text_stripped, re.IGNORECASE):
            return "general", None

    return "project", None


def _is_follow_up(text: str, has_history: bool) -> bool:
    """
    Retourne True si le message semble être une question de suivi
    et qu'il y a un historique de conversation disponible.
    """
    if not has_history:
        return False
    text_stripped = text.strip()
    for pattern in _FOLLOW_UP_PATTERNS:
        if re.search(pattern, text_stripped, re.IGNORECASE):
            return True
    # Message très court (< 20 chars) sans intent → probablement un follow-up ("et lui ?", "pourquoi ?")
    if len(text_stripped) < 20 and has_history:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════
# Intent handlers
# ═══════════════════════════════════════════════════════════════════

async def _handle_candidate_profile(
    name: str,
    original_text: str,
    history: list[dict] | None = None,
    user_memory: str = "",
) -> str:
    """Recherche un candidat par nom et génère un résumé de profil."""
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.infrastructure.database.models import CandidateModel
    from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
    from app.services.multi_llm_service import get_llm_service
    from sqlalchemy import select, or_

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel).where(
                or_(
                    CandidateModel.full_name.ilike(f"%{name}%"),
                    CandidateModel.candidate_id.ilike(f"%{name}%"),
                )
            ).limit(1)
        )
        candidate = result.scalar_one_or_none()

    if not candidate:
        return f"❌ Aucun candidat correspondant à **\"{name}\"** n'a été trouvé dans la base de données."

    milvus_store = MilvusVectorStore()
    chunks = await milvus_store.fetch_chunks_by_candidate_ids([candidate.candidate_id])
    cv_text = "\n\n".join(chunk.get("text", "") for chunk in chunks)

    if not cv_text:
        cv_text = (
            f"Nom: {candidate.full_name}\n"
            f"Expérience: {candidate.total_years_experience} ans\n"
            f"Compétences: {', '.join(candidate.skills or [])}"
        )

    llm_service = get_llm_service()
    prompt = f"""Voici le CV complet d'un candidat:

{cv_text[:4000]}

Question / demande de l'utilisateur: {original_text}

Génère une réponse professionnelle, structurée et concise.
Utilise des sections claires: **Profil**, **Expériences clés**, **Compétences techniques**, **Points forts**, **Recommandation**.
Si la demande est spécifique (ex: résumé, évaluation sur une techno), réponds directement à cette demande."""

    memory_block = (user_memory + "\n\n") if user_memory else ""
    system_prompt = f"""{memory_block}Tu es un assistant RH expert. Tu analyses des CVs et fournis des évaluations professionnelles aux recruteurs.
Sois factuel, précis et mets en avant les éléments les plus pertinents pour le recrutement.
RÈGLE ABSOLUE: Réponds TOUJOURS en français, quelle que soit la langue de la question ou du CV.
Utilise du markdown pour structurer la réponse."""

    response = await llm_service.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.4,
        max_tokens=1200,
        force_french=True,
        conversation_history=history,
    )
    return f"## Profil de {candidate.full_name}\n\n{response['content']}"


async def _handle_specialty_search(
    specialty: str,
    history: list[dict] | None = None,
    user_memory: str = "",
) -> str:
    """Cherche les candidats par domaine/spécialité et génère une synthèse."""
    from app.agent.tools.cv_extractor.embedder import embed_single_query
    from app.services.retrieval_service import vector_search_by_embedding
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.infrastructure.database.models import CandidateModel
    from app.services.multi_llm_service import get_llm_service
    from sqlalchemy import select

    query_embedding = await embed_single_query(
        f"expert développeur spécialiste {specialty} compétences techniques {specialty}"
    )

    raw_chunks = await vector_search_by_embedding(query_embedding=query_embedding, top_k=60)

    candidates_data: dict = defaultdict(lambda: {"chunks": [], "scores": []})
    for chunk in raw_chunks:
        cid = chunk.get("candidate_id") or chunk.get("id")
        if not cid:
            continue
        score = chunk.get("score", 0.0)
        candidates_data[cid]["chunks"].append(chunk)
        candidates_data[cid]["scores"].append(float(score))

    sorted_candidates = sorted(
        candidates_data.items(),
        key=lambda x: (sum(x[1]["scores"]) / len(x[1]["scores"])) if x[1]["scores"] else 0,
        reverse=True,
    )[:10]

    if not sorted_candidates:
        return f"Aucun candidat pertinent trouvé pour la spécialité **{specialty}**."

    candidate_ids = [cid for cid, _ in sorted_candidates]
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel).where(CandidateModel.candidate_id.in_(candidate_ids))
        )
        db_map = {c.candidate_id: c for c in result.scalars().all()}

    profiles = []
    for cid, data in sorted_candidates:
        candidate = db_map.get(cid)
        name = candidate.full_name if candidate else f"Candidat {cid[:8]}"

        skills: list[str] = []
        for chunk in data["chunks"][:4]:
            sj = chunk.get("skills_json")
            if sj:
                try:
                    parsed = json.loads(sj) if isinstance(sj, str) else sj
                    if isinstance(parsed, list):
                        skills.extend(parsed)
                except Exception:
                    pass
        skills = list(set(skills))[:10]

        cv_excerpt = " ".join(
            chunk.get("text", "") for chunk in data["chunks"][:2]
        )[:600]

        avg_score = sum(data["scores"]) / len(data["scores"]) * 100 if data["scores"] else 0
        profiles.append({"name": name, "score": avg_score, "skills": skills, "excerpt": cv_excerpt})

    profiles_text = "\n\n---\n\n".join(
        f"**{p['name']}** — Score de pertinence: {p['score']:.0f}%\n"
        f"Compétences: {', '.join(p['skills']) if p['skills'] else 'N/A'}\n"
        f"Extrait: {p['excerpt'][:400]}"
        for p in profiles
    )

    llm_service = get_llm_service()
    prompt = f"""Tu es un expert RH. L'utilisateur cherche des candidats compétents en **{specialty}**.

Voici les profils les plus pertinents trouvés dans la base:

{profiles_text}

Pour chaque candidat, évalue:
1. Son niveau réel en {specialty} (Débutant / Intermédiaire / Avancé / Expert)
2. Ses points forts spécifiques à cette spécialité
3. Sa séniorité estimée

Présente une synthèse claire et professionnelle, classée du plus au moins pertinent.
Format: liste numérotée avec sous-sections pour chaque candidat."""

    memory_block = (user_memory + "\n\n") if user_memory else ""
    system_prompt = f"{memory_block}Tu es un assistant RH expert. Réponds TOUJOURS en français, quelle que soit la langue des données d'entrée. Analyse professionnelle et concise."

    response = await llm_service.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.4,
        max_tokens=1500,
        force_french=True,
        conversation_history=history,
    )
    return f"## Candidats spécialisés en {specialty}\n\n{response['content']}"


async def _handle_job_offer(
    role: str,
    original_text: str,
    history: list[dict] | None = None,
    user_memory: str = "",
) -> tuple[str, dict]:
    """Génère une offre d'emploi professionnelle au format Sofrecom.
    Retourne (markdown_for_chat, structured_data_for_word).
    """
    from app.services.multi_llm_service import get_llm_service

    llm_service = get_llm_service()

    prompt = f"""Tu es un expert RH Sofrecom spécialisé dans la rédaction d'offres d'emploi.
Génère une offre d'emploi professionnelle pour le poste suivant en respectant EXACTEMENT ce format JSON.

Poste demandé: {role}
Instructions précises du recruteur: {original_text}

RÈGLES ABSOLUES — respecte-les en priorité absolue sur tout le reste:
- Si le recruteur mentionne un nombre d'années d'expérience (ex: "5 ans", "minimum 3 ans"), intègre-le EXACTEMENT dans "experience_required".
- Si le recruteur mentionne un niveau de séniorité (junior, mid, senior, lead, expert), intègre-le EXACTEMENT dans "experience_required" et adapte le contenu en conséquence.
- Si le recruteur liste des compétences spécifiques (ex: React, Python, Docker), inclus-les TOUTES dans "technical_skills" en premier, puis complète avec des compétences complémentaires pertinentes.
- Si le recruteur décrit des missions ou responsabilités spécifiques, inclus-les TOUTES dans "activities" en priorité, puis complète si nécessaire.
- Si aucune instruction spécifique n'est donnée sur un champ, génère un contenu professionnel adapté au poste.

Réponds UNIQUEMENT avec ce JSON valide, sans texte avant ni après:
{{
  "title": "Titre exact du poste (f/h)",
  "experience_required": "Nombre d'années et niveau de formation requis (1 phrase)",
  "activities": [
    "Activité principale 1",
    "Activité principale 2",
    "Activité principale 3",
    "Activité principale 4",
    "Activité principale 5"
  ],
  "technical_skills": [
    "Phrase complète décrivant une maîtrise technique (ex: Excellente maîtrise de Python et des frameworks Data Science tels que PyTorch et TensorFlow).",
    "Phrase complète décrivant une compétence backend ou infrastructure.",
    "Phrase complète décrivant une expérience avec des outils spécifiques.",
    "Phrase complète décrivant une maîtrise base de données ou cloud.",
    "Phrase complète décrivant une compétence complémentaire."
  ],
  "behavioral_skills": [
    "Aptitude comportementale 1",
    "Aptitude comportementale 2",
    "Aptitude comportementale 3",
    "Aptitude comportementale 4"
  ]
}}

Génère entre 4 et 7 éléments par liste. Contenu professionnel, précis et adapté au secteur télécom/IT."""

    memory_block = (user_memory + "\n\n") if user_memory else ""
    system_prompt = f"{memory_block}Tu es un expert RH Sofrecom. Réponds UNIQUEMENT en JSON valide, sans markdown, sans texte additionnel. TOUJOURS en français."

    response = await llm_service.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.5,
        max_tokens=1500,
        force_french=True,
        conversation_history=history,
    )

    raw = response["content"].strip()
    # Strip possible markdown code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract JSON from the response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    title = data.get("title", role)
    intro = (
        f"Le document relatif au poste **{title}** est prêt à être téléchargé. "
        f"Vous y trouverez l'ensemble des missions et responsabilités associées à ce poste, "
        f"ainsi que les compétences techniques et comportementales requises."
    )

    return intro, data


async def _handle_general_question(
    text: str,
    history: list[dict] | None = None,
    user_memory: str = "",
) -> str:
    """Répond aux questions RH générales avec contexte conversationnel."""
    from app.services.multi_llm_service import get_llm_service

    llm_service = get_llm_service()

    prompt = f"""Question de l'utilisateur (recruteur RH): {text}

Réponds de manière professionnelle, structurée et pratique.
Si la question concerne des pratiques RH, des évaluations de compétences, des processus de recrutement ou la gestion d'équipe, fournis des conseils concrets et actionnables."""

    memory_block = (user_memory + "\n\n") if user_memory else ""
    system_prompt = f"""{memory_block}Tu es un assistant RH expert avec une connaissance approfondie du recrutement, de la gestion des talents et des pratiques RH modernes.
Si un historique de conversation est disponible, utilise-le pour répondre avec continuité.
RÈGLE ABSOLUE: Réponds TOUJOURS en français, quelle que soit la langue de la question. Sois concis, professionnel et utile."""

    response = await llm_service.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.5,
        max_tokens=1000,
        force_french=True,
        conversation_history=history,
    )
    return response["content"]


async def _handle_follow_up(
    text: str,
    history: list[dict],
    user_memory: str = "",
) -> str:
    """
    Traite les questions de suivi conversationnelles (ex: "pourquoi ce candidat ?",
    "un autre candidat pour cette tâche ?", "élabore sur le score").
    Passe l'historique complet au LLM pour qu'il comprenne le contexte.
    """
    from app.services.multi_llm_service import get_llm_service

    llm_service = get_llm_service()

    memory_block = (user_memory + "\n\n") if user_memory else ""
    system_prompt = f"""{memory_block}Tu es un assistant RH expert. L'utilisateur te pose une question de suivi sur une analyse ou recommandation précédente.
Utilise l'historique de la conversation pour répondre avec précision et continuité, sans demander à l'utilisateur de répéter le contexte.
Si l'utilisateur demande un autre candidat ou une alternative, propose-en une basée sur les informations de la conversation.
RÈGLE ABSOLUE: Réponds TOUJOURS en français. Sois concis, précis et professionnel."""

    response = await llm_service.generate(
        prompt=text,
        system_prompt=system_prompt,
        temperature=0.4,
        max_tokens=1200,
        force_french=True,
        conversation_history=history,
    )
    return response["content"]


# ═══════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post("/analyze", response_model=ProjectAnalysisResponse, status_code=status.HTTP_200_OK)
async def analyze_project(request: ProjectAnalysisRequest):
    """
    Analyse un projet structuré et recommande une équipe optimale (pipeline RAG → DCI → LLM).
    """
    try:
        logger.info(f"[API] Nouvelle analyse de projet: {request.project_name}")

        tasks = [
            ProjectTask(
                task_id=task.task_id,
                title=task.title,
                description=task.description,
                required_skills=task.required_skills,
                seniority_level=task.seniority_level,
                estimated_workload_days=task.estimated_workload_days,
                priority=task.priority,
                dependencies=task.dependencies,
            )
            for task in request.tasks
        ]

        project = Project(
            project_id=f"proj_{request.project_name.lower().replace(' ', '_')}",
            name=request.project_name,
            description=request.project_description,
            tasks=tasks,
            start_date=request.start_date,
            deadline=request.deadline,
            budget_max=request.budget_max,
            team_size_max=request.team_size_max,
            constraints=request.constraints,
        )

        recommendations = await recommend_team_for_project(project)

        return ProjectAnalysisResponse(
            success=True,
            project_id=project.project_id,
            recommendations=recommendations,
            message=f"Équipe générée en {recommendations.processing_time_ms}ms via {recommendations.llm_provider_used}",
        )

    except Exception as e:
        logger.error(f"[API] Erreur analyse projet: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    from app.services.multi_llm_service import get_llm_service

    svc = get_llm_service()
    return {
        "status": "ok",
        "service": "AI Assistant - Project Team Recommender",
        "llm_fallback_order": list(svc.providers.keys()),
        "failed_providers": list(svc.failed_providers),
        "last_successful_provider": svc.last_successful_provider,
    }


@router.post("/analyze-text", response_model=TextAnalysisResponse, status_code=status.HTTP_200_OK)
async def analyze_project_from_text(
    request: TextAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Point d'entrée universel du chat AI:
    - Analyse de projet en langage naturel → recommandation d'équipe (RAG→DCI→LLM)
    - Profil candidat → résumé détaillé
    - Recherche par spécialité → classement des meilleurs profils
    - Génération d'offre d'emploi → offre professionnelle complète
    - Question de suivi → réponse contextuelle avec historique
    - Question RH générale → réponse experte
    """
    try:
        text = request.text.strip()
        user_id: int = current_user["id"]
        logger.info("[API] Texte reçu (%d chars) user=%d: %s...", len(text), user_id, text[:100])

        # ── 1. Récupérer l'historique de la conversation courante ─────
        conversation_history: list[dict] = []
        if request.conversation_id:
            try:
                from app.infrastructure.repositories.conversation_repo import ConversationRepository
                conv_repo = ConversationRepository()
                conv = await conv_repo.get_conversation_by_id(request.conversation_id, user_id)
                if conv and conv.messages:
                    for m in conv.messages[-12:]:  # 6 derniers échanges
                        role = m.get("role")
                        content = str(m.get("content", ""))
                        if role in ("user", "assistant") and content:
                            conversation_history.append({"role": role, "content": content[:2000]})
                    logger.info("[API] Historique chargé: %d messages", len(conversation_history))
            except Exception as exc:
                logger.warning("[API] Impossible de charger l'historique: %s", exc)

        # ── 2. Récupérer la mémoire utilisateur (cross-conversation) ──
        user_memory = ""
        try:
            from app.services.ai_memory_service import get_user_memory_prompt
            user_memory = await get_user_memory_prompt(user_id)
        except Exception as exc:
            logger.warning("[API] Impossible de charger la mémoire utilisateur: %s", exc)

        has_history = len(conversation_history) > 0

        # ── 3. Détecter l'intention ───────────────────────────────────
        # Les intents spécifiques ont toujours la priorité sur le follow_up.
        # Le follow_up n'est utilisé que si l'intent est "general" ou "project"
        # ET que le message ressemble à une question de suivi.
        intent, extracted = _detect_intent(text)
        logger.info("[API] Intent détecté: %s | Valeur extraite: %s", intent, extracted)

        # ── Profil candidat ──────────────────────────────────────────
        if intent == "candidate_profile" and extracted:
            answer = await _handle_candidate_profile(extracted, text, conversation_history, user_memory)
            return TextAnalysisResponse(
                success=True,
                message=answer,
                response_type="candidate_profile",
            )

        # ── Génération d'offre d'emploi ──────────────────────────────
        if intent == "job_offer" and extracted:
            answer, offer_data = await _handle_job_offer(extracted, text, conversation_history, user_memory)
            return TextAnalysisResponse(
                success=True,
                message=answer,
                response_type="job_offer",
                job_offer_data=offer_data,
            )

        # ── Recherche par spécialité ─────────────────────────────────
        if intent == "specialty_search" and extracted:
            answer = await _handle_specialty_search(extracted, conversation_history, user_memory)
            return TextAnalysisResponse(
                success=True,
                message=answer,
                response_type="specialty_search",
            )

        # ── Follow-up conversationnel (general ou project ambigus + historique) ──
        if _is_follow_up(text, has_history):
            logger.info("[API] Intent: follow_up")
            answer = await _handle_follow_up(text, conversation_history, user_memory)
            return TextAnalysisResponse(
                success=True,
                message=answer,
                response_type="general",
            )

        # ── Question RH générale ─────────────────────────────────────
        if intent == "general":
            answer = await _handle_general_question(text, conversation_history, user_memory)
            return TextAnalysisResponse(
                success=True,
                message=answer,
                response_type="general",
            )

        # ── Analyse de projet (défaut) ───────────────────────────────
        from app.services.project_text_analyzer import get_text_analyzer

        text_analyzer = get_text_analyzer()
        analysis_result = await text_analyzer.analyze_text(text)

        if not analysis_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible d'extraire les informations du projet depuis le texte",
            )

        project_data = analysis_result["project_data"]
        logger.info("[API] Projet extrait: %s — %d tâches", project_data['project_name'], len(project_data['tasks']))

        tasks = [
            ProjectTask(
                task_id=t["task_id"],
                title=t["title"],
                description=t["description"],
                required_skills=t["required_skills"],
                seniority_level=t["seniority_level"],
                estimated_workload_days=t["estimated_workload_days"],
            )
            for t in project_data["tasks"]
        ]

        project = Project(
            project_id=f"proj_{project_data['project_name'].lower().replace(' ', '_')}",
            name=project_data["project_name"],
            description=project_data["project_description"],
            tasks=tasks,
            budget_max=project_data.get("budget_max"),
            team_size_max=project_data.get("team_size_max"),
        )

        recommendations = await recommend_team_for_project(project)

        # ── Sauvegarder le contexte en mémoire utilisateur ───────────
        try:
            from app.services.ai_memory_service import save_project_context
            top_candidates = [
                f"{m.candidate_name} ({int(sum(a.confidence_score for a in recommendations.assignments if a.candidate_id == m.candidate_id) / max(len([a for a in recommendations.assignments if a.candidate_id == m.candidate_id]), 1) * 100)}%)"
                for m in recommendations.team_members[:5]
            ]
            task_names = [t.title for t in tasks[:6]]
            import asyncio
            asyncio.create_task(save_project_context(
                user_id=user_id,
                project_name=project_data["project_name"],
                top_candidates=top_candidates,
                tasks=task_names,
                conversation_id=request.conversation_id or "",
            ))
        except Exception as exc:
            logger.warning("[API] Impossible de sauvegarder le contexte mémoire: %s", exc)

        message = (
            f"J'ai analysé votre projet **{project_data['project_name']}**.\n\n"
            f"**{len(project_data['tasks'])} tâches** identifiées — "
            f"**{len(recommendations.team_members)} candidats** recommandés.\n\n"
        )
        if recommendations.warnings:
            message += f"⚠️ **Alertes:** {', '.join(recommendations.warnings)}"

        return TextAnalysisResponse(
            success=True,
            message=message,
            response_type="project",
            recommendations=recommendations,
            extracted_project=project_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[API] Erreur analyze-text: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'analyse: {str(e)}",
        )
