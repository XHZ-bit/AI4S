"""Tenant-scoped paper shelf; flags do not imply reading or mastery."""

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictBool, model_validator

from app.db import library
from app.db.sqlite import connect

router = APIRouter(prefix="/api/library", tags=["library"])


class LibraryPaper(BaseModel):
    uid: str
    title: str
    abstract: str
    authors: list[str]
    year: int | None
    source: str
    parse_status: str
    created_at: str
    starred: bool
    read_later: bool
    library_updated_at: str | None


class LibraryPage(BaseModel):
    total: int
    items: list[LibraryPaper]


class LibrarySummary(BaseModel):
    all: int
    starred: int
    read_later: int


class LibraryFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starred: StrictBool | None = None
    read_later: StrictBool | None = None

    @model_validator(mode="after")
    def explicit_flags(self):
        if not self.model_fields_set:
            raise ValueError("至少指定 starred 或 read_later 一项")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("资料架标记必须为布尔值，不能为 null")
        return self


@router.get("/papers", response_model=LibraryPage)
def list_papers(
    filter: Literal["all", "starred", "read_later"] = "all",
    q: str = "",
    parse_status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with closing(connect()) as conn:
        return library.list_papers(conn, filter=filter, q=q, parse_status=parse_status,
                                   limit=limit, offset=offset)


@router.get("/summary", response_model=LibrarySummary)
def summary():
    with closing(connect()) as conn:
        return library.summary(conn)


@router.patch("/papers/{uid}", response_model=LibraryPaper)
def set_flags(uid: str, req: LibraryFlags):
    with closing(connect()) as conn:
        try:
            return library.set_flags(conn, uid, req.model_dump(exclude_unset=True))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
