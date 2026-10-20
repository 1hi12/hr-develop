import logging
from contextlib import asynccontextmanager
from typing import Optional

import uuid
from fastapi import FastAPI, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pymilvus import connections

from sqlalchemy import select, text

from app.config.settings import settings
from app.api.v1.routes.cvs import router as cvs_router
from app.api.v1.routes.matching import router as matching_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.job_postings import router as job_postings_router
from app.api.v1.routes.candidates import router as candidates_router
from app.api.v1.routes.pipeline import router as pipeline_router
from app.api.v1.routes.interviews import router as interviews_router
from app.api.routes.auth import router as auth_router
from app.api.routes.projects import router as projects_router
from app.api.routes.conversations import router as conversations_router
from app.infrastructure.database.pg_notify import CVProcessingListener

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DEFAULT_ROOMS = [
    {"name": "Salle Atlas",    "floor": "1", "building": "Bât. A", "capacity": 6,  "equipment": ["projector", "whiteboard"]},
    {"name": "Salle Toubkal",  "floor": "2", "building": "Bât. A", "capacity": 10, "equipment": ["projector", "tv", "webcam"]},
    {"name": "Salle Rif",      "floor": "1", "building": "Bât. B", "capacity": 4,  "equipment": ["whiteboard"]},
    {"name": "Salle Sahara",   "floor": "3", "building": "Bât. A", "capacity": 8,  "equipment": ["projector", "phone"]},
    {"name": "Salle Mogador",  "floor": "2", "building": "Bât. B", "capacity": 6,  "equipment": ["tv", "whiteboard"]},
]

