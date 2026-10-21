# 🧑‍💼 HR System — Plateforme de recrutement assistée par IA

Application web qui automatise l'analyse des CV, le matching candidats / offres et la composition d'équipes projet grâce à un pipeline **RAG → DCI → LLM**.

`Python 3.10` · `FastAPI` · `React 18` · `PostgreSQL 15` · `Milvus` · `Redis` · `Docker`

## 📖 Description

HR System aide les équipes RH à gagner du temps sur trois tâches :

1. **Centraliser les CV** : import, extraction automatique des compétences et des expériences, indexation vectorielle.
2. **Trouver les bons profils** : le recruteur décrit une offre ou un projet avec ses tâches, et le système recommande les meilleurs candidats avec une explication.
3. **Piloter le recrutement** : suivi du pipeline, planification des entretiens, emails automatiques et tableau de bord.

## ✨ Fonctionnalités

- 📄 **Analyse de CV** (PDF, Word, OCR)
- 🎯 **Matching candidats / offres** avec score et justification
- 👥 **Recommandation d'équipe projet** à partir d'un projet et de ses tâches
- 💼 **Offres d'emploi** : création et amélioration de la description par IA
- 📈 **Pipeline de recrutement** et 📅 **planification des entretiens**
- 📧 **Emails automatiques** aux candidats
- 🤖 **Assistant IA** pour interroger la base de candidats
- 📊 **Tableau de bord** et mises à jour en temps réel (WebSocket)
- 🔐 **SSO Azure AD** et 🌍 interface FR / EN

## 🏗️ Architecture du pipeline IA

### Déroulement d'une analyse

| Étape | Description |
| --- | --- |
| 1️⃣ Saisie | L'utilisateur saisit un projet et ses tâches dans l'interface React |
| 2️⃣ Requête | L'interface envoie `POST /projects/analyze` au backend FastAPI |
| 3️⃣ Pipeline | Le backend déclenche le pipeline **RAG → DCI → LLM** |
| 4️⃣ Recommandations | Le résultat est renvoyé au backend |
| 5️⃣ Temps réel | La progression est diffusée à l'interface par WebSocket |
| 6️⃣ Réponse | Le backend renvoie la réponse JSON |
| 7️⃣ Affichage | L'équipe recommandée est affichée à l'utilisateur |

### Les trois étapes du pipeline

- 🔎 **RAG (recherche vectorielle)** : la tâche est transformée en embedding et comparée aux CV indexés dans Milvus. On retient les **50 meilleurs candidats par tâche**.
- 🧬 **DCI (analyse approfondie)** : les candidats retenus sont enrichis avec leurs métadonnées (PostgreSQL), leurs extraits de CV (Milvus) et un cache de résultats (Redis). On garde les **10 meilleurs profils enrichis par tâche**.
- 🧠 **LLM (optimisation d'équipe)** : un modèle de langage, via un proxy LiteLLM, compose l'équipe finale et rédige les explications des choix.

### Composants

| Bloc | Rôle | Technologie |
| --- | --- | --- |
| 🖥️ Client | Interface utilisateur | React |
| 🔌 Backend API | REST et WebSocket | FastAPI |
| 🗄️ Données | Métadonnées candidats | PostgreSQL |
| 🧲 Données | Embeddings des CV | Milvus |
| ⚡ Données | Cache et file de tâches | Redis (ARQ) |
| 🌐 Services externes | Embeddings et raisonnement | Modèle d'embeddings, proxy LiteLLM (GPT-4o / Claude) |

## 🛠️ Stack technique

| Couche | Technologies |
| --- | --- |
| 🐍 Backend | Python, FastAPI, SQLAlchemy, Alembic |
| 🧠 IA / RAG | LangGraph, LiteLLM, Milvus |
| 🗄️ Données | PostgreSQL, Redis, ARQ |
| 🎨 Frontend | React, TypeScript, Vite, Tailwind CSS |
| 🚢 DevOps | Docker, GitLab CI, Prometheus, Grafana |

## 📂 Structure

```
├── app/            # Backend (api, services, workers, infrastructure)
├── alembic/        # Migrations
├── frontend/       # Application React
├── monitoring/     # Prometheus et Grafana
├── tests/          # Tests Pytest
├── cypress/        # Tests end-to-end
└── main.py         # Point d'entrée FastAPI
```

## 🚀 Démarrage rapide

**Prérequis** : Python 3.10+, Node.js 20+, Docker.

```bash
# 1. Cloner
git clone https://github.com/1hi12/hr_system.git
cd hr_system

# 2. Services (PostgreSQL, Redis, Milvus)
docker compose up -d

# 3. Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000

# 4. Frontend (dans un autre terminal)
cd frontend
npm install --legacy-peer-deps
npm run dev
```

- Application : http://localhost:5173
- API et Swagger : http://localhost:8000/docs

## ⚙️ Configuration

Créez un fichier `.env` à la racine :

```env
LITELLM_API_KEY=votre_cle
LITELLM_BASE_URL=https://votre-proxy-litellm
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/cv_db
REDIS_URL=redis://localhost:6379
AZURE_TENANT_ID=votre_tenant_id
AZURE_CLIENT_ID=votre_client_id
SMTP_HOST=smtp.exemple.com
SMTP_USER=votre_utilisateur
SMTP_PASSWORD=votre_mot_de_passe
```

> ⚠️ Ne publiez jamais le fichier `.env` sur GitHub.

## 🧪 Tests

```bash
pytest              # Backend
npx cypress run     # End-to-end
```

## 🔄 CI/CD

Le pipeline CI/CD orchestre trois environnements : **DEV → UAT → PROD**.

| Environnement | Étapes |
| --- | --- |
| 🧑‍💻 **DEV** | Push Git, build Docker automatique, tests unitaires (pytest), déploiement auto |
| 🧪 **UAT** | Tests d'intégration (Cypress), tests de performance (K6), déploiement validé |
| 🚀 **PROD** | Déploiement, monitoring 24/7 (Prometheus, Grafana), rollback automatique en cas d'erreur |

Les images Docker sont stockées sur Docker Hub, et un retour (feedback, incidents, hotfix) alimente l'environnement DEV.

## 📊 Monitoring

Supervision applicative avec Prometheus et Grafana : services actifs, latence, requêtes par endpoint, CPU, mémoire et état des workers.

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

## 👤 Auteur

Projet développé par [1hi12](https://github.com/1hi12).
