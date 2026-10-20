"""
project_team_recommender.py
============================
Pipeline RAG → DCI → LLM pour recommandation d'équipes projet

Architecture:
  1. RAG  : Recherche vectorielle rapide (top-50 candidats/tâche)
  2. DCI  : Analyse approfondie (top-10 enrichis/tâche)
  3. LLM  : Raisonnement + optimisation finale
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any, Optional

from app.config.settings import settings
from app.core.entities.project import (
    ProjectTask,
    Project,
    TaskAssignment,
    CandidateInTeam,
    TeamComposition
)
from app.services.multi_llm_service import get_llm_service
from app.services.retrieval_service import fetch_selected_cvs, vector_search_by_embedding
from app.services.ranking_service import _normalize_cv_texts
from app.agent.tools.cv_extractor.embedder import embed_single_query
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.database.models import CandidateModel
from sqlalchemy import select

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# HELPER : Récupération des noms de candidats
# ═══════════════════════════════════════════════════════════════════

def _name_from_filename(filename: str) -> str:
    """Extrait un nom lisible depuis un nom de fichier CV.
    Ex: 'John_Doe_CV.pdf' → 'John Doe', 'CV_Ahmed_Ben_Ali.pdf' → 'Ahmed Ben Ali'
    """
    import os
    stem = os.path.splitext(filename)[0]
    # Supprimer mots parasites courants
    stem = re.sub(r'\b(CV|cv|Resume|resume|Curriculum|Vitae|vitae)\b', '', stem)
    # Remplacer séparateurs par espace
    stem = re.sub(r'[_\-\.]+', ' ', stem).strip()
    # Supprimer chiffres en début/fin
    stem = re.sub(r'^[\d\s]+|[\d\s]+$', '', stem).strip()
    words = [w for w in stem.split() if len(w) >= 2]
    if len(words) >= 2:
        return ' '.join(w.capitalize() for w in words)
    if len(words) == 1 and len(words[0]) >= 3:
        return words[0].capitalize()
    return ""


def _name_from_cv_text(cv_text: str) -> str:
    """Cherche un nom dans les premières lignes du texte brut d'un CV."""
    lines = [ln.strip() for ln in cv_text.split('\n') if ln.strip()]
    for line in lines[:8]:
        # Ignorer lignes avec email, URL, téléphone, dates
        if re.search(r'[@/\\]|https?:|^\d|\d{6,}', line):
            continue
        if len(line) > 60:
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and re.match(r'^[A-Za-zÀ-ÖØ-öø-ÿ\s\-]+$', line):
            return line.title()
    return ""


async def fetch_candidate_names(candidate_ids: list[str]) -> dict[str, str]:
    """
    Récupère les noms complets des candidats depuis PostgreSQL.
    Cascade de fallbacks: full_name → filename → cv_raw_text → ID court
    """
    if not candidate_ids:
        return {}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                CandidateModel.candidate_id,
                CandidateModel.full_name,
                CandidateModel.filename,
                CandidateModel.cv_raw_text,
            ).where(CandidateModel.candidate_id.in_(candidate_ids))
        )
        rows = result.all()

    names_map: dict[str, str] = {}
    for cid, full_name, filename, cv_raw_text in rows:
        # Priorité 1 : full_name direct
        if full_name and full_name.strip():
            names_map[cid] = full_name.strip()
            continue
        # Priorité 2 : extraire depuis le nom de fichier
        if filename:
            extracted = _name_from_filename(filename)
            if extracted:
                names_map[cid] = extracted
                continue
        # Priorité 3 : extraire depuis le texte brut du CV
        if cv_raw_text:
            extracted = _name_from_cv_text(cv_raw_text)
            if extracted:
                names_map[cid] = extracted
                continue
        # Candidat en base mais sans nom exploitable → fallback minimal
        names_map[cid] = f"Candidat {cid[:8]}"

    # IMPORTANT : les candidats ABSENTS de PostgreSQL ne sont intentionnellement
    # PAS ajoutés au dict → ils seront filtrés dans dci_enrich_candidates.
    # Cela corrige l'incohérence Milvus/Postgres (candidats fantômes).
    logger.info(f"[fetch_names] {len(names_map)}/{len(candidate_ids)} candidats trouvés dans PostgreSQL")
    return names_map


# ═══════════════════════════════════════════════════════════════════
# ÉTAPE 1 — RAG : Recherche vectorielle rapide
# ═══════════════════════════════════════════════════════════════════

