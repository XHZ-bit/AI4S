import re

from pydantic import BaseModel, Field


def normalize_arxiv_id(raw: str) -> str:
    rid = raw.strip()
    if rid.lower().startswith("arxiv:"):
        rid = rid[6:]
    return re.sub(r"v\d+$", "", rid)


class PaperDoc(BaseModel):
    uid: str = Field(min_length=1)
    arxiv_id: str | None = None
    title: str
    abstract: str = ""
    authors: list[str] = []
    year: int
    venue: str | None = None
    categories: list[str] = []
    published: str | None = None
    pdf_url: str | None = None
    code_url: str | None = None
    source: str = "arxiv"


class Section(BaseModel):
    heading: str
    text: str
    page: int | None = None
    kind: str = 'text'
    metadata: dict = {}


class ParsedPaper(BaseModel):
    uid: str
    title: str
    abstract: str
    sections: list[Section] = []
