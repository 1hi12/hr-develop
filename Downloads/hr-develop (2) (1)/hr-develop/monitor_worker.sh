#!/bin/bash
# Script de monitoring du worker ARQ

echo "═══════════════════════════════════════════════"
echo "  Worker ARQ - Status Monitor"
echo "═══════════════════════════════════════════════"
echo ""

# Vérifier si le worker tourne
WORKER_COUNT=$(ps aux | grep "arq app.workers.arq_worker" | grep -v grep | wc -l)

if [ $WORKER_COUNT -eq 0 ]; then
    echo "❌ Worker ARQ: STOPPED"
    echo ""
    echo "Pour démarrer:"
    echo "  source venv/bin/activate"
    echo "  arq app.workers.arq_worker.WorkerSettings"
elif [ $WORKER_COUNT -eq 1 ]; then
    echo "✅ Worker ARQ: RUNNING"
    ps aux | grep "arq app.workers.arq_worker" | grep -v grep | awk '{print "   PID:", $2, "| CPU:", $3"%", "| RAM:", $4"%", "| Time:", $10}'
elif [ $WORKER_COUNT -gt 1 ]; then
    echo "⚠️  WARNING: $WORKER_COUNT workers running (should be 1)"
    echo ""
    echo "Arrêter tous les workers:"
    echo "  pkill -f 'arq app.workers.arq_worker'"
fi

echo ""
echo "───────────────────────────────────────────────"
echo "  Redis Queue Status"
echo "───────────────────────────────────────────────"

# Vérifier Redis
if command -v redis-cli &> /dev/null; then
    QUEUE_LEN=$(redis-cli -h localhost -p 6379 LLEN arq:queue 2>/dev/null || echo "N/A")
    echo "Jobs en attente: $QUEUE_LEN"
else
    echo "redis-cli non disponible"
fi

echo ""
echo "───────────────────────────────────────────────"
echo "  Database Status (PostgreSQL)"
echo "───────────────────────────────────────────────"

# Tester la connexion PostgreSQL
if command -v psql &> /dev/null; then
    PENDING=$(psql postgresql://postgres:postgres@localhost:5432/cv_db -t -c "SELECT COUNT(*) FROM cv_files WHERE processing_status = 'pending';" 2>/dev/null | xargs || echo "N/A")
    PROCESSING=$(psql postgresql://postgres:postgres@localhost:5432/cv_db -t -c "SELECT COUNT(*) FROM cv_files WHERE processing_status = 'processing';" 2>/dev/null | xargs || echo "N/A")
    DONE=$(psql postgresql://postgres:postgres@localhost:5432/cv_db -t -c "SELECT COUNT(*) FROM cv_files WHERE processing_status = 'done';" 2>/dev/null | xargs || echo "N/A")
    FAILED=$(psql postgresql://postgres:postgres@localhost:5432/cv_db -t -c "SELECT COUNT(*) FROM cv_files WHERE processing_status = 'failed';" 2>/dev/null | xargs || echo "N/A")
    
    echo "Pending:    $PENDING"
    echo "Processing: $PROCESSING"
    echo "Done:       $DONE"
    echo "Failed:     $FAILED"
else
    echo "psql non disponible"
fi

echo ""
echo "═══════════════════════════════════════════════"
