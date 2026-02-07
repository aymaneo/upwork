"""FastAPI server that bridges the frontend to the LangGraph workflow via SSE."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from agent_marketplace.config import MCP_ENABLED, MCP_REGISTRY_PATH
from agent_marketplace.graph import build_graph, set_payment_provider
from agent_marketplace.mcp.registry import load_registry
from agent_marketplace.payments.plasma import PlasmaEscrowProvider
from agent_marketplace.state import MarketplaceState

logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Marketplace API")

# In-memory job store: job_id -> asyncio.Queue
_jobs: dict[str, asyncio.Queue] = {}
_executor = ThreadPoolExecutor(max_workers=4)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #

class JobRequest(BaseModel):
    description: str
    budget: float
    job_type: str = "text"


class JobResponse(BaseModel):
    job_id: str


# --------------------------------------------------------------------------- #
# State sanitization
# --------------------------------------------------------------------------- #

def _sanitize_state(state: dict) -> dict:
    """Strip non-serializable fields before sending over SSE."""
    out = {}
    for key, value in state.items():
        if key in ("mcp_registry", "mcp_provider_map", "_current_provider"):
            continue
        if key == "discovered_providers" and isinstance(value, list):
            # Strip agent objects from provider descriptors
            clean = []
            for p in value:
                if isinstance(p, dict):
                    clean.append({k: v for k, v in p.items() if k != "agent"})
                else:
                    clean.append(p)
            out[key] = clean
        else:
            out[key] = value
    return out


def _make_serializable(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable types."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    # Fall through for str, int, float, bool, None
    return obj


# --------------------------------------------------------------------------- #
# Background workflow runner
# --------------------------------------------------------------------------- #

def _run_workflow(
    job_id: str,
    initial_state: MarketplaceState,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
) -> None:
    """Run the LangGraph workflow in a background thread, pushing SSE events to the queue."""
    try:
        provider = PlasmaEscrowProvider()
        set_payment_provider(provider)

        graph = build_graph()
        compiled = graph.compile()

        current_state: dict = dict(initial_state)

        for event in compiled.stream(initial_state, stream_mode="updates"):
            for node_name, updates in event.items():
                if not isinstance(updates, dict):
                    continue

                # Merge updates (same logic as cli.py)
                for key, value in updates.items():
                    if key in ("bids", "events_log") and isinstance(value, list):
                        if not isinstance(current_state.get(key), list):
                            current_state[key] = []
                        current_state[key] = current_state[key] + value
                    else:
                        current_state[key] = value

                # Build SSE payload
                sanitized = _sanitize_state(current_state)
                serializable = _make_serializable(sanitized)
                sse_data = {
                    "job_id": job_id,
                    "node": node_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "state": serializable,
                }

                sse_event = f"event: {node_name}\ndata: {json.dumps(sse_data)}\n\n"
                loop.call_soon_threadsafe(queue.put_nowait, sse_event)

        # Done event
        done_data = {
            "job_id": job_id,
            "node": "done",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": _make_serializable(_sanitize_state(current_state)),
        }
        loop.call_soon_threadsafe(
            queue.put_nowait, f"event: done\ndata: {json.dumps(done_data)}\n\n"
        )
    except Exception as exc:
        logger.exception("Workflow failed for job %s", job_id)
        error_data = {
            "job_id": job_id,
            "node": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }
        loop.call_soon_threadsafe(
            queue.put_nowait, f"event: error\ndata: {json.dumps(error_data)}\n\n"
        )
    finally:
        # Sentinel to close the SSE stream
        loop.call_soon_threadsafe(queue.put_nowait, None)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.post("/api/jobs", response_model=JobResponse)
async def create_job(req: JobRequest) -> JobResponse:
    """Create a new job and start the workflow in a background thread."""
    job_id = uuid.uuid4().hex[:12]

    # Load MCP registry
    registry = load_registry(Path(MCP_REGISTRY_PATH)) if MCP_ENABLED else {}

    # Build initial state (same pattern as cli.py)
    initial_state: MarketplaceState = {
        "job_description": req.description,
        "job_budget_xpl": req.budget,
        "bids": [],
        "selected_provider": "",
        "selected_price": 0.0,
        "budget_valid": False,
        "payment_receipt": {"tx_hash": "", "from_addr": "", "to_addr": "", "amount_xpl": 0.0, "chain": ""},
        "payment_status": "pending",
        "escrow_id": "",
        "escrow_status": "pending",
        "escrow_receipt": {"tx_hash": "", "from_addr": "", "to_addr": "", "amount_xpl": 0.0, "chain": ""},
        "judge_scores": {},
        "judge_verdict": "",
        "judge_reasoning": "",
        "work_result": "",
        "job_type": req.job_type,
        "marketplace_status": "idle",
        "events_log": [],
        "discovered_providers": [],
        "mcp_provider_map": {},
        "mcp_registry": registry,
    }

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = queue

    # Submit workflow to thread pool
    _executor.submit(_run_workflow, job_id, initial_state, loop, queue)

    return JobResponse(job_id=job_id)


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """SSE stream of real-time workflow state updates."""
    queue = _jobs.get(job_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            msg = await queue.get()
            if msg is None:
                break
            yield msg

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
async def serve_frontend():
    """Serve the frontend index.html."""
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index, media_type="text/html")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    """Run the API server."""
    uvicorn.run(
        "agent_marketplace.api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
