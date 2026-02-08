"""Smithery.ai registry client — discovers MCP servers from the public catalog."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SMITHERY_API = "https://registry.smithery.ai/servers"
MAX_PAGES = 5
PAGE_SIZE = 100
CACHE_TTL = 300  # 5 minutes

# Module-level TTL cache
_cache: list[dict[str, Any]] = []
_cache_ts: float = 0.0


async def fetch_smithery_servers() -> list[dict[str, Any]]:
    """Fetch up to MAX_PAGES pages of deployed servers from the Smithery registry.

    Returns raw server dicts. Uses an in-memory TTL cache to avoid
    hammering the API on every page load.
    """
    global _cache, _cache_ts

    if _cache and (time.monotonic() - _cache_ts) < CACHE_TTL:
        return _cache

    servers: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for page in range(1, MAX_PAGES + 1):
            resp = await client.get(
                SMITHERY_API,
                params={"q": "", "page": page, "pageSize": PAGE_SIZE},
            )
            resp.raise_for_status()
            data = resp.json()

            page_servers = data.get("servers", [])
            if not page_servers:
                break

            for s in page_servers:
                if s.get("isDeployed"):
                    servers.append(s)

    _cache = servers
    _cache_ts = time.monotonic()
    return servers


def smithery_to_provider(server: dict[str, Any]) -> dict[str, Any]:
    """Transform a Smithery server dict into the provider shape used by the API."""
    qualified = server.get("qualifiedName", "")
    return {
        "name": server.get("displayName") or qualified,
        "description": server.get("description", ""),
        "capabilities": [],
        "source": "smithery",
        "server_key": qualified,
        "status": "registry",
        # Smithery extras
        "icon_url": server.get("iconUrl") or "",
        "verified": bool(server.get("verified")),
        "use_count": server.get("useCount", 0),
        "homepage": f"https://smithery.ai/server/{qualified}" if qualified else "",
        "qualified_name": qualified,
    }


async def discover_smithery_providers() -> tuple[list[dict[str, Any]], list[str]]:
    """Discover providers from the Smithery registry.

    Returns ``(providers, warnings)`` matching the contract from
    ``mcp/registry.py``.  Degrades gracefully: on HTTP error returns
    stale cache if available, else an empty list.
    """
    global _cache, _cache_ts
    warnings: list[str] = []

    try:
        servers = await fetch_smithery_servers()
    except Exception as exc:
        logger.warning("Smithery fetch failed: %s", exc)
        warnings.append(f"[SMITHERY] Fetch failed: {exc}")
        # Return stale cache if we have one
        if _cache:
            warnings.append("[SMITHERY] Returning stale cached data")
            servers = _cache
        else:
            return [], warnings

    providers = [smithery_to_provider(s) for s in servers]
    return providers, warnings
