 docker rm -f hr-app 2>/dev/null
  docker run -d --name hr-app \
    --network hr_system-main_default \
    -p 8000:8000 \
    --env-file .env \
    -e MILVUS_HOST=milvus-standalone \
    -e DB_HOST=cv_db_postgres \
    -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@cv_db_postgres
  :5432/cv_db \
    -e REDIS_URL=redis://hr_redis:6379 \
    hr-system:latest
