from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    UNKNOWN = "unknown"


class Skill(BaseModel):
    name: str = Field(..., description="Nom de la compétence")
    category: Optional[str] = Field(None, description="Catégorie : backend, frontend, devops, soft, langue...")
    level: Optional[str] = Field(None, description="Niveau : débutant, intermédiaire, avancé, expert")
    years_of_experience: Optional[float] = Field(None, description="Années d'expérience estimées")


class Experience(BaseModel):
    company: Optional[str] = Field(None, description="Nom de l'entreprise")
    title: Optional[str] = Field(None, description="Intitulé du poste")
    start_date: Optional[str] = Field(None, description="Date de début (MM/YYYY ou YYYY)")
    end_date: Optional[str] = Field(None, description="Date de fin ou 'présent'")
    duration_months: Optional[int] = Field(None, description="Durée estimée en mois")
    description: Optional[str] = Field(None, description="Description des missions")
    location: Optional[str] = Field(None, description="Lieu de travail")


class Education(BaseModel):
    institution: Optional[str] = Field(None, description="Nom de l'établissement")
    degree: Optional[str] = Field(None, description="Diplôme obtenu")
    field_of_study: Optional[str] = Field(None, description="Domaine d'étude")
    graduation_year: Optional[int] = Field(None, description="Année d'obtention")


class CVExtracted(BaseModel):
    # Informations générales
    full_name: Optional[str] = Field(None, description="Nom complet du candidat")
    email: Optional[str] = Field(None, description="Adresse email")
    phone: Optional[str] = Field(None, description="Numéro de téléphone")
    location: Optional[str] = Field(None, description="Ville / Pays")
    linkedin: Optional[str] = Field(None, description="URL LinkedIn")
    github: Optional[str] = Field(None, description="URL GitHub")
    summary: Optional[str] = Field(None, description="Résumé ou objectif professionnel")
    languages: Optional[list[str]] = Field(default_factory=list, description="Langues parlées")

    # Compétences
    skills: list[Skill] = Field(default_factory=list, description="Liste des compétences extraites")

    # Expériences
    experiences: list[Experience] = Field(default_factory=list, description="Expériences professionnelles")

    # Formation
    education: list[Education] = Field(default_factory=list, description="Formations et diplômes")

    # Séniorité
    seniority_level: SeniorityLevel = Field(SeniorityLevel.UNKNOWN, description="Niveau de séniorité estimé")
    total_years_experience: Optional[float] = Field(None, description="Total années d'expérience")

    # Métadonnées
    raw_text: Optional[str] = Field(None, description="Texte brut extrait du fichier")
    extraction_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Score de confiance de l'extraction")


class JobDescription(BaseModel):
    title: Optional[str] = None
    text: str
    description: Optional[str] = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_years: Optional[float] = None
    location: Optional[str] = None
