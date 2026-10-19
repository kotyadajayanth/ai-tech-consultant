"""Scope Builder API + one simple screen. Run: uvicorn app.main:factory --factory --port 8003"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import Settings
from .kb_client import KnowledgeClient
from .llm import ClaudeLLM
from .pipeline import run_meeting
from .projects import ApprovalError, ProjectStore


class NewProject(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    meeting_date: str = Field(min_length=4, max_length=40)
    transcript: str = Field(min_length=20, max_length=300_000)


class NewMeeting(BaseModel):
    meeting_date: str = Field(min_length=4, max_length=40)
    transcript: str = Field(min_length=20, max_length=300_000)


class Approve(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)


def create_app(llm=None, kb=None, store: ProjectStore | None = None, settings: Settings | None = None) -> FastAPI:
    s = settings or Settings()
    llm = llm or ClaudeLLM()
    kb = kb or KnowledgeClient(s.knowledge_url, s.knowledge_key)
    store = store or ProjectStore(s.db_path)
    app = FastAPI(title="Meeting to Scope", version="0.1.0")

    def get(pid: str):
        p = store.projects.get(pid)
        if not p:
            raise HTTPException(404, "project not found")
        return p

    async def guarded(coro):
        try:
            return await coro
        except ApprovalError as e:
            raise HTTPException(409, str(e))
        except RuntimeError as e:   # model failure after retries
            raise HTTPException(502, str(e))

    @app.post("/projects", status_code=201)
    async def create(req: NewProject):
        p = store.new(req.name)
        v = await guarded(run_meeting(llm, kb, s, store, p, req.meeting_date, req.transcript))
        return {"project_id": p.id, "version": v.number}

    @app.get("/projects")
    def list_projects():
        return [{"id": p.id, "name": p.name, "versions": [{"number": v.number, "status": v.status} for v in p.versions]} for p in store.projects.values()]

    @app.get("/projects/{pid}")
    def show(pid: str):
        return get(pid).model_dump(exclude={"meetings"})

    @app.post("/projects/{pid}/meetings", status_code=201)
    async def follow_up(pid: str, req: NewMeeting):
        v = await guarded(run_meeting(llm, kb, s, store, get(pid), req.meeting_date, req.transcript))
        return {"version": v.number, "change_report": v.change_report}

    @app.post("/projects/{pid}/versions/{n}/approve")
    def approve(pid: str, n: int, req: Approve):
        try:
            return store.approve(get(pid), n, req.reviewer).model_dump(include={"number", "status", "approved_by", "approved_at"})
        except KeyError:
            raise HTTPException(404, "version not found")
        except ApprovalError as e:
            raise HTTPException(409, str(e))

    @app.post("/projects/{pid}/versions/{n}/send")
    def send(pid: str, n: int):
        try:
            return store.send(get(pid), n).model_dump(include={"number", "sent_at"})
        except KeyError:
            raise HTTPException(404, "version not found")
        except ApprovalError as e:
            raise HTTPException(409, str(e))

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(Path(__file__).parent.parent / "static" / "index.html")

    return app


def factory() -> FastAPI:
    return create_app()
