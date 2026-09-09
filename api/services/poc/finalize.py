from __future__ import annotations

from api.db import db_client
from api.services.poc.costs import calculate_poc_cost, summarize_latency


async def finalize_poc_run(workflow_run_id: int) -> None:
    run = await db_client.get_workflow_run_by_id(workflow_run_id)
    if not run:
        return
    gathered = dict(run.gathered_context or {})
    engine = gathered.get("poc_engine") or (run.initial_context or {}).get("poc_engine")
    if not engine:
        return
    cost = calculate_poc_cost(engine, run.usage_info or {})
    gathered["poc_engine"] = engine
    gathered["poc_cost"] = cost
    gathered["poc_latency"] = summarize_latency(
        run.logs or {}, gathered.get("poc_tool_events", [])
    )
    await db_client.update_workflow_run(
        workflow_run_id,
        gathered_context=gathered,
        cost_info={**(run.cost_info or {}), "poc": cost},
    )
