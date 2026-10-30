from contextlib import closing

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.action_lists import action_view, build_actions, replan_actions, save_actions
from app.db.sqlite import connect
from app.models.roadmap import LearnerProfile

router = APIRouter(prefix='/api/actions/v1', tags=['automatic-actions'])


class ActionInputs(BaseModel):
    paper_uids: list[str] = Field(default_factory=list, max_length=50)
    weekly_hours: float = Field(default=10, ge=1, le=80)
    profile: LearnerProfile | None = None


class CreateActions(ActionInputs):
    title: str = Field(min_length=1, max_length=200)
    input_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class ReplanRequest(BaseModel):
    expected_version: int = Field(ge=1)


class SaveReplan(ReplanRequest):
    input_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


def translate(exc):
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    return HTTPException(409 if '变化' in str(exc) else 422, str(exc))


@router.post('/preview')
def preview(req: ActionInputs):
    with closing(connect()) as conn:
        try:
            return build_actions(conn, req.model_dump())
        except (ValueError, LookupError) as exc:
            raise translate(exc) from exc


@router.post('')
def create(req: CreateActions):
    with closing(connect()) as conn:
        try:
            inputs = req.model_dump(exclude={'title', 'input_fingerprint'})
            # Idempotent repeated save of the same immutable input and title.
            prior = conn.execute('SELECT list_id,version FROM automatic_action_versions WHERE fingerprint=? AND title=? ORDER BY created_at DESC LIMIT 1',
                                 (req.input_fingerprint, req.title)).fetchone()
            if prior:
                current = build_actions(conn, inputs)
                if current['input_fingerprint'] != req.input_fingerprint:
                    raise ValueError('清单来源已变化，请重新预览')
                return action_view(conn, prior['list_id'], prior['version'])
            return save_actions(conn, req.title.strip(), inputs, fingerprint=req.input_fingerprint)
        except (ValueError, LookupError) as exc:
            raise translate(exc) from exc


@router.get('')
def list_actions(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with closing(connect()) as conn:
        rows = conn.execute('SELECT list_id AS id,MAX(version) AS version,title FROM automatic_action_versions GROUP BY list_id ORDER BY MAX(created_at) DESC,list_id LIMIT ? OFFSET ?', (limit, offset)).fetchall()
        total = conn.execute('SELECT COUNT(DISTINCT list_id) FROM automatic_action_versions').fetchone()[0]
        return {'items': [dict(row) for row in rows], 'total': total}


@router.get('/{ident}')
def get_actions(ident: str, version: int | None = Query(None, ge=1)):
    with closing(connect()) as conn:
        try:
            return action_view(conn, ident, version)
        except (ValueError, LookupError) as exc:
            raise translate(exc) from exc


@router.post('/{ident}/replan-preview')
def preview_replan(ident: str, req: ReplanRequest):
    with closing(connect()) as conn:
        try:
            return replan_actions(conn, ident, req.expected_version)
        except (ValueError, LookupError) as exc:
            raise translate(exc) from exc


@router.get('/{ident}/history')
def action_history(ident: str):
    with closing(connect()) as conn:
        rows = conn.execute('SELECT version,title,fingerprint,created_at FROM automatic_action_versions '
                            'WHERE list_id=? ORDER BY version DESC', (ident,)).fetchall()
        if not rows:
            raise HTTPException(404, '自动行动清单不存在')
        return {'id': ident, 'items': [dict(row) for row in rows]}


@router.post('/{ident}/replan')
def commit_replan(ident: str, req: SaveReplan):
    with closing(connect()) as conn:
        try:
            preview = replan_actions(conn, ident, req.expected_version)
            return save_actions(conn, preview['title'], preview['inputs'], list_id=ident,
                                expected_version=req.expected_version, fingerprint=req.input_fingerprint)
        except (ValueError, LookupError) as exc:
            raise translate(exc) from exc