async def rag_search_candidates_for_task(
    task: ProjectTask,
    top_k: int = 50
) -> list[dict[str, Any]]:
    """
    Étape 1: RAG - Recherche vectorielle rapide
    
    Returns:
        Liste de {candidate_id, similarity_score, chunks}
    """
    logger.info(f"[RAG] Recherche pour tâche: {task.title}")
    
    # 1. Construire la query enrichie
    query_text = f"""
Tâche: {task.title}
Description: {task.description}
Compétences requises: {', '.join(task.required_skills)}
Séniorité: {task.seniority_level}
Charge: {task.estimated_workload_days} jours
""".strip()
    
    # 2. Générer embedding
    query_embedding = await embed_single_query(query_text)
    
    # 3. Recherche vectorielle dans Milvus
    raw_chunks = await vector_search_by_embedding(
        query_embedding=query_embedding,
        top_k=top_k
    )
    
    # 4. Regrouper par candidate_id et calculer score moyen
    candidates_data = defaultdict(lambda: {"chunks": [], "scores": []})
    
    for chunk in raw_chunks:
        cid = chunk.get("candidate_id") or chunk.get("id")
        if not cid:
            continue
        
        score = chunk.get("distance", 0.0)
        # Convertir distance en similarité (plus proche = meilleur)
        similarity = 1.0 - score if score < 1.0 else score
        
        candidates_data[cid]["chunks"].append(chunk)
        candidates_data[cid]["scores"].append(similarity)
    
    # 5. Top-N candidats avec meilleur score moyen
    results = []
    for cid, data in candidates_data.items():
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0.0
        results.append({
            "candidate_id": str(cid),
            "similarity_score": avg_score,
            "chunks": data["chunks"][:5],  # Garder top-5 chunks
            "stage": "RAG"
        })
    
    # 5b. Récupérer aussi les scores bruts pour usage DCI (max score vs moyenne)
    for r in results:
        cid = r["candidate_id"]
        r["scores"] = candidates_data[cid]["scores"]

    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    logger.info(f"[RAG] ✅ {len(results)} candidats trouvés pour {task.title}")

    return results[:20]  # Top-20 pour DCI


# ═══════════════════════════════════════════════════════════════════
# ÉTAPE 2 — DCI : Deep Context Inspection
# ═══════════════════════════════════════════════════════════════════

