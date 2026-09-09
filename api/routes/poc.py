from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from api.db import db_client
from api.db.models import UserModel
from api.schemas.poc import (
    DeletePocCallsRequest,
    DeletePocCallsResponse,
    PocCallDetail,
    PocCallList,
)
from api.services.auth.depends import get_user
from api.services.poc.inspector import (
    calls_csv,
    detail_run,
    recording_path_for_run,
    summarize_run,
)

router = APIRouter(prefix="/poc/calls", tags=["poc"])


def _organization(user: UserModel) -> int:
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")
    return user.selected_organization_id


@router.get("", response_model=PocCallList)
async def list_calls(
    engine: str | None = None,
    outcome: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: UserModel = Depends(get_user),
) -> PocCallList:
    rows, total = await db_client.list_poc_calls(
        _organization(user),
        engine=engine,
        outcome=outcome,
        created_from=created_from,
        created_to=created_to,
        search=search,
        limit=limit,
        offset=offset,
    )
    return PocCallList(items=[summarize_run(row) for row in rows], total=total)


@router.get("/export.csv")
async def export_calls(
    engine: str | None = None,
    outcome: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    search: str | None = None,
    user: UserModel = Depends(get_user),
) -> Response:
    rows, _ = await db_client.list_poc_calls(
        _organization(user),
        engine=engine,
        outcome=outcome,
        created_from=created_from,
        created_to=created_to,
        search=search,
        limit=None,
    )
    return Response(
        calls_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=poc-calls.csv"},
    )


@router.get("/{run_id:int}", response_model=PocCallDetail)
async def get_call(run_id: int, user: UserModel = Depends(get_user)) -> PocCallDetail:
    run = await db_client.get_poc_call(run_id, _organization(user))
    if not run:
        raise HTTPException(status_code=404, detail="POC call not found")
    return detail_run(run)


@router.get("/{run_id:int}/recording")
async def get_recording(
    run_id: int, user: UserModel = Depends(get_user)
) -> FileResponse:
    run = await db_client.get_poc_call(run_id, _organization(user))
    path = recording_path_for_run(run) if run else None
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(path, media_type="audio/wav", filename=f"poc-call-{run_id}.wav")


async def _delete(run_ids: list[int], organization_id: int) -> int:
    try:
        rows = await db_client.delete_poc_calls(organization_id, run_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for row in rows:
        path = recording_path_for_run(row)
        if path and path.is_file():
            path.unlink()
    return len(rows)


@router.delete("/all", response_model=DeletePocCallsResponse)
async def delete_all_calls(
    user: UserModel = Depends(get_user),
) -> DeletePocCallsResponse:
    rows = await db_client.delete_poc_calls(_organization(user), None)
    for row in rows:
        path = recording_path_for_run(row)
        if path and path.is_file():
            path.unlink()
    return DeletePocCallsResponse(deleted=len(rows))


@router.delete("/{run_id:int}", response_model=DeletePocCallsResponse)
async def delete_call(
    run_id: int, user: UserModel = Depends(get_user)
) -> DeletePocCallsResponse:
    return DeletePocCallsResponse(deleted=await _delete([run_id], _organization(user)))


@router.delete("", response_model=DeletePocCallsResponse)
async def delete_calls(
    request: DeletePocCallsRequest, user: UserModel = Depends(get_user)
) -> DeletePocCallsResponse:
    return DeletePocCallsResponse(
        deleted=await _delete(request.run_ids, _organization(user))
    )
