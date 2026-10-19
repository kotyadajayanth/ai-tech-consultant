"""Projects, versions and the approval gate (JSON file store)."""
import datetime as dt
import os
import uuid
from pathlib import Path

from .models import Meeting, Project, Version


class ApprovalError(Exception):
    pass


class ProjectStore:
    def __init__(self, path: str | None):
        self.path, self.projects = path, {}
        if path and os.path.exists(path):
            for p in __import__("json").loads(Path(path).read_text(encoding="utf-8")):
                pr = Project.model_validate(p)
                self.projects[pr.id] = pr
        self.outbox: list[dict] = []   # SIMULATED delivery: nothing is emailed

    def save(self) -> None:
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            Path(tmp).write_text("[" + ",".join(p.model_dump_json() for p in self.projects.values()) + "]", encoding="utf-8")
            os.replace(tmp, self.path)

    def new(self, name: str) -> Project:
        p = Project(id=uuid.uuid4().hex[:8], name=name)
        self.projects[p.id] = p
        return p

    def add_meeting(self, p: Project, date: str, text: str) -> Meeting:
        m = Meeting(id=f"M{len(p.meetings) + 1}", date=date, text=text)
        p.meetings.append(m)
        return m

    def approve(self, p: Project, number: int, reviewer: str) -> Version:
        v = self._v(p, number)
        if not reviewer.strip():
            raise ApprovalError("reviewer name is required")
        if v.status == "approved":
            return v
        v.status, v.approved_by, v.approved_at = "approved", reviewer.strip(), dt.datetime.now(dt.timezone.utc).isoformat()
        self.save()
        return v

    def send(self, p: Project, number: int) -> Version:
        v = self._v(p, number)
        if v.status != "approved":
            raise ApprovalError("nothing reaches the client until a human approves this version")
        if v.sent_at:
            raise ApprovalError("this version was already sent")
        v.sent_at = dt.datetime.now(dt.timezone.utc).isoformat()
        self.outbox.append({"project": p.id, "version": number, "approved_by": v.approved_by, "proposal_md": v.proposal_md})
        self.save()
        return v

    @staticmethod
    def _v(p: Project, number: int) -> Version:
        for v in p.versions:
            if v.number == number:
                return v
        raise KeyError(number)
