"""
project.py
==========
Entités pour la gestion de projets et tâches pour l'AI Assistant
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProjectTask(BaseModel):
    """
    Représente une tâche dans un projet
    """
    task_id: str = Field(..., description="Identifiant unique de la tâche")
    title: str = Field(..., description="Titre de la tâche")
    description: str = Field(..., description="Description détaillée de la tâche")
    required_skills: list[str] = Field(default_factory=list, description="Compétences requises")
    seniority_level: str = Field(default="mid", description="Niveau de séniorité requis (intern, junior, mid, senior, expert)")
    estimated_workload_days: float = Field(..., description="Charge de travail estimée en jours")
    priority: int = Field(default=1, description="Priorité de la tâche (1=basse, 5=haute)")
    dependencies: list[str] = Field(default_factory=list, description="IDs des tâches dont celle-ci dépend")


class Project(BaseModel):
    """
    Représente un projet complet à analyser
    """
    project_id: Optional[str] = Field(None, description="Identifiant unique du projet")
    name: str = Field(..., description="Nom du projet")
    description: str = Field(..., description="Description détaillée du projet")
    tasks: list[ProjectTask] = Field(default_factory=list, description="Liste des tâches du projet")
    start_date: Optional[date] = Field(None, description="Date de début prévue")
    deadline: Optional[date] = Field(None, description="Date limite du projet")
    budget_max: Optional[float] = Field(None, description="Budget maximum en euros")
    team_size_max: Optional[int] = Field(None, description="Taille maximale de l'équipe")
    constraints: dict = Field(default_factory=dict, description="Contraintes supplémentaires")
    created_at: datetime = Field(default_factory=datetime.now, description="Date de création")


class TaskAssignment(BaseModel):
    """
    Représente l'assignation d'un candidat à une tâche
    """
    task_id: str = Field(..., description="ID de la tâche")
    task_title: str = Field(..., description="Titre de la tâche")
    candidate_id: str = Field(..., description="ID du candidat assigné")
    candidate_name: str = Field(..., description="Nom du candidat")
    confidence_score: float = Field(..., description="Score de confiance (0-1)")
    matching_score: float = Field(..., description="Score de matching (0-100)")
    reasoning: str = Field(..., description="Explication du choix")
    is_primary: bool = Field(default=True, description="Assignation principale ou alternative")


class CandidateInTeam(BaseModel):
    """
    Représente un candidat dans la composition d'équipe
    """
    candidate_id: str = Field(..., description="ID du candidat")
    candidate_name: str = Field(..., description="Nom du candidat")
    assigned_tasks: list[str] = Field(default_factory=list, description="IDs des tâches assignées")
    total_workload_days: float = Field(..., description="Charge totale en jours")
    estimated_cost: Optional[float] = Field(None, description="Coût estimé en euros")
    skills: list[str] = Field(default_factory=list, description="Compétences du candidat")
    years_experience: int = Field(default=0, description="Années d'expérience")


class TeamComposition(BaseModel):
    """
    Représente la composition finale d'équipe recommandée
    """
    project_id: str = Field(..., description="ID du projet")
    assignments: list[TaskAssignment] = Field(default_factory=list, description="Assignations tâche → candidat")
    team_members: list[CandidateInTeam] = Field(default_factory=list, description="Membres de l'équipe")
    warnings: list[str] = Field(default_factory=list, description="Avertissements détectés")
    alternatives: dict = Field(default_factory=dict, description="Alternatives proposées par tâche")
    overall_recommendation: str = Field(default="", description="Recommandation globale")
    processing_time_ms: int = Field(default=0, description="Temps de traitement en ms")
    llm_provider_used: str = Field(default="", description="Provider LLM utilisé")
    mode: str = Field(default="full", description="Mode d'exécution (full, degraded)")
