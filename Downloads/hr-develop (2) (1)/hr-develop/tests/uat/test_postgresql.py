"""
Tests UAT — PostgreSQL
Vérifie : connexion, tables, migrations, CRUD, intégrité des données
"""
import os
import pytest
import psycopg2

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cv_db")

# Convertir asyncpg → psycopg2
DB_SYNC = DB_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+asyncio://", "postgresql://")


@pytest.fixture(scope="module")
def db():
    conn = psycopg2.connect(DB_SYNC)
    conn.autocommit = True
    yield conn
    conn.close()


# ── Connexion ────────────────────────────────────────────────

class TestPostgreSQLConnexion:

    def test_connexion_reussie(self, db):
        cur = db.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1

    def test_base_de_donnees_correcte(self, db):
        cur = db.cursor()
        cur.execute("SELECT current_database()")
        nom = cur.fetchone()[0]
        assert "uat" in nom or "cv_db" in nom

    def test_version_postgres(self, db):
        cur = db.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        assert "PostgreSQL" in version


# ── Tables existent ──────────────────────────────────────────

class TestPostgreSQLTables:

    TABLES_REQUISES = [
        "candidates",
        "job_postings",
        "candidate_skills",
        "candidate_experiences",
        "candidate_educations",
        "candidate_chunks",
        "cv_files",
    ]

    def test_toutes_les_tables_existent(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
        """)
        tables_existantes = {row[0] for row in cur.fetchall()}
        for table in self.TABLES_REQUISES:
            assert table in tables_existantes, f"Table manquante: {table}"

    def test_table_candidates_a_les_bonnes_colonnes(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'candidates'
        """)
        colonnes = {row[0] for row in cur.fetchall()}
        for col in ["candidate_id", "status", "created_at", "filename"]:
            assert col in colonnes, f"Colonne manquante: {col}"

    def test_table_job_postings_a_les_bonnes_colonnes(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'job_postings'
        """)
        colonnes = {row[0] for row in cur.fetchall()}
        for col in ["job_id", "title", "status", "created_at"]:
            assert col in colonnes, f"Colonne manquante: {col}"


# ── CRUD Offres d'emploi ─────────────────────────────────────

class TestPostgreSQLCRUD:

    def _insert_test_posting(self, cur, title):
        cur.execute("""
            INSERT INTO job_postings
              (job_id, title, status, employment_type,
               required_skills, preferred_skills, created_at, updated_at)
            VALUES
              (gen_random_uuid(), %s, 'active', 'full-time',
               '[]'::jsonb, '[]'::jsonb, NOW(), NOW())
            RETURNING job_id
        """, (title,))
        return cur.fetchone()[0]

    def test_inserer_offre_emploi(self, db):
        cur = db.cursor()
        job_id = self._insert_test_posting(cur, 'Test UAT PostgreSQL')
        assert job_id is not None
        cur.execute("DELETE FROM job_postings WHERE job_id = %s", (str(job_id),))

    def test_lire_offre_inseree(self, db):
        cur = db.cursor()
        job_id = self._insert_test_posting(cur, 'Test Lecture UAT')

        cur.execute("SELECT title FROM job_postings WHERE job_id = %s", (str(job_id),))
        assert cur.fetchone()[0] == "Test Lecture UAT"

        cur.execute("DELETE FROM job_postings WHERE job_id = %s", (str(job_id),))

    def test_mettre_a_jour_statut_offre(self, db):
        cur = db.cursor()
        job_id = self._insert_test_posting(cur, 'Test Update UAT')

        cur.execute("UPDATE job_postings SET status = 'closed' WHERE job_id = %s", (str(job_id),))
        cur.execute("SELECT status FROM job_postings WHERE job_id = %s", (str(job_id),))
        assert cur.fetchone()[0] == "closed"

        cur.execute("DELETE FROM job_postings WHERE job_id = %s", (str(job_id),))

    def test_supprimer_offre(self, db):
        cur = db.cursor()
        job_id = self._insert_test_posting(cur, 'Test Delete UAT')

        cur.execute("DELETE FROM job_postings WHERE job_id = %s", (str(job_id),))
        cur.execute("SELECT COUNT(*) FROM job_postings WHERE job_id = %s", (str(job_id),))
        assert cur.fetchone()[0] == 0


# ── Intégrité des données ────────────────────────────────────

class TestPostgreSQLIntegrite:

    def test_job_id_est_unique(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT job_id, COUNT(*) as cnt
                FROM job_postings
                GROUP BY job_id
                HAVING COUNT(*) > 1
            ) doublons
        """)
        assert cur.fetchone()[0] == 0

    def test_candidates_status_valide(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM candidates
            WHERE status NOT IN ('pending','active','interviewing','hired','rejected','unknown')
        """)
        assert cur.fetchone()[0] == 0

    def test_comptage_tables(self, db):
        cur = db.cursor()
        for table in ["candidates", "job_postings"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            assert count >= 0
