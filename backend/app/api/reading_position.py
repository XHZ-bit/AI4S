"""Persist page navigation without marking a reading task or concept complete."""

from contextlib import closing

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.db import reading_position as store
from app.db.sqlite import connect

router = APIRouter(prefix="/api/papers", tags=["reading-position"])


class ReadingPosition(BaseModel):
    paper_uid: str
    document_id: str
    document_version: str
    page: int
    page_count: int
    updated_at: str


class PositionResponse(BaseModel):
    position: ReadingPosition | None


class PositionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: StrictStr = Field(min_length=1, max_length=256)
    page: StrictInt = Field(ge=1)


@router.get("/{uid}/reading-position", response_model=PositionResponse)
def get_position(uid: str, document_id: str = Query(min_length=1, max_length=256)):
    with closing(connect()) as conn:
        try:
            return {"position": store.get_position(conn, uid, document_id)}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except store.PositionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc


@router.put("/{uid}/reading-position", response_model=PositionResponse)
def save_position(uid: str, req: PositionUpdate):
    with closing(connect()) as conn:
        try:
            return {"position": store.save_position(conn, uid, req.document_id, req.page)}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except store.PositionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
