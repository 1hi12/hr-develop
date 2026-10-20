"""
Skill normalization — maps common aliases and variants to canonical names.
Applied at ingestion time so all CVs use the same skill vocabulary.
"""

from __future__ import annotations

_ALIASES: dict[str, str] = {
    # JavaScript ecosystem
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "reactjs": "React",
    "react.js": "React",
    "react js": "React",
    "vuejs": "Vue.js",
    "vue": "Vue.js",
    "vue js": "Vue.js",
    "angularjs": "Angular",
    "angular js": "Angular",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "node js": "Node.js",
    "node": "Node.js",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "nuxtjs": "Nuxt.js",
    "nuxt.js": "Nuxt.js",
    "expressjs": "Express.js",
    "express.js": "Express.js",
    # Python ecosystem
    "py": "Python",
    "python3": "Python",
    "drf": "Django REST Framework",
    "django rest framework": "Django REST Framework",
    "django-rest-framework": "Django REST Framework",
    "fastapi": "FastAPI",
    "flask": "Flask",
    # Databases
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "pg": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "mysql": "MySQL",
    "mssql": "SQL Server",
    "ms sql": "SQL Server",
    "microsoft sql server": "SQL Server",
    "elastic": "Elasticsearch",
    "es": "Elasticsearch",
    # Cloud & DevOps
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    "kubernetes": "Kubernetes",
    "tf": "Terraform",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "aws": "AWS",
    "amazon web services": "AWS",
    "azure": "Microsoft Azure",
    "ms azure": "Microsoft Azure",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "ci cd": "CI/CD",
    "github actions": "GitHub Actions",
    "gitlab ci": "GitLab CI",
    "gitlab-ci": "GitLab CI",
    # ML/AI
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "cv": "Computer Vision",
    "computer vision": "Computer Vision",
    "tf": "TensorFlow",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "sklearn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "scikit-learn": "Scikit-learn",
    # APIs
    "rest": "REST API",
    "restful": "REST API",
    "rest api": "REST API",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    # Other
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "jira": "Jira",
    "confluence": "Confluence",
    "docker": "Docker",
    "linux": "Linux",
    "bash": "Bash/Shell",
    "shell": "Bash/Shell",
    "shell scripting": "Bash/Shell",
    "java": "Java",
    "spring": "Spring Boot",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    "c#": "C#",
    "csharp": "C#",
    "dotnet": ".NET",
    ".net": ".NET",
    "asp.net": "ASP.NET",
    "golang": "Go",
    "go lang": "Go",
    "ruby on rails": "Ruby on Rails",
    "ror": "Ruby on Rails",
    "redis": "Redis",
    "kafka": "Apache Kafka",
    "apache kafka": "Apache Kafka",
    "rabbitmq": "RabbitMQ",
    "celery": "Celery",
    "nginx": "Nginx",
    "ansible": "Ansible",
    "jenkins": "Jenkins",
    "sonarqube": "SonarQube",
}


def normalize_skill(skill: str) -> str:
    """Return canonical skill name for a given input string."""
    key = skill.strip().lower()
    return _ALIASES.get(key, skill.strip())


def normalize_skills(skills: list[str]) -> list[str]:
    """Normalize and deduplicate a list of skill strings."""
    seen: set[str] = set()
    result: list[str] = []
    for s in skills:
        if not s or not s.strip():
            continue
        normalized = normalize_skill(s)
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def skill_overlap_score(candidate_skills: list[str], required_skills: list[str]) -> float:
    """
    Compute what fraction of required skills the candidate has.
    Returns a float 0.0–1.0.
    Matching is case-insensitive and uses normalization.
    """
    if not required_skills:
        return 1.0
    if not candidate_skills:
        return 0.0

    normalized_candidate = {normalize_skill(s).lower() for s in candidate_skills}
    matched = sum(
        1 for rs in required_skills
        if normalize_skill(rs).lower() in normalized_candidate
    )
    return round(matched / len(required_skills), 4)
