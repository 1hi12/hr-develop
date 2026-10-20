"""
Service pour analyser du texte libre et extraire les informations d'un projet.
Utilise le Multi-LLM pour parser la description du projet.
"""

import json
import re
from typing import Dict, List, Any
from app.services.multi_llm_service import get_llm_service
from app.core.entities.project import Project, ProjectTask


class ProjectTextAnalyzer:
    """Analyse un texte libre et extrait les tâches d'un projet."""
    
    def __init__(self):
        self.llm_service = get_llm_service()
    
    async def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        Analyse le texte et extrait les informations du projet.
        
        Args:
            text: Description libre du projet par l'utilisateur
            
        Returns:
            Dict avec project_name, project_description, tasks, budget_max, team_size_max
        """
        
        prompt = self._build_extraction_prompt(text)
        
        try:
            result = await self.llm_service.generate(prompt)
            response_text = result["content"]
            provider = result["provider"]
            
            # Nettoyer la réponse (enlever markdown)
            clean_json = self._extract_json(response_text)
            
            # Parser le JSON
            project_data = json.loads(clean_json)
            
            # Valider et normaliser
            normalized = self._normalize_project_data(project_data)
            
            return {
                "success": True,
                "project_data": normalized,
                "llm_provider": provider
            }
            
        except Exception as e:
            raise Exception(f"Erreur lors de l'analyse du texte: {str(e)}")
    
    def _build_extraction_prompt(self, text: str) -> str:
        """Construit le prompt d'extraction."""
        
        return f"""Tu es un assistant IA spécialisé en gestion de projets RH. Analyse le texte suivant et extrais les informations du projet.

TEXTE DE L'UTILISATEUR:
{text}

INSTRUCTIONS:
1. Identifie le nom du projet (ou génère un nom basé sur la description)
2. Extrais la description générale du projet
3. Liste toutes les tâches mentionnées avec:
   - Un identifiant unique (task1, task2, etc.)
   - Un titre clair
   - Une description détaillée
   - Les compétences requises (technologies, langages, outils) — garde les noms techniques tels quels (ex: React, Python, Docker)
   - Le niveau de séniorité (junior, mid, senior, expert)
   - La charge de travail en jours (estime si non précisé)
4. Identifie le budget maximum (si mentionné)
5. Identifie la taille max de l'équipe (si mentionné)

RÈGLE ABSOLUE DE LANGUE:
- Peu importe la langue du texte d'entrée (anglais, arabe, etc.), tu dois TOUJOURS rédiger project_name, project_description, task title et task description EN FRANÇAIS.
- Les required_skills restent dans leur forme technique originale (React, Node.js, Docker, etc.)
- Exemples de traduction: "Create REST API" → "Créer l'API REST", "Deploy on cloud" → "Déploiement cloud"

RÉPONDS UNIQUEMENT AVEC UN JSON VALIDE (pas de texte avant ou après):
{{
  "project_name": "string (EN FRANÇAIS)",
  "project_description": "string (EN FRANÇAIS)",
  "tasks": [
    {{
      "task_id": "task1",
      "title": "string (EN FRANÇAIS)",
      "description": "string (EN FRANÇAIS)",
      "required_skills": ["skill1", "skill2"],
      "seniority_level": "mid",
      "estimated_workload_days": 10
    }}
  ],
  "budget_max": 50000,
  "team_size_max": 5
}}

ATTENTION:
- Si le budget n'est pas mentionné, mets null
- Si la taille d'équipe n'est pas mentionnée, mets null
- Pour seniority_level, utilise: "intern", "junior", "mid", "senior", ou "expert"
- Extrais toutes les technologies mentionnées comme required_skills

JSON:"""
    
    def _extract_json(self, text: str) -> str:
        """Extrait le JSON d'une réponse LLM (enlève markdown, etc.)"""
        
        # Chercher du JSON entre ```json et ``` ou ``` et ```
        json_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(json_pattern, text, re.DOTALL)
        
        if match:
            return match.group(1)
        
        # Sinon chercher juste des accolades
        json_pattern2 = r"(\{.*\})"
        match2 = re.search(json_pattern2, text, re.DOTALL)
        
        if match2:
            return match2.group(1)
        
        return text.strip()
    
    def _normalize_project_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise et valide les données extraites."""
        
        # Validation des tâches
        tasks = data.get("tasks", [])
        normalized_tasks = []
        
        for i, task in enumerate(tasks):
            normalized_task = {
                "task_id": task.get("task_id", f"task{i+1}"),
                "title": task.get("title", f"Tâche {i+1}"),
                "description": task.get("description", ""),
                "required_skills": task.get("required_skills", []),
                "seniority_level": task.get("seniority_level", "mid"),
                "estimated_workload_days": int(task.get("estimated_workload_days", 5))
            }
            normalized_tasks.append(normalized_task)
        
        return {
            "project_name": data.get("project_name", "Projet sans nom"),
            "project_description": data.get("project_description", ""),
            "tasks": normalized_tasks,
            "budget_max": data.get("budget_max"),
            "team_size_max": data.get("team_size_max")
        }


# Singleton
_analyzer_instance = None

def get_text_analyzer() -> ProjectTextAnalyzer:
    """Retourne une instance singleton du text analyzer."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ProjectTextAnalyzer()
    return _analyzer_instance