async def dci_enrich_candidates(
    task: ProjectTask,
    rag_candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Étape 2: DCI - Analyse approfondie des CVs complets
    
    Returns:
        Liste de candidats enrichis avec métadata complète
    """
    logger.info(f"[DCI] Analyse approfondie de {len(rag_candidates)} candidats pour {task.title}")

    # ── Étape 0 : récupérer les noms pour TOUS les candidats RAG ──────────
    # (pas seulement les 10 premiers) pour filtrer les candidats fantômes
    all_ids = [r["candidate_id"] for r in rag_candidates]
    candidate_names = await fetch_candidate_names(all_ids)

    # Filtrer : ne garder QUE les candidats présents dans PostgreSQL
    valid_rag = [r for r in rag_candidates if r["candidate_id"] in candidate_names]
    if not valid_rag:
        logger.warning(f"[DCI] ⚠️ Aucun candidat PostgreSQL valide pour {task.title}")
        return []

    logger.info(f"[DCI] {len(valid_rag)}/{len(rag_candidates)} candidats valides (PostgreSQL)")

    enriched = []

    for rag_result in valid_rag[:10]:  # Top-10 valides pour DCI
        cid = rag_result["candidate_id"]
        
        # Reconstituer le CV complet depuis les chunks
        cv_texts = _normalize_cv_texts(rag_result["chunks"])
        full_cv_text = cv_texts.get(cid, "")
        
        if not full_cv_text:
            # Fallback: concaténer les textes des chunks
            full_cv_text = "\n\n".join([
                chunk.get("text", "") for chunk in rag_result["chunks"]
            ])
        
        # Extraire les compétences des chunks
        skills = []
        for chunk in rag_result["chunks"]:
            skills_json = chunk.get("skills_json")
            if skills_json:
                try:
                    if isinstance(skills_json, str):
                        skills_data = json.loads(skills_json)
                    else:
                        skills_data = skills_json
                    if isinstance(skills_data, list):
                        skills.extend(skills_data)
                except:
                    pass
        
        skills = list(set(skills))[:10]  # Unique + limiter à 10
        
        # Matching compétences — comparaison insensible à la casse + correspondance partielle
        task_skills_lower = [s.lower().strip() for s in task.required_skills]
        cand_skills_lower = [s.lower().strip() for s in skills]
        matched_skills = sum(
            1 for ts in task_skills_lower
            if any(ts in cs or cs in ts for cs in cand_skills_lower)
        )
        skill_coverage = matched_skills / len(task.required_skills) if task.required_skills else 0.0

        # Score composite: 60% similarité vectorielle + 40% couverture compétences
        # Utiliser le meilleur score RAG (pas la moyenne) pour éviter la dilution
        best_rag_score = max(rag_result["scores"]) if rag_result.get("scores") else rag_result["similarity_score"]
        matching_score = (best_rag_score * 0.6 + skill_coverage * 0.4) * 100

        # Estimer les années d'expérience — regex sur le texte CV
        years_exp = 3  # Défaut
        exp_match = re.search(r'(\d+)\s*(?:ans?\s*d\'expérience|ans?\s+d\'exp|years?\s+of\s+exp|years?\s+exp)',
                               full_cv_text, re.IGNORECASE)
        if exp_match:
            years_exp = min(int(exp_match.group(1)), 30)
        else:
            text_lower = full_cv_text.lower()
            if any(kw in text_lower for kw in ['senior', 'lead', 'principal', 'staff', 'architect', 'tech lead']):
                years_exp = 7
            elif any(kw in text_lower for kw in ['confirmé', 'confirmed', 'intermediate', 'mid-level']):
                years_exp = 4
            elif 'junior' in text_lower:
                years_exp = 2
            else:
                # Déduire depuis les années présentes dans le CV
                year_matches = re.findall(r'\b(200[0-9]|201[0-9]|202[0-5])\b', full_cv_text)
                if year_matches:
                    years = [int(y) for y in year_matches]
                    span = max(years) - min(years)
                    if span > 0:
                        years_exp = min(span, 20)
        
        enriched.append({
            "candidate_id": cid,
            "name": candidate_names[cid],  # garanti présent (filtré ci-dessus)
            "rag_score": rag_result["similarity_score"],
            "matching_score": matching_score,
            "skill_coverage": skill_coverage,
            "full_cv_text": full_cv_text[:2000],  # Limiter la taille
            "metadata": {
                "skills": skills,
                "years_experience": years_exp,
            },
            "stage": "DCI"
        })
    
    # Trier par matching_score
    enriched.sort(key=lambda x: x["matching_score"], reverse=True)
    logger.info(f"[DCI] ✅ {len(enriched)} candidats enrichis")
    
    return enriched


# ═══════════════════════════════════════════════════════════════════
# ÉTAPE 3 — LLM : Raisonnement et optimisation
# ═══════════════════════════════════════════════════════════════════

def _build_optimization_prompt(
    project: Project,
    tasks: list[ProjectTask],
    candidates_per_task: dict[str, list[dict[str, Any]]]
) -> str:
    """Construit le prompt pour le LLM"""
    
    prompt = f"""# PROJET À COMPOSER

## Description
{project.description}

## Contraintes
- Budget maximum: {project.budget_max if project.budget_max else 'Non spécifié'}€
- Deadline: {project.deadline if project.deadline else 'Non spécifié'}
- Taille équipe max: {project.team_size_max if project.team_size_max else 'Non spécifié'}

## TÂCHES ET CANDIDATS

"""
    
    for task in tasks:
        prompt += f"""
### Tâche: {task.title}
- Description: {task.description}
- Compétences: {', '.join(task.required_skills)}
- Séniorité requise: {task.seniority_level}
- Charge: {task.estimated_workload_days} jours

**Top candidats:**
"""
        
        candidates = candidates_per_task.get(task.task_id, [])[:5]
        for i, cand in enumerate(candidates, 1):
            cv_excerpt = cand.get('full_cv_text', '')[:400].replace('\n', ' ').strip()
            prompt += f"""
{i}. {cand['name']} (ID: {cand['candidate_id']})
   - Score matching: {cand['matching_score']:.1f}/100
   - Couverture skills: {cand['skill_coverage']*100:.0f}%
   - Expérience: {cand['metadata']['years_experience']} ans
   - Compétences: {', '.join(cand['metadata']['skills'][:7])}
   - Extrait CV: {cv_excerpt[:300] if cv_excerpt else 'N/A'}
"""
    
    prompt += """

## TA MISSION

1. Analyser TOUS les candidats de TOUTES les tâches
2. Identifier les meilleures assignations en optimisant:
   - Qualité du match (favoriser score > 70)
   - Complémentarité (FAVORISER des candidats différents pour chaque tâche)
   - Diversité d'équipe (assigner plusieurs personnes plutôt qu'une seule)
   - Un candidat peut faire plusieurs tâches SEULEMENT si les autres candidats sont vraiment insuffisants
