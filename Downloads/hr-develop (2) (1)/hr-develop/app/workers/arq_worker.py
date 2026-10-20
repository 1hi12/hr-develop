"""
arq_worker.py
=============
ARQ worker entry point.

Run the worker with:
    arq app.workers.arq_worker.WorkerSettings

Or via docker-compose (see service definition in docker-compose.yml).
"""

from arq.connections import RedisSettings

from app.config.settings import settings
from app.workers.tasks.ingest_task import task_ingest_cv

async def startup(ctx):
    from pymilvus import connections
    from app.config.settings import settings
    connections.connect(
        alias="default",
        host=settings.milvus_host,
        port=settings.milvus_port,
    )

class WorkerSettings:
    """ARQ worker configuration."""

    functions  = [task_ingest_cv]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # Process multiple CVs in parallel (LLM semaphore prevents 429)
    max_jobs = 8

    # Timeout per job in seconds (5 minutes)
    job_timeout = 300

    # How long job results are kept in Redis (1 hour)
    keep_result = 3600

    # Retry failed jobs up to 3 times with 60s delay
    max_tries = 3
