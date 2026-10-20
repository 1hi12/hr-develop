#!/bin/bash
# ============================================================
# Commande unique — Lance tous les tests UAT
# Usage : ./run_uat.sh
# ============================================================

set -e
mkdir -p reports

echo ""
echo "=============================================="
echo "   TESTS UAT — HR SYSTEM"
echo "=============================================="
echo ""

source venv/bin/activate 2>/dev/null || true

# ── 1. Tests PostgreSQL ──────────────────────────────────────
echo "[ 1/4 ] Tests PostgreSQL..."
python -m pytest tests/uat/test_postgresql.py -v --tb=short \
  --junitxml=reports/uat_postgresql.xml 2>&1
echo ""

# ── 2. Tests Redis ───────────────────────────────────────────
echo "[ 2/4 ] Tests Redis..."
python -m pytest tests/uat/test_redis.py -v --tb=short \
  --junitxml=reports/uat_redis.xml 2>&1
echo ""

# ── 3. Tests Milvus ──────────────────────────────────────────
echo "[ 3/4 ] Tests Milvus..."
python -m pytest tests/uat/test_milvus.py -v --tb=short \
  --junitxml=reports/uat_milvus.xml 2>&1
echo ""

# ── 4. Tests API FastAPI ─────────────────────────────────────
echo "[ 4/4 ] Tests API FastAPI..."
python -m pytest tests/uat/test_api_fastapi.py -v --tb=short \
  --junitxml=reports/uat_api.xml 2>&1
echo ""

# ── Résumé ───────────────────────────────────────────────────
echo "=============================================="
echo "   RÉSUMÉ UAT"
echo "=============================================="
python -m pytest tests/uat/ -v --tb=no -q 2>&1 | tail -5
echo ""
echo "Rapports XML générés dans : reports/"
echo "=============================================="
