RERANK_PROMPT = """
Tu es un expert en recrutement. Évalue la pertinence de chaque extrait de CV pour cette offre.

OFFRE D'EMPLOI :
{job_description}

EXTRAITS DE CV :
{candidates_text}

Réponds UNIQUEMENT en JSON valide :
{{
  "rankings": [
    {{
      "index": 0,
      "score": 8.5,
      "justification": "Expérience directe en Python et FastAPI"
    }}
  ]
}}
"""

PRESENTATION_PROMPT = """
Tu es un assistant RH expert. Présente ce candidat pour un recruteur.

OFFRE D'EMPLOI :
{job_description}

PROFIL DU CANDIDAT :
{candidate_text}

COMPÉTENCES MATCHÉES : {matched_skills}
SCORE : {score_percent}%

Réponds UNIQUEMENT en JSON valide :
{{
  "profile_summary": "Résumé objectif en 2-3 phrases",
  "key_strengths": ["Point fort 1", "Point fort 2", "Point fort 3"],
  "missing_skills": ["Compétence manquante 1"],
  "recommendation": "Fortement recommandé | Recommandé | À considérer | Non recommandé"
}}
"""

GLOBAL_ADVICE_PROMPT = """
Tu es un consultant RH senior. Voici les {n} meilleurs candidats pour ce poste :

OFFRE : {job_description}

CANDIDATS :
{candidates_summary}

Donne un conseil global au recruteur en 2-3 phrases.
"""

EXTRACTION_PROMPT = """
Tu es un expert en recrutement.
Extrais les informations structurées du CV suivant au format JSON.
"""

GENERAL_INFO_PROMPT = """
Tu es un expert en recrutement.
Extrais les informations générales du CV suivant.
Réponds UNIQUEMENT en JSON valide :
{{
  "full_name": "",
  "email": "",
  "phone": "",
  "location": "",
  "linkedin": "",
  "github": "",
  "summary": "",
  "seniority_level": "junior",
  "total_years_experience": 0
}}

CV :
{cv_text}
"""

SKILLS_EXTRACTION_PROMPT = """
Tu es un expert en recrutement.
Extrais toutes les compétences du CV suivant et classe-les par catégorie.
Réponds UNIQUEMENT en JSON valide avec exactement ces clés :
{{
  "technical": ["Python", "Java"],
  "frameworks": ["FastAPI", "React"],
  "databases": ["PostgreSQL", "MongoDB"],
  "devops": ["Docker", "Kubernetes"],
  "soft_skills": ["Communication", "Leadership"],
  "languages": ["French", "English"],
  "all_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"]
}}
Note: "all_skills" doit contenir la union de technical + frameworks + databases + devops.

CV :
{cv_text}
"""

SENIORITY_PROMPT = """
Tu es un expert RH. Analyse ce CV et détermine le niveau de séniorité.
Réponds UNIQUEMENT en JSON valide :
{{
  "seniority_level": "junior | mid | senior | lead | executive",
  "total_years_experience": 0,
  "justification": "Explication courte"
}}

CV :
{cv_text}
"""
