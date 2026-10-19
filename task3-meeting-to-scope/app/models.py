from typing import Literal

from pydantic import BaseModel, Field, model_validator

Feasibility = Literal["existing_configuration", "existing_with_limitation", "custom_development", "needs_clarification", "unchecked"]


class EstTask(BaseModel):
    name: str
    low: float = Field(gt=0)
    likely: float = Field(gt=0)
    high: float = Field(gt=0)
    assumptions: str = ""

    @model_validator(mode="after")
    def ordered(self):
        if not (self.low <= self.likely <= self.high):
            raise ValueError("estimate must satisfy low <= likely <= high")
        return self


class Requirement(BaseModel):
    id: str
    description: str
    quote: str = ""
    quote_verified: bool = False         # True only if the quote really appears in the transcript
    speaker: str = ""
    meeting_id: str = ""
    status: Literal["confirmed", "unclear", "disputed"] = "unclear"
    priority: Literal["must", "should", "optional"] = "should"
    origin: Literal["explicit", "inferred"] = "explicit"   # said by the client, or inferred by the agent
    removed: bool = False
    dependencies: list[str] = []
    acceptance_criteria: list[str] = []  # PROPOSED by the agent; client must confirm
    feasibility: Feasibility = "unchecked"
    feasibility_note: str = ""
    evidence_urls: list[str] = []
    tasks: list[EstTask] = []
    needs_estimate_review: bool = False


class Meeting(BaseModel):
    id: str
    date: str
    text: str


class Version(BaseModel):
    number: int
    meeting_ids: list[str]
    requirements: list[Requirement]
    facts: dict[str, str] = {}           # e.g. delivery_date, budget
    open_questions: list[str] = []
    scope: dict = {}
    scope_md: str = ""
    proposal_md: str = ""
    totals: dict[str, float] = {}
    price_estimate: float | None = None
    currency: str = "USD"
    change_report: dict | None = None
    status: Literal["draft", "approved"] = "draft"
    approved_by: str | None = None
    approved_at: str | None = None
    sent_at: str | None = None
    usage: dict = {}
    prompt_version: str = ""
    created_at: str = ""


class Project(BaseModel):
    id: str
    name: str
    meetings: list[Meeting] = []
    versions: list[Version] = []

    def baseline(self) -> Version | None:
        """The latest APPROVED version. New meetings are compared against this, never against a draft."""
        ok = [v for v in self.versions if v.status == "approved"]
        return ok[-1] if ok else None
