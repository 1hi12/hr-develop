"""
fixtures.py — Calibration cases for AIScorer precision
========================================================
Each case pairs a candidate + a job with an "expected" score range and
verdict. `validated: False` means the range below is a PLACEHOLDER I
(Claude) wrote to shape the schema — it has NOT been reviewed by a human
and must not be trusted as ground truth.

To make a case count as real evidence of precision:
  1. Read the candidate/job text yourself (or a recruiter does).
  2. Decide what score range and verdict a good recruiter would actually
     give — independently of what the LLM says.
  3. Fill in `expected_score_range` and `expected_verdict`, set
     `validated: True`.

Until `validated` is True, test_precision.py SKIPS the case rather than
silently passing or failing against a made-up number.
"""

FIXTURES = [
    {
        "id": "strong-match-python-backend",
        "candidate": {
            "name": "Test Candidate A",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "REST API"],
            "seniority": "mid",
            "years_exp": 4,
            "cv_summary": (
                "Développeur backend avec 4 ans d'expérience, spécialisé en "
                "Python/FastAPI, bases PostgreSQL, API REST, déploiement Docker."
            ),
        },
        "job": {
            "title": "Développeur Backend Python",
            "description": (
                "Nous recherchons un développeur backend maîtrisant Python, FastAPI "
                "et PostgreSQL pour construire notre API REST."
            ),
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "seniority": "mid",
        },
        "expected_score_range": (75, 95),  # PLACEHOLDER
        "expected_verdict": "recommandé",  # PLACEHOLDER
        "notes": "Match évident : recouvrement exact des compétences, même séniorité, même domaine.",
        "validated": False,
    },
    {
        "id": "weak-match-different-domain",
        "candidate": {
            "name": "Test Candidate B",
            "skills": ["Comptabilité", "Excel", "SAP", "Fiscalité"],
            "seniority": "senior",
            "years_exp": 8,
            "cv_summary": (
                "Comptable senior avec 8 ans d'expérience en fiscalité d'entreprise, "
                "clôtures comptables, et outils SAP."
            ),
        },
        "job": {
            "title": "Développeur Backend Python",
            "description": (
                "Nous recherchons un développeur backend maîtrisant Python, FastAPI "
                "et PostgreSQL pour construire notre API REST."
            ),
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "seniority": "mid",
        },
        "expected_score_range": (0, 20),  # PLACEHOLDER
        "expected_verdict": "refusé",  # PLACEHOLDER
        "notes": "Domaine totalement différent (comptabilité vs dev backend) — aucun recouvrement de compétences.",
        "validated": False,
    },
    {
        "id": "adjacent-domain-partial-match",
        "candidate": {
            "name": "Test Candidate C",
            "skills": ["JavaScript", "React", "Node.js", "MongoDB"],
            "seniority": "mid",
            "years_exp": 3,
            "cv_summary": (
                "Développeur fullstack JavaScript avec 3 ans d'expérience, "
                "React côté frontend, Node.js et MongoDB côté backend."
            ),
        },
        "job": {
            "title": "Développeur Backend Python",
            "description": (
                "Nous recherchons un développeur backend maîtrisant Python, FastAPI "
                "et PostgreSQL pour construire notre API REST."
            ),
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "seniority": "mid",
        },
        "expected_score_range": (30, 55),  # PLACEHOLDER
        "expected_verdict": "à former",  # PLACEHOLDER
        "notes": "Domaine adjacent (dev backend JS vs Python) — compétences transférables mais pas de recouvrement direct.",
        "validated": False,
    },
    {
        "id": "underqualified-seniority-gap",
        "candidate": {
            "name": "Test Candidate D",
            "skills": ["Python", "Flask"],
            "seniority": "junior",
            "years_exp": 1,
            "cv_summary": (
                "Développeur junior, 1 an d'expérience en stage, bases de Python "
                "et Flask acquises en formation."
            ),
        },
        "job": {
            "title": "Lead Développeur Backend Python",
            "description": (
                "Poste senior : lead technique pour une équipe backend Python, "
                "architecture microservices, mentorat d'équipe."
            ),
            "required_skills": ["Python", "FastAPI", "PostgreSQL", "Architecture microservices"],
            "seniority": "senior",
        },
        "expected_score_range": (10, 35),  # PLACEHOLDER
        "expected_verdict": "à former",  # PLACEHOLDER
        "notes": "Même domaine que le poste mais écart de séniorité important (junior vs lead senior).",
        "validated": False,
    },
]