async def _init_db_and_seed_rooms() -> None:
    import json
    from app.infrastructure.database.session import engine

    async with engine.begin() as conn:
        # 1. Create rooms table if it does not exist
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id    VARCHAR(36)  PRIMARY KEY,
                name       VARCHAR(128) NOT NULL UNIQUE,
                floor      VARCHAR(64),
                building   VARCHAR(128),
                capacity   INTEGER      NOT NULL DEFAULT 4,
                equipment  JSONB        NOT NULL DEFAULT '[]',
                is_active  BOOLEAN      NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
        """))

        # 2. Create interviews table if it does not exist
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS interviews (
                interview_id     VARCHAR(36)  PRIMARY KEY,
                candidate_id     VARCHAR(36)  NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
                job_posting_id   VARCHAR(36)  REFERENCES job_postings(job_id) ON DELETE SET NULL,
                room_id          VARCHAR(36)  REFERENCES rooms(room_id) ON DELETE SET NULL,
                interview_date   VARCHAR(10)  NOT NULL,
                interview_time   VARCHAR(5)   NOT NULL,
                duration_min     INTEGER      NOT NULL DEFAULT 45,
                format           VARCHAR(20)  NOT NULL DEFAULT 'online',
                platform         VARCHAR(32),
                meeting_link     VARCHAR(512),
                interviewer_name VARCHAR(256),
                notes            TEXT,
                status           VARCHAR(32)  NOT NULL DEFAULT 'scheduled',
                reminder_sent    BOOLEAN      NOT NULL DEFAULT false,
                email_sent       BOOLEAN      NOT NULL DEFAULT false,
                created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
                updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
        """))

        # 3. Add updated_at if the table already existed without it
        await conn.execute(text(
            "ALTER TABLE interviews "
            "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ))

        # 4. Seed default rooms if empty
        count = (await conn.execute(text("SELECT COUNT(*) FROM rooms"))).scalar()
        if count == 0:
            for r in _DEFAULT_ROOMS:
                await conn.execute(text("""
                    INSERT INTO rooms (room_id, name, floor, building, capacity, equipment, is_active)
                    VALUES (:rid, :name, :floor, :building, :capacity, :equipment::jsonb, true)
                    ON CONFLICT (name) DO NOTHING
                """), {
                    "rid":      str(uuid.uuid4()),
                    "name":     r["name"],
                    "floor":    r["floor"],
                    "building": r["building"],
                    "capacity": r["capacity"],
                    "equipment": json.dumps(r["equipment"]),
                })
            logger.info("Seeded %d default rooms", len(_DEFAULT_ROOMS))

    logger.info("DB tables verified / rooms ready")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HR Matching Backend starting up")

    # ── Milvus ────────────────────────────────────────────────────────────
    try:
        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=settings.milvus_port,
        )
        logger.info("Milvus connected at %s:%s", settings.milvus_host, settings.milvus_port)
        # Crée la collection cv_chunks (avec le bon schéma et l'index HNSW)
        # si elle n'existe pas encore, ou la recrée si les dimensions ont changé.
        from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
        MilvusVectorStore()
        logger.info("Milvus collection '%s' ready (dim=%d)", settings.milvus_collection, settings.embedding_dim)
    except Exception as e:
        logger.warning("Milvus connection failed (non-fatal — CV search disabled): %s", e)

    # ── Create missing tables + seed rooms ───────────────────────────────
    try:
        await _init_db_and_seed_rooms()
    except Exception as e:
        logger.warning("DB init / room seeding failed (non-fatal): %s", e)

    # ── pg_notify listener ────────────────────────────────────────────────
    pg_listener = CVProcessingListener()
    try:
        await pg_listener.start()
    except Exception as e:
        logger.warning("pg_notify listener failed to start (non-fatal): %s", e)
        pg_listener = None  # type: ignore[assignment]

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    if pg_listener is not None:
        await pg_listener.stop()
    connections.disconnect("default")
    logger.info("HR Matching Backend shut down")


app = FastAPI(
    title="HR Matching Backend",
    description="RAG pipeline: CV extraction -> embedding -> Milvus -> LLM matching",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── v1 routes ────────────────────────────────────────────────────────────────
app.include_router(auth_router,          prefix="/api/v1")
app.include_router(cvs_router,           prefix="/api/v1")
app.include_router(matching_router,      prefix="/api/v1")
app.include_router(dashboard_router,     prefix="/api/v1")
app.include_router(job_postings_router,  prefix="/api/v1")
app.include_router(candidates_router,    prefix="/api/v1")
app.include_router(pipeline_router,      prefix="/api/v1")
app.include_router(interviews_router,    prefix="/api/v1")
app.include_router(projects_router)
app.include_router(conversations_router)

# ── Legacy URL shims (frontend still calls /api/cvs/* and /api/match) ────────
# These forward to the v1 routes without redirecting the browser,
# so FormData and JSON bodies are preserved.

@app.post("/api/cvs/upload")
async def _shim_upload(
    request: Request,
    file:         UploadFile = File(...),
    job_id:       Optional[str] = Form(None),
    candidate_id: Optional[str] = Form(None),
):
    from app.api.v1.routes.cvs import upload_cv, get_arq_pool
    arq = await get_arq_pool()
    return await upload_cv(file=file, job_id=job_id, candidate_id=candidate_id, arq=arq)


@app.post("/api/cvs/match")
async def _shim_match(request: Request):
    from app.api.v1.routes.matching import match_candidates, get_match_use_case
    from app.application.dtos.match_dto import MatchRequest
    body = await request.json()
    req  = MatchRequest(**body)
    use_case = get_match_use_case()
    return await match_candidates(req=req, use_case=use_case)


@app.get("/api/cvs/status/{candidate_id}")
async def _shim_status(candidate_id: str, job_id: Optional[str] = None):
    from app.api.v1.routes.cvs import get_cv_status, get_arq_pool, get_vector_store
    arq   = await get_arq_pool()
    store = get_vector_store()
    return await get_cv_status(
        candidate_id=candidate_id, job_id=job_id, arq=arq, store=store
    )


# ── Dashboard shims (frontend calls /api/dashboard/* directly) ────────────────

@app.get("/api/dashboard")
async def _shim_dashboard(email: Optional[str] = None):
    from app.api.v1.routes.dashboard import get_dashboard
    return await get_dashboard(email=email)


@app.get("/api/dashboard/stats")
async def _shim_dashboard_stats(period: Optional[str] = None):
    from app.api.v1.routes.dashboard import get_stats
    return await get_stats(period=period)


@app.get("/api/dashboard/departments")
async def _shim_dashboard_departments():
    from app.api.v1.routes.dashboard import get_departments
    return await get_departments()


@app.get("/api/dashboard/trends")
async def _shim_dashboard_trends(period: Optional[str] = None):
    from app.api.v1.routes.dashboard import get_trends
    return await get_trends(period=period)


# ─────────────────────────────────────────────────────────────────────────────

# ── WebSocket endpoint — real-time candidate updates ─────────────────────────
@app.websocket("/ws/candidates")
async def ws_candidates(websocket: WebSocket):
    from app.websocket.ws_ingestion import register_connection, unregister_connection, subscribe
    client_id = str(uuid.uuid4())
    await websocket.accept()
    await register_connection(client_id, websocket)
    subscribe(client_id, "candidates")
    logger.info("[WS/candidates] Client %s connected", client_id[:8])
    try:
        while True:
            await websocket.receive_text()  # keep alive; client sends nothing
    except WebSocketDisconnect:
        await unregister_connection(client_id)
        logger.info("[WS/candidates] Client %s disconnected", client_id[:8])


app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA fallback — serve index.html for all frontend routes."""
    return FileResponse("static/index.html")