3. Détecter les risques/warnings
4. Proposer des alternatives si nécessaire

IMPORTANT: Pour un projet avec N tâches, essaie d'assigner N candidats différents si leurs scores sont > 60.
Un candidat polyvalent ne doit pas monopoliser toutes les tâches sauf nécessité absolue.

Réponds UNIQUEMENT en JSON valide avec cette structure exacte:
{
    "assignments": [
        {
            "task_id": "...",
            "task_title": "...",
            "candidate_id": "...",
            "candidate_name": "...",
            "confidence_score": 0.85,
            "reasoning": "Explication courte"
        }
    ],
    "team_members": [
        {
            "candidate_id": "...",
            "candidate_name": "...",
            "assigned_tasks": ["task1"],
            "total_workload_days": 10,
            "estimated_cost": 12000
        }
    ],
    "warnings": ["Liste des warnings"],
    "overall_recommendation": "Résumé global"
}
"""
    
    return prompt


async def llm_optimize_team(
    project: Project,
    tasks: list[ProjectTask],
    candidates_per_task: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """
    Étape 3: LLM - Raisonnement final et optimisation d'équipe
    """
    logger.info(f"[LLM] Optimisation de l'équipe pour {len(tasks)} tâches")
    
    prompt = _build_optimization_prompt(project, tasks, candidates_per_task)
    
    system_prompt = """Tu es un expert RH et chef de projet.
