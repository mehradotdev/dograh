from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, cast, func, or_, select

from api.db.base_client import BaseDBClient
from api.db.models import WorkflowModel, WorkflowRunModel


def _poc_engine_expression():
    return func.coalesce(
        WorkflowRunModel.gathered_context["poc_engine"].as_string(),
        WorkflowRunModel.initial_context["poc_engine"].as_string(),
    )


class PocCallClient(BaseDBClient):
    async def list_poc_calls(
        self,
        organization_id: int,
        *,
        engine: str | None = None,
        outcome: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        search: str | None = None,
        limit: int | None = 50,
        offset: int = 0,
    ) -> tuple[list[WorkflowRunModel], int]:
        conditions = [
            WorkflowModel.organization_id == organization_id,
            _poc_engine_expression().is_not(None),
        ]
        if engine:
            conditions.append(_poc_engine_expression() == engine)
        if outcome:
            conditions.append(
                WorkflowRunModel.gathered_context["poc_outcome"].as_string() == outcome
            )
        if created_from:
            conditions.append(WorkflowRunModel.created_at >= created_from)
        if created_to:
            conditions.append(WorkflowRunModel.created_at <= created_to)
        if search:
            needle = f"%{search.strip()}%"
            conditions.append(
                or_(
                    cast(WorkflowRunModel.id, String).ilike(needle),
                    WorkflowRunModel.initial_context["caller_number"]
                    .as_string()
                    .ilike(needle),
                    WorkflowRunModel.gathered_context["ticket_number"]
                    .as_string()
                    .ilike(needle),
                )
            )
        base = select(WorkflowRunModel).join(WorkflowModel).where(*conditions)
        async with self.async_session() as session:
            total = (
                await session.execute(
                    select(func.count(WorkflowRunModel.id))
                    .join(WorkflowModel)
                    .where(*conditions)
                )
            ).scalar_one()
            query = base.order_by(WorkflowRunModel.created_at.desc())
            if limit is not None:
                query = query.limit(min(max(limit, 1), 500))
            if offset:
                query = query.offset(max(offset, 0))
            rows = (await session.execute(query)).scalars().all()
            return list(rows), total

    async def get_poc_call(
        self, run_id: int, organization_id: int
    ) -> WorkflowRunModel | None:
        async with self.async_session() as session:
            return (
                (
                    await session.execute(
                        select(WorkflowRunModel)
                        .join(WorkflowModel)
                        .where(
                            WorkflowRunModel.id == run_id,
                            WorkflowModel.organization_id == organization_id,
                            _poc_engine_expression().is_not(None),
                        )
                    )
                )
                .scalars()
                .first()
            )

    async def count_poc_calls_since(
        self, organization_id: int, engine: str, since: datetime
    ) -> int:
        async with self.async_session() as session:
            return (
                await session.execute(
                    select(func.count(WorkflowRunModel.id))
                    .join(WorkflowModel)
                    .where(
                        WorkflowModel.organization_id == organization_id,
                        _poc_engine_expression() == engine,
                        WorkflowRunModel.created_at >= since,
                    )
                )
            ).scalar_one()

    async def delete_poc_calls(
        self, organization_id: int, run_ids: list[int] | None
    ) -> list[dict[str, Any]]:
        if run_ids == []:
            return []
        conditions = [
            WorkflowModel.organization_id == organization_id,
            _poc_engine_expression().is_not(None),
        ]
        if run_ids is not None:
            conditions.append(WorkflowRunModel.id.in_(run_ids))
        async with self.async_session() as session:
            rows = (
                (
                    await session.execute(
                        select(WorkflowRunModel).join(WorkflowModel).where(*conditions)
                    )
                )
                .scalars()
                .all()
            )
            if run_ids is not None and len(rows) != len(set(run_ids)):
                raise ValueError(
                    "One or more calls are missing or outside this organization"
                )
            deleted_rows = [
                {
                    "id": row.id,
                    "initial_context": dict(row.initial_context or {}),
                }
                for row in rows
            ]
            for row in rows:
                await session.delete(row)
            await session.commit()
            return deleted_rows
