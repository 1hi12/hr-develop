"""
Tests de Performance — HR System
Outil   : pytest + httpx + threading
Serveur : http://localhost:8000

Scénarios :
  - Temps de réponse par endpoint
  - Charge simultanée (10 utilisateurs)
  - Débit (requêtes/seconde)
"""

import os
import time
import threading
import statistics
import httpx
import pytest

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8002")
client   = httpx.Client(base_url=BASE_URL, timeout=30)


# ============================================================
# TEMPS DE RÉPONSE — chaque endpoint doit répondre vite
# ============================================================

class TestResponseTime:

    def _mesure(self, url: str) -> float:
        start = time.time()
        client.get(url)
        return (time.time() - start) * 1000  # en ms

    def test_health_repond_sous_500ms(self):
        ms = self._mesure("/health")
        print(f"\n  /health → {ms:.0f} ms")
        assert ms < 500, f"Trop lent: {ms:.0f}ms (max 500ms)"

    def test_candidates_repond_sous_2000ms(self):
        ms = self._mesure("/api/v1/candidates")
        print(f"\n  /candidates → {ms:.0f} ms")
        assert ms < 2000, f"Trop lent: {ms:.0f}ms (max 2000ms)"

    def test_postings_repond_sous_2000ms(self):
        ms = self._mesure("/api/v1/postings")
        print(f"\n  /postings → {ms:.0f} ms")
        assert ms < 2000, f"Trop lent: {ms:.0f}ms (max 2000ms)"

    def test_dashboard_stats_repond_sous_3000ms(self):
        ms = self._mesure("/api/v1/dashboard/stats")
        print(f"\n  /dashboard/stats → {ms:.0f} ms")
        assert ms < 3000, f"Trop lent: {ms:.0f}ms (max 3000ms)"

    def test_dashboard_trends_repond_sous_3000ms(self):
        ms = self._mesure("/api/v1/dashboard/trends")
        print(f"\n  /dashboard/trends → {ms:.0f} ms")
        assert ms < 3000, f"Trop lent: {ms:.0f}ms (max 3000ms)"

    def test_dashboard_departments_repond_sous_3000ms(self):
        ms = self._mesure("/api/v1/dashboard/departments")
        print(f"\n  /dashboard/departments → {ms:.0f} ms")
        assert ms < 3000, f"Trop lent: {ms:.0f}ms (max 3000ms)"


# ============================================================
# STABILITÉ — 20 requêtes consécutives, aucune erreur
# ============================================================

class TestStabilite:

    def test_health_20_requetes_sans_erreur(self):
        erreurs = 0
        for _ in range(20):
            r = client.get("/health")
            if r.status_code != 200:
                erreurs += 1
        assert erreurs == 0, f"{erreurs}/20 requêtes ont échoué"

    def test_candidates_10_requetes_sans_erreur(self):
        erreurs = 0
        for _ in range(10):
            r = client.get("/api/v1/candidates")
            if r.status_code != 200:
                erreurs += 1
        assert erreurs == 0, f"{erreurs}/10 requêtes ont échoué"

    def test_postings_10_requetes_sans_erreur(self):
        erreurs = 0
        for _ in range(10):
            r = client.get("/api/v1/postings")
            if r.status_code != 200:
                erreurs += 1
        assert erreurs == 0, f"{erreurs}/10 requêtes ont échoué"

    def test_temps_moyen_health_sous_500ms(self):
        temps = []
        for _ in range(15):
            start = time.time()
            client.get("/health")
            temps.append((time.time() - start) * 1000)
        moyenne = statistics.mean(temps)
        p95     = sorted(temps)[int(len(temps) * 0.95)]
        print(f"\n  moyenne={moyenne:.0f}ms  p95={p95:.0f}ms")
        assert moyenne < 500, f"Moyenne trop lente: {moyenne:.0f}ms"

    def test_temps_moyen_candidates_sous_2000ms(self):
        temps = []
        for _ in range(10):
            start = time.time()
            client.get("/api/v1/candidates")
            temps.append((time.time() - start) * 1000)
        moyenne = statistics.mean(temps)
        p95     = sorted(temps)[int(len(temps) * 0.95)]
        print(f"\n  moyenne={moyenne:.0f}ms  p95={p95:.0f}ms")
        assert moyenne < 2000, f"Moyenne trop lente: {moyenne:.0f}ms"


# ============================================================
# CHARGE SIMULTANÉE — 10 utilisateurs en parallèle
# ============================================================

class TestCharge:

    def _requetes_paralleles(self, url: str, nb_users: int):
        resultats = []
        erreurs   = []

        def appel():
            try:
                c = httpx.Client(base_url=BASE_URL, timeout=30)
                start = time.time()
                r = c.get(url)
                ms = (time.time() - start) * 1000
                resultats.append(ms)
                if r.status_code not in (200, 201):
                    erreurs.append(r.status_code)
                c.close()
            except Exception as e:
                erreurs.append(str(e))

        threads = [threading.Thread(target=appel) for _ in range(nb_users)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return resultats, erreurs

    def test_10_users_health_simultanement(self):
        resultats, erreurs = self._requetes_paralleles("/health", 10)
        print(f"\n  10 users /health → erreurs={len(erreurs)}  moy={statistics.mean(resultats):.0f}ms")
        assert len(erreurs) == 0, f"Erreurs avec 10 users: {erreurs}"

    def test_10_users_candidates_simultanement(self):
        resultats, erreurs = self._requetes_paralleles("/api/v1/candidates", 10)
        print(f"\n  10 users /candidates → erreurs={len(erreurs)}  moy={statistics.mean(resultats):.0f}ms")
        assert len(erreurs) == 0, f"Erreurs avec 10 users: {erreurs}"

    def test_10_users_postings_simultanement(self):
        resultats, erreurs = self._requetes_paralleles("/api/v1/postings", 10)
        print(f"\n  10 users /postings → erreurs={len(erreurs)}  moy={statistics.mean(resultats):.0f}ms")
        assert len(erreurs) == 0, f"Erreurs avec 10 users: {erreurs}"

    def test_10_users_dashboard_simultanement(self):
        resultats, erreurs = self._requetes_paralleles("/api/v1/dashboard/stats", 10)
        print(f"\n  10 users /dashboard/stats → erreurs={len(erreurs)}  moy={statistics.mean(resultats):.0f}ms")
        assert len(erreurs) == 0, f"Erreurs avec 10 users: {erreurs}"

    def test_temps_max_sous_5000ms_avec_10_users(self):
        resultats, erreurs = self._requetes_paralleles("/api/v1/candidates", 10)
        max_ms = max(resultats)
        print(f"\n  max={max_ms:.0f}ms avec 10 users")
        assert max_ms < 5000, f"Temps max trop élevé: {max_ms:.0f}ms"


# ============================================================
# DÉBIT — nombre de requêtes par seconde
# ============================================================

class TestDebit:

    def test_debit_health_min_10_rps(self):
        nb       = 20
        debut    = time.time()
        for _ in range(nb):
            client.get("/health")
        duree    = time.time() - debut
        rps      = nb / duree
        print(f"\n  /health → {rps:.1f} req/s")
        assert rps >= 10, f"Débit trop faible: {rps:.1f} req/s (min 10)"

    def test_debit_postings_min_3_rps(self):
        nb    = 10
        debut = time.time()
        for _ in range(nb):
            client.get("/api/v1/postings")
        duree = time.time() - debut
        rps   = nb / duree
        print(f"\n  /postings → {rps:.1f} req/s")
        assert rps >= 3, f"Débit trop faible: {rps:.1f} req/s (min 3)"