Ta mission: analyser les candidats proposés pour chaque tâche et composer l'équipe optimale.
Tiens compte de la qualité du match, la complémentarité des profils, les contraintes de budget/délais.
Réponds UNIQUEMENT en JSON valide, sans markdown, sans commentaires.
LANGUE: Tous les textes dans le JSON (reasoning, overall_recommendation, warnings) doivent être rédigés EN FRANÇAIS, quelle que soit la langue des données d'entrée."""
    
    llm_service = get_llm_service()
    
    try:
        response = await llm_service.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=3000
        )
        
        # Parser le JSON
        content = response["content"]
        
        # Nettoyer le contenu (enlever markdown si présent)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        result["_llm_provider"] = response["provider"]
        
        logger.info(f"[LLM] ✅ Équipe optimisée par {response['provider']}")
        
        return result
        
    except Exception as e:
        logger.error(f"[LLM] Erreur lors de l'optimisation: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════
# ORCHESTRATEUR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

async def recommend_team_for_project(
    project: Project
) -> TeamComposition:
    """
    Pipeline complet RAG → DCI → LLM
    
    Args:
        project: Projet avec tâches et contraintes
    
    Returns:
        TeamComposition avec recommandations
    """
    start_time = time.time()
    
    logger.info(f"🚀 Démarrage pipeline RAG→DCI→LLM pour projet: {project.name}")
    logger.info(f"   Tâches: {len(project.tasks)}")
    
    # ──────────────────────────────────────────────────────────────────
    # ÉTAPE 1: RAG - Recherche vectorielle rapide
    # ──────────────────────────────────────────────────────────────────
    
    rag_results_per_task = {}
    
    for task in project.tasks:
        rag_results = await rag_search_candidates_for_task(task, top_k=50)
        rag_results_per_task[task.task_id] = rag_results
    
    logger.info(f"✅ [RAG] Terminé pour {len(project.tasks)} tâches")
    
    # ──────────────────────────────────────────────────────────────────
    # ÉTAPE 2: DCI - Analyse approfondie
    # ──────────────────────────────────────────────────────────────────
    
    dci_results_per_task = {}
    
    for task in project.tasks:
        rag_candidates = rag_results_per_task[task.task_id]
        dci_enriched = await dci_enrich_candidates(task, rag_candidates)
        dci_results_per_task[task.task_id] = dci_enriched
    
    logger.info(f"✅ [DCI] Terminé pour {len(project.tasks)} tâches")
    
    # ──────────────────────────────────────────────────────────────────
    # ÉTAPE 3: LLM - Optimisation finale
    # ──────────────────────────────────────────────────────────────────
    
    llm_result = await llm_optimize_team(
        project=project,
        tasks=project.tasks,
        candidates_per_task=dci_results_per_task
    )
    
    logger.info(f"✅ [LLM] Pipeline complet terminé")
    
    # Construire la réponse finale
    processing_time_ms = int((time.time() - start_time) * 1000)
    
    # Créer un mapping candidat → metadata depuis DCI
    candidate_metadata = {}
    for task_id, dci_candidates in dci_results_per_task.items():
        for cand in dci_candidates:
            cid = cand["candidate_id"]
            if cid not in candidate_metadata:
                candidate_metadata[cid] = {
                    "name": cand["name"],
                    "skills": cand["metadata"]["skills"],
                    "years_experience": cand["metadata"]["years_experience"]
                }
    
    # Index préfixe UUID (8 chars) → full UUID pour récupération rapide
    _prefix_to_fullid: dict[str, str] = {cid[:8]: cid for cid in candidate_metadata}

    def _resolve_candidate(raw_cid: str) -> tuple[str, dict]:
        """Retourne (full_candidate_id, metadata) en gérant IDs tronqués."""
        meta = candidate_metadata.get(raw_cid, {})
        if meta:
            return raw_cid, meta
        # Essai par préfixe (LLM a renvoyé les 8 premiers chars du UUID)
        full_cid = _prefix_to_fullid.get(raw_cid[:8] if len(raw_cid) >= 8 else raw_cid)
        if full_cid:
            return full_cid, candidate_metadata[full_cid]
        return raw_cid, {}

    # ── Construction des assignments avec noms depuis candidate_metadata ──
    assignments = []
    for a in llm_result.get("assignments", []):
        raw_cid = a.get("candidate_id", "")
        cid, metadata = _resolve_candidate(raw_cid)

        # Ignorer les candidats que le LLM aurait inventés ou qui ne sont pas dans PostgreSQL
        if not metadata:
            logger.warning(f"[LLM] Assignment ignoré — candidat inconnu: {raw_cid}")
            continue

        # Nom depuis candidate_metadata (source PostgreSQL, fiable à 100%)
        name = metadata.get("name") or a.get("candidate_name") or "Candidat inconnu"
        assignments.append(TaskAssignment(
            task_id=a.get("task_id", ""),
            task_title=a.get("task_title", ""),
            candidate_id=cid,   # UUID complet résolu (pas l'ID tronqué du LLM)
            candidate_name=name,
            confidence_score=a.get("confidence_score", 0.0),
            matching_score=a.get("matching_score", a.get("confidence_score", 0.0) * 100),
            reasoning=a.get("reasoning", ""),
            is_primary=a.get("is_primary", True)
        ))

    # ── Construction des team_members depuis assignments (source fiable) ──
    # On NE PAS utiliser llm_result["team_members"] comme source des IDs/noms
    # car le LLM génère souvent cette section avec des IDs incorrects/tronqués.
    # Les assignments sont plus fiables: le LLM copie les IDs depuis le prompt.
    assignments_by_candidate: dict[str, list] = defaultdict(list)
    for a in assignments:
        if a.candidate_id:
            assignments_by_candidate[a.candidate_id].append(a)

    # Index LLM team_members par nom (pour récupérer workload/coût uniquement)
    llm_member_by_name: dict[str, dict] = {}
    for m in llm_result.get("team_members", []):
        n = m.get("candidate_name", "").lower().strip()
        if n:
            llm_member_by_name[n] = m

    team_members = []
    for cid, cand_assignments in assignments_by_candidate.items():
        metadata = candidate_metadata.get(cid, {})
        final_name = metadata.get("name") or cand_assignments[0].candidate_name

        # Retrouver données LLM (workload/coût) par correspondance de nom
        llm_m = llm_member_by_name.get(final_name.lower().strip(), {})

        assigned_task_ids = [a.task_id for a in cand_assignments]
        # Calculer workload depuis les tâches réelles du projet
        total_workload = sum(
            t.estimated_workload_days
            for t in project.tasks
            if t.task_id in assigned_task_ids
        )
        if not total_workload:
            total_workload = float(llm_m.get("total_workload_days", 0.0))

        team_members.append(CandidateInTeam(
            candidate_id=cid,
            candidate_name=final_name,
            assigned_tasks=assigned_task_ids,
            total_workload_days=total_workload,
            estimated_cost=llm_m.get("estimated_cost"),
            skills=metadata.get("skills", []),
            years_experience=metadata.get("years_experience", 0)
        ))
    
    return TeamComposition(
        project_id=project.project_id or "unknown",
        assignments=assignments,
        team_members=team_members,
        warnings=llm_result.get("warnings", []),
        alternatives=llm_result.get("alternatives", {}),
        overall_recommendation=llm_result.get("overall_recommendation", ""),
        processing_time_ms=processing_time_ms,
        llm_provider_used=llm_result.get("_llm_provider", "unknown"),
        mode="full"
    )
