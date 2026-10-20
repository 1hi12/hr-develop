"""
Tests UAT — Redis
Vérifie : connexion, set/get, expiration, queue ARQ, performance
"""
import os
import time
import pytest
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="module")
def r():
    client = redis.from_url(REDIS_URL, decode_responses=True)
    yield client
    client.close()


# ── Connexion ────────────────────────────────────────────────

class TestRedisConnexion:

    def test_connexion_reussie(self, r):
        assert r.ping()

    def test_serveur_redis_repond(self, r):
        info = r.info()
        assert "redis_version" in info

    def test_base_de_donnees_accessible(self, r):
        r.set("uat:test:connexion", "ok")
        assert r.get("uat:test:connexion") == "ok"
        r.delete("uat:test:connexion")


# ── Set / Get / Delete ───────────────────────────────────────

class TestRedisCRUD:

    def test_set_et_get(self, r):
        r.set("uat:test:cle", "valeur_test")
        assert r.get("uat:test:cle") == "valeur_test"
        r.delete("uat:test:cle")

    def test_set_avec_expiration(self, r):
        r.set("uat:test:expire", "temporaire", ex=2)
        assert r.get("uat:test:expire") == "temporaire"
        time.sleep(3)
        assert r.get("uat:test:expire") is None

    def test_delete_cle(self, r):
        r.set("uat:test:delete", "à supprimer")
        r.delete("uat:test:delete")
        assert r.get("uat:test:delete") is None

    def test_cle_inexistante_retourne_none(self, r):
        assert r.get("uat:cle:qui:nexiste:pas") is None

    def test_incrementer_compteur(self, r):
        r.set("uat:test:compteur", 0)
        r.incr("uat:test:compteur")
        r.incr("uat:test:compteur")
        assert r.get("uat:test:compteur") == "2"
        r.delete("uat:test:compteur")

    def test_stocker_json_candidat(self, r):
        import json
        candidat = {"id": "abc123", "nom": "Ali Ben Salah", "status": "active"}
        r.set("uat:candidat:abc123", json.dumps(candidat))
        data = json.loads(r.get("uat:candidat:abc123"))
        assert data["nom"] == "Ali Ben Salah"
        assert data["status"] == "active"
        r.delete("uat:candidat:abc123")


# ── Queue ARQ (worker de traitement CVs) ─────────────────────

class TestRedisARQQueue:

    def test_push_message_dans_queue(self, r):
        r.lpush("uat:queue:cvs", "cv_job_001")
        r.lpush("uat:queue:cvs", "cv_job_002")
        assert r.llen("uat:queue:cvs") == 2
        r.delete("uat:queue:cvs")

    def test_pop_message_de_queue(self, r):
        r.rpush("uat:queue:traitement", "job_001")
        r.rpush("uat:queue:traitement", "job_002")
        msg = r.lpop("uat:queue:traitement")
        assert msg == "job_001"
        r.delete("uat:queue:traitement")

    def test_cache_matching_cv_job(self, r):
        import json
        cle     = "uat:cache:match:candidat-abc:job-xyz"
        resultat = {"score": 87.5, "competences": ["Python", "FastAPI"]}
        r.set(cle, json.dumps(resultat), ex=300)
        cached = json.loads(r.get(cle))
        assert cached["score"] == 87.5
        r.delete(cle)


# ── Performance Redis ────────────────────────────────────────

class TestRedisPerformance:

    def test_1000_operations_sous_2_secondes(self, r):
        debut = time.time()
        for i in range(1000):
            r.set(f"uat:perf:{i}", f"val{i}")
        for i in range(1000):
            r.get(f"uat:perf:{i}")
        duree = time.time() - debut
        # Nettoyer
        for i in range(1000):
            r.delete(f"uat:perf:{i}")
        assert duree < 2.0, f"Redis trop lent: {duree:.2f}s pour 2000 ops"

    def test_set_get_sous_10ms(self, r):
        debut = time.time()
        r.set("uat:perf:rapide", "test")
        r.get("uat:perf:rapide")
        ms = (time.time() - debut) * 1000
        r.delete("uat:perf:rapide")
        assert ms < 10, f"Trop lent: {ms:.1f}ms"
