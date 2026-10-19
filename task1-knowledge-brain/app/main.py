"""Knowledge Brain API. Docs: run the server and open /docs (OpenAPI is generated from these models)."""
import asyncio
import contextlib
import time
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import escalations
from .brain import Brain
from .config import Settings
from .ingestion.crawler import HttpFetcher, ingest
from .llm import ClaudeLLM
from .rag import answer_question, evidence_json


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    context: str = Field(default="", max_length=4000, description="Optional extra context, e.g. the customer's email.")
    escalate: bool = Field(default=True, description="Create a human-expert task if the question cannot be answered.")


class Source(BaseModel):
    title: str
    url: str
    relevance: float = Field(description="Cosine similarity of the best matching chunk (0-1). Not a probability.")
    kind: str = Field(description="text | image | expert")
    image_url: str | None = None


class QueryResponse(BaseModel):
    status: str = Field(description="'answered' or 'insufficient_evidence'")
    answer: str
    sources: list[Source]
    needs_human: bool
    reason: str = ""
    escalation_id: int | None = None
    request_id: str
    latency_ms: int
    model: str = ""
    prompt_version: str = ""
    # no 'confidence' field on purpose: we have not calibrated one yet (see DESIGN.md)


class EscalationCreate(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    context: str = ""


class ResolveRequest(BaseModel):
    answer: str = Field(min_length=3, max_length=4000)
    approved: bool = True
    expert: str = "expert"


def create_app(brain: Brain | None = None) -> FastAPI:
    settings = Settings()
    if brain is None:
        brain = Brain(settings, llm=ClaudeLLM())

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_daily(brain)) if brain.settings.enable_scheduler else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Knowledge Brain", version="0.1.0", lifespan=lifespan)
    app.state.brain = brain

    def auth(x_api_key: str | None = Header(default=None)) -> None:
        if brain.settings.api_key and x_api_key != brain.settings.api_key:
            raise HTTPException(401, "invalid or missing X-API-Key")

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        resp = await call_next(request)
        resp.headers["x-request-id"] = rid
        return resp

    @app.get("/health")
    def health():
        conn = brain.conn()
        n = conn.execute("SELECT COUNT(*) FROM chunks WHERE active=1").fetchone()[0]
        conn.close()
        return {"status": "ok", "active_chunks": n, "llm_configured": brain.llm is not None}

    @app.post("/query", response_model=QueryResponse, dependencies=[Depends(auth)])
    async def query(req: QueryRequest):
        if brain.llm is None:
            raise HTTPException(503, "LLM not configured (set ANTHROPIC_API_KEY)")
        try:
            a = await asyncio.wait_for(answer_question(brain, req.question, req.context), timeout=60)
        except asyncio.TimeoutError:
            raise HTTPException(504, "answer timed out")
        except Exception as e:  # model/API failure: say so, never fabricate an answer
            raise HTTPException(502, f"upstream model error: {type(e).__name__}")
        if a.needs_human and req.escalate:
            conn = brain.conn()
            a.escalation_id = escalations.create(conn, req.question, evidence_json(a), a.reason)
            conn.close()
        return a.__dict__

    @app.post("/ingestion/run", dependencies=[Depends(auth)], status_code=202)
    async def run_ingestion(bg: BackgroundTasks, limit: int | None = None):
        bg.add_task(_run, brain, limit)
        return {"accepted": True, "limit": limit}

    @app.get("/ingestion/status", dependencies=[Depends(auth)])
    def ingestion_status():
        conn = brain.conn()
        counts = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM pages GROUP BY status")}
        conn.close()
        return {"pages_by_status": counts, "last_report": brain.last_report}

    @app.post("/escalations", dependencies=[Depends(auth)], status_code=201)
    def create_escalation(req: EscalationCreate):
        conn = brain.conn()
        i = escalations.create(conn, req.question, req.context, "created manually")
        conn.close()
        return {"id": i}

    @app.get("/escalations", dependencies=[Depends(auth)])
    def list_escalations(status: str = "open"):
        conn = brain.conn()
        rows = [dict(r) for r in conn.execute("SELECT * FROM escalations WHERE status=? ORDER BY id DESC", (status,))]
        conn.close()
        return rows

    @app.post("/escalations/{esc_id}/resolve", dependencies=[Depends(auth)])
    def resolve(esc_id: int, req: ResolveRequest):
        conn = brain.conn()
        try:
            return escalations.resolve(conn, brain.embedder, esc_id, req.answer, req.approved, req.expert)
        except KeyError:
            raise HTTPException(404, "escalation not found")
        finally:
            conn.close()

    ui = Path(__file__).parent.parent / "static" / "index.html"

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(ui)

    return app


async def _run(brain: Brain, limit: int | None = None) -> None:
    fetcher = HttpFetcher(brain.settings)
    try:
        rep = await ingest(brain, fetcher, limit)
        brain.last_report = {k: v for k, v in rep.__dict__.items()}
    except Exception as e:
        brain.last_report = {"error": str(e)}
    finally:
        await fetcher.close()


async def _daily(brain: Brain) -> None:
    while True:
        await _run(brain)
        await asyncio.sleep(brain.settings.ingest_interval_hours * 3600)


def factory() -> FastAPI:
    """uvicorn app.main:factory --factory --port 8001"""
    return create_app()
