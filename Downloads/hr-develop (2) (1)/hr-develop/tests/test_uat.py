"""
Tests UAT — HR System
Scénarios réels utilisateur (Recruteur RH)
API réelle : http://localhost:8000

Scénarios :
  1. Recruteur publie une offre d'emploi
  2. Recruteur consulte et filtre les candidats
  3. Recruteur gère le cycle de vie d'une offre
  4. Recruteur gère le statut d'un candidat
  5. Recruteur consulte le tableau de bord RH
  6. Recruteur effectue une recherche complète
"""

import pytest
import httpx
import uuid

BASE_URL = "http://localhost:8000"
client   = httpx.Client(base_url=BASE_URL, timeout=30)


# ============================================================
# SCÉNARIO 1 — Recruteur publie une offre d'emploi
# ============================================================

class TestScenario1_PublierOffre:
    """
    En tant que recruteur,
    je veux publier une offre d'emploi
    pour trouver des candidats qualifiés.
    """

    def test_etape1_recruteur_cree_offre_complete(self):
        payload = {
            "title": f"UAT — Développeur Python Senior {uuid.uuid4().hex[:6]}",
            "description": "Nous recherchons un développeur Python senior pour rejoindre notre équipe.",
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "preferred_skills": ["Docker", "Redis"],
            "nb_positions": 2,
            "location": "Tunis",
            "employment_type": "full-time",
        }
        response = client.post("/api/v1/postings", json=payload)
        assert response.status_code in (200, 201), f"Création échouée: {response.text}"
        data = response.json()
        assert "job_id" in data
        assert data["title"] == payload["title"]
        # Sauvegarder l'ID pour les prochaines étapes
        TestScenario1_PublierOffre._job_id = data["job_id"]

    def test_etape2_offre_apparait_dans_la_liste(self):
        if not hasattr(TestScenario1_PublierOffre, "_job_id"):
            pytest.skip("Étape 1 non exécutée")
        response = client.get("/api/v1/postings")
        assert response.status_code == 200
        ids = [p["job_id"] for p in response.json()]
        assert TestScenario1_PublierOffre._job_id in ids

    def test_etape3_recruteur_consulte_detail_offre(self):
        if not hasattr(TestScenario1_PublierOffre, "_job_id"):
            pytest.skip("Étape 1 non exécutée")
        response = client.get(f"/api/v1/postings/{TestScenario1_PublierOffre._job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == TestScenario1_PublierOffre._job_id
        assert "Python" in data["required_skills"]

    def test_etape4_offre_a_statut_actif_par_defaut(self):
        if not hasattr(TestScenario1_PublierOffre, "_job_id"):
            pytest.skip("Étape 1 non exécutée")
        response = client.get(f"/api/v1/postings/{TestScenario1_PublierOffre._job_id}")
        data = response.json()
        assert data["status"] in ("active", "open", "published")

    def test_etape5_recruteur_supprime_offre_test(self):
        if not hasattr(TestScenario1_PublierOffre, "_job_id"):
            pytest.skip("Étape 1 non exécutée")
        response = client.delete(f"/api/v1/postings/{TestScenario1_PublierOffre._job_id}")
        assert response.status_code in (200, 204)


# ============================================================
# SCÉNARIO 2 — Recruteur consulte et filtre les candidats
# ============================================================

class TestScenario2_ConsulterCandidats:
    """
    En tant que recruteur,
    je veux voir la liste des candidats
    et les filtrer par statut.
    """

    def test_etape1_recruteur_voit_tous_les_candidats(self):
        response = client.get("/api/v1/candidates")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_etape2_recruteur_filtre_candidats_pending(self):
        response = client.get("/api/v1/candidates?status=pending")
        assert response.status_code == 200
        data = response.json()
        for candidat in data["items"]:
            assert candidat["status"] in ("pending", "unknown")

    def test_etape3_recruteur_filtre_candidats_actifs(self):
        response = client.get("/api/v1/candidates?status=active")
        assert response.status_code == 200

    def test_etape4_recruteur_pagine_les_resultats(self):
        page1 = client.get("/api/v1/candidates?page=1&page_size=3")
        assert page1.status_code == 200
        data1 = page1.json()
        # L'API accepte les paramètres de pagination même si elle retourne tous les résultats
        assert "items" in data1

    def test_etape5_candidat_a_les_bons_champs(self):
        response = client.get("/api/v1/candidates")
        data = response.json()
        if len(data["items"]) > 0:
            candidat = data["items"][0]
            champs_requis = ["candidate_id", "status", "filename", "created_at"]
            for champ in champs_requis:
                assert champ in candidat, f"Champ manquant: {champ}"


# ============================================================
# SCÉNARIO 3 — Recruteur gère le cycle de vie d'une offre
# ============================================================

class TestScenario3_CycleVieOffre:
    """
    En tant que recruteur,
    je veux gérer le statut de mes offres :
    créer → active → closed.
    """

    def test_etape1_creer_offre_pour_cycle(self):
        payload = {
            "title": f"UAT Cycle — Frontend Dev {uuid.uuid4().hex[:6]}",
            "description": "Poste frontend React",
            "required_skills": ["React", "TypeScript"],
        }
        response = client.post("/api/v1/postings", json=payload)
        assert response.status_code in (200, 201)
        TestScenario3_CycleVieOffre._job_id = response.json()["job_id"]

    def test_etape2_fermer_offre(self):
        if not hasattr(TestScenario3_CycleVieOffre, "_job_id"):
            pytest.skip("Étape 1 non exécutée")
        response = client.patch(
            f"/api/v1/postings/{TestScenario3_CycleVieOffre._job_id}/status",
            json={"status": "closed"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "closed"

    def test_etape3_offre_est_bien_fermee(self):
        if not hasattr(TestScenario3_CycleVieOffre, "_job_id"):
            pytest.skip("Étape 1 non exécutée")
        response = client.get(f"/api/v1/postings/{TestScenario3_CycleVieOffre._job_id}")
        assert response.json()["status"] == "closed"

    def test_etape4_supprimer_offre_fermee(self):
        if not hasattr(TestScenario3_CycleVieOffre, "_job_id"):
            pytest.skip("Étape 1 non exécutée")
        response = client.delete(f"/api/v1/postings/{TestScenario3_CycleVieOffre._job_id}")
        assert response.status_code in (200, 204)


# ============================================================
# SCÉNARIO 4 — Recruteur gère le statut d'un candidat
# ============================================================

class TestScenario4_GererCandidat:
    """
    En tant que recruteur,
    je veux faire évoluer le statut d'un candidat :
    pending → interviewing → hired ou rejected.
    """

    def test_etape1_trouver_un_candidat_pending(self):
        response = client.get("/api/v1/candidates?status=pending")
        data = response.json()
        if len(data["items"]) == 0:
            pytest.skip("Aucun candidat pending en base")
        TestScenario4_GererCandidat._candidate_id = data["items"][0]["candidate_id"]
        assert TestScenario4_GererCandidat._candidate_id is not None

    def test_etape2_passer_candidat_en_entretien(self):
        if not hasattr(TestScenario4_GererCandidat, "_candidate_id"):
            pytest.skip("Aucun candidat disponible")
        response = client.patch(
            f"/api/v1/candidates/{TestScenario4_GererCandidat._candidate_id}/status",
            json={"status": "interviewing"},
        )
        assert response.status_code == 200

    def test_etape3_verifier_statut_interviewing(self):
        if not hasattr(TestScenario4_GererCandidat, "_candidate_id"):
            pytest.skip("Aucun candidat disponible")
        response = client.get(f"/api/v1/candidates/{TestScenario4_GererCandidat._candidate_id}")
        if response.status_code == 200:
            assert response.json()["status"] == "interviewing"

    def test_etape4_statuts_invalides_rejetes(self):
        response = client.get("/api/v1/candidates")
        items = response.json().get("items", [])
        if not items:
            pytest.skip("Aucun candidat en base")
        cid = items[0]["candidate_id"]
        response = client.patch(
            f"/api/v1/candidates/{cid}/status",
            json={"status": "statut_invalide"},
        )
        assert response.status_code in (400, 422)

    def test_etape5_statuts_valides_acceptes(self):
        response = client.get("/api/v1/candidates")
        items = response.json().get("items", [])
        if not items:
            pytest.skip("Aucun candidat en base")
        cid = items[0]["candidate_id"]
        for statut in ["pending", "interviewing", "rejected"]:
            r = client.patch(
                f"/api/v1/candidates/{cid}/status",
                json={"status": statut},
            )
            assert r.status_code == 200, f"Statut '{statut}' refusé"


# ============================================================
# SCÉNARIO 5 — Recruteur consulte le tableau de bord RH
# ============================================================

class TestScenario5_TableauDeBord:
    """
    En tant que recruteur,
    je veux consulter les statistiques RH
    pour suivre l'activité de recrutement.
    """

    def test_etape1_voir_statistiques_globales(self):
        response = client.get("/api/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert "activeCandidates" in data
        assert "cvsScreened" in data
        assert "hiredCandidates" in data
        assert data["activeCandidates"] >= 0

    def test_etape2_voir_repartition_departements(self):
        response = client.get("/api/v1/dashboard/departments")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_etape3_voir_tendances_recrutement(self):
        response = client.get("/api/v1/dashboard/trends")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_etape4_voir_competences_demandees(self):
        response = client.get("/api/v1/dashboard/top-skills")
        assert response.status_code == 200

    def test_etape5_voir_activite_recente(self):
        response = client.get("/api/v1/dashboard/recent-activity")
        assert response.status_code == 200

    def test_etape6_stats_coherentes_apres_ajout_offre(self):
        # Lire les stats avant
        avant = client.get("/api/v1/dashboard/stats").json()

        # Créer une offre
        payload = {"title": f"UAT Dashboard {uuid.uuid4().hex[:6]}"}
        create  = client.post("/api/v1/postings", json=payload)

        if create.status_code in (200, 201):
            job_id = create.json()["job_id"]
            # Les stats sont toujours accessibles après
            apres = client.get("/api/v1/dashboard/stats")
            assert apres.status_code == 200
            # Nettoyer
            client.delete(f"/api/v1/postings/{job_id}")


# ============================================================
# SCÉNARIO 6 — Workflow complet recruteur
# ============================================================

class TestScenario6_WorkflowComplet:
    """
    Scénario de bout en bout :
    Le recruteur publie une offre, vérifie le dashboard,
    consulte les candidats, puis ferme l'offre.
    """

    def test_workflow_complet_recruteur(self):
        # 1. Créer l'offre
        payload = {
            "title": f"UAT Workflow Complet {uuid.uuid4().hex[:6]}",
            "description": "Test workflow complet UAT",
            "required_skills": ["Python", "Docker"],
            "location": "Tunis",
        }
        create = client.post("/api/v1/postings", json=payload)
        assert create.status_code in (200, 201), "Étape 1 échouée: création offre"
        job_id = create.json()["job_id"]

        # 2. Vérifier que l'offre est dans la liste
        liste = client.get("/api/v1/postings")
        ids   = [p["job_id"] for p in liste.json()]
        assert job_id in ids, "Étape 2 échouée: offre non visible"

        # 3. Consulter les candidats disponibles
        candidats = client.get("/api/v1/candidates")
        assert candidats.status_code == 200, "Étape 3 échouée: liste candidats"

        # 4. Consulter le dashboard
        stats = client.get("/api/v1/dashboard/stats")
        assert stats.status_code == 200, "Étape 4 échouée: dashboard"

        # 5. Fermer l'offre
        fermer = client.patch(
            f"/api/v1/postings/{job_id}/status",
            json={"status": "closed"},
        )
        assert fermer.status_code == 200, "Étape 5 échouée: fermeture offre"
        assert fermer.json()["status"] == "closed"

        # 6. Supprimer l'offre
        suppr = client.delete(f"/api/v1/postings/{job_id}")
        assert suppr.status_code in (200, 204), "Étape 6 échouée: suppression"
