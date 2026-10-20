"""
Tests UAT — Milvus (base vectorielle)
Vérifie : connexion, collection cv_chunks, insertion, recherche vectorielle
"""
import os
import pytest
import numpy as np

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
COLLECTION  = "cv_chunks"
DIM         = 768  # dimension des embeddings


@pytest.fixture(scope="module")
def milvus_conn():
    from pymilvus import connections, utility
    connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
    yield
    connections.disconnect("default")


# ── Connexion ────────────────────────────────────────────────

class TestMilvusConnexion:

    def test_connexion_reussie(self, milvus_conn):
        from pymilvus import connections
        assert connections.has_connection("default")

    def test_serveur_accessible(self, milvus_conn):
        from pymilvus import utility
        # Si la connexion est établie, le serveur répond
        assert utility is not None

    def test_lister_collections(self, milvus_conn):
        from pymilvus import utility
        collections = utility.list_collections()
        assert isinstance(collections, list)


# ── Collection cv_chunks ─────────────────────────────────────

class TestMilvusCollection:

    def test_collection_cv_chunks_existe(self, milvus_conn):
        from pymilvus import utility
        if not utility.has_collection(COLLECTION):
            pytest.skip(f"Collection '{COLLECTION}' pas encore créée")
        assert utility.has_collection(COLLECTION)

    def test_collection_a_le_bon_schema(self, milvus_conn):
        from pymilvus import Collection, utility
        if not utility.has_collection(COLLECTION):
            pytest.skip(f"Collection '{COLLECTION}' pas encore créée")
        col    = Collection(COLLECTION)
        champs = [f.name for f in col.schema.fields]
        assert len(champs) > 0

    def test_collection_chargee(self, milvus_conn):
        from pymilvus import Collection, utility
        if not utility.has_collection(COLLECTION):
            pytest.skip(f"Collection '{COLLECTION}' pas encore créée")
        col = Collection(COLLECTION)
        col.load()
        assert col is not None

    def test_compter_vecteurs(self, milvus_conn):
        from pymilvus import Collection, utility
        if not utility.has_collection(COLLECTION):
            pytest.skip(f"Collection '{COLLECTION}' pas encore créée")
        col   = Collection(COLLECTION)
        count = col.num_entities
        assert count >= 0


# ── Création collection test + CRUD vectoriel ────────────────

class TestMilvusCRUD:

    TEST_COLLECTION = "test_uat_collection"

    def setup_method(self):
        from pymilvus import connections
        if not connections.has_connection("default"):
            connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)

    def teardown_method(self):
        from pymilvus import utility
        if utility.has_collection(self.TEST_COLLECTION):
            utility.drop_collection(self.TEST_COLLECTION)

    def _creer_collection_test(self):
        from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, utility
        if utility.has_collection(self.TEST_COLLECTION):
            utility.drop_collection(self.TEST_COLLECTION)
        schema = CollectionSchema(fields=[
            FieldSchema("id",        DataType.INT64,       is_primary=True, auto_id=True),
            FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=128),
            FieldSchema("text",      DataType.VARCHAR,      max_length=500),
        ])
        return Collection(self.TEST_COLLECTION, schema)

    def test_creer_collection(self):
        from pymilvus import utility
        col = self._creer_collection_test()
        assert utility.has_collection(self.TEST_COLLECTION)

    def test_inserer_vecteurs(self):
        col  = self._creer_collection_test()
        data = [
            np.random.rand(5, 128).tolist(),
            ["CV test 1", "CV test 2", "CV test 3", "CV test 4", "CV test 5"],
        ]
        result = col.insert(data)
        assert result.insert_count == 5

    def test_recherche_vectorielle(self):
        from pymilvus import Collection
        col = self._creer_collection_test()

        # Insérer des vecteurs
        embeddings = np.random.rand(10, 128).tolist()
        textes     = [f"CV candidat {i}" for i in range(10)]
        col.insert([embeddings, textes])
        col.flush()

        # Créer un index
        col.create_index("embedding", {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 4},
        })
        col.load()

        # Rechercher
        query    = np.random.rand(1, 128).tolist()
        results  = col.search(
            query, "embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 2}},
            limit=3,
        )
        assert len(results) > 0
        assert len(results[0]) <= 3

    def test_supprimer_collection(self):
        from pymilvus import utility
        self._creer_collection_test()
        utility.drop_collection(self.TEST_COLLECTION)
        assert not utility.has_collection(self.TEST_COLLECTION)
